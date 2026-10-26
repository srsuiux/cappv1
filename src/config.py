import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


DEFAULT_OLLAMA_URL = "http://localhost:11434"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


# provider -> (API key env var, default model, default fallback model)
# ollama runs on this machine and needs no key, so its key var is empty.
PROVIDERS = {
    "openrouter": ("OPENROUTER_API_KEY", "minimax/minimax-m3:free", "google/gemma-3-12b-it"),
    "openai": ("OPENAI_API_KEY", "gpt-4o-mini", ""),
    "anthropic": ("ANTHROPIC_API_KEY", "claude-haiku-5-5", ""),
    "ollama": ("", "gemma3:4b", ""),
}


def resolve_provider(env: dict[str, str]) -> str:
    """PROVIDER if set, otherwise the first provider that has a key."""
    chosen = env.get("PROVIDER", "").strip().lower()
    if chosen:
        if chosen not in PROVIDERS:
            raise RuntimeError(f"PROVIDER must be one of: {', '.join(PROVIDERS)} (got '{chosen}').")
        return chosen
    for name, (key_var, _, _) in PROVIDERS.items():
        if key_var and env.get(key_var, "").strip():
            return name
    return "openrouter"


def is_local_url(url: str) -> bool:
    return (urlparse(url).hostname or "") in _LOCAL_HOSTS


@dataclass(frozen=True)
class Config:
    provider: str
    api_key: str
    base_url: str
    request_timeout: int
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
    api_key = os.environ.get(key_var, "").strip() if key_var else ""
    if key_var and not api_key:
        raise RuntimeError(f"{key_var} is not set. Add it to .env before running.")

    base_url = os.environ.get("OLLAMA_BASE_URL", "").strip().rstrip("/") or DEFAULT_OLLAMA_URL
    if provider == "ollama" and not is_local_url(base_url):
        if os.environ.get("OLLAMA_ALLOW_REMOTE", "").strip() != "1":
            raise RuntimeError(
                f"OLLAMA_BASE_URL ({base_url}) is not on this computer, so your slides would leave it. "
                "Point it at http://localhost:11434, or set OLLAMA_ALLOW_REMOTE=1 if that is intended."
            )

    is_local = provider == "ollama"
    return Config(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        # local models can take a while on a cold start or a slow CPU
        request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "").strip() or (300 if is_local else 60)),
        model=os.environ.get("MODEL", "").strip() or default_model,
        fallback_model=os.environ.get("FALLBACK_MODEL", "").strip() or default_fallback,
        # one at a time: a single local GPU/CPU doesn't speed up with parallel requests
        concurrency=int(os.environ.get("CONCURRENCY", "").strip() or (1 if is_local else 4)),
        min_image_size_px=int(os.environ.get("MIN_IMAGE_SIZE_PX", "40")),
        max_alt_text_chars=int(os.environ.get("MAX_ALT_TEXT_CHARS", "125")),
        input_dir=ROOT / "input",
        output_dir=ROOT / "output",
        state_dir=ROOT / ".state",
        logs_dir=ROOT / "logs",
    )
