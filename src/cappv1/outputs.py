"""Where finished copies live. Each run writes into its own folder, output/<date>_<time>/, so an
earlier run's copies are kept until someone deletes them. Files placed directly in output/ by older
versions still count, as the oldest run."""
import re
import shutil
from datetime import datetime
from pathlib import Path

_EXTENSIONS = (".pptx", ".docx")
RUN_NAME = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d+)?")
LEGACY = ""  # the run id of files that sit directly in output/


def new_run_dir(root: Path) -> Path:
    """The folder for a run that starts now (not created until a file is saved into it)."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path, n = root / stamp, 1
    while path.exists():
        n += 1
        path = root / f"{stamp}-{n}"
    return path


def _files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in _EXTENSIONS and not p.name.startswith("."))


def run_ids(root: Path) -> list[str]:
    """Run folders, newest first, then "" for loose files from older versions if there are any."""
    ids = sorted((p.name for p in root.iterdir() if p.is_dir() and RUN_NAME.fullmatch(p.name)), reverse=True) if root.is_dir() else []
    if _files(root):
        ids.append(LEGACY)
    return ids


def run_path(root: Path, run: str) -> Path:
    if run and not RUN_NAME.fullmatch(run):
        raise ValueError(run)
    return root / run if run else root


def files_in(root: Path, run: str) -> list[Path]:
    return _files(run_path(root, run))


def latest(root: Path, name: str) -> Path | None:
    """The newest finished copy of a file, or None."""
    for run in run_ids(root):
        path = run_path(root, run) / name
        if path.is_file():
            return path
    return None


def delete_copy(root: Path, run: str, name: str) -> bool:
    """Deletes one finished copy; its run folder goes too when that was the last file in it."""
    folder = run_path(root, run)
    target = folder / name
    if target.parent != folder or not target.is_file():
        return False
    target.unlink()
    if run and not any(folder.iterdir()):
        folder.rmdir()
    return True


def delete_run(root: Path, run: str) -> int:
    """Deletes a whole run folder (loose older files for ""). Returns how many files went."""
    folder = run_path(root, run)
    found = _files(folder)
    if run:
        shutil.rmtree(folder, ignore_errors=True)
    else:
        for p in found:
            p.unlink(missing_ok=True)
    return len(found)
