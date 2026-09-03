# Security TODO

From the pre-release security review (2026-09-03). Not applied yet — deferred until after feature testing. Findings and patches are preserved here so nothing needs to be re-derived later.

## Priority 1 — do before processing anything confidential

- [ ] **README warning on data privacy** (`README.md`) — default model `minimax/minimax-m3:free` is free-tier; OpenRouter's privacy policy allows model providers to train on/log free-endpoint inputs, and free requests route through a rotating set of third-party inference providers with undisclosed individual retention policies. Nothing currently warns the operator.
  ```diff
  +## ⚠️ Data privacy
  +
  +The default model (`minimax/minimax-m3:free`) is a **free-tier** OpenRouter
  +model. OpenRouter's privacy policy states some model providers may use your
  +inputs/outputs for training; free-endpoint requests route through a rotating
  +set of third-party inference providers whose individual retention policies
  +aren't disclosed per-request. **Do not run confidential decks through the
  +default free model.** Either enable OpenRouter's Zero Data Retention (`zdr`)
  +/ data-collection-deny settings for your account, or switch to a paid model
  +you trust (`cappv1 models`, or set `MODEL=` in `.env` directly) before
  +processing anything sensitive.
  ```

## Priority 2 — cheap, closes real landmines

- [ ] **`Config.__repr__` leaks the raw API key** (`src/config.py`) — nothing calls it today, but one debug log line would leak it.
  ```diff
  -from dataclasses import dataclass
  +from dataclasses import dataclass, field
   ...
   class Config:
  -    api_key: str
  +    api_key: str = field(repr=False)
  ```

- [ ] **Control chars in a caption crash the whole file** (`src/llm_client.py`) — contradicts the tool's own "one bad image never fails the deck" guarantee.
  ```diff
   import asyncio
   import base64
   import logging
  +import re
   ...
  +_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
   ...
           if resp.status_code == 200:
               data = resp.json()
  -            text = data["choices"][0]["message"]["content"].strip()
  +            text = _CONTROL_CHARS_RE.sub("", data["choices"][0]["message"]["content"].strip())
               return "" if text.upper() == "DECORATIVE" else text
  ```

## Priority 3 — untrusted-input hardening

- [ ] **Zip bomb DoS** (`src/pptx_reader.py`) — `python-pptx` decompresses every archive member into memory with no size check.
  ```diff
   from dataclasses import dataclass
   from pathlib import Path
  +import zipfile
   
   from pptx import Presentation
   ...
  +MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB - generous for real decks
  +
  +
  +def _check_zip_safety(path: Path) -> None:
  +    try:
  +        with zipfile.ZipFile(path) as zf:
  +            total = sum(zi.file_size for zi in zf.infolist())
  +    except zipfile.BadZipFile as exc:
  +        raise ValueError(f"{path.name} is not a valid .pptx (corrupt zip)") from exc
  +    if total > MAX_UNCOMPRESSED_BYTES:
  +        raise ValueError(
  +            f"{path.name} would decompress to {total / 1_048_576:.0f} MB, over the "
  +            f"{MAX_UNCOMPRESSED_BYTES // 1_048_576} MB safety limit - refusing to open"
  +        )
  +
  +
   def open_presentation(path: Path) -> Presentation:
  +    _check_zip_safety(path)
       return Presentation(str(path))
  ```

- [ ] **Pillow 10.4.0 has an unpatched CVE** (CVE-2026-42311, memory corruption via malicious image content, fixed in ≥12.2.0) (`requirements.txt`)
  ```diff
  -Pillow==10.4.0
  +Pillow==12.3.0
  ```
  Major-version jump — test after upgrading, not just a version bump.

## Priority 4 — lower urgency, fine as fast-follows

- [ ] **State writes not atomic + corrupt JSON crashes the whole batch** (`src/state.py`) — one corrupted `state.json` takes down every file's processing, not just that one.
  ```diff
   import json
  +import logging
  +import os
  +import tempfile
   from dataclasses import asdict, dataclass, field
   from pathlib import Path
  +
  +logger = logging.getLogger("pptx_alt_text")
   ...
   def load_state(state_dir: Path, filename: str) -> FileState:
       path = _state_path(state_dir, filename)
       if not path.exists():
           return FileState(filename=filename)
  -    data = json.loads(path.read_text())
  -    return FileState(**data)
  +    try:
  +        return FileState(**json.loads(path.read_text()))
  +    except (json.JSONDecodeError, TypeError) as exc:
  +        logger.warning("corrupt state file for %s (%s) - starting fresh", filename, exc)
  +        return FileState(filename=filename)
   
   
   def save_state(state_dir: Path, state: FileState) -> None:
       state_dir.mkdir(parents=True, exist_ok=True)
       path = _state_path(state_dir, state.filename)
  -    path.write_text(json.dumps(asdict(state), indent=2))
  +    fd, tmp_path = tempfile.mkstemp(dir=state_dir, prefix=".tmp-", suffix=".json")
  +    try:
  +        with os.fdopen(fd, "w") as f:
  +            f.write(json.dumps(asdict(state), indent=2))
  +        os.replace(tmp_path, path)
  +    except Exception:
  +        os.unlink(tmp_path)
  +        raise
  ```

- [ ] **No file permission hardening** — `.env` (644), `.state/*.json` (plaintext captions), `logs/` all inherit the OS umask default; readable by any other local user on a shared machine.
  ```diff
  --- src/models.py
  +import os
   ...
       ENV_PATH.write_text("\n".join(lines) + "\n")
  +    os.chmod(ENV_PATH, 0o600)
  ```
  Plus once, now: `chmod 600 .env`

- [ ] **No lockfile** — two concurrent `cappv1 start` runs can race on the same file's state/output.
  ```diff
  --- bin/cappv1, inside start()
  +    lock_dir="$PROJECT_DIR/.state/.lock"
  +    mkdir -p "$PROJECT_DIR/.state"
  +    if ! mkdir "$lock_dir" 2>/dev/null; then
  +        echo "${RED}Another cappv1 run is already in progress.${RESET}"
  +        exit 1
  +    fi
  +    trap 'rmdir "$lock_dir" 2>/dev/null' EXIT
  ```

- [x] **Hardcoded personal path published on GitHub** (`bin/cappv1`, `README.md`) — leaks OS username, breaks the script for anyone else who clones the repo. **Fixed**: `bin/cappv1` now resolves its own real location by following the symlink back (the diff below is what was applied), and `README.md`'s setup steps no longer hardcode a path. Verified by simulating a fresh clone at a completely different path (`/tmp/cappv1-elsewhere`, different symlink name) and confirming it correctly found *that* location's `.env`, not the original.
  ```diff
  --- bin/cappv1
  -PROJECT_DIR="/Users/ssharma33/Desktop/cappv1"
  +SOURCE="${BASH_SOURCE[0]}"
  +while [ -L "$SOURCE" ]; do
  +    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  +    SOURCE="$(readlink "$SOURCE")"
  +    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
  +done
  +PROJECT_DIR="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
  ```

- [ ] **`--file` has no path/extension validation** (`src/pipeline.py`) — operator-input only, output side already safe.
  ```diff
       if only_file:
           path = config.input_dir / only_file
  -        if not path.exists():
  +        if not only_file.endswith(".pptx") or not path.resolve().is_relative_to(config.input_dir.resolve()):
  +            raise ValueError(f"--file must be a .pptx file inside {config.input_dir}")
  +        if not path.exists():
               raise FileNotFoundError(f"{path} not found")
  ```

- [ ] **No hash-pinning in `requirements.txt`** — exact versions only, no `--hash`. Generate with: `pip install pip-tools && pip-compile --generate-hashes requirements.in`
