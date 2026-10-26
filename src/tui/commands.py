"""Slash commands. Each handler takes the Session and the argument string."""
import asyncio
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src import doctor, models
from src.state import load_state
from src.tui import envfile
from src.tui.menu import select
from src.tui.theme import ACCENT, BAD, CROSS, MUTED, OK, PROVIDER_LABELS, TICK, WARN


@dataclass
class Command:
    name: str
    help: str
    handler: Callable
    aliases: tuple[str, ...] = ()


# ---------------------------------------------------------------- helpers
def _checking(session, label: str, fn):
    """Runs fn() (blocking) under a spinner and returns its result."""
    with session.console.status(Text(f"{label}…", style=ACCENT), spinner="dots", spinner_style=ACCENT):
        return fn()


def _ok(session, msg: str) -> None:
    session.console.print(Text(f" {TICK} {msg}", style=OK))


def _fail(session, msg: str, fix: str = "") -> None:
    session.console.print(Text(f" {CROSS} {msg}", style=BAD))
    if fix:
        session.console.print(Text(f"   {fix}", style=MUTED))


def _env() -> dict[str, str]:
    return doctor.read_env_file()


# ---------------------------------------------------------------- /help
def cmd_help(session, args: str) -> None:
    table = Table.grid(padding=(0, 3))
    for c in session.commands:
        names = "  ".join([f"/{c.name}"] + [f"/{a}" for a in c.aliases])
        table.add_row(Text(names, style=f"bold {ACCENT}"), Text(c.help))
    session.console.print()
    session.console.print(table)
    session.console.print(Text("\n Tip: drag a .pptx file (or a folder of them) into this window to add it.", style=MUTED))
    session.console.print()


# ---------------------------------------------------------------- /status
def cmd_status(session, args: str) -> None:
    config, err = session.load()
    env = _env()
    rows = Table.grid(padding=(0, 2))
    provider = doctor.pick_provider(env)
    rows.add_row(Text("Service", style=MUTED), Text(PROVIDER_LABELS.get(provider, provider)))
    if config:
        rows.add_row(Text("Model", style=MUTED), Text(config.model))
        rows.add_row(Text("At once", style=MUTED), Text(str(config.concurrency)))
    rows.add_row(Text("Privacy", style=MUTED), session.privacy_text(provider))
    rows.add_row(Text("Workspace", style=MUTED), Text(str(envfile.ROOT)))
    session.console.print(Panel(rows, title="Status", title_align="left", border_style="grey42", padding=(1, 2)))
    if err:
        _fail(session, err, "Type /init to set this up.")


# ---------------------------------------------------------------- /files
def cmd_files(session, args: str) -> None:
    config, _ = session.load(quiet=True)
    input_dir = envfile.ROOT / "input"
    output_dir = envfile.ROOT / "output"
    files = sorted(input_dir.glob("*.pptx"))
    if not files:
        session.console.print(Text("\n No files yet. Drag a .pptx into this window, or copy it into the input/ folder.\n", style=MUTED))
        return
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("File", overflow="fold")
    table.add_column("Status")
    for f in files:
        state = load_state(envfile.ROOT / ".state", f.name)
        done = state.status == "complete" and (output_dir / f.name).exists()
        if done:
            status = Text(f"{TICK} done", style=OK)
        elif state.completed_slide_indices:
            status = Text(f"◐ {len(state.completed_slide_indices)} slides finished, will resume", style=WARN)
        else:
            status = Text("○ waiting", style=MUTED)
        table.add_row(f.name, status)
    session.console.print()
    session.console.print(table)
    session.console.print()


# ---------------------------------------------------------------- /doctor
def cmd_doctor(session, args: str) -> None:
    env = _env()
    provider = doctor.pick_provider(env)
    session.console.print()
    all_ok = True

    def step(label: str, fn):
        nonlocal all_ok
        ok, detail = _checking(session, label, fn)
        all_ok &= ok
        if ok:
            session.console.print(Text(f" {TICK} {label}", style=OK), Text(f" {detail}" if detail else "", style=MUTED), sep="")
        else:
            _fail(session, label, detail)

    step("Settings file found", lambda: ((envfile.ENV_PATH.exists()), "" if envfile.ENV_PATH.exists() else "Type /init"))
    if provider == "ollama":
        base = doctor.ollama_base_url(env)
        local = urlparse(base).hostname in {"localhost", "127.0.0.1", "::1"} or env.get("OLLAMA_ALLOW_REMOTE") == "1"
        step("Ollama address is this computer", lambda: (local, "your slides never leave it" if local else f"{base} is another machine"))

        def ollama_up():
            try:
                installed = doctor.ollama_installed_models(base)
            except Exception:
                return False, "Start the Ollama app, or install it from ollama.com/download"
            session._installed = installed
            return True, ""

        step("Ollama is running", ollama_up)
        model = env.get("MODEL") or doctor.DEFAULT_OLLAMA_MODEL
        installed = getattr(session, "_installed", [])
        have = doctor.model_is_installed(model, installed)
        step(f"Model {model} is downloaded", lambda: (have, "" if have else f"Run: ollama pull {model}"))
    else:
        key_var, name = doctor.PROVIDERS[provider]
        key = env.get(key_var)
        step(f"{key_var} is set", lambda: (bool(key), "" if key else "Type /init to add it"))
        if key:
            step(f"{name} accepts the key", lambda: doctor.check_api_key_live(provider, key))
    deps_ok, deps_detail = doctor.check_venv_deps()
    step("Python packages installed", lambda: (bool(deps_ok) if deps_ok is not None else True, deps_detail))
    step("input/ and output/ folders are ready",
         lambda: (doctor.check_dir_writable(envfile.ROOT / "input") and doctor.check_dir_writable(envfile.ROOT / "output"), ""))
    session.console.print()
    session.console.print(Text(" All good. Type /run to start." if all_ok else " Fix the items marked ✗, then run /doctor again.", style=OK if all_ok else WARN))
    session.console.print()


# ---------------------------------------------------------------- /init
_SERVICES = [
    ("ollama", "Ollama", "Private: runs on this computer. Free, works offline"),
    ("openrouter", "OpenRouter", "Online. Has free models"),
    ("openai", "OpenAI", "Online. Paid, a fraction of a cent per image"),
    ("anthropic", "Anthropic", "Online. Paid, a fraction of a cent per image"),
]
_KEY_HELP = {
    "openrouter": "openrouter.ai -> account settings -> API Keys (starts with sk-or-v1-)",
    "openai": "platform.openai.com/api-keys",
    "anthropic": "console.anthropic.com -> API Keys",
}


def cmd_init(session, args: str) -> None:
    console = session.console
    console.print()
    env = _env()
    current = doctor.pick_provider(env) if envfile.ENV_PATH.exists() else None
    default = next((i for i, s in enumerate(_SERVICES) if s[0] == current), 0)
    choice = select("Which AI service should cappv1 use?", [(n, d) for _, n, d in _SERVICES], default)
    if choice is None:
        console.print(Text(" Setup cancelled.", style=MUTED))
        return
    provider, name, _ = _SERVICES[choice]
    console.print(Text(f" {TICK} Service: {name}", style=OK))
    values = {"PROVIDER": provider}
    previous = env.get("PROVIDER", "")

    if provider == "ollama":
        model = _setup_ollama(session, env)
        if model is None:
            return
        values["MODEL"] = model
        values["FALLBACK_MODEL"] = ""
    else:
        key_var = doctor.PROVIDERS[provider][0]
        existing = env.get(key_var, "")
        console.print(Text(f"   Get a key at {_KEY_HELP[provider]}", style=MUTED))
        if existing:
            console.print(Text(f"   A key ending ...{existing[-4:]} is already saved. Press Enter to keep it.", style=MUTED))
        from prompt_toolkit import prompt
        try:
            key = prompt(f" Paste your {name} key (hidden): ", is_password=True).strip() or existing
        except (EOFError, KeyboardInterrupt):
            console.print(Text("\n Setup cancelled.", style=MUTED))
            return
        if not key:
            _fail(session, "No key entered.")
            return
        ok, detail = _checking(session, f"Checking the key with {name}", lambda: doctor.check_api_key_live(provider, key))
        if ok:
            _ok(session, f"{name} accepted the key")
        else:
            _fail(session, detail)
            keep = select("Save it anyway?", [("No, let me try again", ""), ("Yes, save it", "")])
            if keep != 1:
                console.print(Text(" Nothing saved. Run /init to try again.", style=MUTED))
                return
        values[key_var] = key
        if previous and previous != provider:
            # a model from the old service would be rejected by the new one
            values["MODEL"] = ""
            values["FALLBACK_MODEL"] = ""

    envfile.set_values(values)
    _ok(session, "Saved to .env (readable only by you)")
    if provider != "ollama":
        console.print(Text("   Slide content will be sent to that service. For sensitive files, run /init and pick Ollama.", style=MUTED))
    console.print(Text("\n You're set. Drag a .pptx in here, then type /run.\n", style=OK))
    session.refresh()


def _setup_ollama(session, env: dict[str, str]) -> str | None:
    console = session.console
    base = doctor.ollama_base_url(env)
    while True:
        try:
            installed = _checking(session, "Looking for Ollama", lambda: doctor.ollama_installed_models(base))
            break
        except Exception:
            _fail(session, "Ollama isn't running.", "Open the Ollama app (llama icon). Not installed? Get it at ollama.com/download")
            again = select("What next?", [("Try again", "after starting Ollama"), ("Stop setup", "")])
            if again != 0:
                console.print(Text(" Setup stopped. Run /init when Ollama is ready.", style=MUTED))
                return None
    _ok(session, "Ollama is running")

    vision = _checking(session, "Finding image-capable models", lambda: models.fetch_ollama_vision_models(base))
    names = [n for n, _ in vision]
    suggested = doctor.DEFAULT_OLLAMA_MODEL
    options = [(n, "installed") for n in names]
    if not names or suggested not in names:
        options.append((f"Download {suggested}", "about 3 GB, a one-time download"))
    pick = select("Which model should read your images?", options)
    if pick is None:
        console.print(Text(" Setup cancelled.", style=MUTED))
        return None
    label = options[pick][0]
    if label.startswith("Download "):
        model = suggested
        if not shutil.which("ollama"):
            _fail(session, "Can't find the ollama command.", f"Open a new Terminal and run: ollama pull {model}")
            return None
        console.print(Text(f" Downloading {model}. Ollama shows its own progress below.\n", style=MUTED))
        if subprocess.run(["ollama", "pull", model]).returncode != 0:
            _fail(session, "The download didn't finish.", f"Check your internet, then run /init again (or: ollama pull {model})")
            return None
        _ok(session, f"{model} is ready")
    else:
        model = label
        _ok(session, f"Model: {model}")
    return model


# ---------------------------------------------------------------- /models
def cmd_models(session, args: str) -> None:
    env = _env()
    provider = doctor.pick_provider(env)
    current = env.get("MODEL") or None
    session.console.print()
    try:
        if provider == "ollama":
            found = _checking(session, "Asking Ollama which models are installed",
                              lambda: models.fetch_ollama_vision_models(doctor.ollama_base_url(env)))
        elif provider == "openrouter":
            found = _checking(session, "Fetching free models from OpenRouter", models.fetch_free_vision_models)
        else:
            from prompt_toolkit import prompt
            default = {"openai": "gpt-4o-mini", "anthropic": "claude-haiku-5-5"}[provider]
            value = prompt(f" Model name (Enter keeps {current or default}): ").strip()
            if value:
                envfile.set_values({"MODEL": value})
                _ok(session, f"Model set to {value}")
            return
    except Exception as exc:
        _fail(session, f"Couldn't list models ({exc.__class__.__name__}).",
              "Start Ollama and try again." if provider == "ollama" else "Check your internet connection.")
        return
    if not found:
        _fail(session, "No image-capable models found.", "Try: ollama pull gemma3:4b" if provider == "ollama" else "")
        return
    options = [(mid, "current" if mid == current else name) for mid, name in found]
    start = next((i for i, (mid, _) in enumerate(found) if mid == current), 0)
    pick = select("Pick a model", options, start)
    if pick is None:
        return
    envfile.set_values({"MODEL": found[pick][0]})
    _ok(session, f"Model set to {found[pick][0]}")
    session.refresh()


# ---------------------------------------------------------------- /run
def cmd_run(session, args: str) -> None:
    from src.pipeline import discover_files, run, setup_logging
    from src.tui.runview import RunView

    console = session.console
    config, err = session.load()
    if not config:
        _fail(session, err, "Type /init to set this up.")
        return
    if not list(config.input_dir.glob("*.pptx")):
        console.print(Text("\n Nothing to process yet. Drag a .pptx into this window first.\n", style=MUTED))
        return

    # the same checks `cappv1 doctor --quick` runs, so a problem shows up now, not mid-deck
    env = _env()
    if config.provider == "ollama":
        try:
            installed = _checking(session, "Checking Ollama", lambda: doctor.ollama_installed_models(doctor.ollama_base_url(env)))
        except Exception:
            _fail(session, "Ollama isn't running.", "Open the Ollama app, then run /run again.")
            return
        if not doctor.model_is_installed(config.model, installed):
            _fail(session, f"{config.model} isn't downloaded.", f"Run: ollama pull {config.model}   (or /models to pick another)")
            return

    setup_logging(config.logs_dir, console=False)
    resume = "--resume" in args
    pending = discover_files(config, resume)
    if not pending:
        console.print(Text("\n Everything in input/ is already done. Add more files, or /open to see the results.\n", style=MUTED))
        return

    console.print()
    began = time.monotonic()
    view = RunView(console, config)
    try:
        with view:
            failed = asyncio.run(run(config, resume_only=resume))
    except KeyboardInterrupt:
        console.print(Text("\n Stopped. Finished slides are saved; /run continues from there.\n", style=WARN))
        return
    except Exception as exc:
        _fail(session, f"The run stopped: {exc}")
        return

    took = int(time.monotonic() - began)
    t = view.totals
    body = Text()
    body.append(f"{view.files_ok} of {len(pending)} file(s) finished", style=f"bold {OK if not (failed or view.files_bad) else WARN}")
    body.append(f"   in {took // 60}m {took % 60:02d}s\n", style=MUTED)
    body.append(f"{t['captioned']} described · {t['decorative']} decorative · {t['cached']} reused · {t['failed']} failed")
    if failed or view.files_bad:
        body.append("\nSome items need a retry. Run /run again; finished work isn't redone.", style=WARN)
    else:
        body.append("\nType /open to see the finished files.", style=MUTED)
    console.print(Panel(body, border_style=OK if not (failed or view.files_bad) else WARN, padding=(0, 2)))
    console.print()


# ---------------------------------------------------------------- /open
def cmd_open(session, args: str) -> None:
    out = envfile.ROOT / "output"
    out.mkdir(exist_ok=True)
    opener = "open" if platform.system() == "Darwin" else "xdg-open"
    if shutil.which(opener):
        subprocess.run([opener, str(out)])
        _ok(session, "Opened the output folder")
    else:
        session.console.print(Text(f" Your finished files are in {out}", style=MUTED))


# ---------------------------------------------------------------- /clean
def cmd_clean(session, args: str) -> None:
    root = envfile.ROOT
    inputs, outputs = list((root / "input").glob("*.pptx")), list((root / "output").glob("*.pptx"))
    states = list((root / ".state").glob("*.json"))
    session.console.print(Text(f"\n This permanently deletes {len(inputs)} input, {len(outputs)} output file(s) and saved progress.", style=WARN))
    pick = select("Delete them?", [("No, keep everything", ""), ("Yes, delete", "no undo")])
    if pick != 1:
        session.console.print(Text(" Nothing deleted.", style=MUTED))
        return
    for f in inputs + outputs + states:
        f.unlink()
    _ok(session, "Workspace is clean")


# ---------------------------------------------------------------- /clear, /exit
def cmd_clear(session, args: str) -> None:
    session.console.clear()
    session.banner()


def cmd_exit(session, args: str) -> None:
    raise EOFError


def build_commands() -> list[Command]:
    return [
        Command("run", "Describe everything in input/ (add --resume to continue unfinished files)", cmd_run, ("start",)),
        Command("files", "Show the files waiting in input/ and their progress", cmd_files, ("ls",)),
        Command("init", "Set up or change the AI service", cmd_init, ("setup",)),
        Command("models", "Pick a different model", cmd_models),
        Command("doctor", "Check that everything is working", cmd_doctor),
        Command("status", "Show the current settings", cmd_status),
        Command("open", "Open the output folder", cmd_open),
        Command("clean", "Delete input, output and saved progress", cmd_clean),
        Command("clear", "Clear the screen", cmd_clear),
        Command("help", "Show this list", cmd_help, ("?",)),
        Command("exit", "Leave cappv1", cmd_exit, ("quit",)),
    ]
