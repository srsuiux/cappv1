# cappv1 Web UI: Development Plan

Status: **REVISED DRAFT (v2) for review.** Nothing here is built. Edit freely, then approve phase by phase.

What changed from v1: no web framework (plain HTML/CSS/JS and a standard-library server); the engine stays a library behind a shared **service layer** that both the terminal and the browser use; `/init` ends by asking where to continue; security, testing and CI sections added; phases reordered so the service layer comes first.

## 1. Goal

A clean, accessible, local web interface for cappv1 that a non-technical person can use without touching Terminal or `.env`, while technical users keep full control. The terminal session stays a first-class way to use the tool.

Beyond doing the work, the app should **leave clear notes** so users learn what was wrong with a file, how it was fixed, and how to do better next time.

## 2. Principles (these override convenience)

1. **Local first.** The web UI runs on the user's own computer (`127.0.0.1`). No cloud service, no accounts, no telemetry, no external requests from the page. Slide content only leaves the machine if the user chose an online AI service.
2. **The one safety rule stays.** The engine only ever writes a shape's alt-text field (`skills.md`). Everything new (health check, notes, verification) is read-only with respect to the `.pptx`. Originals are never modified.
3. **One brain, two faces.** All behavior lives in the service layer. The terminal and the browser are thin adapters over it, so they can never disagree.
4. **No framework.** Plain HTML, CSS and JavaScript; Python standard library on the server. Nothing to build, nothing to install, works offline.
5. **The UI is itself accessible** (WCAG 2.2 AA minimum). A tool for accessibility that is not accessible defeats its purpose.
6. **Permission-based storage.** The app reads and writes only inside the workspace folder. It never touches anything outside it.
7. **The CLI keeps working.** `cappv1 start --batch`, `doctor`, `models`, `clean` are unchanged.

## 3. Architecture

```
 Browser (plain HTML/JS)        Terminal session (rich + prompt_toolkit)
          |  HTTP + SSE (127.0.0.1)            |  direct calls
          v                                    v
   Web adapter  src/web/                 TUI adapter  src/tui/
          \                                  /
           \______  Service layer  _________/        src/services/
                    (settings, workspace, runs, health, reports)
                              |  direct calls, in-process
                              v
                    Engine (library)                 src/pipeline.py, pptx_reader.py, llm_client.py ...
```

- **Engine** stays a library with no UI knowledge. It already emits progress events (`src/events.py`).
- **Service layer** is the application logic: plain functions that take and return simple data (dataclasses that serialize to JSON) and raise one `ServiceError(code, message, how_to_fix)` with plain-language text. Modules:
  - `settings`: read and write `.env`, switch service/model, validate a key, privacy label. `.env` stays the single source of truth.
  - `models`: list models per service (Ollama installed, OpenRouter free/paid with prices, curated lists).
  - `workspace`: add, list, delete and describe files (uses `inspect_file`); every path confined to the workspace.
  - `runs`: start, cancel and report on a run. **One active run at a time**, shared by both UIs. Keeps an ordered event log so a page can reconnect and catch up.
  - `health`: environment checks (`doctor`) and the per-file health check.
  - `reports`: the fix notes for a file.
- **Web adapter** maps HTTP to service calls and nothing else. No business logic.
- **TUI adapter** is refactored to call the same services (today `src/tui/commands.py` holds logic that belongs in the layer).
- The engine is **not** run as a separate network service. The only HTTP boundary is browser to web adapter.

### Entry points

| How | What happens |
|---|---|
| `cappv1` / `cappv1 start` | Terminal session (as today). |
| `/init` (or `/models`) | After a successful setup it asks: **Continue in the browser** or **Stay in the terminal**. |
| `/web` in the session | Starts the web server in the background, opens the browser, and the terminal stays usable. `/web stop` stops it. |
| `cappv1 web [--port N] [--no-open]` | Starts only the web UI. |

Both UIs see the same files, settings and run. Starting a run in one shows live progress in the other.

### Web server

- Python standard library (`http.server` threaded server), bound to `127.0.0.1` only, on a free port starting at 8765.
- Static pages served from `src/web/static/`; JSON API under `/api/v1/`.
- **Uploads** are sent as the raw request body (`PUT /api/v1/files/<name>`), not multipart, so no fragile parsing and large files stream to disk.
- **Live progress** over Server-Sent Events (`GET /api/v1/runs/<id>/events`), with `Last-Event-ID` replay after a dropped connection.
- The engine runs in a background thread with its own event loop; the HTTP threads never block on it.

### API (v1, JSON)

`GET/PUT /settings` · `POST /settings/test` · `GET /services` · `GET /services/<name>/models` · `GET /files` · `PUT /files/<name>` · `DELETE /files/<name>` · `GET /files/<name>/download` · `GET /files/<name>/health` · `GET /files/<name>/report` · `POST /runs` · `GET /runs/current` · `POST /runs/<id>/cancel` · `GET /runs/<id>/events` · `GET /doctor`.
Errors always use `{ "error": { "code", "message", "fix" } }`. The contract is written down in `docs/API.md` and covered by tests.

## 4. Security (localhost is not automatically safe)

- Bind to `127.0.0.1`; reject any request whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` (blocks DNS rebinding).
- A random **per-launch token**. It is given in the URL fragment (`#t=...`, never sent to the server in the URL), kept in `sessionStorage`, and required in a custom header on every API call. No CORS headers at all, so other sites cannot call the API.
- Strict `Content-Security-Policy` (`default-src 'self'`, no inline scripts, no external fonts or scripts), plus `X-Content-Type-Options` and `Referrer-Policy: no-referrer`.
- Upload rules: `.pptx` only, size cap, must be a valid zip, sanitized names, no path separators, no symlink escape.
- API keys are written to `.env` with owner-only permissions and are never returned in full (last 4 characters only).
- Remote Ollama keeps its existing guard (`OLLAMA_ALLOW_REMOTE`) and the UI shows a clear warning.
- The page makes no network requests except to its own server.

## 5. Scope

### In scope (v1 of the web UI)
- **Setup**: choose service, key or Ollama check, pick model (same flow as `/models`), "Test connection", plain-language privacy note per service.
- **Upload** one or many files (drag and drop plus a normal file picker).
- **File health check** before processing (see section 7).
- **Run with live progress** per file and slide; cancel; resume; plain-language errors.
- **Results**: slide-by-slide list of every shape with before/after alt text, marking items we **kept as written** and items we **improved**.
- **Fix notes** per file (see section 8).
- **File manager** for inputs, outputs and reports, inside the workspace only.
- **Advanced settings**: model, concurrency, timeout, minimum existing alt-text length, Ollama address.

### Out of scope (for now)
- Editing alt text by hand in the browser (candidate for the next release).
- Accounts, multi-user login, hosting for a campus (section 12).
- Packaged desktop app; Windows support (matches the CLI).
- Auto-fixing anything other than alt text.

## 6. Users and key tasks

| User | Needs |
|---|---|
| Instructor / staff (non-technical) | Pick a service, drop in files, see progress, get fixed files and plain-language notes. |
| Accessibility / IT staff | See exactly what changed per slide, file health, logs, and control over service, model and limits. |
| Developer | A documented local API and the headless `--batch` mode. |

## 7. File health check (the "corrupted file" check)

Read-only; runs before captioning and on demand. Implemented once in the `health` service, shown in both UIs.

| Check | Result if it fails |
|---|---|
| Valid zip and a valid `.pptx` (`[Content_Types].xml`, `presentation.xml` present) | **Damaged**: cannot process |
| Every slide XML is well-formed | **Damaged**, or that slide is skipped and marked needs-attention |
| Relationships resolve (no pointers to missing images, charts, notes, embeddings) | **Minor issue**: process the rest, list what is missing |
| Images decode | **Minor issue**: that image is skipped, noted |
| Embedded objects and SmartArt parts readable | **Minor issue**, noted |
| python-pptx can open the file | **Damaged** if not |

Status per file: **Healthy / Minor issues / Damaged**. Damaged files are skipped with a plain reason and repair steps ("open in PowerPoint and use Open and Repair", "re-insert the missing picture on slide 7").

**Integrity proof after processing:** compare input and output and confirm only alt-text attributes changed. Show "Verified: only alt text changed", or flag any difference loudly.

## 8. Fix notes (the teaching layer)

Per file, a report (viewable in the browser and terminal, downloadable as HTML and Markdown):

1. **Health summary** with repair steps.
2. **What we changed**: every alt text written, by slide and shape; items kept as the author wrote them; items improved; items marked decorative; items we could not caption and why.
3. **Why it matters**: one or two sentences per category on what a screen-reader user hears.
4. **How to do better next time**: short, specific tips.
5. **Using an LLM well**: giving a model slide context, reviewing its output, what not to trust it with.

Facts come from code and are reliable. Only the explanatory wording may use the AI, and it is labeled as AI-written advice. The default is **built-in templates** (works offline, no cost); AI wording is opt-in.

## 9. Screens

1. **Setup**: service cards with cost and privacy, key entry or Ollama check, model picker, test connection.
2. **Home**: drop zone, file list with health and status badges ("already captioned, unchanged", "edited since last run"), Run button.
3. **Run**: per-file and per-slide progress, current activity, cancel.
4. **Results**: summary counts, slide-by-slide before and after, integrity line, downloads.
5. **Notes**: the fix notes for a file.
6. **Files**: manage inputs, outputs, reports; confirm before deleting.
7. **Settings**: advanced options.

Plain multi-page site (one HTML file per screen, shared `app.css` and `app.js`), so every screen has a real URL and the back button works.

## 10. Accessibility requirements (acceptance criteria)

- Fully operable by keyboard; logical tab order; visible focus; no traps.
- Semantic HTML: landmarks, headings, labeled controls, real buttons and links.
- Live regions announce progress, errors and completion; drag and drop has a button equivalent.
- Contrast at least 4.5:1 for text and 3:1 for UI; never color alone (badges carry text).
- Respects `prefers-color-scheme` and `prefers-reduced-motion`; usable at 200% zoom.
- Plain language, about grade 8; errors say what happened and what to do.
- Tested with VoiceOver on macOS, and an automated checker (axe-core, development-only, not shipped) on every screen.

## 11. Testing and quality (new)

- **pytest** for the service layer (the repo has no test suite today). Fixtures: healthy, damaged and missing-part decks; a fake model server (as used in manual testing so far).
- **API tests** against a real server on a random port using the standard-library client: auth token, Host check, path escape, upload limits, error shape.
- **Terminal and web parity tests**: the same service call gives the same result through both adapters.
- **GitHub Actions CI** on every pull request: lint, tests, compile check. Public-repo hygiene: secret scanning on.
- Contract documented in `docs/API.md`; changes to it go in `CHANGELOG.md`.

## 12. Phases

Branching follows `CONTRIBUTING.md`: each phase is a `feature/...` branch off `main`, merged when approved. Releases are tagged `vX.Y.Z`.

| Phase | Branch | Deliverable | Done when |
|---|---|---|---|
| 0 | `docs/webui-plan` | This plan approved | You approve |
| 1 | `feature/service-layer` | Extract logic from `src/tui/commands.py` into `src/services/`; terminal now calls it; pytest suite begins; CI added | Terminal behaves identically; service tests pass |
| 2 | `feature/web-server` | `src/web/` server, `/api/v1`, token and Host checks, SSE, `cappv1 web`, `/web`, and the `/init` browser-or-terminal choice | API tests pass; browser shows a blank shell with live status |
| 3 | `feature/web-ui` | Static pages: Setup, Home and upload, Run, Results (low-fi mockup reviewed first) | A new user goes from install to a captioned file without editing `.env` |
| 4 | `feature/file-health` | `health` service and the integrity check, shown in both UIs | Good, damaged and partial fixtures classified correctly |
| 5 | `feature/fix-notes` | `reports` service, Notes page, HTML and Markdown export | Reports correct on sample files |
| 6 | `feature/a11y-polish` | Keyboard, VoiceOver and axe pass; contrast; zoom; docs and screenshots; release **v1.2.0** | Section 10 criteria met; README works for a first-time user |

Each phase ends with a local commit, a short demo or summary, and your approval before the next starts.

## 13. Later options (not planned)

- **Shared campus server**: the same app on one machine for many people needs real login, TLS, per-user workspaces, queueing and IT approval. Treat it as its own project after the local UI ships.
- Manual alt-text editing in the browser; packaged Mac app; folder watching.
- SQLite instead of JSON files, if history or search screens appear (not needed today).

## 14. Risks

| Risk | Mitigation |
|---|---|
| Hand-written HTTP server has gaps a framework would cover | Small surface; the security checklist in section 4 is tested; revisit a framework only if the surface grows |
| Terminal and browser both start a run | One active run, enforced in the service layer; both UIs show it |
| Service-layer extraction changes terminal behavior | Phase 1 is a pure refactor with tests first; nothing else ships with it |
| Localhost attacks (other sites, DNS rebinding) | Host check, per-launch token, no CORS, strict CSP |
| Scope creep from "teaching" notes into a full accessibility audit | v1 notes describe only what the tool did and found; audit-style checks are a later opt-in |
| Local models are slow and look stuck | Honest per-item progress, "first image is slow" hint (already in the terminal) |

## 15. Decisions made / still open

Decided: no framework (stdlib server, plain pages); engine stays a library behind a shared service layer; `.env` stays the source of truth; workspace is the project folder; notes default to built-in templates, AI wording opt-in; manual alt-text editing is out of this release.

Still open:
1. **Port**: fixed default 8765 with fallback to the next free port. OK?
2. **Open the browser automatically** after `/init`, or wait for a keypress?
3. **Name** in the browser: keep "cappv1", or a friendlier product name?
4. **Mockup first**: confirm Phase 3 starts with a reviewed low-fi mockup before any page code.
