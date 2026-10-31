"""Small drawing helpers shared by the slash commands."""

from rich.text import Text

from cappv1.services.errors import ServiceError
from cappv1.tui.theme import ACCENT, BAD, CROSS, MUTED, OK, TICK


# ---------------------------------------------------------------- helpers
def checking(session, label: str, fn):
    """Runs fn() (blocking) under a spinner and returns its result."""
    with session.console.status(Text(f"{label}…", style=ACCENT), spinner="dots", spinner_style=ACCENT):
        return fn()


def success(session, msg: str) -> None:
    session.console.print(Text(f" {TICK} {msg}", style=OK))


def fail(session, msg: str, fix: str = "") -> None:
    session.console.print(Text(f" {CROSS} {msg}", style=BAD))
    if fix:
        session.console.print(Text(f"   {fix}", style=MUTED))


def service_error(session, err: ServiceError) -> None:
    fail(session, err.message, err.fix)


def nothing_changed(session) -> None:
    session.console.print(Text(" Nothing changed.", style=MUTED))
