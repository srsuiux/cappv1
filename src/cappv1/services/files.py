"""The decks and Word documents in input/ and output/. Add, list, fetch, remove, clean. Finished copies are kept per run (src/cappv1/outputs.py) until deleted."""

import os
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cappv1 import outputs
from cappv1.config import load_config
from cappv1.pipeline import SUPPORTED_EXTENSIONS, inspect_file
from cappv1.services.errors import ServiceError
from cappv1.services.workspace import Workspace

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@dataclass
class FileInfo:
    name: str
    size: int
    state: str  # new | partial | changed | done
    has_output: bool
    modified: float = 0.0  # when the file was added (seconds since 1970)
    output_size: int = 0  # the newest finished copy
    output_modified: float = 0.0
    output_run: str = ""  # which run folder that copy is in
    skipped: list[dict] = field(default_factory=list)  # items it could not read, to look at later: {where, kind, error}

    def as_dict(self) -> dict:
        return asdict(self)


def safe_name(name: str) -> str:
    """A bare, plain .pptx or .docx filename, or ServiceError. Folders in the name are dropped."""
    base = Path(str(name).replace("\\", "/")).name.strip()
    if not base or base.startswith(".") or any(ord(c) < 32 for c in base) or len(base) > 200:
        raise ServiceError("bad_name", "That file name can't be used.", "Rename the file and try again.")
    ext = Path(base).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ServiceError(
            "unsupported_file", f"{base} isn't a .pptx or .docx file.", "cappv1 works with PowerPoint .pptx and Word .docx files."
        )
    return base[: -len(ext)] + ext


_MAIN_PART = {".pptx": "ppt/presentation.xml", ".docx": "word/document.xml"}


def _looks_valid(path: Path, ext: str) -> bool:
    if not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
    return "[Content_Types].xml" in names and _MAIN_PART[ext] in names


def input_candidates(folder: Path) -> list[Path]:
    """Supported files directly inside a folder (Word's ~$ lock files and dotfiles are skipped)."""
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith(("~$", ".")))


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
                    raise ServiceError(
                        "too_big",
                        f"{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                        "Split the file or compress its pictures first.",
                    )
                f.write(chunk)
        ext = Path(name).suffix.lower()
        if not _looks_valid(tmp, ext):
            kind, app = ("PowerPoint", "PowerPoint") if ext == ".pptx" else ("Word", "Word")
            raise ServiceError("unsupported_file", f"{name} isn't a valid {kind} file.", f"Open it in {app} and save a copy as {ext}.")
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
    skipped = []
    try:
        state, saved, _ = inspect_file(load_config(ws.root), path)
        if state != "changed":  # notes about an older version of the file no longer apply
            skipped = list(saved.skipped)
    except Exception:
        state = "new"  # not configured yet: it simply hasn't been processed
    stat = path.stat()
    done = outputs.latest(ws.output_dir, name)
    info = FileInfo(name, stat.st_size, state, done is not None, stat.st_mtime, skipped=skipped)
    if done is not None:
        info.output_size, info.output_modified = done.stat().st_size, done.stat().st_mtime
        info.output_run = done.parent.name if done.parent != ws.output_dir else ""
    return info


def list_files(ws: Workspace) -> list[FileInfo]:
    return [describe(ws, p.name) for p in input_paths(ws)]


def output_file(ws: Workspace, name: str, run: str | None = None) -> Path:
    """A finished copy, for download: the newest one, or the one from a given run."""
    name = safe_name(name)
    try:
        path = outputs.latest(ws.output_dir, name) if run is None else outputs.run_path(ws.output_dir, run) / name
    except ValueError:
        path = None
    if path is None or not path.is_file():
        raise ServiceError("no_output", f"There is no finished copy of {name} yet.", "Run it first.")
    return path


def remove(ws: Workspace, name: str) -> str:
    """Takes a file out of the input list (the web page and the terminal both call this). Finished copies stay."""
    name = safe_name(name)
    path = ws.input_dir / name
    if not path.is_file():
        raise ServiceError("not_found", f"{name} isn't in your list.", "Reload the page, or type /files to see what is there.")
    path.unlink()
    return name


def history(ws: Workspace) -> list[dict]:
    """Finished copies by run, newest run first: {run, when, files: [{name, size, modified}], bytes}."""
    out = []
    for run in outputs.run_ids(ws.output_dir):
        items = [{"name": p.name, "size": p.stat().st_size, "modified": p.stat().st_mtime} for p in outputs.files_in(ws.output_dir, run)]
        if items:
            out.append({"run": run, "legacy": run == outputs.LEGACY, "files": items, "bytes": sum(i["size"] for i in items)})
    return out


def delete_copy(ws: Workspace, run: str, name: str | None = None) -> int:
    """Deletes one finished copy, or the whole run when no name is given. Returns how many files went."""
    try:
        if name is None:
            n = outputs.delete_run(ws.output_dir, run)
        else:
            n = int(outputs.delete_copy(ws.output_dir, run, safe_name(name)))
    except ValueError:
        n = 0
    if not n:
        raise ServiceError(
            "not_found", "That finished copy isn't there any more.", "Reload the page, or type /history to see what is kept."
        )
    return n


def clean(ws: Workspace, dry_run: bool = False) -> dict[str, int]:
    """Deletes decks in input/ and output/ and all saved progress. No undo.
    With dry_run it only counts what would go."""
    counts = {"input": 0, "output": 0, "progress": 0}
    for run in outputs.run_ids(ws.output_dir):
        counts["output"] += len(outputs.files_in(ws.output_dir, run))
        if not dry_run:
            outputs.delete_run(ws.output_dir, run)
    for key, folder, patterns in (("input", ws.input_dir, ("*.pptx", "*.docx")), ("progress", ws.state_dir, ("*.json*",))):
        for f in (f for pattern in patterns for f in folder.glob(pattern)):
            if not dry_run:
                f.unlink(missing_ok=True)
            counts[key] += 1
    return counts
