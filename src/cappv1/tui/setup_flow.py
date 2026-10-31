"""The guided setup shared by /init and /models: pick a service, then a model for it.

This file only asks and draws; what cappv1 actually does lives in src/cappv1/services.
"""

import shutil
import subprocess

from rich.text import Text

from cappv1 import doctor
from cappv1.services import models as model_service
from cappv1.services import settings
from cappv1.services.errors import ServiceError
from cappv1.tui.common import checking, fail, nothing_changed, service_error, success
from cappv1.tui.menu import select
from cappv1.tui.theme import MUTED, OK, TICK


def configure(session, show_current_first: bool) -> bool:
    """True when a service and model are now saved (changed or kept)."""
    console = session.console
    console.print()
    current = settings.read(session.ws)
    active = current.provider

    # Already set up: show what is in use and don't walk through setup again.
    change_model_only = False
    if show_current_first and current.configured and active:
        label = f"{current.provider_label} · {current.model}"
        pick = select(
            f"Currently using {label}",
            [
                ("Keep this", "no changes"),
                ("Change the model", f"stay with {current.provider_label}"),
                ("Switch AI service", "choose a different service"),
            ],
        )
        if pick not in (1, 2):
            success(session, f"Keeping {label}")
            console.print(Text("   ", style=MUTED), session.privacy_text(active), sep="")
            console.print()
            return True
        change_model_only = pick == 1

    if change_model_only and active:
        svc = settings.service(active)
    else:
        rows = [
            (s.label + ("  (active)" if s.id == active else ""), s.note + (", key saved" if current.keys_saved.get(s.id) else ""))
            for s in settings.SERVICES
        ]
        start = next((i for i, s in enumerate(settings.SERVICES) if s.id == active), 0)
        choice = select("Which AI service?", rows, start)
        if choice is None:
            nothing_changed(session)
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
        service_error(session, err)
        return False
    session.refresh()
    success(session, f"Now using {saved.provider_label} · {saved.model}")
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
        nothing_changed(session)
        return None
    ok, detail = checking(session, f"Checking the key with {svc.label}", lambda: settings.check_key(svc.id, key))
    if ok:
        success(session, f"{svc.label} accepted the key")
        return key
    fail(session, detail)
    if select("Save it anyway?", [("No, let me try again", ""), ("Yes, save it", "")]) == 1:
        return key
    console.print(Text(" Nothing changed. Run /models to try again.", style=MUTED))
    return None


def _openrouter_options(session) -> list[tuple[str, str]] | None:
    """Narrows OpenRouter's few hundred image models down to a short list."""
    try:
        catalog = checking(session, "Fetching models from OpenRouter", model_service.openrouter_catalog)
    except ServiceError as err:
        service_error(session, err)
        return None
    makers = catalog.makers()
    pick = select(
        "Which OpenRouter models?",
        [
            ("Free", f"{len(catalog.free)} models, shared servers (may log your slides)"),
            ("Cheapest paid", "the ten lowest prices"),
            ("Browse paid by maker", f"{len(makers)} makers, e.g. OpenAI, Google, DeepSeek"),
        ],
    )
    if pick is None:
        nothing_changed(session)
        return None
    if pick == 0:
        chosen = catalog.free
    elif pick == 1:
        chosen = catalog.cheapest()
    else:
        names = list(makers)
        maker = select("Which maker?", [(m, f"{len(makers[m])} models") for m in names])
        if maker is None:
            nothing_changed(session)
            return None
        chosen = makers[names[maker]]
    if pick != 0:
        session.console.print(
            Text("   Prices are per million input tokens. A picture is roughly a thousand, so most cost a fraction of a cent.", style=MUTED)
        )
    return [(m.id, m.note) for m in chosen]


def _pick_model(session, svc, remembered: str) -> str | None:
    if svc.id == "openrouter":
        options = _openrouter_options(session)
        if options is None:
            return None
    else:
        options = [(m.id, m.note) for m in model_service.CURATED[svc.id]] + [("Other...", "type a model name")]
    if not options:
        fail(session, "No image-capable models found right now.")
        return None
    start = next((i for i, (mid, _) in enumerate(options) if mid == remembered), 0)
    options = [(mid, "last used" if mid == remembered else note) for mid, note in options]
    pick = select(f"Which {svc.label} model?", options, start)
    if pick is None:
        nothing_changed(session)
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
            installed = checking(session, "Looking for Ollama", lambda: model_service.ollama_vision(session.ws))
            break
        except ServiceError as err:
            service_error(session, err)
            if select("What next?", [("Try again", "after starting Ollama"), ("Stop", "")]) != 0:
                console.print(Text(" Nothing changed. Run /models when Ollama is ready.", style=MUTED))
                return None
    success(session, "Ollama is running")

    names = [m.id for m in installed]
    suggested = doctor.DEFAULT_OLLAMA_MODEL
    options = [(n, "last used" if n == remembered else "installed") for n in names]
    if suggested not in names:
        options.append((f"Download {suggested}", "about 3 GB, a one-time download"))
    start = next((i for i, n in enumerate(names) if n == remembered), 0)
    pick = select("Which model should read your images?", options, start)
    if pick is None:
        nothing_changed(session)
        return None
    label = options[pick][0]
    if not label.startswith("Download "):
        return label
    if not shutil.which("ollama"):
        fail(session, "Can't find the ollama command.", f"Open a new Terminal and run: ollama pull {suggested}")
        return None
    console.print(Text(f" Downloading {suggested}. Ollama shows its own progress below.\n", style=MUTED))
    if subprocess.run(["ollama", "pull", suggested]).returncode != 0:
        fail(session, "The download didn't finish.", f"Check your internet, then run /models again (or: ollama pull {suggested})")
        return None
    success(session, f"{suggested} is ready")
    return suggested
