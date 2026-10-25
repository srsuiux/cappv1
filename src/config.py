import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


# provider -> (API key env var, default model, default fallback model)
PROVIDERS = {
    "openrouter": ("OPENROUTER_API_KEY", "minimax/minimax-m3:free", "google/gemma-3-12b-it"),
    "openai": ("OPENAI_API_KEY", "gpt-4o-mini", ""),
    "anthropic": ("ANTHROPIC_API_KEY", "claude-haiku-5-5", ""),
}


def resolve_provider(env: dict[str, str]) -> str:
    """PROVIDER if set, otherwise the first provider that has a key."""
    chosen = env.get("PROVIDER", "").strip().lower()
    if chosen:
        if chosen not in PROVIDERS:
            raise RuntimeError(f"PROVIDER must be one of: {', '.join(PROVIDERS)} (got '{chosen}').")
        return chosen
    for name, (key_var, _, _) in PROVIDERS.items():
        if env.get(key_var, "").strip():
            return name
    return "openrouter"


@dataclass(frozen=True)
class Config:
    provider: str
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
    provider = resolve_provider(os.environ)
    key_var, default_model, default_fallback = PROVIDERS[provider]
    api_key = os.environ.get(key_var, "").strip()
    if not api_key:
        raise RuntimeError(f"{key_var} is not set. Add it to .env before running.")
    return Config(
        provider=provider,
        api_key=api_key,
        model=os.environ.get("MODEL", "").strip() or default_model,
        fallback_model=os.environ.get("FALLBACK_MODEL", "").strip() or default_fallback,
        concurrency=int(os.environ.get("CONCURRENCY", "4")),
        min_image_size_px=int(os.environ.get("MIN_IMAGE_SIZE_PX", "40")),
        max_alt_text_chars=int(os.environ.get("MAX_ALT_TEXT_CHARS", "125")),
        input_dir=ROOT / "input",
        output_dir=ROOT / "output",
        state_dir=ROOT / ".state",
        logs_dir=ROOT / "logs",
    )
