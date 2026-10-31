"""Interactive free-model picker for the PPTX alt-text automation.

Lists vision-capable free models currently
available on OpenRouter, lets you pick one, and writes it into .env as
MODEL=... - the fix when a paid model 402s for lack of credits. With
PROVIDER=ollama it lists the vision models installed on this computer instead.
"""
import json
import sys
import urllib.error
import urllib.request

from cappv1.doctor import ROOT, ollama_base_url, ollama_installed_models, pick_provider, read_env_file

ENV_PATH = ROOT / ".env"

_USE_COLOR = sys.stdout.isatty()
_RESET = "\033[0m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_DIM = "\033[2m" if _USE_COLOR else ""
_RED = "\033[31m" if _USE_COLOR else ""
_GREEN = "\033[32m" if _USE_COLOR else ""
_CYAN = "\033[36m" if _USE_COLOR else ""


def read_current_model() -> str | None:
    if not ENV_PATH.exists():
        return None
    for raw_line in ENV_PATH.read_text().splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("MODEL="):
            return stripped.split("=", 1)[1].strip() or None
    return None


def write_model(model_id: str) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("MODEL="):
            lines[i] = f"MODEL={model_id}"
            found = True
            break
    if not found:
        lines.append(f"MODEL={model_id}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


def fetch_openrouter_vision_models() -> list[dict]:
    """Every image-capable OpenRouter model as {id, name, free, price}, where
    price is US dollars per million input tokens. Routers, aliases, batch
    variants, models that don't answer in text, and variable pricing are left out."""
    req = urllib.request.Request("https://openrouter.ai/api/v1/models")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())["data"]

    found = []
    for m in data:
        model_id = m.get("id", "")
        arch = m.get("architecture", {})
        if "image" not in arch.get("input_modalities", []) or "text" not in arch.get("output_modalities", ["text"]):
            continue
        if model_id.startswith(("~", "openrouter/")) or model_id.endswith(":batch"):
            continue
        try:
            price = float(m.get("pricing", {}).get("prompt", "")) * 1_000_000
        except ValueError:
            continue
        free = model_id.endswith(":free")
        if price < 0 or (price == 0 and not free):
            continue
        found.append({"id": model_id, "name": m.get("name", model_id), "free": free, "price": price})
    return found


def fetch_free_vision_models() -> list[tuple[str, str]]:
    return sorted((m["id"], m["name"]) for m in fetch_openrouter_vision_models() if m["free"])


def fetch_ollama_vision_models(base_url: str) -> list[tuple[str, str]]:
    models = []
    for name in ollama_installed_models(base_url):
        req = urllib.request.Request(
            f"{base_url}/api/show", data=json.dumps({"model": name}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if "vision" in json.loads(resp.read()).get("capabilities", []):
                models.append((name, "installed"))
    return sorted(models)


def main() -> int:
    current = read_current_model()
    env = read_env_file()
    use_ollama = pick_provider(env) == "ollama"
    heading = "vision-capable models installed in Ollama" if use_ollama else "free vision-capable models on OpenRouter"
    print(f"{_BOLD}cappv1 /models{_RESET} - {heading}\n")
    if current:
        print(f"  Current: {_CYAN}{current}{_RESET}\n")

    source = "Ollama" if use_ollama else "OpenRouter"
    try:
        models = fetch_ollama_vision_models(ollama_base_url(env)) if use_ollama else fetch_free_vision_models()
    except Exception as exc:
        print(f"{_RED}Couldn't reach {source} to list models ({exc.__class__.__name__}).{_RESET}")
        if use_ollama:
            print("Start the Ollama app (or run: ollama serve), then try again.")
        return 1

    if not models:
        if use_ollama:
            print(f"{_RED}No vision-capable models installed yet.{_RESET} Try: ollama pull gemma3:4b")
        else:
            print(f"{_RED}No free vision-capable models found right now.{_RESET}")
        return 1

    for i, (model_id, name) in enumerate(models, start=1):
        marker = f" {_GREEN}(current){_RESET}" if model_id == current else ""
        print(f"  {_BOLD}{i:>2}{_RESET}  {model_id}{_DIM} - {name}{_RESET}{marker}")

    print()
    try:
        choice = input(f"Pick a number (1-{len(models)}), or Enter to keep current: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nNo change made.")
        return 0

    if not choice:
        print("No change made.")
        return 0

    if not choice.isdigit() or not (1 <= int(choice) <= len(models)):
        print(f"{_RED}Not a valid choice.{_RESET} No change made.")
        return 1

    model_id, name = models[int(choice) - 1]
    write_model(model_id)
    print(f"\n{_BOLD}{_GREEN}✓{_RESET} Switched to {_CYAN}{model_id}{_RESET} ({name}) - saved to .env")
    print("Open cappv1 and type /run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
