# Contributing to cappv1

cappv1 is open source under the [MIT License](LICENSE). Issues and pull requests are welcome.

## Ground rule

The tool only ever writes to a shape's alt-text field and never changes anything else in a deck. Any change must keep that true (see `skills.md`).

## Branches

- `main` is always releasable. Don't commit work in progress to it.
- Do work on a short-lived branch off `main`, named by purpose: `feature/<name>`, `fix/<name>`, or `docs/<name>`.
- Merge into `main` with a pull request (or `git merge --no-ff` for solo work) once it works and the docs are updated. Delete the branch afterwards.

## Commits

Short imperative subject ("Add Ollama provider"), then a few lines on why. One logical change per commit.

## Versions and tags

- Versions are `MAJOR.MINOR.PATCH`: PATCH for fixes, MINOR for new features that don't break existing use, MAJOR for breaking changes.
- Releases are annotated tags on `main` named `vMAJOR.MINOR.PATCH` (for example `v1.1.0`). Never move or reuse a tag.
- The first release was tagged `engine-cappv1-1.0.0` before this convention; it is version 1.0.0.

## Cutting a release

1. Branch is merged to `main`; `git status` is clean.
2. Update `VERSION` in `src/tui/session.py` and add a section to `CHANGELOG.md`.
3. Commit: `Release vX.Y.Z`.
4. `git tag -a vX.Y.Z -m "cappv1 X.Y.Z"` then `git push origin main vX.Y.Z`.
5. On GitHub, create a Release from the tag and paste the changelog section.

## Never commit

API keys, `.env`, your slide decks, or anything from `input/`, `output/`, `logs/`, `.state/`. They are in `.gitignore`; keep it that way. If a key is ever pushed, revoke it at the provider first, then clean up.
