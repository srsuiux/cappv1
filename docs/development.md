# Development

How cappv1 is built, how to test it, and how to cut a release. The product rule every change must follow is in [`scope.md`](scope.md). LLM agents also read `git-skills.md` in the project root, which `CLAUDE.md` loads automatically.

## Layers

cappv1 is built in layers that only depend downward:

- `src/cappv1/pipeline.py`, `pptx_reader.py`, `docx_reader.py`, `llm_client.py` and friends are the **engine**. They know nothing about screens. [`scope.md`](scope.md) documents the one rule any change must follow: this tool writes alt text, plus only the few fixes it lists.
- `src/cappv1/services/` is the **service layer**: settings, models, files, health checks and runs, as plain functions that return data and raise `ServiceError` with a plain-language message.
- `src/cappv1/tui/` (the terminal session) and `src/cappv1/web/` (the local web server and pages) are the two **front ends**. They only ask and draw.

Put logic in a service, not in a front end, so the terminal and the browser never disagree. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the layout and [`adr/0001-web-ui.md`](adr/0001-web-ui.md) for why the web UI is shaped as it is.

Settings live in `.env`; see [`configuration.md`](configuration.md) for the full list. Set `CAPPV1_HOME` to keep `.env`, `input/`, `output/` and saved progress in another folder instead of the default (`~/cappv1`, or the project folder when run from a cloned copy).

## Running the tests

Clone the repository, create a virtual environment, run `pip install -e ".[dev]"` (the one place dependencies are listed is `pyproject.toml`), then `python -m pytest`. CI runs the same on Python 3.11 to 3.13 for every pull request. New behavior comes with a test.

CI also runs, on every push and pull request:

- `ruff check` and `ruff format --check` (settings in `pyproject.toml`), and `mypy` over every module in `src/cappv1`, with no exceptions. New code needs to type-check; avoid `# type: ignore`, and give a short reason if you must use it.
- The tests on Linux and macOS, with a coverage report (`python -m pytest --cov=cappv1`).
- A build of the wheel, installed and run in a clean environment.
- A markdown link check.

Run the same checks before you push with `pre-commit install` (once), which also blocks committing `.env` files and anything in `input/` or `output/`.

### The fake local model

Tests use a temporary workspace and a fake local model, never your real settings or keys.

## Branches

- `main` is always releasable. Don't commit work in progress to it.
- Do work on a short-lived branch off `main`, named by purpose: `feature/<name>`, `fix/<name>`, or `docs/<name>`.
- Merge into `main` with a pull request (or `git merge --no-ff` for solo work) once it works and the docs are updated. Delete the branch afterwards.

## Web pages and privacy

Pages live in `src/cappv1/web/pages/` (see [`ARCHITECTURE.md`](ARCHITECTURE.md)). Don't add inline script or style, or anything loaded from outside the local server; the tests fail if you do. If a change affects what is sent to an AI service or what is stored on disk, update the in-app Privacy page (`src/cappv1/web/pages/privacy.html`), [`privacy.md`](privacy.md), the Your data descriptions (`src/cappv1/services/storage.py`) and the service notes (`src/cappv1/services/settings.py`) in the same change.

## Commits

Short imperative subject ("Add Ollama provider"), then a few lines on why. One logical change per commit.

## Versions and tags

- Versions are `MAJOR.MINOR.PATCH`: PATCH for fixes, MINOR for new features that don't break existing use, MAJOR for breaking changes.
- Releases are annotated tags on `main` named `vMAJOR.MINOR.PATCH` (for example `v1.1.0`). Never move or reuse a tag.
- The first release was tagged `engine-cappv1-1.0.0` before this convention; it is version 1.0.0.

## Cutting a release

1. Branch is merged to `main`; `git status` is clean.
2. Update `VERSION` in `src/cappv1/version.py` (the package version is read from it) and add a section to `CHANGELOG.md`.
3. Commit: `Release vX.Y.Z`.
4. `git tag -a vX.Y.Z -m "cappv1 X.Y.Z"` then `git push origin main vX.Y.Z`.
5. The `Release` workflow builds the wheel and sdist and creates the GitHub Release from the tag, using that version's `CHANGELOG.md` section as the notes. It fails if the tag does not match `src/cappv1/version.py`.

## Never commit

API keys, `.env`, your slide decks, or anything from `input/`, `output/`, `logs/`, `.state/`. They are in `.gitignore`; keep it that way. If a key is ever pushed, revoke it at the provider first, then clean up.
