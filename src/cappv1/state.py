import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger("pptx_alt_text")


@dataclass
class FileState:
    filename: str
    status: str = "in_progress"  # "in_progress" | "complete"
    completed_slide_indices: list[int] = field(default_factory=list)
    caption_cache: dict[str, str] = field(default_factory=dict)  # element hash -> caption
    content_hash: str = ""  # sha256 of the input file this progress belongs to
    skipped: list[dict] = field(default_factory=list)  # items it could not read: {where, kind, error}

    def is_slide_done(self, slide_index: int) -> bool:
        return slide_index in self.completed_slide_indices

    def mark_slide_done(self, slide_index: int) -> None:
        if slide_index not in self.completed_slide_indices:
            self.completed_slide_indices.append(slide_index)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state_path(state_dir: Path, filename: str) -> Path:
    return state_dir / f"{filename}.json"


def load_state(state_dir: Path, filename: str) -> FileState:
    """A progress file that can't be read (half-written, hand-edited) is set
    aside as *.corrupt and treated as no progress, so one bad file can never
    stop the rest of a run."""
    path = _state_path(state_dir, filename)
    if not path.exists():
        return FileState(filename=filename)
    try:
        return FileState(**json.loads(path.read_text()))
    except (OSError, ValueError, TypeError):
        aside = path.with_name(path.name + ".corrupt")
        try:
            os.replace(path, aside)
        except OSError:
            pass
        logger.warning("[file: %s] saved progress was unreadable and was set aside (%s); starting this file fresh",
                       filename, aside.name)
        return FileState(filename=filename)


def atomic_write(path: Path, data: bytes) -> None:
    """Writes to a temporary file, then renames it over the target. The rename
    is all-or-nothing, so a crash leaves either the old file or the new one,
    never a half-written one."""
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save_state(state_dir: Path, state: FileState) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(_state_path(state_dir, state.filename), json.dumps(asdict(state), indent=2).encode())
