"""Which AI service and model cappv1 uses."""

from dataclasses import asdict, dataclass

from cappv1 import doctor
from cappv1.config import load_config
from cappv1.services import envfile
from cappv1.services.errors import ServiceError
from cappv1.services.workspace import Workspace


@dataclass(frozen=True)
class Service:
    id: str
    label: str
    private: bool  # True when slides never leave this computer
    key_var: str
    key_help: str
    handling: str = ""  # what happens to slides sent through this service, in plain words
    policy_url: str = ""  # the service's own privacy policy

    @property
    def note(self) -> str:
        return "private: runs on this computer" if self.private else f"sends slides to {self.label}"


SERVICES = (
    Service(
        "ollama",
        "Ollama",
        True,
        "",
        "",
        "Runs on this computer. Pictures and slide text never leave it. Needs Ollama installed and a vision model downloaded.",
    ),
    Service(
        "openrouter",
        "OpenRouter",
        False,
        "OPENROUTER_API_KEY",
        "openrouter.ai -> account settings -> API Keys (starts with sk-or-v1-)",
        "Pictures and slide text go to OpenRouter, which passes them to the company that runs the model you pick. "
        "Free models may log requests, so avoid them for private slides.",
        "https://openrouter.ai/privacy",
    ),
    Service(
        "openai",
        "OpenAI",
        False,
        "OPENAI_API_KEY",
        "platform.openai.com/api-keys",
        "Pictures and slide text go to OpenAI's API.",
        "https://openai.com/policies/privacy-policy",
    ),
    Service(
        "anthropic",
        "Anthropic",
        False,
        "ANTHROPIC_API_KEY",
        "console.anthropic.com -> API Keys",
        "Pictures and slide text go to Anthropic's API.",
        "https://www.anthropic.com/legal/privacy",
    ),
)


def service(provider: str) -> Service:
    for s in SERVICES:
        if s.id == provider:
            return s
    raise ServiceError("bad_service", f"Unknown AI service '{provider}'.", "Choose one of: " + ", ".join(s.id for s in SERVICES))


@dataclass
class Settings:
    configured: bool
    provider: str | None
    provider_label: str
    model: str
    private: bool
    concurrency: int
    keys_saved: dict[str, bool]  # service -> a key is saved (never the key itself)
    remembered: dict[str, str]  # service -> the model last used with it
    error: str
    workspace: str

    def as_dict(self) -> dict:
        return asdict(self)


def read(ws: Workspace) -> Settings:
    env = envfile.read(ws)
    provider = doctor.pick_provider(env) if ws.env_path.exists() else None
    keys = {s.id: bool(env.get(s.key_var)) for s in SERVICES if s.key_var}
    remembered = {s.id: env.get(f"MODEL_{s.id.upper()}", "") for s in SERVICES}
    try:
        config, error = load_config(ws.root), ""
    except Exception as exc:
        config, error = None, str(exc)
    return Settings(
        configured=config is not None,
        provider=provider,
        provider_label=service(provider).label if provider else "",
        model=config.model if config else "",
        private=bool(provider and service(provider).private),
        concurrency=config.concurrency if config else 0,
        keys_saved=keys,
        remembered=remembered,
        error=error,
        workspace=str(ws.root),
    )


def check_key(provider: str, key: str) -> tuple[bool, str]:
    """Asks the service whether it accepts this key (needs the internet)."""
    if not service(provider).key_var:
        return True, "no key needed"
    return doctor.check_api_key_live(provider, key)


def save(ws: Workspace, provider: str, model: str, api_key: str | None = None) -> Settings:
    """Makes `provider` + `model` the active choice. FALLBACK_MODEL is cleared so
    a model from the old service is never sent to the new one."""
    svc = service(provider)
    model = model.strip()
    if not model:
        raise ServiceError("no_model", "Pick a model first.")
    if svc.key_var and not (api_key or envfile.read(ws).get(svc.key_var)):
        raise ServiceError("no_key", f"{svc.label} needs an API key.", f"Get one at {svc.key_help}")
    values = {"PROVIDER": provider, "MODEL": model, "FALLBACK_MODEL": "", f"MODEL_{provider.upper()}": model}
    if api_key:
        values[svc.key_var] = api_key.strip()
    envfile.set_values(ws, values)
    return read(ws)


def remove_key(ws: Workspace, provider: str) -> Settings:
    """Forgets a saved key. The service stays chosen but can't be used until a new key is added."""
    svc = service(provider)
    if not svc.key_var:
        raise ServiceError("bad_request", f"{svc.label} doesn't use a key.")
    envfile.set_values(ws, {svc.key_var: ""})
    return read(ws)
