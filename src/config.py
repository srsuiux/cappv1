import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    api_key: str
    model: str
    fallback_model: str
    concurrency: int
    min_image_size_px: int
    max_alt_text_chars: int
    input_dir: Path
    output_dir: Path
    state_dir: Path
    logs_dir: Path


def load_config() -> Config:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env before running."
        )
    return Config(
        api_key=api_key,
        model=os.environ.get("MODEL", "minimax/minimax-m3:free"),
        fallback_model=os.environ.get("FALLBACK_MODEL", "google/gemma-3-12b-it"),
        concurrency=int(os.environ.get("CONCURRENCY", "4")),
        min_image_size_px=int(os.environ.get("MIN_IMAGE_SIZE_PX", "40")),
        max_alt_text_chars=int(os.environ.get("MAX_ALT_TEXT_CHARS", "125")),
        input_dir=ROOT / "input",
        output_dir=ROOT / "output",
        state_dir=ROOT / ".state",
        logs_dir=ROOT / "logs",
    )
