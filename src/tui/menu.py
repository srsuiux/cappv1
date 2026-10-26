"""Arrow-key menu that renders inline (like Claude Code's selectors) and
erases itself when you choose."""
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension

from src.tui.theme import ACCENT

_PAGE = 10


def select(title: str, options: list[tuple[str, str]], default: int = 0) -> int | None:
    """Returns the chosen index, or None if cancelled (Esc / Ctrl+C)."""
    if not options:
        return None
    state = {"i": min(default, len(options) - 1)}

    def render():
        start = max(0, min(state["i"] - _PAGE // 2, len(options) - _PAGE))
        shown = options[start:start + _PAGE]
        out = [("bold", f"{title}\n")]
        if start > 0:
            out.append(("fg:#777777", "   ↑ more\n"))
        for offset, (label, desc) in enumerate(shown):
            i = start + offset
            if i == state["i"]:
                out.append((f"fg:{ACCENT} bold", f" ❯ {label}"))
                out.append(("fg:#aaaaaa", f"  {desc}\n" if desc else "\n"))
            else:
                out.append(("", f"   {label}"))
                out.append(("fg:#666666", f"  {desc}\n" if desc else "\n"))
        if start + _PAGE < len(options):
            out.append(("fg:#777777", "   ↓ more\n"))
        out.append(("fg:#777777 italic", "↑/↓ move · Enter select · Esc cancel"))
        return out

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(event):
        state["i"] = (state["i"] - 1) % len(options)

    @kb.add("down")
    @kb.add("j")
    def _down(event):
        state["i"] = (state["i"] + 1) % len(options)

    @kb.add("enter")
    def _enter(event):
        event.app.exit(result=state["i"])

    @kb.add("escape", eager=True)
    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result=None)

    for n in range(1, min(len(options), 9) + 1):
        @kb.add(str(n))
        def _number(event, n=n):
            event.app.exit(result=n - 1)

    app = Application(
        layout=Layout(Window(FormattedTextControl(render), height=Dimension(min=3))),
        key_bindings=kb,
        full_screen=False,
        erase_when_done=True,
    )
    return app.run()
