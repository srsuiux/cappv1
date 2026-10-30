import asyncio
import hashlib
import logging
import os
from pathlib import Path

import httpx

from src import events
from src.config import Config
from src.docx_reader import (
    extract_objects,
    extract_pictures,
    extract_tables,
    get_alt_text,
    get_context,
    get_object_alt_text,
    get_table_alt_text,
    mark_decorative,
    mark_table_header,
    nearby_caption,
    open_document,
    save_document,
    table_alt_text_unsupported,
    set_alt_text,
    set_object_alt_text,
    set_table_alt_text,
    table_to_text,
)
from src.image_filter import is_too_small
from src.docx_structure import fix_contrast, normalize_headings, set_title
from src.llm_client import generate_caption, generate_ole_alt_text, generate_table_alt_text
from src.pipeline import _FILE_NAME, PlainNote, inspect_file, record_skip
from src.pptx_reader import ole_object_to_text
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
    state.skipped = []
    save_state(config.state_dir, state)

    pictures, tables, objects = [], [], []
    for kind, find, into in (("pictures", extract_pictures, pictures), ("tables", extract_tables, tables),
                             ("embedded objects", extract_objects, objects)):
        try:
            into.extend(find(doc))
        except Exception as exc:  # unreadable parts of the document are noted, the rest still gets done
            record_skip(state, filename, 0, "the document", kind, exc)
    reason = table_alt_text_unsupported(doc)
    if tables and reason:
        count = f"{len(tables)} table" + ("" if len(tables) == 1 else "s")
        record_skip(state, filename, 0, "the document", "tables", PlainNote(f"{count} not described: {reason}"))
    events.emit("file_open", filename=filename, kind="document", total_slides=1, items=len(pictures) + len(tables) + len(objects),
                resumed=len(state.completed_slide_indices))
    events.emit("slide_start", filename=filename, slide=0, total=1,
                counts={"picture": len(pictures), "table": len(tables), "chart": 0,
                        "object": len(objects), "diagram": 0, "invisible": 0})

    headers = {"set": 0, "already": 0, "skipped": 0}
    n = {"captioned": 0, "enhanced": 0, "kept": 0, "decorative": 0, "cached": 0, "failed": 0, "skipped": 0}
    skipped = 0  # pictures that can't be sent to a model; left as they were

    async def guarded(kind: str, handler, element, number: int) -> None:
        try:
            await handler(element)
        except Exception as exc:  # one unreadable item must not stop the document
            n["skipped"] += 1
            record_skip(state, filename, 0, f"{kind} {number} of the document", kind, exc)

    def remember(key: str, caption: str) -> None:
        # saved at once, so stopping a long document keeps the captions already paid for
        state.caption_cache[key] = caption
        save_state(config.state_dir, state)

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
        if pic.image_bytes is None:
            raise ValueError("the picture's image is missing from the file (a broken link in the original)")
        author = author_text(get_alt_text(pic.doc_pr))
        if pic.ext.lower() in _UNSENDABLE_EXTS:
            if author:
                n["kept"] += 1
                return
            # no model can read this format, but the document names it: its own caption is a true description
            text = nearby_caption(pic.block, config.max_alt_text_chars)
            logger.info("[file: %s] a .%s picture can't be sent to a vision model - %s", filename, pic.ext,
                        "described by its caption" if text else "no caption beside it")
            n["captioned"] += 1
            set_alt_text(pic.doc_pr, text or "Picture (automatic description unavailable)")
            events.emit("alt_written", filename=filename, slide=0, outcome="captioned",
                        text=pic.doc_pr.get("descr"))
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
            remember(key, "")
            return
        remember(key, settle(write, caption, author))

    async def handle_table(tbl):
        result = mark_table_header(tbl.table)
        headers[result.split(":")[0]] += 1
        if result.startswith("skipped"):
            logger.info("[file: %s] table header row: %s", filename, result)
        if reason:
            return  # Word cannot open this document with table descriptions in it
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
        remember(key, settle(write, caption, author))

    async def handle_object(obj):
        author = author_text(get_object_alt_text(obj.shape))
        write = lambda text: set_object_alt_text(obj.shape, text)  # noqa: E731
        if obj.blob is None:
            raise ValueError("the embedded object is linked or missing from the file, so there is nothing to read")
        text_repr = ole_object_to_text(obj.blob)
        key = key_for("ole:" + hashlib.sha256(obj.blob).hexdigest(), author)
        if from_cache(write, key):
            return

        caption = None
        if text_repr:
            context = get_context(doc, obj.block)
            async with semaphore, events.working("object", 0):
                caption = await generate_ole_alt_text(client, config, text_repr, context, existing=author)
        elif author:
            n["kept"] += 1  # nothing readable to improve it with
            return

        if text_repr and caption is None:
            n["failed"] += 1
            return
        if not author and (not text_repr or caption.strip().upper() == "UNKNOWN"):
            # nothing usable to read: an honest label of what it is, not an invented description
            caption = f"Embedded {obj.prog_id or 'object'} (automatic description unavailable)"
        remember(key, settle(write, caption, author))

    await asyncio.gather(
        *(guarded("embedded object", handle_object, o, i) for i, o in enumerate(objects, 1)),
        *(guarded("picture", handle_picture, p, i) for i, p in enumerate(pictures, 1)),
        *(guarded("table", handle_table, t, i) for i, t in enumerate(tables, 1)),
    )

    failed = n["failed"]
    logger.info("[file: %s] table header rows: %d marked, %d already, %d left alone", filename,
                headers["set"], headers["already"], headers["skipped"])
    logger.info(
        "[file: %s] captioned %d, enhanced %d, kept author's %d, decorative %d, cached %d, failed %d, "
        "left as is %d, skipped %d (of %d elements: %d images, %d tables, %d objects)",
        filename, n["captioned"], n["enhanced"], n["kept"], n["decorative"], n["cached"], failed, skipped, n["skipped"],
        len(pictures) + len(tables) + len(objects), len(pictures), len(tables), len(objects),
    )
    events.emit("slide_end", filename=filename, slide=0, total=1, empty=not (pictures or tables or objects), **n)
    if failed == 0:
        state.mark_slide_done(0)
        save_state(config.state_dir, state)
    else:
        logger.warning("[file: %s] finished with some elements uncaptioned - run again to retry them "
                       "(cached captions won't be re-fetched)", filename)

    # structure fixes Ally scores: heading levels and the Title are invisible; a contrast fix changes a
    # color, so each one is noted for the person to look at
    try:
        headings = normalize_headings(doc)
        if headings:
            logger.info("[file: %s] headings: %s", filename, headings)
        for note in fix_contrast(doc):
            record_skip(state, filename, 0, "the document", "contrast", PlainNote(note))
        title = set_title(doc)
        if title:
            logger.info("[file: %s] document title set to \"%s\"", filename, title)
    except Exception as exc:  # a structure fix that fails leaves the file as it was; it never stops it
        record_skip(state, filename, 0, "the document", "structure", exc)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.output_dir / filename
    events.emit("file_saving", filename=filename)
    part_path = out_path.with_name(out_path.name + ".part")
    save_document(doc, path, part_path)
    os.replace(part_path, out_path)
    if failed == 0:
        state.status = "complete"
        save_state(config.state_dir, state)
    events.emit("file_saved", filename=filename, path=str(out_path), incomplete=failed > 0, skipped=len(state.skipped))
    if state.skipped:
        logger.warning("[file: %s] %d item(s) were skipped and need a look: %s", filename, len(state.skipped),
                       "; ".join(f"{s['kind']} on {s['where']}" for s in state.skipped))
    logger.info("[file: %s] saved to %s", filename, out_path)
