"""Live display for a processing run, driven by engine events."""
import time

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from src import events
from src.config import Config
from src.tui import anim
from src.tui.theme import ACCENT, ANIMATE, BAD, CROSS, DOT, MUTED, OK, TICK, WARN


class RunView:
    def __init__(self, console: Console, config: Config) -> None:
        self.console = console
        self.config = config
        self.started = time.monotonic()
        self.phase, self.phase_since = "check", self.started
        self.file, self.file_index, self.file_total = "", 0, 0
        self.slide, self.slides = 0, 0
        self.in_flight: list[tuple[str, int, float]] = []
        self.first_call_done = False
        self.totals = {"captioned": 0, "enhanced": 0, "kept": 0, "decorative": 0, "cached": 0, "failed": 0}
        self.file_totals = dict(self.totals)
        self.files_ok, self.files_bad = 0, []
        self.live: Live | None = None
        self._unsub = None

    def __enter__(self) -> "RunView":
        self._unsub = events.subscribe(self.on_event)
        if ANIMATE:
            self.live = Live(self, console=self.console, refresh_per_second=12, transient=True)
            self.live.start()
        return self

    def __exit__(self, *exc) -> None:
        if self.live:
            self.live.stop()
        if self._unsub:
            self._unsub()

    # ---- rendering -------------------------------------------------------
    def _status(self) -> Text:
        if self.in_flight:
            kind, slide, started = self.in_flight[-1]
            label = f"{anim.phrase(kind, started)} on slide {slide + 1}"
            more = f"+{len(self.in_flight) - 1} more at once" if len(self.in_flight) > 1 else ""
            return anim.spinner_line(kind, label, started, more)
        labels = {
            "check": "Getting ready",
            "opening": f"Opening {self.file}" if self.file else "Opening the deck",
            "slide": f"Preparing slide {self.slide + 1}",
            "saving": f"Saving {self.file}",
        }
        kind = self.phase if self.phase in ("saving", "opening", "check") else "think"
        return anim.spinner_line(kind, labels.get(self.phase, "Thinking"), self.phase_since)

    def _bar(self) -> Text:
        width = 28
        done = self.slide if self.phase != "saving" else self.slides
        frac = (done / self.slides) if self.slides else 0
        filled = int(width * frac)
        line = Text(" ")
        line.append("━" * filled, style=ACCENT)
        line.append("╌" * (width - filled), style="grey35")
        line.append(f"  slide {min(done + 1, self.slides) if self.slides else 0} of {self.slides}", style=MUTED)
        line.append(f"  {int(frac * 100)}%", style=MUTED)
        return line

    def _counts(self) -> Text:
        t = self.file_totals
        line = Text(" ")
        line.append(f"{TICK} {t['captioned']} described", style=OK)
        line.append("   ")
        if t["enhanced"]:
            line.append(f"✎ {t['enhanced']} improved", style=OK)
            line.append("   ")
        if t["kept"]:
            line.append(f"❝ {t['kept']} kept as written", style=MUTED)
            line.append("   ")
        line.append(f"◐ {t['decorative']} decorative", style=MUTED)
        line.append("   ")
        line.append(f"↺ {t['cached']} reused", style=MUTED)
        line.append("   ")
        line.append(f"{CROSS} {t['failed']} failed", style=BAD if t["failed"] else MUTED)
        return line

    def _hint(self) -> Text | None:
        """Only says something when it's useful in the current situation."""
        if not self.in_flight:
            return None
        waited = time.monotonic() - self.in_flight[-1][2]
        if self.config.provider == "ollama" and not self.first_call_done and waited > 6:
            return Text("  The first image is slow on a local model while it loads into memory.", style=f"italic {MUTED}")
        if waited > 45:
            return Text("  Still working. Large images take longer; Ctrl+C stops and keeps your progress.", style=f"italic {MUTED}")
        return None

    def __rich__(self) -> Group:
        parts: list = [self._status(), Text()]
        if self.file:
            head = Text(" ")
            head.append(self.file, style="bold")
            head.append(f"   file {self.file_index} of {self.file_total}", style=MUTED)
            parts += [head, self._bar(), self._counts()]
        hint = self._hint()
        if hint:
            parts += [Text(), hint]
        return Group(*parts)

    # ---- events ----------------------------------------------------------
    def _say(self, text: Text) -> None:
        (self.live.console if self.live else self.console).print(text)

    def on_event(self, event: str, d: dict) -> None:
        now = time.monotonic()
        if event == "file_start":
            self.file, self.file_index, self.file_total = d["filename"], d["index"], d["total"]
            self.slide, self.slides = 0, 0
            self.file_totals = {k: 0 for k in self.totals}
            self.phase, self.phase_since = "opening", now
            if not ANIMATE:
                self._say(Text(f"[{d['index']}/{d['total']}] {d['filename']}"))
        elif event == "file_open":
            self.slides = d["total_slides"]
            self.slide = d["resumed"]
            self.phase, self.phase_since = "slide", now
            if d["resumed"]:
                self._say(Text(f"  {DOT} continuing from an earlier run; saved captions are reused, not redone", style=MUTED))
        elif event == "slide_start":
            self.slide, self.slides = d["slide"], d["total"]
            self.phase, self.phase_since = "slide", now
        elif event == "element_start":
            self.in_flight.append((d["kind"], d["slide"], now))
        elif event == "element_end":
            self.first_call_done = True
            for i, (kind, slide, _) in enumerate(self.in_flight):
                if kind == d["kind"] and slide == d["slide"]:
                    del self.in_flight[i]
                    break
        elif event == "slide_end":
            for key in self.totals:
                self.file_totals[key] += d[key]
                self.totals[key] += d[key]
            self.slide = d["slide"] + 1
            if not d["empty"]:
                bits = [f"{d['captioned']} described"]
                if d["enhanced"]:
                    bits.append(f"{d['enhanced']} improved")
                if d["kept"]:
                    bits.append(f"{d['kept']} kept as written")
                if d["decorative"]:
                    bits.append(f"{d['decorative']} decorative")
                if d["cached"]:
                    bits.append(f"{d['cached']} reused")
                if d["failed"]:
                    bits.append(f"{d['failed']} failed")
                mark, style = (CROSS, WARN) if d["failed"] else (TICK, MUTED)
                self._say(Text(f"  {mark} slide {d['slide'] + 1:<3} {' · '.join(bits)}", style=style))
        elif event == "file_saving":
            self.phase, self.phase_since = "saving", now
        elif event == "file_saved":
            if d["incomplete"]:
                self.files_bad.append(d["filename"])
            else:
                self.files_ok += 1
            line = Text(f" {'!' if d['incomplete'] else TICK} ", style=WARN if d["incomplete"] else OK)
            line.append(f"Saved output/{d['filename']}", style="bold")
            line.append("  some items need a retry, run /run again" if d["incomplete"] else "", style=WARN)
            if d.get("skipped"):
                line.append(f"  {d['skipped']} item(s) skipped, see the notes above", style=WARN)
            self._say(line)
        elif event == "element_skipped":
            self._say(Text(f"  ! skipped a {d['kind']} on {d['where']}: {d['error']}", style=WARN))
        elif event == "file_failed":
            self.files_bad.append(d["filename"])
            self._say(Text(f" {CROSS} {d['filename']} could not be processed: {d['error']}", style=BAD))

