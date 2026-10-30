import asyncio
import hashlib
import logging
import os
import re
import sys
import time
from pathlib import Path

import httpx

from src import events
from src.config import Config
from src.image_filter import is_too_small
from src.llm_client import (
    generate_caption,
    generate_chart_alt_text,
    generate_ole_alt_text,
    generate_smartart_alt_text,
    generate_table_alt_text,
)
from src.pptx_reader import (
    SlideContext,
    chart_to_text,
    extract_charts,
    extract_invisible_shapes,
    extract_ole_objects,
    extract_pictures,
    extract_smartart,
    extract_tables,
    get_alt_text,
    get_section_map,
    get_slide_context,
    mark_decorative,
    mark_table_header,
    ole_object_to_text,
    open_presentation,
    save_presentation,
    set_alt_text,
    smartart_to_text,
    table_to_text,
)
from src.state import FileState, file_sha256, load_state, save_state

logger = logging.getLogger("pptx_alt_text")

_FILE_NAME = re.compile(r"[\w\- .()]+\.(png|jpe?g|gif|bmp|tiff?|emf|wmf|svg|webp)", re.IGNORECASE)

SUPPORTED_EXTENSIONS = (".pptx", ".docx")

_RESET, _BOLD, _DIM = "\033[0m", "\033[1m", "\033[2m"
_RED, _GREEN, _YELLOW, _CYAN, _GRAY = (
    "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[90m",
)
_LEVEL_COLOR = {logging.INFO: _CYAN, logging.WARNING: _YELLOW, logging.ERROR: _RED}


class _ColorFormatter(logging.Formatter):
    """Colorizes by log level, with a couple of message-aware overrides so
    completions and skips stand out at a glance."""

    def __init__(self, fmt: str, datefmt: str, use_color: bool) -> None:
        super().__init__(fmt, datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        if not self.use_color:
            return line
        msg = record.getMessage().lower()
        if "saved to" in msg:
            return f"{_BOLD}{_GREEN}✓ {line}{_RESET}"
        if "already complete, skipping" in msg or "nothing to process" in msg:
            return f"{_GRAY}{line}{_RESET}"
        color = _LEVEL_COLOR.get(record.levelno, "")
        return f"{color}{line}{_RESET}" if color else line


class PlainNote(Exception):
    """A note already written for a person; shown as it is, without an error type."""


def explain_error(exc: Exception) -> str:
    """One plain line for a person reading the notes, never a traceback."""
    text = str(exc).strip().strip("\"'")
    if isinstance(exc, PlainNote):
        return text
    if isinstance(exc, KeyError) and "no relationship" in text:
        return "the file points to a part that isn't inside it (a broken link in the original)"
    return f"{type(exc).__name__}: {text}"[:200] if text else type(exc).__name__


def record_skip(state: FileState, filename: str, slide: int, where: str, kind: str, exc: Exception) -> None:
    """An item that can't be read is skipped, never fatal to the file. It is
    noted in the file's saved progress, the log and the event stream, so
    someone can look at it later."""
    error = explain_error(exc)
    state.skipped.append({"where": where, "kind": kind, "error": error})
    logger.warning("[file: %s] skipped %s on %s: %s", filename, kind, where, error)
    events.emit("element_skipped", filename=filename, slide=slide, where=where, kind=kind, error=error)


def progress_bar(done: int, total: int, width: int = 18) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = min(width, int(width * done / total))
    return "[" + "█" * filled + "-" * (width - filled) + "]"


def setup_logging(logs_dir: Path, console: bool = True) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.log"
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = not console  # with its own console handler, the root logger would print every line twice

    fmt = "%(asctime)s %(levelname)s %(message)s"
    datefmt = "%H:%M:%S"

    # stdout is colored only when it's a real terminal - stays plain when
    # captured by nohup so the fallback launcher log has no escape codes.
    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(_ColorFormatter(fmt, datefmt, use_color=sys.stdout.isatty()))
        logger.addHandler(stream_handler)

    # the persisted per-run log is always colored - it's meant to be tailed
    # live in a terminal, not opened in a plain-text editor.
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(_ColorFormatter(fmt, datefmt, use_color=True))
    logger.addHandler(file_handler)


def inspect_file(config: Config, path: Path) -> tuple[str, FileState, str]:
    """Decides what a file in input/ needs. Returns (kind, state, content_hash):

    done     unchanged since it was captioned, and its output still exists
    changed  edited since the last run: redo it, reusing captions for unchanged items
    partial  started earlier (stopped or some items failed): finish it
    new      never processed
    """
    digest = file_sha256(path)
    state = load_state(config.state_dir, path.name)
    output_exists = (config.output_dir / path.name).exists()

    if state.content_hash and state.content_hash != digest:
        # the deck was edited: its slides may differ, but captions are keyed by
        # element content so the ones that still apply are reused
        state.status, state.completed_slide_indices = "in_progress", []
        return "changed", state, digest
    if state.status == "complete" and output_exists:
        return "done", state, digest
    if state.status == "complete":
        # output was deleted or moved: rebuild it from the saved captions, no model calls
        state.status, state.completed_slide_indices = "in_progress", []
        return "partial", state, digest
    if state.completed_slide_indices or state.caption_cache:
        return "partial", state, digest
    return "new", state, digest


def discover_candidates(config: Config) -> list[Path]:
    """The .pptx and .docx files in input/ (Word's ~$ lock files are not files)."""
    candidates = config.input_dir.iterdir() if config.input_dir.is_dir() else []
    return sorted(p for p in candidates if p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith("~$"))


def file_kind(path: Path) -> str:
    """"document" for a Word file, "slides" for a deck: front ends show a view to match."""
    return "document" if path.suffix.lower() == ".docx" else "slides"


def discover_files(config: Config, resume_only: bool, force: bool = False, only: list[str] | None = None) -> list[Path]:
    """only: process just these file names (None means every file in input/)."""
    result = []
    for f in discover_candidates(config):
        if only is not None and f.name not in only:
            continue
        if force:
            (config.state_dir / f"{f.name}.json").unlink(missing_ok=True)  # forget saved progress and captions
        kind, state, _ = inspect_file(config, f)
        if kind == "done":
            logger.info("[file: %s] already captioned and unchanged, skipping", f.name)
            events.emit("file_skipped", filename=f.name)
            continue
        if kind == "changed":
            logger.info("[file: %s] changed since the last run - reprocessing (unchanged items reuse saved captions)", f.name)
        if resume_only and kind in ("new", "changed"):
            continue
        result.append(f)
    return result


async def _process_slide(
    slide,
    slide_index: int,
    total_slides: int,
    filename: str,
    section: str | None,
    config: Config,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    state: FileState,
) -> int:
    """Returns the number of images on this slide that failed to caption.

    A slide is only marked done when this is 0, so a transient failure
    (rate limit, network blip) leaves the slide eligible for automatic
    retry on the next run instead of being silently locked in forever.
    """
    context: SlideContext = get_slide_context(slide, slide_index, section)
    pictures = extract_pictures(slide)
    tables = extract_tables(slide)
    charts = extract_charts(slide)
    ole_objects = extract_ole_objects(slide)
    smartart_shapes = extract_smartart(slide)
    invisible_shapes = extract_invisible_shapes(slide)
    bar = progress_bar(slide_index + 1, total_slides)
    total_elements = (
        len(pictures) + len(tables) + len(charts) + len(ole_objects)
        + len(smartart_shapes) + len(invisible_shapes)
    )

    events.emit(
        "slide_start", filename=filename, slide=slide_index, total=total_slides,
        counts={
            "picture": len(pictures), "table": len(tables), "chart": len(charts),
            "object": len(ole_objects), "diagram": len(smartart_shapes),
            "invisible": len(invisible_shapes),
        },
    )

    if total_elements == 0:
        events.emit("slide_end", filename=filename, slide=slide_index, total=total_slides,
                    captioned=0, enhanced=0, kept=0, decorative=0, cached=0, failed=0, skipped=0, empty=True)
        logger.info(
            "[file: %s] %s %d/%d [section: %s] no images, tables, or charts",
            filename, bar, slide_index + 1, total_slides, section or "-",
        )
        state.mark_slide_done(slide_index)
        return 0

    n = {"captioned": 0, "enhanced": 0, "kept": 0, "decorative": 0, "cached": 0, "failed": 0, "skipped": 0}

    def skip(kind: str, exc: Exception) -> None:
        n["skipped"] += 1
        record_skip(state, filename, slide_index, f"slide {slide_index + 1}", kind, exc)

    async def guarded(kind: str, handler, shape) -> None:
        try:
            await handler(shape)
        except Exception as exc:  # one unreadable item must not stop the file
            skip(kind, exc)

    def author_text(shape) -> str:
        """Alt-text the slide's author already wrote. We build on it, never
        replace it, unless the run was started with --force. A bare file name
        ("image1.png"), which some tools fill in automatically, isn't alt text."""
        text = "" if config.overwrite_existing else get_alt_text(shape).strip()
        return "" if _FILE_NAME.fullmatch(text) else text

    def key_for(base: str, author: str) -> str:
        # the author's text changes what a good result is, so it is part of the cache key
        return base + (f"|author:{hashlib.sha256(author.encode()).hexdigest()[:12]}" if author else "")

    def from_cache(shape, key: str) -> bool:
        if key not in state.caption_cache:
            return False
        n["cached"] += 1
        set_alt_text(shape, state.caption_cache[key])
        events.emit("alt_written", filename=filename, slide=slide_index, outcome="cached", text=state.caption_cache[key])
        return True

    def settle(shape, caption: str, author: str) -> str:
        """Writes the model's answer and returns the final alt-text. With an
        author's text, KEEP (or any non-answer) leaves it exactly as written."""
        if author:
            answer = caption.strip().strip("\"'. ").upper()
            if not answer or answer.startswith("KEEP") or answer in ("DECORATIVE", "UNKNOWN"):
                n["kept"] += 1
                events.emit("alt_written", filename=filename, slide=slide_index, outcome="kept", text=author)
                return author
            n["enhanced"] += 1
        else:
            n["captioned"] += 1
        set_alt_text(shape, caption)
        events.emit("alt_written", filename=filename, slide=slide_index,
                    outcome="enhanced" if author else "captioned", text=caption)
        return caption

    # No LLM call needed here - these are provably zero-pixel shapes (explicit
    # no-fill + no-line + no text), not a judgment call, so marking them
    # decorative is a pure XML write, same as PowerPoint's own "Mark as
    # decorative" action. Anything the author labeled is left alone.
    for shape in invisible_shapes:
        if author_text(shape):
            n["kept"] += 1
            continue
        try:
            mark_decorative(shape)
        except Exception as exc:
            skip("invisible shape", exc)
            continue
        n["decorative"] += 1

    async def handle_picture(shape):
        author = author_text(shape)
        image_bytes, ext = shape.image.blob, shape.image.ext

        if is_too_small(image_bytes, config.min_image_size_px):
            if author:
                n["kept"] += 1
            else:
                n["decorative"] += 1
                mark_decorative(shape)
            return

        # exact bytes, not a 'looks similar' fingerprint: flat or near-identical
        # images must never share a caption
        img_hash = "img:" + hashlib.sha256(image_bytes).hexdigest()
        key = key_for(img_hash, author)
        if from_cache(shape, key):
            return

        async with semaphore, events.working("picture", slide_index):
            caption = await generate_caption(client, config, image_bytes, ext, context, existing=author)

        if caption is None:
            n["failed"] += 1
            return
        if caption == "" and not author:
            n["decorative"] += 1
            mark_decorative(shape)
            state.caption_cache[key] = ""
            return

        state.caption_cache[key] = settle(shape, caption, author)

    async def handle_table(shape):
        header = mark_table_header(shape)
        if header != "already":
            logger.info("[file: %s] [slide %d] table header row: %s", filename, slide_index, header)
        author = author_text(shape)
        text_repr = table_to_text(shape.table)
        key = key_for("table:" + hashlib.sha256(text_repr.encode()).hexdigest(), author)
        if from_cache(shape, key):
            return

        async with semaphore, events.working("table", slide_index):
            caption = await generate_table_alt_text(client, config, text_repr, context, existing=author)

        if caption is None:
            n["failed"] += 1
            return
        state.caption_cache[key] = settle(shape, caption, author)

    async def handle_chart(shape):
        author = author_text(shape)
        text_repr = chart_to_text(shape.chart)
        key = key_for("chart:" + hashlib.sha256(text_repr.encode()).hexdigest(), author)
        if from_cache(shape, key):
            return

        async with semaphore, events.working("chart", slide_index):
            caption = await generate_chart_alt_text(client, config, text_repr, context, existing=author)

        if caption is None:
            n["failed"] += 1
            return
        state.caption_cache[key] = settle(shape, caption, author)

    async def handle_ole(shape):
        author = author_text(shape)
        of = shape.ole_format
        blob = of.blob
        if blob is None:
            n["kept" if author else "failed"] += 1
            return
        text_repr = ole_object_to_text(blob)
        key = key_for("ole:" + hashlib.sha256(blob).hexdigest(), author)
        if from_cache(shape, key):
            return

        caption = None
        if text_repr:
            async with semaphore, events.working("object", slide_index):
                caption = await generate_ole_alt_text(client, config, text_repr, context, existing=author)
        elif author:
            n["kept"] += 1  # nothing readable to improve it with
            return

        if caption is None:
            n["failed"] += 1
            return
        if caption.strip().upper() == "UNKNOWN" and not author:
            # Heuristic extraction gave the model nothing usable - still
            # better than silence: an honest, non-invented fallback naming
            # what kind of object this is, not what it contains.
            caption = f"Embedded {of.prog_id or 'object'} (automatic description unavailable)"
        state.caption_cache[key] = settle(shape, caption, author)

    async def handle_smartart(shape):
        author = author_text(shape)
        text_repr = smartart_to_text(shape)
        if not text_repr:
            n["kept" if author else "failed"] += 1
            return
        key = key_for("smartart:" + hashlib.sha256(text_repr.encode()).hexdigest(), author)
        if from_cache(shape, key):
            return

        async with semaphore, events.working("diagram", slide_index):
            caption = await generate_smartart_alt_text(client, config, text_repr, context, existing=author)

        if caption is None:
            n["failed"] += 1
            return
        state.caption_cache[key] = settle(shape, caption, author)

    await asyncio.gather(
        *(guarded("picture", handle_picture, shape) for shape in pictures),
        *(guarded("table", handle_table, shape) for shape in tables),
        *(guarded("chart", handle_chart, shape) for shape in charts),
        *(guarded("embedded object", handle_ole, shape) for shape in ole_objects),
        *(guarded("diagram", handle_smartart, shape) for shape in smartart_shapes),
    )

    failed = n["failed"]
    logger.info(
        "[file: %s] %s %d/%d [section: %s] captioned %d, enhanced %d, kept author's %d, "
        "decorative %d, cached %d, failed %d, skipped %d (of %d elements: %d images, %d tables, "
        "%d charts, %d OLE objects, %d SmartArt, %d invisible shapes)",
        filename, bar, slide_index + 1, total_slides, section or "-",
        n["captioned"], n["enhanced"], n["kept"], n["decorative"], n["cached"], failed, n["skipped"],
        total_elements, len(pictures), len(tables), len(charts), len(ole_objects),
        len(smartart_shapes), len(invisible_shapes),
    )
    events.emit("slide_end", filename=filename, slide=slide_index, total=total_slides, empty=False, **n)
    if failed == 0:
        state.mark_slide_done(slide_index)
    return failed


async def run_file(config: Config, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, path: Path) -> None:
    if path.suffix.lower() == ".docx":
        from src.docx_pipeline import run_docx_file  # imported here: it imports this module

        return await run_docx_file(config, client, semaphore, path)
    filename = path.name
    logger.info("[file: %s] starting", filename)

    prs = open_presentation(path)
    section_map = get_section_map(prs)
    total_slides = len(prs.slides)
    _, state, digest = inspect_file(config, path)
    state.content_hash = digest
    state.skipped = []  # every slide is walked again, so the notes are rebuilt
    save_state(config.state_dir, state)
    events.emit("file_open", filename=filename, kind="slides", total_slides=total_slides,
                resumed=len(state.completed_slide_indices))

    # Every slide is walked again on a resume: the output deck is rebuilt from
    # the untouched input, so slides finished before a crash must have their
    # saved captions applied again. Cached items cost no model calls.
    any_failed = False
    for index, slide in enumerate(prs.slides):
        try:
            failed = await _process_slide(
                slide, index, total_slides, filename, section_map.get(index),
                config, client, semaphore, state,
            )
        except Exception as exc:  # the slide itself is unreadable: note it and move on
            record_skip(state, filename, index, f"slide {index + 1}", "whole slide", exc)
            state.mark_slide_done(index)
            failed = 0
            events.emit("slide_end", filename=filename, slide=index, total=total_slides, empty=False,
                        captioned=0, enhanced=0, kept=0, decorative=0, cached=0, failed=0, skipped=1)
        any_failed = any_failed or failed > 0
        save_state(config.state_dir, state)

    if any_failed:
        # leave status "in_progress" so a plain rerun retries just the
        # failed slides - succeeded images on them are still cached, so
        # nothing gets re-captioned unnecessarily.
        logger.warning(
            "[file: %s] finished with some images uncaptioned - type /run again "
            "to retry them (cached captions won't be re-fetched)",
            filename,
        )
    save_state(config.state_dir, state)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.output_dir / filename
    events.emit("file_saving", filename=filename)
    # save beside the target, then rename: a crash never leaves a half-written deck in output/
    part_path = out_path.with_name(out_path.name + ".part")
    save_presentation(prs, path, part_path)
    os.replace(part_path, out_path)
    if not any_failed:
        # only now is the file really done
        state.status = "complete"
        save_state(config.state_dir, state)
    events.emit("file_saved", filename=filename, path=str(out_path), incomplete=any_failed, skipped=len(state.skipped))
    if state.skipped:
        logger.warning("[file: %s] %d item(s) were skipped and need a look: %s", filename, len(state.skipped),
                       "; ".join(f"{s['kind']} on {s['where']}" for s in state.skipped))
    logger.info("[file: %s] saved to %s", filename, out_path)


async def run(config: Config, resume_only: bool = False, force: bool = False, only: list[str] | None = None) -> list[str]:
    for leftover in config.output_dir.glob("*.part"):
        leftover.unlink(missing_ok=True)  # from a run that was killed mid-save
    files = discover_files(config, resume_only, force, only)
    if not files:
        logger.info("nothing to process")
        events.emit("run_empty")
        return []

    semaphore = asyncio.Semaphore(config.concurrency)
    total = len(files)
    failed_files: list[str] = []

    # Files run strictly one at a time, in order; the semaphore only bounds
    # concurrent API calls within a file. One bad file doesn't stop the rest.
    async with httpx.AsyncClient() as client:
        for n, path in enumerate(files, start=1):
            logger.info("=== file %d/%d: %s ===", n, total, path.name)
            events.emit("file_start", filename=path.name, index=n, total=total, kind=file_kind(path))
            try:
                await run_file(config, client, semaphore, path)
            except Exception as exc:
                logger.error("[file: %s] failed: %s", path.name, exc)
                events.emit("file_failed", filename=path.name, error=str(exc))
                failed_files.append(path.name)

    logger.info("finished %d/%d file(s) without errors", total - len(failed_files), total)
    if failed_files:
        logger.error("failed: %s", ", ".join(failed_files))
    events.emit("run_done", total=total, failed=failed_files)
    return failed_files
