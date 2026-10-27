"""Accessibility report for one deck: what cappv1 noticed but will not change."""
from src.audit import audit_deck
from src.services.errors import ServiceError
from src.services import files
from src.services.workspace import Workspace


def report(ws: Workspace, name: str) -> dict:
    """Checks the finished copy if there is one, otherwise the original. Read-only."""
    name = files.safe_name(name)
    finished = ws.output_dir / name
    path = finished if finished.is_file() else ws.input_dir / name
    if not path.is_file():
        raise ServiceError("not_found", f"{name} isn't in your list.", "Add it first, or check the name.")
    try:
        result = audit_deck(path).as_dict()
    except Exception as exc:  # a damaged deck must not crash the caller
        raise ServiceError("unreadable", f"{name} couldn't be read.", "Open it in PowerPoint and save it again.") from exc
    return {"file": name, "checked": "finished copy" if path == finished else "original", **result}
