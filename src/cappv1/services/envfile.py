"""Reads and edits a workspace's .env in place, keeping comments and order."""
import os
import shutil

from dotenv import load_dotenv

from cappv1 import doctor, home
from cappv1.services.workspace import Workspace


def read(ws: Workspace) -> dict[str, str]:
    return doctor.read_env_file(ws.root)


def set_values(ws: Workspace, values: dict[str, str]) -> None:
    """Sets KEY=value lines (adding missing ones), then loads them into this
    process so a running session sees the change straight away."""
    example = ws.root / ".env.example"
    if not example.exists():
        example = home.bundled_file(".env.example") or example
    if not ws.env_path.exists() and example.exists():
        shutil.copy(example, ws.env_path)
    lines = ws.env_path.read_text().splitlines() if ws.env_path.exists() else []
    for key, value in values.items():
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
    ws.env_path.write_text("\n".join(lines) + "\n")
    os.chmod(ws.env_path, 0o600)  # holds API keys: owner-only
    for key in values:
        os.environ.pop(key, None)
    load_dotenv(ws.env_path, override=True)
