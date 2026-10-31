"""What cappv1 keeps on this computer, and erasing it. Shown on the Your data page."""

from dataclasses import asdict, dataclass
from pathlib import Path

from cappv1.services import files
from cappv1.services.workspace import Workspace


@dataclass
class Place:
    id: str
    label: str
    path: str
    what: str
    files: int
    bytes: int
    has_slides: bool  # holds slide content (decks, or text taken from them)

    def as_dict(self) -> dict:
        return asdict(self)


def _measure(path: Path) -> tuple[int, int]:
    if path.is_file():
        return 1, path.stat().st_size
    items = [p for p in path.rglob("*") if p.is_file() and p.name != ".gitkeep"] if path.is_dir() else []
    return len(items), sum(p.stat().st_size for p in items)


def describe(ws: Workspace) -> list[Place]:
    rows = [
        ("input", "Your decks", ws.input_dir, "Copies of the decks you added. Your originals are never touched.", True),
        (
            "output",
            "Finished decks",
            ws.output_dir,
            "The same decks with alt text added, one folder for each run until you delete it.",
            True,
        ),
        (
            "state",
            "Saved progress",
            ws.state_dir,
            "Which slides are done, the alt text already written, and notes on items it could not read, so a repeat run costs nothing.",
            True,
        ),
        ("logs", "Run logs", ws.logs_dir, "File names, slide counts and error messages. Not slide content.", False),
        ("settings", "Settings and keys", ws.env_path, "Your chosen service and model, and any API keys. Readable only by you.", False),
    ]
    out = []
    for id_, label, path, what, slides in rows:
        count, size = _measure(path)
        out.append(Place(id_, label, str(path), what, count, size, slides))
    return out


def erase(ws: Workspace) -> dict[str, int]:
    """Deletes decks, finished copies, saved progress and logs. Keys and settings stay. No undo."""
    counts = files.clean(ws)
    counts["logs"] = 0
    for log in ws.logs_dir.glob("*.log*"):
        log.unlink(missing_ok=True)
        counts["logs"] += 1
    return counts
