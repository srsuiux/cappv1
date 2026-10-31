"""Where cappv1 keeps .env, input/, output/, .state/ and logs/. Stdlib only."""

import os
from pathlib import Path


def default_root() -> Path:
    """CAPPV1_HOME if set; the project folder when running from a source checkout; otherwise ~/cappv1."""
    chosen = os.environ.get("CAPPV1_HOME")
    if chosen:
        return Path(chosen).expanduser()
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "pyproject.toml").is_file() and (checkout / "src" / "cappv1").is_dir():
        return checkout
    return Path.home() / "cappv1"


def bundled_file(name: str) -> Path | None:
    """A file shipped beside the code (installed) or kept at the project root (checkout)."""
    for candidate in (Path(__file__).resolve().parent / name, Path(__file__).resolve().parents[2] / name):
        if candidate.is_file():
            return candidate
    return None
