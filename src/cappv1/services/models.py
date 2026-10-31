"""The models a service offers. Only models that can read images are listed."""

from dataclasses import dataclass

from cappv1 import doctor
from cappv1 import models as catalog
from cappv1.services import envfile
from cappv1.services.errors import ServiceError
from cappv1.services.workspace import Workspace


@dataclass(frozen=True)
class ModelOption:
    id: str
    note: str = ""
    price: float | None = None  # US dollars per million input tokens, when known


# Short lists of vision-capable models; an "other" entry covers anything newer.
CURATED = {
    "openai": (
        ModelOption("gpt-4o-mini", "default, lowest cost"),
        ModelOption("gpt-4o", "higher quality"),
        ModelOption("gpt-4.1-mini", "newer, low cost"),
    ),
    "anthropic": (
        ModelOption("claude-haiku-5-5", "default, lowest cost"),
        ModelOption("claude-sonnet-5-5", "higher quality"),
        ModelOption("claude-opus-5-5", "best quality, highest cost"),
    ),
}


def price_text(per_million: float | None) -> str:
    if per_million is None:
        return ""
    if per_million == 0:
        return "free"
    return f"${per_million:.2f} per 1M tokens" if per_million >= 0.01 else "under $0.01 per 1M tokens"


def _base_url(ws: Workspace) -> str:
    return doctor.ollama_base_url(envfile.read(ws))


def ollama_installed(ws: Workspace) -> list[str]:
    try:
        return doctor.ollama_installed_models(_base_url(ws))
    except Exception:
        raise ServiceError(
            "ollama_down", "Ollama isn't running.", "Open the Ollama app (llama icon). Not installed? Get it at ollama.com/download"
        ) from None


def ollama_vision(ws: Workspace) -> list[ModelOption]:
    ollama_installed(ws)  # raises the friendly error first
    try:
        return [ModelOption(name, "installed") for name, _ in catalog.fetch_ollama_vision_models(_base_url(ws))]
    except Exception:
        raise ServiceError("ollama_down", "Couldn't read Ollama's model list.", "Make sure Ollama is running.") from None


@dataclass(frozen=True)
class OpenRouterCatalog:
    free: list[ModelOption]
    paid: list[ModelOption]  # cheapest first

    def cheapest(self, n: int = 10) -> list[ModelOption]:
        return self.paid[:n]

    def makers(self) -> dict[str, list[ModelOption]]:
        out: dict[str, list[ModelOption]] = {}
        for m in self.paid:
            out.setdefault(m.id.split("/")[0], []).append(m)
        return dict(sorted(out.items()))


def openrouter_catalog() -> OpenRouterCatalog:
    try:
        found = catalog.fetch_openrouter_vision_models()
    except Exception as exc:
        raise ServiceError("network", f"Couldn't reach OpenRouter ({exc.__class__.__name__}).", "Check your internet connection.") from None
    as_option = lambda m: ModelOption(m["id"], price_text(m["price"]), m["price"])  # noqa: E731
    free = sorted((m for m in found if m["free"]), key=lambda m: m["id"])
    paid = sorted((m for m in found if not m["free"]), key=lambda m: (m["price"], m["id"]))
    return OpenRouterCatalog([as_option(m) for m in free], [as_option(m) for m in paid])
