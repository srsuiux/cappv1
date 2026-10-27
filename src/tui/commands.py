"""Slash commands. Each handler takes the Session and the argument string."""
import asyncio
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, replace
from typing import Callable
from urllib.parse import urlparse

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src import doctor, models
from src.pipeline import discover_files, inspect_file, run, setup_logging
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
    files = sorted(input_dir.glob("*.pptx"))
    if not files:
        session.console.print(Text("\n No files yet. Drag a .pptx into this window, or copy it into the input/ folder.\n", style=MUTED))
        return
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("File", overflow="fold")
    table.add_column("Status")
    for f in files:
        kind, _, _ = inspect_file(config, f) if config else ("new", None, "")
        status = {
            "done": Text(f"{TICK} already captioned, unchanged", style=OK),
            "changed": Text("◐ edited since the last run, will redo what changed", style=WARN),
            "partial": Text("◐ unfinished, will continue where it stopped", style=WARN),
            "new": Text("○ waiting", style=MUTED),
        }[kind]
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


# ---------------------------------------------------------------- /models, /init
# Both commands open the same flow: pick a service, then a model for it.
_SERVICES = [("ollama", "Ollama"), ("openrouter", "OpenRouter"), ("openai", "OpenAI"), ("anthropic", "Anthropic")]
_KEY_HELP = {
    "openrouter": "openrouter.ai -> account settings -> API Keys (starts with sk-or-v1-)",
    "openai": "platform.openai.com/api-keys",
    "anthropic": "console.anthropic.com -> API Keys",
}
# Short lists of vision-capable models. "Other..." covers anything newer.
_CURATED = {
    "openai": [("gpt-4o-mini", "default, lowest cost"), ("gpt-4o", "higher quality"), ("gpt-4.1-mini", "newer, low cost")],
    "anthropic": [("claude-haiku-5-5", "default, lowest cost"), ("claude-sonnet-5-5", "higher quality"),
                  ("claude-opus-5-5", "best quality, highest cost")],
}


def _service_rows(env: dict[str, str], active: str | None) -> list[tuple[str, str]]:
    rows = []
    for provider, name in _SERVICES:
        if provider == "ollama":
            note = "private: runs on this computer"
        else:
            note = f"sends slides to {name}" + (", key saved" if env.get(doctor.PROVIDERS[provider][0]) else "")
        rows.append((name + ("  (active)" if provider == active else ""), note))
    return rows


def cmd_models(session, args: str) -> None:
    console = session.console
    console.print()
    env = _env()
    active = doctor.pick_provider(env) if envfile.ENV_PATH.exists() else None

    # Already set up: show what is in use and don't walk through setup again.
    config, _ = session.load()
    change_model_only = False
    if config and active:
        label = f"{PROVIDER_LABELS[active]} · {config.model}"
        pick = select(f"Currently using {label}", [
            ("Keep this", "no changes"),
            ("Change the model", f"stay with {PROVIDER_LABELS[active]}"),
            ("Switch AI service", "choose a different service"),
        ])
        if pick not in (1, 2):
            _ok(session, f"Keeping {label}")
            console.print(Text("   ", style=MUTED), session.privacy_text(active), sep="")
            console.print()
            return
        change_model_only = pick == 1

    if change_model_only:
        provider, name = active, PROVIDER_LABELS[active]
    else:
        start = next((i for i, (p, _) in enumerate(_SERVICES) if p == active), 0)
        choice = select("Which AI service?", _service_rows(env, active), start)
        if choice is None:
            console.print(Text(" Nothing changed.", style=MUTED))
            return
        provider, name = _SERVICES[choice]
        console.print(Text(f" {TICK} Service: {name}", style=OK))

    # the model last used with this service, so switching back is one Enter
    remembered = env.get(f"MODEL_{provider.upper()}") or (env.get("MODEL", "") if provider == active else "")
    values = {"PROVIDER": provider}
    if provider == "ollama":
        model = _setup_ollama(session, env, remembered)
    else:
        key_var = doctor.PROVIDERS[provider][0]
        key = _ensure_key(session, provider, name, env.get(key_var, ""))
        if key is None:
            return
        if key != env.get(key_var, ""):
            values[key_var] = key
        model = _pick_model(session, provider, name, remembered)
    if not model:
        return

    # FALLBACK_MODEL is blanked so the new service's own default applies
    values.update({"MODEL": model, "FALLBACK_MODEL": "", f"MODEL_{provider.upper()}": model})
    envfile.set_values(values)
    session.refresh()
    _ok(session, f"Now using {name} · {model}")
    console.print(Text("   ", style=MUTED), session.privacy_text(provider), sep="")
    console.print()


def _ensure_key(session, provider: str, name: str, existing: str) -> str | None:
    """The saved key, or a newly entered and checked one. None means stop."""
    if existing:
        return existing
    from prompt_toolkit import prompt

    console = session.console
    console.print(Text(f"   Get a key at {_KEY_HELP[provider]}", style=MUTED))
    try:
        key = prompt(f" Paste your {name} key (hidden): ", is_password=True).strip()
    except (EOFError, KeyboardInterrupt):
        key = ""
    if not key:
        console.print(Text(" Nothing changed.", style=MUTED))
        return None
    ok, detail = _checking(session, f"Checking the key with {name}", lambda: doctor.check_api_key_live(provider, key))
    if ok:
        _ok(session, f"{name} accepted the key")
        return key
    _fail(session, detail)
    if select("Save it anyway?", [("No, let me try again", ""), ("Yes, save it", "")]) == 1:
        return key
    console.print(Text(" Nothing changed. Run /models to try again.", style=MUTED))
    return None


def _price(per_million: float) -> str:
    return "free" if per_million == 0 else (f"${per_million:.2f} per 1M tokens" if per_million >= 0.01 else "under $0.01 per 1M tokens")


def _openrouter_options(session) -> list[tuple[str, str]] | None:
    """Narrows OpenRouter's few hundred image models down to a short list."""
    try:
        found = _checking(session, "Fetching models from OpenRouter", models.fetch_openrouter_vision_models)
    except Exception as exc:
        _fail(session, f"Couldn't reach OpenRouter ({exc.__class__.__name__}).", "Check your internet connection.")
        return None
    free = sorted((m for m in found if m["free"]), key=lambda m: m["id"])
    paid = sorted((m for m in found if not m["free"]), key=lambda m: (m["price"], m["id"]))
    makers = sorted({m["id"].split("/")[0] for m in paid})

    pick = select("Which OpenRouter models?", [
        ("Free", f"{len(free)} models, shared servers (may log your slides)"),
        ("Cheapest paid", "the ten lowest prices"),
        ("Browse paid by maker", f"{len(makers)} makers, e.g. OpenAI, Google, DeepSeek"),
    ])
    if pick is None:
        session.console.print(Text(" Nothing changed.", style=MUTED))
        return None
    if pick == 0:
        chosen = free
    elif pick == 1:
        chosen = paid[:10]
    else:
        maker = select("Which maker?", [(m, f"{sum(x['id'].startswith(m + '/') for x in paid)} models") for m in makers])
        if maker is None:
            session.console.print(Text(" Nothing changed.", style=MUTED))
            return None
        chosen = [m for m in paid if m["id"].startswith(makers[maker] + "/")]
    if pick != 0:
        session.console.print(Text("   Prices are per million input tokens. A picture is roughly a thousand, so most cost a fraction of a cent.", style=MUTED))
    return [(m["id"], _price(m["price"])) for m in chosen]


def _pick_model(session, provider: str, name: str, remembered: str) -> str | None:
    if provider == "openrouter":
        options = _openrouter_options(session)
        if options is None:
            return None
    else:
        options = list(_CURATED[provider]) + [("Other...", "type a model name")]
    if not options:
        _fail(session, "No image-capable models found right now.")
        return None
    start = next((i for i, (mid, _) in enumerate(options) if mid == remembered), 0)
    options = [(mid, "last used" if mid == remembered else desc) for mid, desc in options]
    pick = select(f"Which {name} model?", options, start)
    if pick is None:
        session.console.print(Text(" Nothing changed.", style=MUTED))
        return None
    chosen = options[pick][0]
    if chosen != "Other...":
        return chosen
    from prompt_toolkit import prompt

    try:
        return prompt(" Model name: ").strip() or None
    except (EOFError, KeyboardInterrupt):
        return None


def _setup_ollama(session, env: dict[str, str], remembered: str) -> str | None:
    console = session.console
    base = doctor.ollama_base_url(env)
    while True:
        try:
            _checking(session, "Looking for Ollama", lambda: doctor.ollama_installed_models(base))
            break
        except Exception:
            _fail(session, "Ollama isn't running.", "Open the Ollama app (llama icon). Not installed? Get it at ollama.com/download")
            if select("What next?", [("Try again", "after starting Ollama"), ("Stop", "")]) != 0:
                console.print(Text(" Nothing changed. Run /models when Ollama is ready.", style=MUTED))
                return None
    _ok(session, "Ollama is running")

    vision = _checking(session, "Finding image-capable models", lambda: models.fetch_ollama_vision_models(base))
    names = [n for n, _ in vision]
    suggested = doctor.DEFAULT_OLLAMA_MODEL
    options = [(n, "last used" if n == remembered else "installed") for n in names]
    if suggested not in names:
        options.append((f"Download {suggested}", "about 3 GB, a one-time download"))
    start = next((i for i, n in enumerate(names) if n == remembered), 0)
    pick = select("Which model should read your images?", options, start)
    if pick is None:
        console.print(Text(" Nothing changed.", style=MUTED))
        return None
    label = options[pick][0]
    if not label.startswith("Download "):
        return label
    if not shutil.which("ollama"):
        _fail(session, "Can't find the ollama command.", f"Open a new Terminal and run: ollama pull {suggested}")
        return None
    console.print(Text(f" Downloading {suggested}. Ollama shows its own progress below.\n", style=MUTED))
    if subprocess.run(["ollama", "pull", suggested]).returncode != 0:
        _fail(session, "The download didn't finish.", f"Check your internet, then run /models again (or: ollama pull {suggested})")
        return None
    _ok(session, f"{suggested} is ready")
    return suggested


# ---------------------------------------------------------------- /run
def cmd_run(session, args: str) -> None:
    from src.tui.runview import RunView

    console = session.console
    config, err = session.load()
    if not config:
        _fail(session, err, "Type /init to set this up.")
        return
    if not list(config.input_dir.glob("*.pptx")):
        console.print(Text("\n Nothing to process yet. Drag a .pptx into this window first.\n", style=MUTED))
        return

    force = "--force" in args
    if force:
        console.print(Text("\n --force redoes every file from scratch and replaces alt text that authors wrote themselves.", style=WARN))
        if select("Continue?", [("No, keep what's there", ""), ("Yes, redo everything", "author text is replaced")]) != 1:
            console.print(Text(" Nothing changed.\n", style=MUTED))
            return
        config = replace(config, overwrite_existing=True)

    # the same quick checks as /doctor, so a problem shows up now, not mid-deck
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
    pending = discover_files(config, resume, force)
    if not pending:
        names = [f.name for f in config.input_dir.glob("*.pptx")]
        shown = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
        console.print(Text(f"\n {TICK} Already captioned and unchanged: {shown}.", style=OK))
        console.print(Text(" Their finished copies are in output/ (type /open). Add new files, or edit a deck and drop it in again.\n", style=MUTED))
        return

    console.print()
    began = time.monotonic()
    view = RunView(console, config)
    try:
        with view:
            failed = asyncio.run(run(config, resume_only=resume, force=force))
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
    parts = [f"{t['captioned']} described"]
    if t["enhanced"]:
        parts.append(f"{t['enhanced']} improved")
    if t["kept"]:
        parts.append(f"{t['kept']} kept as written")
    parts += [f"{t['decorative']} decorative", f"{t['cached']} reused", f"{t['failed']} failed"]
    body.append(" · ".join(parts))
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
        Command("run", "Describe everything in input/ (--resume continues unfinished files; --force redoes all and replaces authors' text)", cmd_run, ("start",)),
        Command("files", "Show the files waiting in input/ and their progress", cmd_files, ("ls",)),
        Command("models", "Switch the AI service or model", cmd_models, ("init", "setup", "provider")),
        Command("doctor", "Check that everything is working", cmd_doctor),
        Command("status", "Show the current settings", cmd_status),
        Command("open", "Open the output folder", cmd_open),
        Command("clean", "Delete input, output and saved progress", cmd_clean),
        Command("clear", "Clear the screen", cmd_clear),
        Command("help", "Show this list", cmd_help, ("?",)),
        Command("exit", "Leave cappv1", cmd_exit, ("quit",)),
    ]
