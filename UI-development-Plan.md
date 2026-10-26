# cappv1 GUI: Development Plan

Status: **DRAFT for review.** Nothing here is built. Edit freely, then approve phase by phase.

## 1. Goal

A clean, accessible, local web interface for cappv1 that a non-technical person can use without touching Terminal or `.env`, while technical users keep full control.

Beyond doing the work, the app should **leave clear notes** so users learn what was wrong with a file, how it was fixed, and how to do better next time (including how to use an LLM well for this).

## 2. Principles (these override convenience)

1. **Local first.** The web UI runs on the user's own computer (`localhost`). No cloud service, no accounts, no telemetry. Slide content only leaves the machine if the user chose an online AI provider.
2. **The one safety rule stays.** The engine only ever writes to a shape's alt-text field (`skills.md`). New features (health check, notes) are read-only with respect to the `.pptx`. Originals are never modified.
3. **The GUI is a thin layer.** The existing Python pipeline remains the engine. No rewrite.
4. **The GUI is itself accessible** (WCAG 2.2 AA minimum). A tool for accessibility that is not accessible defeats its purpose.
5. **Permission-based storage.** The app reads and writes only inside one workspace folder the user chose. It never touches anything outside it.
6. **CLI keeps working.** `cappv1 start`, `doctor`, `models`, `clean` are unchanged.

## 3. Versioning and branching

- Tag the current terminal app on `main` as **`engine-cappv1-1.0.0`** (the frozen CLI release).
- Do all GUI work on a branch named **`gui`**. Merge to `main` only when a phase is approved.
- Commit locally after every clean state and every major update. Push only when asked.

## 4. Users and key tasks

| User | Needs |
|---|---|
| Instructor / staff (non-technical) | Pick a service, drop in files, see progress, get fixed files and plain-language notes. |
| Accessibility / IT staff | See what changed per slide, health status, logs, and control over provider, model and concurrency. |
| Developer | A documented local API and the ability to run headless as before. |

## 5. Scope

### In scope (v1)
- First-run **setup**: choose provider (Ollama, OpenAI, Anthropic, OpenRouter), enter key or check Ollama, run a built-in doctor, save settings.
- **Single and multiple file upload** (drag and drop plus a normal file picker).
- **File health check** before processing: detect corrupted or damaged files and explain how to repair them.
- **Run and live progress** per file and per slide, with plain-language errors. Resume interrupted runs.
- **Results view**: per-slide list of every shape, its before/after alt text, and what was marked decorative.
- **Fix notes**: a readable report per file (see section 8).
- **Workspace file manager**: list, download, and delete inputs, outputs, and reports inside the workspace only.
- **Advanced settings**: model, fallback model, concurrency, timeout, max alt-text length, Ollama address.

### Out of scope (v1, revisit later)
- Auto-fixing anything other than alt text (titles, reading order, contrast).
- Accounts, multi-user login, or hosting for a whole campus (see section 12).
- A packaged desktop app (.app / installer).
- Windows support (matches current CLI).
- Editing alt text by hand in the GUI (candidate for v1.1).

## 6. Architecture

```
Browser (localhost)  <-->  Local web server (Python)  <-->  existing engine (src/pipeline.py ...)
                                   |
                                   +--> Workspace folder (input/, output/, reports/, .state/)
```

- **Server:** a small Python web server started by `cappv1 ui`, bound to `127.0.0.1` only (never `0.0.0.0` by default). It opens the user's browser on start.
- **Framework:** recommend **FastAPI + Uvicorn** (async fits the existing asyncio pipeline; server-sent events for live progress). Alternative: stdlib-only `http.server` to avoid new dependencies, at the cost of more hand-written code. *Decision needed.*
- **Front end:** plain HTML, CSS and a small amount of vanilla JavaScript, served by the same process. No Node build step, no front-end framework, no CDN calls. This keeps install simple and works offline.
- **Engine hook:** refactor `run_file` / `run` so they can report progress through a callback or event queue instead of only logging. The CLI keeps using the log output.
- **Job model:** one background job per run, with states `queued -> checking -> running -> complete | failed | needs-attention`. State is persisted in `.state/` (already exists) so a closed browser or restart can resume.
- **Local API (JSON):** `GET /api/settings`, `PUT /api/settings`, `POST /api/doctor`, `POST /api/files`, `GET /api/files`, `POST /api/runs`, `GET /api/runs/{id}/events` (SSE), `GET /api/files/{id}/report`, `GET /api/files/{id}/download`, `DELETE /api/files/{id}`.

### Security
- Bind to localhost only. Reject requests whose `Host` header is not localhost.
- Per-session random token required on API calls (blocks other web pages from driving the local server).
- Upload limits: `.pptx` only, size cap, validate the file is a zip before storing.
- Sanitize filenames; confine all paths to the workspace (no `..`, no symlink escape).
- API keys stored in the workspace `.env` with owner-only file permissions; never returned to the browser in full (show last 4 characters).
- No external network calls from the UI itself. Fonts and assets are bundled.
- Remote Ollama keeps the existing guard (`OLLAMA_ALLOW_REMOTE`) and shows a clear warning in the UI.

## 7. File health check (the "corrupted data" check)

Read-only; runs before captioning and on demand.

| Check | Result if it fails |
|---|---|
| File is a valid zip and a valid `.pptx` (`[Content_Types].xml`, `presentation.xml` present) | **Damaged**: cannot process |
| Every slide XML is well-formed | **Damaged** (or skip that slide, marked needs-attention) |
| Relationships resolve (no pointers to missing images, charts, notes, embeddings) | **Minor issue**: process the rest, list what is missing |
| Images decode (Pillow can open them) | **Minor issue**: that image is skipped, noted |
| Embedded objects / SmartArt parts readable | **Minor issue**, noted |
| python-pptx can open the file | **Damaged** if not |

Status per file: **Healthy / Minor issues / Damaged**. Damaged files are skipped with a plain-language reason instead of failing mid-run.

**Integrity proof after processing:** compare input and output and confirm that only alt-text attributes changed. Show "Verified: only alt text changed" in the results, or flag any difference loudly.

## 8. Fix notes (the teaching layer)

Per file, generate a report (viewable in the GUI, downloadable as HTML and Markdown) containing:

1. **Health summary**: what was found, in plain language, with steps to repair (for example "open in PowerPoint and use Open and Repair", "re-insert the missing picture on slide 7").
2. **What we changed**: every alt-text written, by slide and shape, plus items marked decorative and items we could not caption and why.
3. **Why it matters**: one or two sentences per category (picture, chart, table, SmartArt, embedded object, decorative) on what a screen-reader user hears.
4. **How to do better next time**: short, specific tips (for example "describe the point of a chart, not each bar", "mark purely decorative shapes as decorative in PowerPoint").
5. **Using an LLM well**: guidance on giving a model slide context, reviewing its output, and what not to trust it with.

Rule-based facts (what is missing, what changed) are generated by code so they are reliable. Only the explanatory wording may use the LLM, and it is clearly labeled as AI-written advice. Optional: a no-LLM template mode so notes work with zero network access.

A later, optional layer can add accessibility-structure findings (missing slide titles, reading order, small fonts, low contrast). That stays read-only advice, not auto-fix.

## 9. Screens

1. **Setup** (first run, and reachable from Settings): provider cards with plain-language pros and cons (cost, privacy, speed); key entry or Ollama check; "Test connection" with a clear pass or fail; a "Which should I choose?" helper.
2. **Home / Workspace**: drop zone, file list with health badges, "Run" button, recent runs.
3. **Run progress**: per-file and per-slide progress, current status, cancel, resume. Updates are announced to screen readers.
4. **Results**: file summary, slide-by-slide before/after, integrity line, downloads.
5. **Notes / Report**: the fix notes for a file.
6. **Files**: manage inputs, outputs, reports; delete with confirmation.
7. **Settings**: advanced options and workspace location.

## 10. Accessibility requirements (acceptance criteria)

- Fully operable by keyboard; logical tab order; visible focus; no keyboard traps.
- Semantic HTML: landmarks, headings, labeled form controls, real buttons and links.
- Live regions announce progress, errors and completion; drag-and-drop has a button equivalent.
- Color contrast at least 4.5:1 for text and 3:1 for UI; never rely on color alone (badges include text and icons).
- Respects `prefers-color-scheme`, `prefers-reduced-motion`, and browser zoom to 200%+ without loss.
- Plain language at about a grade-8 reading level; errors say what happened and what to do.
- Tested with VoiceOver on macOS and an automated checker (axe) on every screen.

## 11. Phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Tag `engine-cappv1-1.0.0`, create `gui` branch, add this plan to the repo | Tag and branch exist |
| 1 | Design: low-fi wireframes and a clickable mockup of all screens; pick framework | Plan owner approves the mockup |
| 2 | Engine refactor: progress events, cancel, and a health-check module with unit tests | CLI behaves identically; health checks pass on good, damaged and missing-part fixture files |
| 3 | Local server and API (`cappv1 ui`), security basics, workspace confinement | API works end to end with a test client; path-escape and token tests pass |
| 4 | Front end: Setup, Home, Run, Results | A new user can go from install to a captioned file with no Terminal editing |
| 5 | Fix notes and report export; integrity verification | Reports are correct on sample files; "only alt text changed" check works |
| 6 | Accessibility pass and polish: keyboard, VoiceOver, axe, contrast, zoom | Section 10 criteria all met |
| 7 | Docs: README section for the GUI, screenshots, updated troubleshooting; release `v1.1.0` | A first-time user succeeds from the README alone |

Each phase ends with a local commit, a short demo or summary, and your approval before the next starts.

## 12. Later options (not planned yet)

- **Shared campus server:** run the same app on one machine for many users. This needs real login, TLS, per-user workspaces, request queueing, and IT approval. Treat it as its own project after v1.
- Manual alt-text editing in the GUI.
- Packaged Mac app.
- Batch folder watching.

## 13. Risks

| Risk | Mitigation |
|---|---|
| Scope creep from "teaching" notes into a full accessibility audit | Keep v1 notes tied to what the tool did and found; audit checks are a later opt-in layer |
| Local web server is reachable by other sites or users | Localhost bind, Host check, session token, no CORS |
| LLM-written advice is wrong or generic | Facts come from code; AI wording labeled; template mode available |
| Large decks block the UI | Background jobs with persisted state; streamed progress |
| Local models are slow and look "stuck" | Honest progress per image, time estimates, clear "first image is slow" message |
| New dependencies make install harder | Minimal dependencies; no Node toolchain; pinned versions |

## 14. Open questions for you

1. **Framework:** FastAPI + Uvicorn (recommended) or stdlib-only?
2. **Workspace location:** inside the project folder (as today) or a user-chosen folder such as `~/cappv1-workspace`?
3. **Notes:** AI-written explanations by default, or no-LLM templates by default with AI as an opt-in?
4. **Manual alt-text editing:** include in v1 or hold for v1.1?
5. **Name and branding:** keep "cappv1" in the UI, or a friendlier product name?
6. **Mockup first:** confirm Phase 1 comes before any server code.
