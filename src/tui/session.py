"""The interactive session: banner, prompt, slash commands, drag-and-drop."""
import difflib
import shlex
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.styles import Style
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from src import doctor
from src.config import Config, load_config
from src.pipeline import inspect_file
from src.tui import anim, envfile
from src.version import VERSION
from src.tui.commands import build_commands
from src.tui.menu import select
from src.tui.theme import ACCENT, ANIMATE, ARROW, MUTED, OK, PROVIDER_LABELS, TICK, WARN


_PROMPT_STYLE = Style.from_dict({
    "rule": "#555555",
    "prompt": f"{ACCENT} bold",
    "bottom-toolbar": "noreverse #888888",
    "completion-menu": "bg:#222222 #bbbbbb",
    "completion-menu.completion.current": f"bg:#333333 {ACCENT}",
    "completion-menu.meta.completion": "bg:#222222 #777777",
    "completion-menu.meta.completion.current": "bg:#333333 #aaaaaa",
})

# bare words people will type without the slash
_WORDS = {"run": "run", "start": "run", "go": "run", "help": "help", "?": "help", "exit": "exit",
          "quit": "exit", "q": "exit", "init": "init", "setup": "init", "doctor": "doctor",
          "files": "files", "ls": "files", "models": "models", "status": "status", "open": "open",
          "clean": "clean", "clear": "clear"}


class _SlashCompleter(Completer):
    def __init__(self, commands) -> None:
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        word = text[1:]
        for c in self.commands:
            if c.name.startswith(word):
                yield Completion(c.name, start_position=-len(word), display=f"/{c.name}", display_meta=c.help)


class Session:
    def __init__(self) -> None:
        self.console = Console()
        self.commands = build_commands()
        self.config: Config | None = None
        self.config_error = ""
        self._installed: list[str] = []
        (envfile.ROOT / ".state").mkdir(exist_ok=True)
        try:
            history = FileHistory(str(envfile.ROOT / ".state" / "history"))
        except OSError:
            history = InMemoryHistory()
        self.prompt = PromptSession(
            history=history, completer=_SlashCompleter(self.commands), complete_while_typing=True,
            style=_PROMPT_STYLE, bottom_toolbar=self._toolbar, reserve_space_for_menu=4,
        )

    # ---- config ----------------------------------------------------------
    def load(self, quiet: bool = False) -> tuple[Config | None, str]:
        try:
            self.config, self.config_error = load_config(), ""
        except Exception as exc:
            self.config, self.config_error = None, str(exc)
        return self.config, self.config_error

    def refresh(self) -> None:
        load_dotenv(envfile.ENV_PATH, override=True)
        self.load()

    def pending_count(self) -> int:
        """Files in input/ that still need work."""
        if not self.config:
            return len(list((envfile.ROOT / "input").glob("*.pptx")))
        return sum(inspect_file(self.config, f)[0] != "done" for f in self.config.input_dir.glob("*.pptx"))

    # ---- pieces of the screen -------------------------------------------
    def privacy_text(self, provider: str) -> Text:
        if provider == "ollama":
            return Text("● private: runs on this computer", style=OK)
        return Text(f"☁ slide content is sent to {PROVIDER_LABELS.get(provider, provider)}", style=WARN)

    def banner(self) -> None:
        provider = doctor.pick_provider(doctor.read_env_file()) if envfile.ENV_PATH.exists() else None
        body = Text()
        body.append("✻ ", style=ACCENT)
        body.append("Welcome to cappv1", style="bold")
        body.append(f"  v{VERSION}\n", style=MUTED)
        body.append("  Alt-text for PowerPoint, with a screen-reader user in mind\n\n", style=MUTED)
        if self.config:
            body.append(f"  {PROVIDER_LABELS.get(self.config.provider)} · {self.config.model}\n")
            body.append("  ")
            body.append_text(self.privacy_text(self.config.provider))
        else:
            body.append("  Not set up yet. ", style=WARN)
            body.append("Type /init to choose an AI service.", style="bold")
        body.append(f"\n  {envfile.ROOT}", style=MUTED)
        self.console.print(Panel(body, box=box.ROUNDED, border_style=ACCENT, padding=(1, 2), expand=False))
        n = self.pending_count()
        hint = f"{n} file(s) in input/. Type /run to start." if n and self.config else \
            "Drag a .pptx into this window to add it · / for commands · /help"
        self.console.print(Text(f" {hint}\n", style=MUTED))

    def _toolbar(self):
        width = shutil.get_terminal_size((80, 20)).columns
        left = f" {self.config.model}" if self.config else " not set up (type /init)"
        n = self.pending_count()
        mid = f" · {n} file{'s' if n != 1 else ''} in input/" if n else ""
        right = "/ commands · Ctrl+D exit "
        gap = max(2, width - len(left) - len(mid) - len(right))
        return FormattedText([("", left + mid + " " * gap + right)])

    def _message(self):
        width = shutil.get_terminal_size((80, 20)).columns
        return FormattedText([("class:rule", "─" * width + "\n"), ("class:prompt", f"{ARROW} ")])

    # ---- startup ---------------------------------------------------------
    def start(self) -> None:
        with self.console.status(anim.shimmer("Checking your setup", None), spinner="dots", spinner_style=ACCENT):
            self.load()
        self.console.print()
        self.banner()
        if not self.config:
            pick = select("Set up now?", [("Yes, choose an AI service", "takes about a minute"), ("Not now", "")])
            if pick == 0:
                self.dispatch("init", "")

    # ---- input handling --------------------------------------------------
    def find(self, name: str):
        for c in self.commands:
            if name == c.name or name in c.aliases:
                return c
        return None

    def dispatch(self, name: str, args: str) -> None:
        cmd = self.find(name)
        if not cmd:
            close = difflib.get_close_matches(name, [c.name for c in self.commands], n=1)
            hint = f" Did you mean /{close[0]}?" if close else " Type /help to see what's available."
            self.console.print(Text(f" Unknown command /{name}.{hint}\n", style=WARN))
            return
        cmd.handler(self, args)

    def add_files(self, paths: list[Path]) -> None:
        dest = envfile.ROOT / "input"
        dest.mkdir(exist_ok=True)
        added = 0
        for src in paths:
            sources = sorted(src.glob("*.pptx")) if src.is_dir() else [src]
            for f in sources:
                target = dest / f.name
                if target.exists() and target.resolve() != f.resolve():
                    pick = select(f"{f.name} is already in input/. Replace it?", [("Keep the one already there", ""), ("Replace it", "")])
                    if pick != 1:
                        continue
                if target.resolve() != f.resolve():
                    shutil.copy2(f, target)
                added += 1
                self.console.print(Text(f" {TICK} Added {f.name}", style=OK))
        if added:
            self.console.print(Text(f" Type /run to describe {'it' if added == 1 else 'them'}.\n", style=MUTED))
        else:
            self.console.print(Text(" No .pptx files found there.\n", style=WARN))

    def as_paths(self, line: str) -> list[Path] | None:
        """Terminal drag-and-drop pastes a (quoted or escaped) path."""
        try:
            parts = shlex.split(line)
        except ValueError:
            return None
        paths = [Path(p).expanduser() for p in parts]
        if paths and all(p.exists() and (p.is_dir() or p.suffix.lower() == ".pptx") for p in paths):
            return paths
        return None

    def handle(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        if line.startswith("/"):
            name, _, args = line[1:].partition(" ")
            self.dispatch(name.lower(), args.strip())
            return
        paths = self.as_paths(line)
        if paths:
            self.add_files(paths)
            return
        word, _, args = line.partition(" ")
        if word.lower() in _WORDS and len(line.split()) <= 2:
            self.dispatch(_WORDS[word.lower()], args)
            return
        close = difflib.get_close_matches(word.lower(), list(_WORDS), n=1)
        hint = f" Did you mean /{_WORDS[close[0]]}?" if close else ""
        self.console.print(Text(f" I don't understand that yet.{hint} Type /help for commands, or drag a .pptx file here.\n", style=WARN))

    def loop(self) -> None:
        while True:
            try:
                line = self.prompt.prompt(self._message())
            except KeyboardInterrupt:
                self.console.print(Text(" Press Ctrl+D or type /exit to leave.", style=MUTED))
                continue
            except EOFError:
                break
            try:
                self.handle(line)
            except EOFError:
                break
            except KeyboardInterrupt:
                self.console.print(Text("\n Cancelled.\n", style=MUTED))
            except Exception as exc:  # a bug in one command shouldn't end the session
                self.console.print(Text(f"\n Something went wrong: {exc.__class__.__name__}: {exc}", style="red"))
                self.console.print(Text(" Your files and progress are safe. Try again, or run /doctor.\n", style=MUTED))
        self.console.print(Text("\n Bye. Your files are in output/.\n", style=MUTED))


def main(argv: list[str]) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("cappv1 needs an interactive terminal. For scripts or background runs use: cappv1 --batch")
        return 1
    session = Session()
    session.start()
    session.loop()
    return 0
