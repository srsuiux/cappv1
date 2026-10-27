# Changelog

All notable changes to cappv1. Versions follow [Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.

## Unreleased

### Added
- Local web server (`src/web`, standard library only) with a documented JSON API (`docs/API.md`): token and Host checks, size-limited uploads, live progress over Server-Sent Events.
- `cappv1 --web [--port N] [--no-open]` and `/web` / `/web stop` inside cappv1; `/init` now ends by offering the browser or the terminal.
- `src/services/`, a service layer between the engine and the screens, with a pytest suite and GitHub Actions CI.
- `CAPPV1_HOME` to keep settings, decks and progress in a folder of your choice.

### Fixed
- Pictures are matched by their exact bytes. Before, flat or near-identical images (for example two solid-color pictures) could share one caption.
- A picture whose "alt text" is only its file name (`image1.png`, filled in by some tools) is no longer treated as text the author wrote.
- The terminal toolbar no longer re-reads every deck on each keystroke.

### Changed
- `cappv1` is now the only command in the shell. `cappv1 doctor`, `models`, `clean`, `init` and `start` are refused; use `/doctor`, `/models`, `/clean` and the others inside the session. `cappv1 --batch` remains for scripts, plus `--version` and `--help`.
- `/init` shows the current service and model first and lets you keep it, change only the model, or switch service, instead of asking everything again. `/models` goes straight to the service and model pickers. Both are listed in `/help` and in the `/` menu.

## 1.1.0

### Added
- Interactive terminal session (`cappv1`, `cappv1 start`, `cappv1 init`): slash commands with completion, arrow-key menus, drag-and-drop of `.pptx` files, and a live run view whose animation follows what is happening (picture, chart, table, diagram, saving).
- Local, private captioning with Ollama (`PROVIDER=ollama`); nothing leaves the computer, and a remote Ollama address is refused unless explicitly allowed.
- `/models`: one flow to switch AI service and model, including free and paid OpenRouter vision models with prices (reaches DeepSeek, Google, OpenAI and more).
- Alt text that authors already wrote is built on, not replaced: short text is improved, adequate text is kept as written. `/run --force` replaces it after confirmation.
- Edited decks are recognised by content hash and reprocessed; unchanged items reuse saved captions. Unchanged files are reported as already captioned.

### Fixed
- Resuming after a crash lost the captions of slides finished before the crash.
- One unreadable progress file stopped the whole run; it is now set aside.
- Output and progress files are written atomically, so a crash cannot leave a half-written file.
- An edited deck with the same filename was skipped as "already complete".

### Changed
- `cappv1 start` opens the interactive session. The old background behavior is `cappv1 start --batch` (also used automatically when there is no terminal).

## 1.0.0 (tag `engine-cappv1-1.0.0`)

- Terminal engine: alt text for pictures, tables, charts, SmartArt and embedded objects; invisible shapes marked decorative; files processed in sequence and resumable.
- Providers: OpenRouter, OpenAI, Anthropic, and Ollama.
