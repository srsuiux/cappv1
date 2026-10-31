"""Context-aware animation: what spins, and what it says, depends on what the
engine is actually doing right now (a picture, a chart, saving the deck...)."""
import time

from rich.text import Text

from cappv1.tui.theme import ACCENT, ANIMATE

# kind -> (frames, rotating status phrases)
KINDS = {
    "picture": (list("◜◠◝◞◡◟"), ["Looking at the picture", "Working out what it shows", "Writing a description"]),
    "chart": (list("▁▂▃▄▅▆▇█▇▆▅▄▃▂"), ["Reading the chart", "Spotting the trend", "Writing the takeaway"]),
    "table": (list("▤▥▦▧▨▩"), ["Reading the table", "Summarizing the rows", "Writing a description"]),
    "diagram": (list("◇◈◆◈"), ["Tracing the diagram", "Following the connections", "Writing a description"]),
    "object": (list("⬒⬔⬓⬕"), ["Opening the embedded object", "Making sense of its content", "Writing a description"]),
    "think": (list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"), ["Thinking"]),
    "saving": (list("⣾⣽⣻⢿⡿⣟⣯⣷"), ["Saving the deck"]),
    "opening": (list("⠁⠂⠄⡀⢀⠠⠐⠈"), ["Opening the deck"]),
    "check": (list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"), ["Checking"]),
}

_FPS = 12.0


def frame(kind: str, now: float | None = None) -> str:
    frames = KINDS[kind][0]
    if not ANIMATE:
        return frames[0]
    return frames[int((now if now is not None else time.monotonic()) * _FPS) % len(frames)]


def phrase(kind: str, started: float, now: float | None = None) -> str:
    """Cycles through the kind's phrases every few seconds."""
    phrases = KINDS[kind][1]
    now = now if now is not None else time.monotonic()
    return phrases[int((now - started) / 3.0) % len(phrases)]


def shimmer(text: str, now: float | None = None) -> Text:
    """A highlight that sweeps across the text, like Claude Code's status line."""
    out = Text()
    if not ANIMATE:
        out.append(text)
        return out
    now = now if now is not None else time.monotonic()
    pos = int(now * 14) % (len(text) + 8) - 4
    for i, ch in enumerate(text):
        d = abs(i - pos)
        out.append(ch, style=f"bold {ACCENT}" if d == 0 else (ACCENT if d == 1 else ""))
    return out


def spinner_line(kind: str, label: str, started: float, extra: str = "") -> Text:
    now = time.monotonic()
    line = Text(" ")
    line.append(frame(kind, now), style=ACCENT)
    line.append(" ")
    line.append_text(shimmer(label, now))
    line.append("…", style=ACCENT)
    if extra:
        line.append(f"  {extra}", style="grey62")
    line.append(f"  {int(now - started)}s", style="grey50")
    return line
