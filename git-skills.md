# git-skills: how an LLM works in this repository

Read this first, every session. It tells you how the project is laid out, which rules cannot be broken, and how to decide what to do without being told each time. `docs/scope.md` holds the one product rule; this file holds everything else. If the two ever disagree, `docs/scope.md` wins.

## 1. What this project is

cappv1 writes alt text into PowerPoint decks using vision models (OpenRouter, OpenAI, Anthropic, or local Ollama). Open source, MIT, Mac and Linux, Python 3.11+. Public repo: `srsuiux/cappv1`.

## 2. Hard rules (never break these, even if asked in passing)

1. **Visually inert output.** The tool writes alt text (`descr` on `cNvPr`) and, from a short named list in `docs/scope.md`, fixes that change nothing you can see. Never change fonts, sizes, layout, text or table styles. Colors are changed in one case only: Word text that fails the 4.5:1 contrast check is darkened (`src/cappv1/docx_structure.py`, owner-approved, always noted in the file's skip notes). Report every other problem; do not fix it.
2. **No secrets in the repo.** Never commit `.env`, keys, decks, or anything under `input/`, `output/`, `logs/`, `.state/`. Never print a key.
3. **Privacy is a feature.** If a change affects what is sent to an AI service or stored on disk, update in the same change: `src/cappv1/web/pages/privacy.html`, `src/cappv1/services/storage.py`, `src/cappv1/services/settings.py` (service notes). Tests tie the Privacy page to the code.
4. **No tracking.** No analytics, telemetry, cookies, update checks, or third-party requests.
5. **Not a data manager.** No database or file manager. The one history allowed (owner-approved, 2026-10): each run keeps its finished copies in `output/<date>_<time>/` until the person deletes them, from the web page or the terminal. Nothing else is recorded.
6. **Never move or reuse a tag.** Never rewrite pushed history.

## 3. Layers (each depends only on the one below)

```
src/cappv1/tui/  src/cappv1/web/        front ends: no logic, call services
src/cappv1/services/             settings, models, files, runs, health, storage, workspace, envfile
src/cappv1/ engine               pipeline.py, pptx_reader.py, llm_client.py, state.py, events.py, config.py,
                          image_filter.py, doctor.py, models.py, outputs.py, main.py
```

- Put logic in a service, not in a front end, so terminal and browser never disagree.
- The engine knows nothing about screens; it reports progress through the event bus (`src/cappv1/events.py`). The terminal and web server share one `RunManager`.
- Errors from services are `ServiceError(code, message, fix)`: plain words plus a next step.
- Identify PowerPoint shapes by XML tag (`shape._element.tag`), never `shape.shape_type` (see `docs/scope.md`).
- `set_alt_text()` is the single write path for alt text; `mark_table_header()` is the only other write, and only when visually inert.

### Web (`src/cappv1/web`)
- stdlib server, 127.0.0.1 only, token header, Host allowlist, strict CSP. No framework, no build step.
- Pages are fragments in `pages/*.html` with a first-line metadata comment, wrapped by `templates/app.html`. **No inline script or style**; nothing loaded from outside. Tests enforce this.
- Styles are tokens in `static/app.css` for light and dark. Every text pair must keep 4.5:1 contrast (tested). No one-sided border strokes. Targets at least 44px. Sentence case. No gradients or shadows.
- API under `/api/v1`, documented in `docs/API.md`; errors are `{"error": {"code","message","fix"}}`.

### Terminal (`src/cappv1/tui`)
Slash commands live inside the session. The shell exposes only `cappv1`, `--batch`, `--web`, `--version`, `--help`. Do not re-add shell-level `init/doctor/models/clean/start`.

## 4. Choosing what to do (decision procedure)

1. Read the request. If it is a question, answer it; do not change files.
2. Find the code that already does something similar and match its style, naming and comment density.
3. Classify the change:
   - **Engine behavior** → check `docs/scope.md` first; add a test in `tests/`.
   - **New capability** → service function plus test, then wire to front ends.
   - **Copy or docs** → keep claims true; grep for sentences the change makes false (README, About, front page, Privacy, brief).
   - **Release or push** → only on explicit request.
4. Prefer the smallest change that works. Do not add options, abstractions or files "for later".
5. If something is ambiguous and the answer changes what you build, ask one short question; otherwise pick the conventional default and say so.
6. Say plainly what you verified and what you did not (for example "not run through a real model", "not tested with a screen reader").

## 5. Git workflow

- `main` is always releasable. Work on `feature/<name>`, `fix/<name>` or `docs/<name>`; merge with `git merge --no-ff`; delete the branch.
- **Commit locally after every clean, meaningful change. Push only when the user asks.** Never force-push `main`.
- Commit message: short imperative subject, a few lines on why, one logical change per commit, then the attribution line the environment specifies.
- Versions `MAJOR.MINOR.PATCH`; releases are annotated tags `vX.Y.Z` on `main`.
- Release steps: merge, clean `git status`, bump `src/cappv1/version.py`, add a `CHANGELOG.md` section, commit `Release vX.Y.Z`, `git tag -a vX.Y.Z -m "cappv1 X.Y.Z"`, `git push origin main vX.Y.Z`, and the `Release` workflow creates the GitHub Release from the tag (`gh` is not installed here).
- CI: GitHub Actions (ruff, mypy, tests on Linux and macOS with Python 3.11, 3.12, 3.13, a wheel build, a link check). Check it after a push. `pre-commit` runs the same lint locally.

## 6. Tests and checks

- `python3 -m pytest -q` before every commit; it must pass. Tests use a temp workspace and a fake local model, so they never touch real settings or keys.
- New behavior comes with a test. A bug fix comes with a test that failed before.
- Web changes: also load the page in a browser if you can, in light and dark, at narrow width.
- macOS has BSD `sed`: use Python or the edit tool for in-place edits.

## 7. Where things are

| Need | File |
|---|---|
| The one product rule | `docs/scope.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| HTTP API | `docs/API.md` |
| Why the web UI is shaped as it is | `docs/adr/0001-web-ui.md` |
| Contribution and release process | `CONTRIBUTING.md` |
| Security reporting | `SECURITY.md` |
| Settings variables | `.env.example` |
| Release notes | `CHANGELOG.md` |
| README screenshots | `docs/images/` (descriptive names, under about 300 KB, no keys, tokens or private paths) |

## 8. Status (update when it changes)

Stable: engine, services, terminal, batch CLI, web server and API, web UI (v1.3.0). Added in v1.4.0: read-only `/audit` (contrast, reading order; `src/cappv1/audit.py`). Its web UI page is not built yet. Planned: file health check, screen-reader audit. Installable from GitHub with `pipx install git+https://github.com/srsuiux/cappv1.git` (`pyproject.toml` is the only place dependencies are listed; the package lives in `src/cappv1/`). PyPI publishing runs from the Release workflow (Trusted Publishing, `pypi` environment) when a version tag is pushed; v1.7.0 is the first. Not started: Homebrew, Windows. Added in v1.5.0: Word (.docx) through the engine, services, terminal and web server/UI (pictures and tables only; the accessibility check `/audit` is decks only). Added in v1.6.0: Word files are repaired for Blackboard Ally (`src/cappv1/docx_structure.py`, checked by `src/cappv1/docx_check.py`), embedded objects get alt text, files are selectable on the Files page, and each unreadable item is skipped with a note instead of stopping the file. Added in v1.7.0: the app shell is fixed to the window (no sidebar toggle), an accent color picker, an installable web app manifest (the server must still be running, and the address with its token is needed to connect), a wide Files page with Current files, Past files and Finished copies, one full-width card layout on every page, an Appearance page (theme and accent color), a Changelog page read from `CHANGELOG.md`, and per-run output folders with `/history`, `/remove` and `/api/v1/history`. Do not describe anything unstarted as available.

## 9. Keep this file honest

If you change the layout, a rule, or the workflow, change this file in the same commit.
