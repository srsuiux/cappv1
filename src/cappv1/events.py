"""Tiny progress event bus. The pipeline emits; the terminal UI subscribes.
With no subscribers (the plain CLI) emit() does nothing."""
from contextlib import asynccontextmanager
from typing import Any, Callable

_listeners: list[Callable[[str, dict[str, Any]], None]] = []


def subscribe(listener: Callable[[str, dict[str, Any]], None]) -> Callable[[], None]:
    _listeners.append(listener)
    return lambda: _listeners.remove(listener) if listener in _listeners else None


def emit(event: str, **data: Any) -> None:
    for listener in list(_listeners):
        try:
            listener(event, data)
        except Exception:
            pass  # a display bug must never break captioning


@asynccontextmanager
async def working(kind: str, slide: int):
    """Marks one model call (picture, chart, table, ...) as in flight."""
    emit("element_start", kind=kind, slide=slide)
    try:
        yield
    finally:
        emit("element_end", kind=kind, slide=slide)
