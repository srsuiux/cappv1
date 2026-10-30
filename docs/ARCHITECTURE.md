# Architecture

cappv1 is three layers. Each depends only on the one below it.

```
  terminal (src/tui)        browser (src/web)
            \                 /
        services (src/services)      settings, models, files, runs, health, storage
                    |
        engine (src/pipeline.py and friends)     reads decks, calls the AI, writes alt text
```

- **Engine** (`pipeline.py`, `pptx_reader.py`, `docx_pipeline.py`, `docx_reader.py`, `docx_structure.py`, `docx_check.py`, `llm_client.py`, `state.py`, `events.py`): the work itself. `pipeline.py` picks the deck or Word path by file extension (`SUPPORTED_EXTENSIONS`); run events carry `kind` (`slides` or `document`) so a front end can show the right view. `docx_structure.py` repairs headings, contrast and the Title for Blackboard Ally; `docx_check.py` is the read-only check of those rules (`python -m src.docx_check files...`). A library, not a service. It reports progress through `events.py`.
- **Services** (`src/services/`): everything a screen needs, as plain functions that return data or raise `ServiceError(code, message, fix)`. No printing, no HTTP.
- **Front ends**: `src/tui` (terminal session) and `src/web` (local web server). They only ask and draw; the logic lives in services, so they never disagree. A run started in one is visible in the other because they share one `RunManager`.

## The web front end

```
src/web/
  server.py      standard-library HTTP server, security checks, page rendering
  api.py         /api/v1 routes, each a few lines over a service  (docs/API.md)
  templates/     the page layout: sidebar, status line, footer
  pages/         one fragment per page; the first line holds its title, menu entry and script
  static/        app.css, scripts (one per page, plus shell.js, app.js and theme.js), fonts
```

A page is a fragment in `pages/` wrapped in a layout from `templates/` when requested, so the menu, footer and version live in one place and there is no build step. Scripts are plain ES modules served from `static/`. The content policy forbids inline script and style; `tests/test_web_pages.py` enforces it.

To add a page: create `pages/<name>.html` with a metadata comment on the first line, add a link in `templates/app.html`, and add a script in `static/` if it needs data.

## Where data lives

Everything is in one folder (the project folder, or `CAPPV1_HOME`): `input/`, `output/` (one `<date>_<time>/` folder per run, see `src/outputs.py`), `.state/`, `logs/`, `.env`. The Your data page and `docs/PRIVACY` content (the in-app Privacy page) describe it; change them together with any change to what is sent or stored.
