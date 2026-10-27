"""The decks in input/ and output/. Deliberately small: add, list, fetch, clean."""
import os
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from src.config import load_config
from src.pipeline import inspect_file
from src.services.errors import ServiceError
from src.services.workspace import Workspace

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@dataclass
class FileInfo:
    name: str
    size: int
    state: str  # new | partial | changed | done
    has_output: bool

    def as_dict(self) -> dict:
        return asdict(self)


def safe_name(name: str) -> str:
    """A bare, plain .pptx filename, or ServiceError. Folders in the name are dropped."""
    base = Path(str(name).replace("\\", "/")).name.strip()
    if not base or base.startswith(".") or any(ord(c) < 32 for c in base) or len(base) > 200:
        raise ServiceError("bad_name", "That file name can't be used.", "Rename the file and try again.")
    if not base.lower().endswith(".pptx"):
        raise ServiceError("not_pptx", f"{base} isn't a .pptx file.", "cappv1 only works with PowerPoint .pptx files.")
    return base[:-5] + ".pptx"


def _looks_like_pptx(path: Path) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
    return "[Content_Types].xml" in names and "ppt/presentation.xml" in names


def store(ws: Workspace, name: str, chunks: Iterable[bytes]) -> FileInfo:
    """Saves an uploaded deck into input/ (replacing one with the same name).
    Written to a temporary file first, so a failed upload leaves nothing behind."""
    name = safe_name(name)
    ws.input_dir.mkdir(parents=True, exist_ok=True)
    target, tmp = ws.input_dir / name, ws.input_dir / f".{name}.upload"
    size = 0
    try:
        with open(tmp, "wb") as f:
            for chunk in chunks:
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ServiceError("too_big", f"{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                                       "Split the deck or compress its pictures in PowerPoint.")
                f.write(chunk)
        if not _looks_like_pptx(tmp):
            raise ServiceError("not_pptx", f"{name} isn't a valid PowerPoint file.",
                               "Open it in PowerPoint and save a copy as .pptx.")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return describe(ws, name)


def store_path(ws: Workspace, source: Path) -> FileInfo:
    def chunks():
        with open(source, "rb") as f:
            while block := f.read(1 << 20):
                yield block

    return store(ws, source.name, chunks())


def exists(ws: Workspace, name: str) -> bool:
    return (ws.input_dir / safe_name(name)).exists()


def describe(ws: Workspace, name: str) -> FileInfo:
    path = ws.input_dir / name
    try:
        state = inspect_file(load_config(ws.root), path)[0]
    except Exception:
        state = "new"  # not configured yet: it simply hasn't been processed
    return FileInfo(name, path.stat().st_size, state, (ws.output_dir / name).exists())


def list_files(ws: Workspace) -> list[FileInfo]:
    return [describe(ws, p.name) for p in sorted(ws.input_dir.glob("*.pptx"))]


def output_file(ws: Workspace, name: str) -> Path:
    """The finished copy of a deck, for download."""
    path = ws.output_dir / safe_name(name)
    if not path.is_file() or path.resolve().parent != ws.output_dir.resolve():
        raise ServiceError("no_output", f"There is no finished copy of {name} yet.", "Run it first.")
    return path


def clean(ws: Workspace, dry_run: bool = False) -> dict[str, int]:
    """Deletes decks in input/ and output/ and all saved progress. No undo.
    With dry_run it only counts what would go."""
    counts = {"input": 0, "output": 0, "progress": 0}
    for key, folder, pattern in (("input", ws.input_dir, "*.pptx"), ("output", ws.output_dir, "*.pptx"),
                                 ("progress", ws.state_dir, "*.json*")):
        for f in folder.glob(pattern):
            if not dry_run:
                f.unlink(missing_ok=True)
            counts[key] += 1
    return counts
