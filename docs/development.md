# Development

How cappv1 is built, how to test it, and how to cut a release. The product rule every change must follow is in [`scope.md`](scope.md). LLM agents also read `git-skills.md` in the project root, which `CLAUDE.md` loads automatically.

## Layers

cappv1 is built in layers that only depend downward:

- `src/pipeline.py`, `pptx_reader.py`, `docx_reader.py`, `llm_client.py` and friends are the **engine**. They know nothing about screens. [`scope.md`](scope.md) documents the one rule any change must follow: this tool writes alt text, plus only the few fixes it lists.
- `src/services/` is the **service layer**: settings, models, files, health checks and runs, as plain functions that return data and raise `ServiceError` with a plain-language message.
- `src/tui/` (the terminal session) and `src/web/` (the local web server and pages) are the two **front ends**. They only ask and draw.

Put logic in a service, not in a front end, so the terminal and the browser never disagree. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the layout and [`adr/0001-web-ui.md`](adr/0001-web-ui.md) for why the web UI is shaped as it is.

Settings live in `.env`; see [`configuration.md`](configuration.md) for the full list. Set `CAPPV1_HOME` to keep `.env`, `input/`, `output/` and saved progress in another folder instead of the project folder.

## Running the tests

`pip install -r requirements-dev.txt`, then `python -m pytest`. CI runs the same on Python 3.11 to 3.13 for every pull request. New behavior comes with a test.

### The fake local model

Tests use a temporary workspace and a fake local model, never your real settings or keys.

## Branches

- `main` is always releasable. Don't commit work in progress to it.
- Do work on a short-lived branch off `main`, named by purpose: `feature/<name>`, `fix/<name>`, or `docs/<name>`.
- Merge into `main` with a pull request (or `git merge --no-ff` for solo work) once it works and the docs are updated. Delete the branch afterwards.

## Web pages and privacy

Pages live in `src/web/pages/` (see [`ARCHITECTURE.md`](ARCHITECTURE.md)). Don't add inline script or style, or anything loaded from outside the local server; the tests fail if you do. If a change affects what is sent to an AI service or what is stored on disk, update the in-app Privacy page (`src/web/pages/privacy.html`), [`privacy.md`](privacy.md), the Your data descriptions (`src/services/storage.py`) and the service notes (`src/services/settings.py`) in the same change.

## Commits

Short imperative subject ("Add Ollama provider"), then a few lines on why. One logical change per commit.

## Versions and tags

- Versions are `MAJOR.MINOR.PATCH`: PATCH for fixes, MINOR for new features that don't break existing use, MAJOR for breaking changes.
- Releases are annotated tags on `main` named `vMAJOR.MINOR.PATCH` (for example `v1.1.0`). Never move or reuse a tag.
- The first release was tagged `engine-cappv1-1.0.0` before this convention; it is version 1.0.0.

## Cutting a release

1. Branch is merged to `main`; `git status` is clean.
2. Update `VERSION` in `src/version.py` and add a section to `CHANGELOG.md`.
3. Commit: `Release vX.Y.Z`.
4. `git tag -a vX.Y.Z -m "cappv1 X.Y.Z"` then `git push origin main vX.Y.Z`.
5. On GitHub, create a Release from the tag and paste the changelog section.

## Never commit

API keys, `.env`, your slide decks, or anything from `input/`, `output/`, `logs/`, `.state/`. They are in `.gitignore`; keep it that way. If a key is ever pushed, revoke it at the provider first, then clean up.
