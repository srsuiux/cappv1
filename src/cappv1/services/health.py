"""Is cappv1 ready to run? The checks behind /doctor and the web Doctor page."""
from collections.abc import Callable
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from cappv1 import doctor
from cappv1.services import envfile
from cappv1.services.workspace import Workspace


@dataclass
class Check:
    label: str
    ok: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlannedCheck:
    """A check not yet run, so a screen can show a spinner for each one in turn."""

    label: str
    run: Callable[[], tuple[bool, str]]


def planned_checks(ws: Workspace, live: bool = True) -> list[PlannedCheck]:
    env = envfile.read(ws)
    provider = doctor.pick_provider(env)
    plan = [PlannedCheck("Settings file found", lambda: (ws.env_path.exists(), "" if ws.env_path.exists() else "Open /init to set up"))]

    if provider == "ollama":
        base = doctor.ollama_base_url(env)
        local = urlparse(base).hostname in {"localhost", "127.0.0.1", "::1"} or env.get("OLLAMA_ALLOW_REMOTE") == "1"
        installed: list[str] = []
        model = env.get("MODEL") or doctor.DEFAULT_OLLAMA_MODEL

        def ollama_up() -> tuple[bool, str]:
            try:
                installed[:] = doctor.ollama_installed_models(base)
            except Exception:
                return False, "Start the Ollama app, or install it from ollama.com/download"
            return True, ""

        def model_ready() -> tuple[bool, str]:
            have = doctor.model_is_installed(model, installed)
            return have, "" if have else f"Run: ollama pull {model}"

        plan += [
            PlannedCheck("Ollama address is this computer",
                         lambda: (local, "your slides never leave it" if local else f"{base} is another machine")),
            PlannedCheck("Ollama is running", ollama_up),
            PlannedCheck(f"Model {model} is downloaded", model_ready),
        ]
    else:
        key_var, name = doctor.PROVIDERS[provider]
        key = env.get(key_var)
        plan.append(PlannedCheck(f"{key_var} is set", lambda: (bool(key), "" if key else "Open /init to add it")))
        if key and live:
            plan.append(PlannedCheck(f"{name} accepts the key", lambda: doctor.check_api_key_live(provider, key)))

    def deps() -> tuple[bool, str]:
        return doctor.check_packages()

    plan += [
        PlannedCheck("Python packages installed", deps),
        PlannedCheck("input/ and output/ folders are ready",
                     lambda: (doctor.check_dir_writable(ws.input_dir) and doctor.check_dir_writable(ws.output_dir), "")),
    ]
    return plan


def run_all(ws: Workspace, live: bool = True) -> list[Check]:
    return [Check(p.label, *p.run()) for p in planned_checks(ws, live)]
