import asyncio
import logging
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


def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.log"
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(fmt)
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
    client: httpx.AsyncClient | None,
    semaphore: asyncio.Semaphore,
    state: FileState,
    dry_run: bool,
) -> None:
    context: SlideContext = get_slide_context(slide, slide_index, section)
    pictures = extract_pictures(slide, slide_index)

    if not pictures:
        logger.info(
            "[file: %s] [slide %d/%d] [section: %s] no images",
            filename, slide_index + 1, total_slides, section or "-",
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
            if not dry_run:
                mark_decorative(shape)
            return

        img_hash = perceptual_hash(image_bytes)
        if img_hash and img_hash in state.caption_cache:
            cached += 1
            if not dry_run:
                set_alt_text(shape, state.caption_cache[img_hash])
            return

        if dry_run:
            captioned += 1
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
        "[file: %s] [slide %d/%d] [section: %s] captioned %d, decorative %d, "
        "cached %d, failed %d (of %d images)",
        filename, slide_index + 1, total_slides, section or "-",
        captioned, decorative, cached, failed, len(pictures),
    )
    state.mark_slide_done(slide_index)


async def run_file(config: Config, client: httpx.AsyncClient | None, semaphore: asyncio.Semaphore, path: Path, dry_run: bool) -> None:
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
            config, client, semaphore, state, dry_run,
        )
        if not dry_run:
            save_state(config.state_dir, state)

    if dry_run:
        logger.info("[file: %s] dry-run complete, no files written", filename)
        return

    state.status = "complete"
    save_state(config.state_dir, state)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.output_dir / filename
    prs.save(str(out_path))
    logger.info("[file: %s] saved to %s", filename, out_path)


async def run(config: Config, only_file: str | None = None, resume_only: bool = False, dry_run: bool = False) -> None:
    files = discover_files(config, only_file, resume_only)
    if not files:
        logger.info("nothing to process")
        return

    semaphore = asyncio.Semaphore(config.concurrency)

    if dry_run:
        for path in files:
            await run_file(config, None, semaphore, path, dry_run=True)
        return

    async with httpx.AsyncClient() as client:
        for path in files:
            try:
                await run_file(config, client, semaphore, path, dry_run=False)
            except Exception as exc:
                logger.error("[file: %s] failed: %s", path.name, exc)
