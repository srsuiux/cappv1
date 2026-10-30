# Changelog

All notable changes to cappv1. Versions follow [Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.

## Unreleased

- App feel: the window is fixed to the screen and only the content scrolls; the sidebar no longer folds. A new Accent color setting (six choices, each checked for contrast in light and dark) changes the color of buttons and links. cappv1 can be installed from the browser as an app (it still needs to be running, and the address it prints, to connect).
- Files page: uses the whole width, in three panels: Current files, Past files and Finished copies. Cards show size and dates. Long processing notes moved into a ? on the card that shows them on hover, focus or tap.
- Each run now keeps its finished copies in `output/<date>_<time>/` instead of replacing the last ones. Finished copies can be downloaded and deleted (one copy or a whole run) from the Files page or the terminal (`/history`, `/remove`), and both see the change. Copies left loose in `output/` by older versions show as the oldest run.
- PowerPoint: finished decks open without the repair prompt and preview in Blackboard. The output is now the original file with only the slides that got alt text replaced, instead of a python-pptx re-save, which dropped embedded-object relationships with `Target="NULL"` and left slides pointing at nothing.

## 1.6.0

- Word: Blackboard Ally structure fixes. Heading levels are renumbered to start at Heading 1 with no gaps, using copies of the existing heading styles so nothing looks different; captions become Heading 1 in a document with no headings; empty headings stop being headings; every table gets a header row, including one-row boxes; the Title property is filled when empty or wrong; text that fails the 4.5:1 contrast check is darkened to 7:1 and noted (the one visible change). `python -m src.docx_check` checks a file against these rules.
- Word: a table's first row is now marked as its header (the Header Row box and Repeat as header row), which Blackboard Ally needs: a test file scored 100% with both and 68% with the box alone. Only plain tables: no table style, two or more rows and columns, text in every first-row cell, nothing merged. One visible effect, which the owner accepted: a table that runs onto a second page repeats its header row there. Applied even in documents where table descriptions are skipped.
- Word: finished copies open in Word and preview in Blackboard. The output is now the original file with only `word/document.xml` replaced, instead of a python-docx re-save. Documents saved in Word compatibility mode 11 or 12 (what LibreOffice writes) get no table alt text, because Word refuses to open them with it; picture alt text is unaffected, and one note says to use Save As in Word first.
- Word: embedded objects (for example Visio drawings) now get alt text, so an accessibility checker no longer sees them as undescribed pictures. The Privacy page now lists the text read from an embedded object.
- Files page: every file has a checkbox, with Select all and a count. "Improve accessibility" runs only the ticked files (`POST /runs` takes `files`). New files are ticked for you; previous files can be ticked too. "Remove all" empties the Current files list after an inline confirmation.
- Sidebar: an icon beside every link, and a button that folds it to an icon rail (remembered in this browser). The theme choice is now three icon buttons (System, Light, Dark) with tooltips and screen-reader names.
- Fixes a stray "null" shown on the finished-run card.

- A damaged item no longer stops a file. A slide or document item that cannot be read (for example an embedded object whose part is missing, which used to end the file with "no relationship with key 'rId4'") is skipped, noted in the file's saved progress and the log, and the rest finishes. The Files page lists what was skipped under each file and marks the slide, and the terminal run view prints it. Applies to decks and Word documents.
- A run started from the browser now prints its log in the terminal that started cappv1 (`--web`, or `/web` in the terminal session).

## 1.5.0

- Word documents (`.docx`): pictures and tables get alt text (`wp:docPr` description and `w:tblDescription`), through the terminal, the batch command and the web UI. Charts, SmartArt, embedded objects and headers/footers are not handled yet, and `/audit` stays decks-only.
- The Files page shows a deck's slide tiles or a document's item chips, lists current files apart from previous (already finished) ones, and always shows the "replace alt text" option, off by default.
- Wording now describes cappv1 as improving accessibility (by writing alt text) for PowerPoint and Word.
- API: the upload error code `not_pptx` is now `unsupported_file`; the audit of a Word file returns `audit_unsupported`. Run events carry `kind`.

## 1.4.3

- On the Files page, a finished run shows every slide tile instead of clipping long decks.

## 1.4.2

- The contrast audit now also checks text in table cells and in grouped shapes.

## 1.4.1

- Fixes a syntax error that stopped cappv1 from installing on Python 3.11 (1.4.0 only works on 3.12 and newer, so use 1.4.1).

## 1.4.0

- The Files page now puts a run front and center: a card at the top shows each slide lighting up and ticking off, what cappv1 is reading, and, when done, a clear "Your finished document is ready" card with Download, the saved location, and a note that the original is unchanged. The finished file is marked in the list too. Animations respect reduced-motion settings.
- The Files page has a Check accessibility button that shows the same report in the browser.
- New `/audit` command and `GET /api/v1/files/<name>/audit`: reports low-contrast text (WCAG AA, judged against the real backdrop including template shapes, patterns and gradients) and slides whose reading order doesn't follow the layout. Findings with the same cause are grouped across slides. It only reports; colors and layout are never changed.

## 1.3.0

- A table's first row is now flagged as its header when that changes nothing visually (no table style, two or more rows, every first-row cell filled, nothing merged). This fixes Blackboard Ally's "tables are missing headers". Tables where it would change the look are left alone and the reason is logged.
- `skills.md` now allows a short list of visually inert accessibility fixes beyond alt text. Colors, including low contrast, are never changed.

## 1.2.0

### Added
- **Local web interface** (`cappv1 --web`, or `/web` inside cappv1; `/init` now ends by offering the browser or the terminal). It is a small site served on this computer only:
  - A front page that introduces cappv1 to new visitors and, once you're set up, leads with an Overview (next step, file counts, service, health, data) and moves the introduction below it.
  - Files (add decks, run, live feed of the alt text being written, stop, download), Services (choose service, model and key), Health, and Your data (what is kept and where, with an erase button).
  - How it works, Privacy, FAQ and About pages. The Privacy page states exactly what is sent to an AI service and what is stored, and a test keeps it in step with the code.
  - Light, dark and system themes with a switch in the side panel, applied before the page paints; a test checks the contrast of every color pair in both themes. Keyboard, screen-reader and small-screen friendly; a favicon.
- **Web server and API** (`src/web`, standard library only, documented in `docs/API.md`): bound to this computer, per-launch token, Host check, strict content policy, size-limited validated uploads, live progress over Server-Sent Events that resumes after a dropped connection.
- Each service says what it does with your slides and links to its privacy policy; saved API keys can be removed from Services.
- A new `alt_written` progress event carrying each piece of alt text as it is settled.
- `src/services/`, a service layer between the engine and the screens, with a pytest suite and GitHub Actions CI.
- `CAPPV1_HOME` to keep settings, decks and progress in a folder of your choice.
- Project files: `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and pull request templates, `.editorconfig`, `pyproject.toml`, and `docs/ARCHITECTURE.md`.

### Fixed
- Pictures are matched by their exact bytes. Before, flat or near-identical images (for example two solid-color pictures) could share one caption.
- A picture whose "alt text" is only its file name (`image1.png`, filled in by some tools) is no longer treated as text the author wrote.
- The terminal toolbar no longer re-reads every deck on each keystroke.

### Changed
- No more colored bars down one side of panels, menu items or messages; they use whole, subtle borders instead. The three steps and other boxes follow the same paper-like style.
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
