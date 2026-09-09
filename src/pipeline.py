import asyncio
import hashlib
import logging
import sys
import time
from pathlib import Path

import httpx

from src.config import Config
from src.image_filter import is_too_small, perceptual_hash
from src.llm_client import generate_caption, generate_chart_alt_text, generate_table_alt_text
from src.pptx_reader import (
    SlideContext,
    chart_to_text,
    extract_charts,
    extract_pictures,
    extract_tables,
    get_alt_text,
    get_section_map,
    get_slide_context,
    mark_decorative,
    open_presentation,
    set_alt_text,
    table_to_text,
)
from src.state import FileState, load_state, save_state

logger = logging.getLogger("pptx_alt_text")

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


def progress_bar(done: int, total: int, width: int = 18) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = min(width, int(width * done / total))
    return "[" + "█" * filled + "-" * (width - filled) + "]"


def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.log"
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = "%(asctime)s %(levelname)s %(message)s"
    datefmt = "%H:%M:%S"

    # stdout is colored only when it's a real terminal - stays plain when
    # captured by nohup so the fallback launcher log has no escape codes.
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(_ColorFormatter(fmt, datefmt, use_color=sys.stdout.isatty()))
    logger.addHandler(stream_handler)

    # the persisted per-run log is always colored - it's meant to be tailed
    # live in a terminal, not opened in a plain-text editor.
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(_ColorFormatter(fmt, datefmt, use_color=True))
    logger.addHandler(file_handler)


def discover_files(config: Config, only_file: str | None, resume_only: bool) -> list[Path]:
    if only_file:
        path = config.input_dir / only_file
        if not path.exists():
            raise FileNotFoundError(f"{path} not found")
        return [path]

    files = sorted(config.input_dir.glob("*.pptx"))
    result = []
    for f in files:
        state = load_state(config.state_dir, f.name)
        if state.status == "complete":
            if (config.output_dir / f.name).exists():
                logger.info("[file: %s] already complete, skipping", f.name)
                continue
            # state and output/ have drifted apart (output was deleted/moved
            # without clearing state) - reprocess rather than skip forever.
            # Cached captions are kept, so this costs no extra API calls for
            # images already captioned.
            logger.warning(
                "[file: %s] marked complete but output/%s is missing - "
                "reprocessing (cached captions are reused, no extra API cost)",
                f.name, f.name,
            )
            state.status = "in_progress"
            state.completed_slide_indices = []
            save_state(config.state_dir, state)
        if resume_only and state.status != "in_progress":
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
    bar = progress_bar(slide_index + 1, total_slides)
    total_elements = len(pictures) + len(tables) + len(charts)

    if total_elements == 0:
        logger.info(
            "[file: %s] %s %d/%d [section: %s] no images, tables, or charts",
            filename, bar, slide_index + 1, total_slides, section or "-",
        )
        state.mark_slide_done(slide_index)
        return 0

    captioned, decorative, cached, failed = 0, 0, 0, 0

    async def handle_picture(shape):
        nonlocal captioned, decorative, cached, failed
        image = shape.image
        image_bytes, ext = image.blob, image.ext

        if is_too_small(image_bytes, config.min_image_size_px):
            decorative += 1
            mark_decorative(shape)
            return

        img_hash = perceptual_hash(image_bytes)
        if img_hash and img_hash in state.caption_cache:
            cached += 1
            set_alt_text(shape, state.caption_cache[img_hash])
            return

        async with semaphore:
            caption = await generate_caption(client, config, image_bytes, ext, context)

        if caption is None:
            failed += 1
            return
        if caption == "":
            decorative += 1
            mark_decorative(shape)
            return

        captioned += 1
        set_alt_text(shape, caption)
        if img_hash:
            state.caption_cache[img_hash] = caption

    async def handle_table(shape):
        nonlocal captioned, cached, failed
        table = shape.table
        text_repr = table_to_text(table)
        content_hash = "table:" + hashlib.sha256(text_repr.encode()).hexdigest()
        if content_hash in state.caption_cache:
            cached += 1
            set_alt_text(shape, state.caption_cache[content_hash])
            return

        async with semaphore:
            caption = await generate_table_alt_text(client, config, text_repr, context)

        if caption is None:
            failed += 1
            return

        captioned += 1
        set_alt_text(shape, caption)
        state.caption_cache[content_hash] = caption

    async def handle_chart(shape):
        nonlocal captioned, cached, failed
        chart = shape.chart
        text_repr = chart_to_text(chart)
        content_hash = "chart:" + hashlib.sha256(text_repr.encode()).hexdigest()
        if content_hash in state.caption_cache:
            cached += 1
            set_alt_text(shape, state.caption_cache[content_hash])
            return

        async with semaphore:
            caption = await generate_chart_alt_text(client, config, text_repr, context)

        if caption is None:
            failed += 1
            return

        captioned += 1
        set_alt_text(shape, caption)
        state.caption_cache[content_hash] = caption

    await asyncio.gather(
        *(handle_picture(shape) for shape in pictures),
        *(handle_table(shape) for shape in tables),
        *(handle_chart(shape) for shape in charts),
    )

    logger.info(
        "[file: %s] %s %d/%d [section: %s] captioned %d, decorative %d, cached %d, "
        "failed %d (of %d elements: %d images, %d tables, %d charts)",
        filename, bar, slide_index + 1, total_slides, section or "-",
        captioned, decorative, cached, failed,
        total_elements, len(pictures), len(tables), len(charts),
    )
    if failed == 0:
        state.mark_slide_done(slide_index)
    return failed


async def run_file(config: Config, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, path: Path) -> None:
    filename = path.name
    logger.info("[file: %s] starting", filename)

    prs = open_presentation(path)
    section_map = get_section_map(prs)
    total_slides = len(prs.slides)
    state = load_state(config.state_dir, filename)

    any_failed = False
    for index, slide in enumerate(prs.slides):
        if state.is_slide_done(index):
            continue
        failed = await _process_slide(
            slide, index, total_slides, filename, section_map.get(index),
            config, client, semaphore, state,
        )
        any_failed = any_failed or failed > 0
        save_state(config.state_dir, state)

    if any_failed:
        # leave status "in_progress" so a plain rerun retries just the
        # failed slides - succeeded images on them are still cached, so
        # nothing gets re-captioned unnecessarily.
        logger.warning(
            "[file: %s] finished with some images uncaptioned - rerun cappv1 start "
            "to retry them (cached captions won't be re-fetched)",
            filename,
        )
    else:
        state.status = "complete"
    save_state(config.state_dir, state)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.output_dir / filename
    prs.save(str(out_path))
    logger.info("[file: %s] saved to %s", filename, out_path)


async def run(config: Config, only_file: str | None = None, resume_only: bool = False) -> None:
    files = discover_files(config, only_file, resume_only)
    if not files:
        logger.info("nothing to process")
        return

    semaphore = asyncio.Semaphore(config.concurrency)

    async with httpx.AsyncClient() as client:
        for path in files:
            try:
                await run_file(config, client, semaphore, path)
            except Exception as exc:
                logger.error("[file: %s] failed: %s", path.name, exc)
