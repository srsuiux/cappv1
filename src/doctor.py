"""Environment/setup diagnostics for the PPTX alt-text automation.

Deliberately stdlib-only (no project dependencies) so it can run with
plain `python3` even before the .venv has been created - it's meant to
be the first thing you reach for when something looks broken.
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
CHECK, CROSS, SKIP = "✓", "✗", "-"

_USE_COLOR = sys.stdout.isatty()
_RESET = "\033[0m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_DIM = "\033[2m" if _USE_COLOR else ""
_RED = "\033[31m" if _USE_COLOR else ""
_GREEN = "\033[32m" if _USE_COLOR else ""


# provider -> (API key env var, display name)
PROVIDERS = {
    "openrouter": ("OPENROUTER_API_KEY", "OpenRouter"),
    "openai": ("OPENAI_API_KEY", "OpenAI"),
    "anthropic": ("ANTHROPIC_API_KEY", "Anthropic"),
    "ollama": ("", "Ollama (on this computer)"),
}
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "gemma3:4b"  # mirrors src.config.PROVIDERS


def read_env_file() -> dict[str, str]:
    env_path = ROOT / ".env"
    values = {}
    if env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            stripped = raw_line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                name, value = stripped.split("=", 1)
                values[name.strip()] = value.strip()
    return values


def pick_provider(env: dict[str, str]) -> str:
    """Mirrors src.config.resolve_provider (this file stays stdlib-only)."""
    chosen = env.get("PROVIDER", "").lower()
    if chosen in PROVIDERS:
        return chosen
    for name, (key_var, _) in PROVIDERS.items():
        if key_var and env.get(key_var):
            return name
    return "openrouter"


def check_venv_deps() -> tuple[bool | None, str]:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return None, "will be created automatically the first time you run cappv1 start"
    try:
        subprocess.run(
            [str(venv_python), "-c", "import pptx, httpx, PIL, imagehash, dotenv, rich, prompt_toolkit"],
            check=True, capture_output=True, timeout=15,
        )
        return True, "installed"
    except Exception:
        return False, "venv exists but dependencies are incomplete - try: rm -rf .venv && cappv1 start"


def check_api_key_live(provider: str, key: str) -> tuple[bool, str]:
    name = PROVIDERS[provider][1]
    if provider == "openrouter":
        url, headers = "https://openrouter.ai/api/v1/auth/key", {"Authorization": f"Bearer {key}"}
    elif provider == "openai":
        url, headers = "https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"}
    else:
        url = "https://api.anthropic.com/v1/models"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                return True, f"verified with {name}"
            return False, f"unexpected response ({resp.status})"
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return False, f"{name} rejected this key (401 unauthorized)"
        return False, f"{name} returned an error ({exc.code})"
    except Exception as exc:
        return False, f"couldn't reach {name} ({exc.__class__.__name__})"


def ollama_base_url(env: dict[str, str]) -> str:
    return env.get("OLLAMA_BASE_URL", "").rstrip("/") or DEFAULT_OLLAMA_URL


def ollama_installed_models(base_url: str) -> list[str]:
    """Names of the models pulled into Ollama. Raises if it isn't reachable."""
    with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
        return [m["name"] for m in json.loads(resp.read()).get("models", [])]


def model_is_installed(model: str, installed: list[str]) -> bool:
    # "gemma3" means "gemma3:latest" to Ollama
    wanted = model if ":" in model else f"{model}:latest"
    return wanted in installed


def check_ollama(env: dict[str, str]) -> bool:
    base_url = ollama_base_url(env)
    ok = True
    is_local = (urlparse(base_url).hostname or "") in {"localhost", "127.0.0.1", "::1"}
    if is_local:
        report(True, "Ollama address is this computer", "your slides never leave it")
    else:
        allowed = env.get("OLLAMA_ALLOW_REMOTE") == "1"
        ok &= report(allowed, "Ollama address is this computer",
                     f"{base_url} is another machine; set OLLAMA_BASE_URL=http://localhost:11434, "
                     "or OLLAMA_ALLOW_REMOTE=1 if that is intended")
    try:
        installed = ollama_installed_models(base_url)
    except Exception:
        return report(False, "Ollama is running", "start the Ollama app (or run: ollama serve), "
                      "or install it from ollama.com/download") and ok
    report(True, "Ollama is running")
    model = env.get("MODEL") or DEFAULT_OLLAMA_MODEL
    ok &= report(model_is_installed(model, installed), f"model '{model}' is downloaded",
                 "" if model_is_installed(model, installed) else f"run: ollama pull {model}")
    return ok


def check_dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return True
    except Exception:
        return False


def report(ok: bool, label: str, detail: str = "") -> bool:
    color = _GREEN if ok else _RED
    mark = CHECK if ok else CROSS
    suffix = f"{_DIM} - {detail}{_RESET}" if detail else ""
    print(f"  [{color}{mark}{_RESET}] {label}{suffix}")
    return ok


def skip(label: str, detail: str) -> None:
    print(f"  [{_DIM}{SKIP}{_RESET}] {_DIM}{label} - {detail}{_RESET}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="skip the live API key check")
    args = parser.parse_args()

    print(f"{_BOLD}cappv1 doctor{_RESET} - environment check\n")
    all_ok = True

    env_exists = (ROOT / ".env").exists()
    all_ok &= report(env_exists, ".env file found")

    env = read_env_file() if env_exists else {}
    provider = pick_provider(env)
    key_var, provider_name = PROVIDERS[provider]
    key = env.get(key_var) or None
    print(f"  {_DIM}provider: {provider_name}{_RESET}")
    if provider == "ollama":
        all_ok &= check_ollama(env)
    else:
        all_ok &= report(bool(key), f"{key_var} is set")
        if not key:
            skip("API key check", "no key to test")
        elif args.quick:
            skip("API key live check", "skipped (--quick)")
        else:
            ok, detail = check_api_key_live(provider, key)
            all_ok &= report(ok, "API key is valid", detail)

    deps_ok, deps_detail = check_venv_deps()
    if deps_ok is None:
        skip("Python environment ready", deps_detail)
    else:
        all_ok &= report(deps_ok, "Python environment ready", deps_detail)

    input_dir, output_dir = ROOT / "input", ROOT / "output"
    all_ok &= report(check_dir_writable(input_dir), "input/ folder is ready")
    all_ok &= report(check_dir_writable(output_dir), "output/ folder is ready")

    if not args.quick:
        pptx_count = len(list(input_dir.glob("*.pptx")))
        print(f"\n  {_BOLD}{pptx_count}{_RESET} file(s) waiting in input/")

    print()
    if all_ok:
        print(f"{_BOLD}{_GREEN}All checks passed{_RESET} - ready to run. Type: cappv1 start")
    else:
        print(f"{_BOLD}{_RED}Some checks failed.{_RESET} Fix the [{CROSS}] items above, then run: cappv1 doctor")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
