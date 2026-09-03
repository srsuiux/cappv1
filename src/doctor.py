"""Environment/setup diagnostics for the PPTX alt-text automation.

Deliberately stdlib-only (no project dependencies) so it can run with
plain `python3` even before the .venv has been created - it's meant to
be the first thing you reach for when something looks broken.
"""
import argparse
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK, CROSS, SKIP = "✓", "✗", "-"


def read_env_key() -> str | None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text().splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("OPENROUTER_API_KEY="):
            return stripped.split("=", 1)[1].strip() or None
    return None


def check_venv_deps() -> tuple[bool | None, str]:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return None, "will be created automatically the first time you run cappv1"
    try:
        subprocess.run(
            [str(venv_python), "-c", "import pptx, httpx, PIL, imagehash, dotenv"],
            check=True, capture_output=True, timeout=15,
        )
        return True, "installed"
    except Exception:
        return False, "venv exists but dependencies are incomplete - try: rm -rf .venv && cappv1"


def check_api_key_live(key: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                return True, "verified with OpenRouter"
            return False, f"unexpected response ({resp.status})"
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return False, "OpenRouter rejected this key (401 unauthorized)"
        return False, f"OpenRouter returned an error ({exc.code})"
    except Exception as exc:
        return False, f"couldn't reach OpenRouter ({exc.__class__.__name__})"


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
    mark = CHECK if ok else CROSS
    suffix = f" - {detail}" if detail else ""
    print(f"  [{mark}] {label}{suffix}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="skip the live OpenRouter check")
    args = parser.parse_args()

    print("cappv1 doctor - environment check\n")
    all_ok = True

    env_exists = (ROOT / ".env").exists()
    all_ok &= report(env_exists, ".env file found")

    key = read_env_key() if env_exists else None
    all_ok &= report(bool(key), "OPENROUTER_API_KEY is set")

    if not key:
        print(f"  [{SKIP}] API key check skipped (no key to test)")
    elif args.quick:
        print(f"  [{SKIP}] API key live check skipped (--quick)")
    else:
        ok, detail = check_api_key_live(key)
        all_ok &= report(ok, "API key is valid", detail)

    deps_ok, deps_detail = check_venv_deps()
    if deps_ok is None:
        print(f"  [{SKIP}] Python environment ready - {deps_detail}")
    else:
        all_ok &= report(deps_ok, "Python environment ready", deps_detail)

    input_dir, output_dir = ROOT / "input", ROOT / "output"
    all_ok &= report(check_dir_writable(input_dir), "input/ folder is ready")
    all_ok &= report(check_dir_writable(output_dir), "output/ folder is ready")

    if not args.quick:
        pptx_count = len(list(input_dir.glob("*.pptx")))
        print(f"\n  {pptx_count} file(s) waiting in input/")

    print()
    if all_ok:
        print("All checks passed - ready to run. Type: cappv1")
    else:
        print("Some checks failed. Fix the [x] items above, then run: cappv1 doctor")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
