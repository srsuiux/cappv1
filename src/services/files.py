"""The decks and Word documents in input/ and output/. Deliberately small: add, list, fetch, clean."""
import os
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from src.config import load_config
from src.pipeline import SUPPORTED_EXTENSIONS, inspect_file
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
    """A bare, plain .pptx or .docx filename, or ServiceError. Folders in the name are dropped."""
    base = Path(str(name).replace("\\", "/")).name.strip()
    if not base or base.startswith(".") or any(ord(c) < 32 for c in base) or len(base) > 200:
        raise ServiceError("bad_name", "That file name can't be used.", "Rename the file and try again.")
    ext = Path(base).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ServiceError("unsupported_file", f"{base} isn't a .pptx or .docx file.",
                           "cappv1 works with PowerPoint .pptx and Word .docx files.")
    return base[:-len(ext)] + ext


_MAIN_PART = {".pptx": "ppt/presentation.xml", ".docx": "word/document.xml"}


def _looks_valid(path: Path, ext: str) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
    return "[Content_Types].xml" in names and _MAIN_PART[ext] in names


def input_candidates(folder: Path) -> list[Path]:
    """Supported files directly inside a folder (Word's ~$ lock files and dotfiles are skipped)."""
    return sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith(("~$", ".")))


def input_paths(ws: Workspace) -> list[Path]:
    return input_candidates(ws.input_dir) if ws.input_dir.is_dir() else []


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
                                       "Split the file or compress its pictures first.")
                f.write(chunk)
        ext = Path(name).suffix.lower()
        if not _looks_valid(tmp, ext):
            kind, app = ("PowerPoint", "PowerPoint") if ext == ".pptx" else ("Word", "Word")
            raise ServiceError("unsupported_file", f"{name} isn't a valid {kind} file.",
                               f"Open it in {app} and save a copy as {ext}.")
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
    return [describe(ws, p.name) for p in input_paths(ws)]


def output_file(ws: Workspace, name: str) -> Path:
    """The finished copy of a file, for download."""
    path = ws.output_dir / safe_name(name)
    if not path.is_file() or path.resolve().parent != ws.output_dir.resolve():
        raise ServiceError("no_output", f"There is no finished copy of {name} yet.", "Run it first.")
    return path


def clean(ws: Workspace, dry_run: bool = False) -> dict[str, int]:
    """Deletes decks in input/ and output/ and all saved progress. No undo.
    With dry_run it only counts what would go."""
    counts = {"input": 0, "output": 0, "progress": 0}
    for key, folder, patterns in (("input", ws.input_dir, ("*.pptx", "*.docx")), ("output", ws.output_dir, ("*.pptx", "*.docx")),
                                  ("progress", ws.state_dir, ("*.json*",))):
        for f in (f for pattern in patterns for f in folder.glob(pattern)):
            if not dry_run:
                f.unlink(missing_ok=True)
            counts[key] += 1
    return counts
