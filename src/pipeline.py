import asyncio
import logging
import sys
import time
from pathlib import Path

import httpx

from src.config import Config
from src.image_filter import image_size_px, is_too_small, perceptual_hash
from src.llm_client import generate_caption
from src.pptx_reader import (
    SlideContext,
    extract_pictures,
    get_alt_text,
    get_section_map,
    get_slide_context,
    mark_decorative,
    open_presentation,
    set_alt_text,
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
            logger.info("[file: %s] already complete, skipping", f.name)
            continue
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
) -> None:
    context: SlideContext = get_slide_context(slide, slide_index, section)
    pictures = extract_pictures(slide, slide_index)
    bar = progress_bar(slide_index + 1, total_slides)

    if not pictures:
        logger.info(
            "[file: %s] %s %d/%d [section: %s] no images",
            filename, bar, slide_index + 1, total_slides, section or "-",
        )
        state.mark_slide_done(slide_index)
        return

    captioned, decorative, cached, failed = 0, 0, 0, 0

    async def handle_one(shape):
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

    await asyncio.gather(*(handle_one(p.shape) for p in pictures))

    logger.info(
        "[file: %s] %s %d/%d [section: %s] captioned %d, decorative %d, "
        "cached %d, failed %d (of %d images)",
        filename, bar, slide_index + 1, total_slides, section or "-",
        captioned, decorative, cached, failed, len(pictures),
    )
    state.mark_slide_done(slide_index)


async def run_file(config: Config, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, path: Path) -> None:
    filename = path.name
    logger.info("[file: %s] starting", filename)

    prs = open_presentation(path)
    section_map = get_section_map(prs)
    total_slides = len(prs.slides)
    state = load_state(config.state_dir, filename)

    for index, slide in enumerate(prs.slides):
        if state.is_slide_done(index):
            continue
        await _process_slide(
            slide, index, total_slides, filename, section_map.get(index),
            config, client, semaphore, state,
        )
        save_state(config.state_dir, state)

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
