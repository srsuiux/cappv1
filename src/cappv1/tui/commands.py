"""Slash commands. Each handler takes the Session and the argument string.

This file only asks and draws; what cappv1 actually does lives in src/cappv1/services.
"""
import platform
import shutil
import subprocess
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Callable

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cappv1 import doctor, outputs
from cappv1.services import audit, files, health, settings
from cappv1.services import models as model_service
from cappv1.services.errors import ServiceError
from cappv1.tui.menu import select
from cappv1.tui.theme import ACCENT, BAD, CROSS, MUTED, OK, TICK, WARN


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


def _service_error(session, err: ServiceError) -> None:
    _fail(session, err.message, err.fix)


def _nothing_changed(session) -> None:
    session.console.print(Text(" Nothing changed.", style=MUTED))


# ---------------------------------------------------------------- /help
def cmd_help(session, args: str) -> None:
    table = Table.grid(padding=(0, 3))
    for c in session.commands:
        names = "  ".join([f"/{c.name}"] + [f"/{a}" for a in c.aliases])
        table.add_row(Text(names, style=f"bold {ACCENT}"), Text(c.help))
    session.console.print()
    session.console.print(table)
    session.console.print(Text("\n Tip: drag a .pptx or .docx file (or a folder of them) into this window to add it.", style=MUTED))
    session.console.print()


# ---------------------------------------------------------------- /status
def cmd_status(session, args: str) -> None:
    s = session.refresh()
    rows = Table.grid(padding=(0, 2))
    rows.add_row(Text("Service", style=MUTED), Text(s.provider_label or "not set up"))
    if s.configured:
        rows.add_row(Text("Model", style=MUTED), Text(s.model))
        rows.add_row(Text("At once", style=MUTED), Text(str(s.concurrency)))
        rows.add_row(Text("Privacy", style=MUTED), session.privacy_text(s.provider))
    rows.add_row(Text("Workspace", style=MUTED), Text(s.workspace))
    session.console.print(Panel(rows, title="Status", title_align="left", border_style="grey42", padding=(1, 2)))
    if s.error:
        _fail(session, s.error, "Type /init to set this up.")


# ---------------------------------------------------------------- /files
_STATE_TEXT = {
    "done": (f"{TICK} already captioned, unchanged", OK),
    "changed": ("◐ edited since the last run, will redo what changed", WARN),
    "partial": ("◐ unfinished, will continue where it stopped", WARN),
    "new": ("○ waiting", MUTED),
}


def cmd_files(session, args: str) -> None:
    listing = files.list_files(session.ws)
    if not listing:
        session.console.print(Text("\n No files yet. Drag a .pptx or .docx into this window, or copy it into the input/ folder.\n", style=MUTED))
        return
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("File", overflow="fold")
    table.add_column("Size", justify="right")
    table.add_column("Added")
    table.add_column("Status")
    for f in listing:
        text, style = _STATE_TEXT[f.state]
        table.add_row(f.name, _size(f.size), _when(f.modified), Text(text, style=style))
    session.console.print()
    session.console.print(table)
    session.console.print()


def _size(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n >= 104858 else f"{max(1, round(n / 1024))} KB"


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")


def _run_label(run: str) -> str:
    if not run:
        return "earlier versions"
    return _when(datetime.strptime(run[:19], "%Y-%m-%d_%H-%M-%S").timestamp())


# ---------------------------------------------------------------- /history, /remove
def cmd_history(session, args: str) -> None:
    runs = files.history(session.ws)
    if not runs:
        session.console.print(Text("\n No finished copies yet. Type /run to make some.\n", style=MUTED))
        return
    table = Table(box=None, padding=(0, 2), show_edge=False)
    for col in ("Run", "Folder", "Files", "Size"):
        table.add_column(col, justify="right" if col == "Size" else "left", overflow="fold")
    for r in runs:
        names = ", ".join(f["name"] for f in r["files"])
        table.add_row(_run_label(r["run"]), r["run"] or "output/", names, _size(r["bytes"]))
    session.console.print()
    session.console.print(table)
    session.console.print(Text("\n /remove <run folder> deletes a run; /remove <run folder>/<file> deletes one copy.\n", style=MUTED))


def cmd_remove(session, args: str) -> None:
    """Removes a file from the list, or a finished copy / whole run from the history. The web page shows the change too."""
    target = args.strip().strip("/")
    if not target:
        session.console.print(Text("\n Type /remove <file name> to take a file off the list, or /remove <run folder> for a run (see /history).\n", style=MUTED))
        return
    run, _, name = target.partition("/")
    try:
        if session.runs.running:
            raise ServiceError("busy", "A run is in progress.", "Wait for it to finish, or stop it first.")
        if outputs.RUN_NAME.fullmatch(run):
            what = f"the copy {name} in run {run}" if name else f"every finished copy in run {run}"
            if select(f"Delete {what}?", [("No, keep it", ""), ("Yes, delete", "no undo")]) != 1:
                _nothing_changed(session)
                return
            files.delete_copy(session.ws, run, name or None)
            _ok(session, f"Deleted {what}")
        else:
            files.remove(session.ws, target)
            _ok(session, f"Removed {target} from the list. Finished copies are kept.")
    except ServiceError as err:
        _service_error(session, err)


# ---------------------------------------------------------------- /audit
def _slide_list(slides: list) -> str:
    return ", ".join(str(n) for n in slides[:12]) + (f" and {len(slides) - 12} more" if len(slides) > 12 else "")


def cmd_audit(session, args: str) -> None:
    """Reports what cappv1 noticed but will not change. Read-only."""
    names = [args.strip()] if args.strip() else [f.name for f in files.list_files(session.ws) if f.name.lower().endswith(".pptx")]  # the check reads decks only
    if not names:
        session.console.print(Text("\n No files yet. Drag a .pptx or .docx into this window first.\n", style=MUTED))
        return
    for name in names:
        try:
            result = audit.report(session.ws, name)
        except ServiceError as err:
            _fail(session, name, f"{err.message} {err.fix}".strip())
            continue
        session.console.print()
        session.console.print(Text(f" {result['file']}", style="bold"), Text(f"  (checked the {result['checked']})", style=MUTED), sep="")
        if not result["groups"]:
            session.console.print(Text(f" {TICK} No contrast or reading-order problems found.", style=OK))
        for g in result["groups"]:
            session.console.print(Text(f" ! {g['message']}", style=WARN))
            session.console.print(Text(f"   {g['detail']}", style=MUTED))
            session.console.print(Text(f"   Slides: {_slide_list(g['slides'])}", style=MUTED))
        session.console.print(Text(" cappv1 only reports these. Colors and layout are yours to change.", style=MUTED))
    session.console.print()


# ---------------------------------------------------------------- /doctor
def cmd_doctor(session, args: str) -> None:
    session.console.print()
    all_ok = True
    for planned in health.planned_checks(session.ws):
        ok, detail = _checking(session, planned.label, planned.run)
        all_ok &= ok
        if ok:
            session.console.print(Text(f" {TICK} {planned.label}", style=OK), Text(f" {detail}" if detail else "", style=MUTED), sep="")
        else:
            _fail(session, planned.label, detail)
    session.console.print()
    session.console.print(Text(" All good. Type /run to start." if all_ok else " Fix the items marked ✗, then run /doctor again.", style=OK if all_ok else WARN))
    session.console.print()


# ---------------------------------------------------------------- /init, /models
# /init is the guided setup: if cappv1 is already configured it shows the current
# choice first and lets you keep it. /models goes straight to the pickers.
# Both then share one flow: pick a service, then a model for it.
def cmd_init(session, args: str) -> None:
    if _configure(session, show_current_first=True):
        _where_next(session)


def _where_next(session) -> None:
    pick = select("Where would you like to go on?", [
        ("Continue in the browser", "same settings, easier for first-time users"),
        ("Stay in the terminal", "type /run when you're ready"),
    ])
    if pick == 0:
        cmd_web(session, "")


# ---------------------------------------------------------------- /web
def cmd_web(session, args: str) -> None:
    import webbrowser

    from cappv1.web.server import WebServer

    console = session.console
    if args.strip() == "stop":
        if session.web:
            session.web.stop()
            session.web = None
            _ok(session, "Web page stopped")
        else:
            console.print(Text(" The web page isn't running.", style=MUTED))
        return
    if not session.web:
        session.web = WebServer(session.ws, runs=session.runs)
        try:
            session.web.start()
        except ServiceError as err:
            session.web = None
            _service_error(session, err)
            return
    url = session.web.url
    _ok(session, "Web page is running on this computer only")
    console.print(Text(f"   {url}", style=ACCENT))
    console.print(Text("   Opened in your browser. Type /web stop to turn it off. Runs started there show up here too.", style=MUTED))
    webbrowser.open(url)


def cmd_models(session, args: str) -> None:
    _configure(session, show_current_first=False)


def _configure(session, show_current_first: bool) -> bool:
    """True when a service and model are now saved (changed or kept)."""
    console = session.console
    console.print()
    current = settings.read(session.ws)
    active = current.provider

    # Already set up: show what is in use and don't walk through setup again.
    change_model_only = False
    if show_current_first and current.configured and active:
        label = f"{current.provider_label} · {current.model}"
        pick = select(f"Currently using {label}", [
            ("Keep this", "no changes"),
            ("Change the model", f"stay with {current.provider_label}"),
            ("Switch AI service", "choose a different service"),
        ])
        if pick not in (1, 2):
            _ok(session, f"Keeping {label}")
            console.print(Text("   ", style=MUTED), session.privacy_text(active), sep="")
            console.print()
            return True
        change_model_only = pick == 1

    if change_model_only:
        svc = settings.service(active)
    else:
        rows = [(s.label + ("  (active)" if s.id == active else ""),
                 s.note + (", key saved" if current.keys_saved.get(s.id) else "")) for s in settings.SERVICES]
        start = next((i for i, s in enumerate(settings.SERVICES) if s.id == active), 0)
        choice = select("Which AI service?", rows, start)
        if choice is None:
            _nothing_changed(session)
            return False
        svc = settings.SERVICES[choice]
        console.print(Text(f" {TICK} Service: {svc.label}", style=OK))

    # the model last used with this service, so switching back is one Enter
    remembered = current.remembered.get(svc.id) or (current.model if svc.id == active else "")
    new_key = None
    if svc.id == "ollama":
        model = _pick_ollama_model(session, remembered)
    else:
        new_key = _ensure_key(session, svc, current.keys_saved.get(svc.id, False))
        if new_key is None:
            return False
        model = _pick_model(session, svc, remembered)
    if not model:
        return False

    try:
        saved = settings.save(session.ws, svc.id, model, api_key=new_key or None)
    except ServiceError as err:
        _service_error(session, err)
        return False
    session.refresh()
    _ok(session, f"Now using {saved.provider_label} · {saved.model}")
    console.print(Text("   ", style=MUTED), session.privacy_text(saved.provider), sep="")
    console.print()
    return True


def _ensure_key(session, svc, key_saved: bool) -> str | None:
    """'' when a saved key will be used, a newly entered and checked key, or
    None when the person stopped."""
    if key_saved:
        return ""
    from prompt_toolkit import prompt

    console = session.console
    console.print(Text(f"   Get a key at {svc.key_help}", style=MUTED))
    try:
        key = prompt(f" Paste your {svc.label} key (hidden): ", is_password=True).strip()
    except (EOFError, KeyboardInterrupt):
        key = ""
    if not key:
        _nothing_changed(session)
        return None
    ok, detail = _checking(session, f"Checking the key with {svc.label}", lambda: settings.check_key(svc.id, key))
    if ok:
        _ok(session, f"{svc.label} accepted the key")
        return key
    _fail(session, detail)
    if select("Save it anyway?", [("No, let me try again", ""), ("Yes, save it", "")]) == 1:
        return key
    console.print(Text(" Nothing changed. Run /models to try again.", style=MUTED))
    return None


def _openrouter_options(session) -> list[tuple[str, str]] | None:
    """Narrows OpenRouter's few hundred image models down to a short list."""
    try:
        catalog = _checking(session, "Fetching models from OpenRouter", model_service.openrouter_catalog)
    except ServiceError as err:
        _service_error(session, err)
        return None
    makers = catalog.makers()
    pick = select("Which OpenRouter models?", [
        ("Free", f"{len(catalog.free)} models, shared servers (may log your slides)"),
        ("Cheapest paid", "the ten lowest prices"),
        ("Browse paid by maker", f"{len(makers)} makers, e.g. OpenAI, Google, DeepSeek"),
    ])
    if pick is None:
        _nothing_changed(session)
        return None
    if pick == 0:
        chosen = catalog.free
    elif pick == 1:
        chosen = catalog.cheapest()
    else:
        names = list(makers)
        maker = select("Which maker?", [(m, f"{len(makers[m])} models") for m in names])
        if maker is None:
            _nothing_changed(session)
            return None
        chosen = makers[names[maker]]
    if pick != 0:
        session.console.print(Text("   Prices are per million input tokens. A picture is roughly a thousand, so most cost a fraction of a cent.", style=MUTED))
    return [(m.id, m.note) for m in chosen]


def _pick_model(session, svc, remembered: str) -> str | None:
    if svc.id == "openrouter":
        options = _openrouter_options(session)
        if options is None:
            return None
    else:
        options = [(m.id, m.note) for m in model_service.CURATED[svc.id]] + [("Other...", "type a model name")]
    if not options:
        _fail(session, "No image-capable models found right now.")
        return None
    start = next((i for i, (mid, _) in enumerate(options) if mid == remembered), 0)
    options = [(mid, "last used" if mid == remembered else note) for mid, note in options]
    pick = select(f"Which {svc.label} model?", options, start)
    if pick is None:
        _nothing_changed(session)
        return None
    chosen = options[pick][0]
    if chosen != "Other...":
        return chosen
    from prompt_toolkit import prompt

    try:
        return prompt(" Model name: ").strip() or None
    except (EOFError, KeyboardInterrupt):
        return None


def _pick_ollama_model(session, remembered: str) -> str | None:
    console = session.console
    while True:
        try:
            installed = _checking(session, "Looking for Ollama", lambda: model_service.ollama_vision(session.ws))
            break
        except ServiceError as err:
            _service_error(session, err)
            if select("What next?", [("Try again", "after starting Ollama"), ("Stop", "")]) != 0:
                console.print(Text(" Nothing changed. Run /models when Ollama is ready.", style=MUTED))
                return None
    _ok(session, "Ollama is running")

    names = [m.id for m in installed]
    suggested = doctor.DEFAULT_OLLAMA_MODEL
    options = [(n, "last used" if n == remembered else "installed") for n in names]
    if suggested not in names:
        options.append((f"Download {suggested}", "about 3 GB, a one-time download"))
    start = next((i for i, n in enumerate(names) if n == remembered), 0)
    pick = select("Which model should read your images?", options, start)
    if pick is None:
        _nothing_changed(session)
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
    from cappv1.tui.runview import RunView

    console = session.console
    resume, force = "--resume" in args, "--force" in args
    try:
        plan = _checking(session, "Checking everything is ready", lambda: session.runs.prepare(resume, force))
    except ServiceError as err:
        if err.code == "nothing_to_do":
            console.print(Text(f"\n {TICK} {err.message}", style=OK))
            console.print(Text(" Their finished copies are in output/ (type /open). Add new files, or edit a deck and drop it in again.\n", style=MUTED))
        elif err.code == "no_files":
            console.print(Text("\n Nothing to process yet. Drag a .pptx or .docx into this window first.\n", style=MUTED))
        else:
            _service_error(session, err)
        return

    if force:
        console.print(Text("\n --force redoes every file from scratch and replaces alt text that authors wrote themselves.", style=WARN))
        if select("Continue?", [("No, keep what's there", ""), ("Yes, redo everything", "author text is replaced")]) != 1:
            console.print(Text(" Nothing changed.\n", style=MUTED))
            return

    console.print()
    began = time.monotonic()
    view = RunView(console, plan.config)
    with view:  # subscribe before launching so no early event is missed
        session.runs.launch(plan)
        try:
            while session.runs.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            session.runs.cancel()
            session.runs.wait()
    status = session.runs.status()

    if status.state == "cancelled":
        console.print(Text("\n Stopped. Finished slides are saved; /run continues from there.\n", style=WARN))
        return
    if status.state == "failed":
        _fail(session, f"The run stopped: {status.error}")
        return

    took = int(time.monotonic() - began)
    t = view.totals
    problems = bool(status.failed_files or view.files_bad)
    body = Text()
    body.append(f"{view.files_ok} of {len(plan.pending)} file(s) finished", style=f"bold {WARN if problems else OK}")
    body.append(f"   in {took // 60}m {took % 60:02d}s\n", style=MUTED)
    parts = [f"{t['captioned']} described"]
    if t["enhanced"]:
        parts.append(f"{t['enhanced']} improved")
    if t["kept"]:
        parts.append(f"{t['kept']} kept as written")
    parts += [f"{t['decorative']} decorative", f"{t['cached']} reused", f"{t['failed']} failed"]
    body.append(" · ".join(parts))
    if problems:
        body.append("\nSome items need a retry. Run /run again; finished work isn't redone.", style=WARN)
    else:
        body.append("\nType /open to see the finished files.", style=MUTED)
    console.print(Panel(body, border_style=WARN if problems else OK, padding=(0, 2)))
    console.print()


# ---------------------------------------------------------------- /open
def cmd_open(session, args: str) -> None:
    out = session.ws.output_dir
    out.mkdir(exist_ok=True)
    opener = "open" if platform.system() == "Darwin" else "xdg-open"
    if shutil.which(opener):
        subprocess.run([opener, str(out)])
        _ok(session, "Opened the output folder")
    else:
        session.console.print(Text(f" Your finished files are in {out}", style=MUTED))


# ---------------------------------------------------------------- /clean
def cmd_clean(session, args: str) -> None:
    counts = files.clean(session.ws, dry_run=True)
    session.console.print(Text(f"\n This permanently deletes {counts['input']} input, {counts['output']} output file(s) and saved progress.", style=WARN))
    if select("Delete them?", [("No, keep everything", ""), ("Yes, delete", "no undo")]) != 1:
        session.console.print(Text(" Nothing deleted.", style=MUTED))
        return
    files.clean(session.ws)
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
        Command("init", "Set up cappv1, or check what it's set up with", cmd_init, ("setup",)),
        Command("models", "Pick a different AI service or model", cmd_models, ("provider",)),
        Command("doctor", "Check that everything is working", cmd_doctor),
        Command("audit", "Report low contrast and reading-order problems (changes nothing)", cmd_audit),
        Command("web", "Open cappv1 in your browser (/web stop turns it off)", cmd_web),
        Command("status", "Show the current settings", cmd_status),
        Command("history", "List the finished copies kept from each run", cmd_history),
        Command("remove", "Take a file off the list, or delete a finished copy or run", cmd_remove, ("rm", "delete")),
        Command("open", "Open the output folder", cmd_open),
        Command("clean", "Delete input, output and saved progress", cmd_clean),
        Command("clear", "Clear the screen", cmd_clear),
        Command("help", "Show this list", cmd_help, ("?",)),
        Command("exit", "Leave cappv1", cmd_exit, ("quit",)),
    ]
