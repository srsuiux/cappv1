"""Accessibility report for one deck: what cappv1 noticed but will not change."""
from cappv1 import outputs
from cappv1.audit import audit_deck
from cappv1.services import files
from cappv1.services.errors import ServiceError
from cappv1.services.workspace import Workspace


def report(ws: Workspace, name: str) -> dict:
    """Checks the finished copy if there is one, otherwise the original. Read-only."""
    name = files.safe_name(name)
    if not name.lower().endswith(".pptx"):
        raise ServiceError("audit_unsupported", "The accessibility check only reads PowerPoint decks for now.",
                           "Word documents get alt text, but are not checked yet.")
    finished = outputs.latest(ws.output_dir, name)
    path = finished if finished is not None else ws.input_dir / name
    if not path.is_file():
        raise ServiceError("not_found", f"{name} isn't in your list.", "Add it first, or check the name.")
    try:
        result = audit_deck(path).as_dict()
    except Exception as exc:  # a damaged deck must not crash the caller
        raise ServiceError("unreadable", f"{name} couldn't be read.", "Open it in PowerPoint and save it again.") from exc
    return {"file": name, "checked": "finished copy" if path == finished else "original", **result}
