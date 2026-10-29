import asyncio
import hashlib
import logging
import os
from pathlib import Path

import httpx

from src import events
from src.config import Config
from src.docx_reader import (
    extract_pictures,
    extract_tables,
    get_alt_text,
    get_context,
    get_table_alt_text,
    mark_decorative,
    open_document,
    set_alt_text,
    set_table_alt_text,
    table_to_text,
)
from src.image_filter import is_too_small
from src.llm_client import generate_caption, generate_table_alt_text
from src.pipeline import _FILE_NAME, inspect_file
from src.state import FileState, save_state

logger = logging.getLogger("pptx_alt_text")

# Word documents paste in Windows vector images; no vision model accepts them
_UNSENDABLE_EXTS = {"emf", "wmf", "svg", "tif", "tiff"}


async def run_docx_file(
    config: Config, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, path: Path
) -> None:
    """Captions one Word document. The whole document is treated as a single
    unit (slide 0 of 1) so progress, resume and the event stream match decks."""
    filename = path.name
    logger.info("[file: %s] starting", filename)

    doc = open_document(path)
    _, state, digest = inspect_file(config, path)
    state.content_hash = digest
    save_state(config.state_dir, state)
    events.emit("file_open", filename=filename, total_slides=1, resumed=len(state.completed_slide_indices))

    pictures = extract_pictures(doc)
    tables = extract_tables(doc)
    events.emit("slide_start", filename=filename, slide=0, total=1,
                counts={"picture": len(pictures), "table": len(tables), "chart": 0,
                        "object": 0, "diagram": 0, "invisible": 0})

    n = {"captioned": 0, "enhanced": 0, "kept": 0, "decorative": 0, "cached": 0, "failed": 0}
    skipped = 0

    def author_text(raw: str) -> str:
        text = "" if config.overwrite_existing else raw.strip()
        return "" if _FILE_NAME.fullmatch(text) else text

    def key_for(base: str, author: str) -> str:
        return base + (f"|author:{hashlib.sha256(author.encode()).hexdigest()[:12]}" if author else "")

    def settle(write, caption: str, author: str) -> str:
        if author:
            answer = caption.strip().strip("\"'. ").upper()
            if not answer or answer.startswith("KEEP") or answer in ("DECORATIVE", "UNKNOWN"):
                n["kept"] += 1
                events.emit("alt_written", filename=filename, slide=0, outcome="kept", text=author)
                return author
            n["enhanced"] += 1
        else:
            n["captioned"] += 1
        write(caption)
        events.emit("alt_written", filename=filename, slide=0,
                    outcome="enhanced" if author else "captioned", text=caption)
        return caption

    def from_cache(write, key: str) -> bool:
        if key not in state.caption_cache:
            return False
        n["cached"] += 1
        write(state.caption_cache[key])
        events.emit("alt_written", filename=filename, slide=0, outcome="cached", text=state.caption_cache[key])
        return True

    async def handle_picture(pic):
        nonlocal skipped
        author = author_text(get_alt_text(pic.doc_pr))
        if pic.ext.lower() in _UNSENDABLE_EXTS:
            logger.warning("[file: %s] a .%s picture can't be sent to a vision model - left as it is", filename, pic.ext)
            skipped += 1
            return
        if is_too_small(pic.image_bytes, config.min_image_size_px):
            if author:
                n["kept"] += 1
            else:
                n["decorative"] += 1
                mark_decorative(pic.doc_pr)
            return

        key = key_for("img:" + hashlib.sha256(pic.image_bytes).hexdigest(), author)
        write = lambda text: set_alt_text(pic.doc_pr, text)  # noqa: E731
        if from_cache(write, key):
            return

        context = get_context(doc, pic.block)
        async with semaphore, events.working("picture", 0):
            caption = await generate_caption(client, config, pic.image_bytes, pic.ext, context, existing=author)

        if caption is None:
            n["failed"] += 1
            return
        if caption == "" and not author:
            n["decorative"] += 1
            mark_decorative(pic.doc_pr)
            state.caption_cache[key] = ""
            return
        state.caption_cache[key] = settle(write, caption, author)

    async def handle_table(tbl):
        author = author_text(get_table_alt_text(tbl.table))
        text_repr = table_to_text(tbl.table)
        key = key_for("table:" + hashlib.sha256(text_repr.encode()).hexdigest(), author)
        write = lambda text: set_table_alt_text(tbl.table, text)  # noqa: E731
        if from_cache(write, key):
            return

        context = get_context(doc, tbl.block)
        async with semaphore, events.working("table", 0):
            caption = await generate_table_alt_text(client, config, text_repr, context, existing=author)

        if caption is None:
            n["failed"] += 1
            return
        state.caption_cache[key] = settle(write, caption, author)

    await asyncio.gather(*(handle_picture(p) for p in pictures), *(handle_table(t) for t in tables))

    failed = n["failed"]
    logger.info(
        "[file: %s] captioned %d, enhanced %d, kept author's %d, decorative %d, cached %d, failed %d, "
        "skipped %d (of %d elements: %d images, %d tables)",
        filename, n["captioned"], n["enhanced"], n["kept"], n["decorative"], n["cached"], failed, skipped,
        len(pictures) + len(tables), len(pictures), len(tables),
    )
    events.emit("slide_end", filename=filename, slide=0, total=1, empty=not (pictures or tables), **n)
    if failed == 0:
        state.mark_slide_done(0)
        save_state(config.state_dir, state)
    else:
        logger.warning("[file: %s] finished with some elements uncaptioned - run again to retry them "
                       "(cached captions won't be re-fetched)", filename)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.output_dir / filename
    events.emit("file_saving", filename=filename)
    part_path = out_path.with_name(out_path.name + ".part")
    doc.save(str(part_path))
    os.replace(part_path, out_path)
    if failed == 0:
        state.status = "complete"
        save_state(config.state_dir, state)
    events.emit("file_saved", filename=filename, path=str(out_path), incomplete=failed > 0)
    logger.info("[file: %s] saved to %s", filename, out_path)
