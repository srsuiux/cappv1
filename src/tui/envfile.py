"""Reads and edits .env in place, keeping the user's comments and order."""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"


def ensure_env_file() -> None:
    if not ENV_PATH.exists() and EXAMPLE_PATH.exists():
        shutil.copy(EXAMPLE_PATH, ENV_PATH)


def set_values(values: dict[str, str]) -> None:
    """Sets KEY=value lines (adding any that are missing), then reloads them
    into this process so the running session sees the change."""
    ensure_env_file()
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    for key, value in values.items():
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")
    os.chmod(ENV_PATH, 0o600)  # holds API keys: owner-only
    for key in values:
        os.environ.pop(key, None)
    load_dotenv(ENV_PATH, override=True)
