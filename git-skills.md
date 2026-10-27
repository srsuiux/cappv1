# git-skills: how an LLM works in this repository

Read this first, every session. It tells you how the project is laid out, which rules cannot be broken, and how to decide what to do without being told each time. `skills.md` holds the one product rule; this file holds everything else. If the two ever disagree, `skills.md` wins.

## 1. What this project is

cappv1 writes alt text into PowerPoint decks using vision models (OpenRouter, OpenAI, Anthropic, or local Ollama). Open source, MIT, Mac and Linux, Python 3.11+. Public repo: `srsuiux/cappv1`.

## 2. Hard rules (never break these, even if asked in passing)

1. **Visually inert output.** The tool writes alt text (`descr` on `cNvPr`) and, from a short named list in `skills.md`, fixes that change nothing you can see. Never change colors, fonts, sizes, layout, text or table styles. Report problems like low contrast; do not fix them.
2. **No secrets in the repo.** Never commit `.env`, keys, decks, or anything under `input/`, `output/`, `logs/`, `.state/`. Never print a key.
3. **Privacy is a feature.** If a change affects what is sent to an AI service or stored on disk, update in the same change: `src/web/pages/privacy.html`, `src/services/storage.py`, `src/services/settings.py` (service notes). Tests tie the Privacy page to the code.
4. **No tracking.** No analytics, telemetry, cookies, update checks, or third-party requests.
5. **Not a data manager.** No database, history, or file manager features.
6. **Never move or reuse a tag.** Never rewrite pushed history.

## 3. Layers (each depends only on the one below)

```
src/tui/  src/web/        front ends: no logic, call services
src/services/             settings, models, files, runs, health, storage, workspace, envfile
src/ engine               pipeline.py, pptx_reader.py, llm_client.py, state.py, events.py, config.py,
                          image_filter.py, doctor.py, models.py, main.py
```

- Put logic in a service, not in a front end, so terminal and browser never disagree.
- The engine knows nothing about screens; it reports progress through the event bus (`src/events.py`). The terminal and web server share one `RunManager`.
- Errors from services are `ServiceError(code, message, fix)`: plain words plus a next step.
- Identify PowerPoint shapes by XML tag (`shape._element.tag`), never `shape.shape_type` (see `skills.md`).
- `set_alt_text()` is the single write path for alt text; `mark_table_header()` is the only other write, and only when visually inert.

### Web (`src/web`)
- stdlib server, 127.0.0.1 only, token header, Host allowlist, strict CSP. No framework, no build step.
- Pages are fragments in `pages/*.html` with a first-line metadata comment, wrapped by `templates/app.html`. **No inline script or style**; nothing loaded from outside. Tests enforce this.
- Styles are tokens in `static/app.css` for light and dark. Every text pair must keep 4.5:1 contrast (tested). No one-sided border strokes. Targets at least 44px. Sentence case. No gradients or shadows.
- API under `/api/v1`, documented in `docs/API.md`; errors are `{"error": {"code","message","fix"}}`.

### Terminal (`src/tui`)
Slash commands live inside the session. The shell exposes only `cappv1`, `--batch`, `--web`, `--version`, `--help`. Do not re-add shell-level `init/doctor/models/clean/start`.

## 4. Choosing what to do (decision procedure)

1. Read the request. If it is a question, answer it; do not change files.
2. Find the code that already does something similar and match its style, naming and comment density.
3. Classify the change:
   - **Engine behavior** → check `skills.md` first; add a test in `tests/`.
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
- Release steps: merge, clean `git status`, bump `src/version.py`, add a `CHANGELOG.md` section, commit `Release vX.Y.Z`, `git tag -a vX.Y.Z -m "cappv1 X.Y.Z"`, `git push origin main vX.Y.Z`, then create the GitHub Release by hand (`gh` is not installed).
- CI: GitHub Actions on Python 3.11, 3.12, 3.13. Check it after a push.

## 6. Tests and checks

- `python3 -m pytest -q` before every commit; it must pass. Tests use a temp workspace and a fake local model, so they never touch real settings or keys.
- New behavior comes with a test. A bug fix comes with a test that failed before.
- Web changes: also load the page in a browser if you can, in light and dark, at narrow width.
- macOS has BSD `sed`: use Python or the edit tool for in-place edits.

## 7. Where things are

| Need | File |
|---|---|
| The one product rule | `skills.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| HTTP API | `docs/API.md` |
| Plans and scope | `docs/web-ui-plan.md` |
| Portfolio facts and status board | `docs/PORTFOLIO-BRIEF.md` |
| Contribution and release process | `CONTRIBUTING.md` |
| Security reporting | `SECURITY.md` |
| Settings variables | `.env.example` |
| Release notes | `CHANGELOG.md` |

## 8. Status (update when it changes)

Stable: engine, services, terminal, batch CLI, web server and API, web UI (v1.3.0). Planned: file health check, screen-reader audit. Not started: npm launcher, PyPI/Homebrew, Windows. Do not describe anything unstarted as available.

## 9. Keep this file honest

If you change the layout, a rule, or the workflow, change this file in the same commit.
