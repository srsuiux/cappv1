# cappv1: portfolio brief

**Purpose of this file.** Everything needed to present cappv1 on a portfolio site: a project card, a project details (case study) page, an app page, and a marketing landing page. It is written so that another Claude instance, with no other context, can build all four. Facts here were checked against the repository at **v1.2.0 (27 Oct 2026)**. Where something is not built, not tested, or unknown, this file says so. Do not fill gaps with invented numbers, quotes, users or benchmarks.

Repository: https://github.com/srsuiux/cappv1 · License: MIT · Owner: Sundar Raj Sharma (GitHub `srsuiux`)

---

## 0. Instructions for the builder

Deliverables, in order of importance:

1. **Project card** (listing tile on the portfolio). Fields in section 1.
2. **Project details page** (case study: problem, decisions, architecture, outcomes, what is unfinished). Material in sections 2 to 9 and 14.
3. **App page** (a product page inside the portfolio, `…/apps/cappv1`: what it is, install, commands, status board, changelog, links). Material in sections 3 to 8, 10 to 12.
4. **Marketing landing page** (public pitch for people who have never heard of it). Copy and structure in section 13.

Rules for all four:

- **Status is shown per component**, using exactly these four labels: `Stable release`, `In progress`, `Planned`, `Not started`. The board is in section 2. Do not upgrade a status.
- **Be honest.** Use only the facts below. No user counts, testimonials, benchmarks, awards or "trusted by". The tool is new (first release tags 26 to 27 Oct 2026).
- **Accessibility is the subject of this project**, so the pages you build must be accessible: semantic HTML, one `h1`, labelled controls, visible focus, 44px touch targets, text contrast of at least 4.5:1 in light and dark, respect `prefers-reduced-motion`, working at 320px width and 200% zoom, no information by color alone, alt text on every image (you can write good alt text; that is the point).
- **Light and dark mode are required**, with System / Light / Dark choice if the page has a theme control. Tokens are in section 9.
- **No tracking.** cappv1 promises no analytics. If the portfolio adds analytics to these pages, that must be stated on the page. Prefer none.
- Do not copy the in-app pages verbatim into a different promise: the in-app Privacy page describes the software; the marketing page may summarise it and link to the repository.

---

## 1. Project card data

```yaml
name: cappv1
tagline: Alt text for every slide, written for you.
one_liner: >
  Open-source tool that writes alt text for the pictures, charts and tables in
  PowerPoint files, using vision AI that can run entirely on your own computer.
status: Stable release          # overall; per-component board in section 2
version: 1.2.0
released: 2026-10-27
license: MIT
type: Open-source developer tool / accessibility
platforms: [macOS, Linux]       # Windows not supported yet
language: Python 3.11+
interfaces: [Terminal session, Local web UI, Batch CLI]
ai_services: [Ollama (local, private), OpenRouter, OpenAI, Anthropic]
tags: [accessibility, a11y, PowerPoint, alt text, screen readers, LLM, vision models, privacy, Python, open source]
links:
  repo: https://github.com/srsuiux/cappv1
  issues: https://github.com/srsuiux/cappv1/issues
  changelog: https://github.com/srsuiux/cappv1/blob/main/CHANGELOG.md
  license: https://github.com/srsuiux/cappv1/blob/main/LICENSE
card_image: needs a screenshot (see section 12); the favicon is a placeholder only
card_highlights:
  - Never changes anything in a deck except alt text
  - Runs fully offline and private with Ollama
  - Crash-safe: resumes where it stopped, never pays twice for the same slide
  - Terminal and browser interfaces over one shared core
```

---

## 2. Status board (use these exact labels)

Labels: `Stable release`, `In progress`, `Planned`, `Not started`.

| Component | Status | Since | What "status" means here | Caveat to show |
|---|---|---|---|---|
| **Engine** (reads decks, calls the AI, writes alt text, resumes) | **Stable release** | engine v1.0.0 (tag `engine-cappv1-1.0.0`, 26 Oct 2026); hardened in v1.1.0 | Tested by automated suite; used for real decks | AI output can be wrong; always review |
| **Service layer** (settings, models, files, runs, health, storage) | **Stable release** | v1.2.0 | Plain Python functions shared by both interfaces; unit and API tested | none |
| **Terminal UI (TUI)** (slash-command session, live animated run view) | **Stable release** | v1.1.0 | Interactive session with menus, live progress, context-aware animations | Tested by hand and a scripted pseudo-terminal, not by a screen reader |
| **Batch CLI** (`cappv1 --batch`) | **Stable release** | v1.0.0 | Non-interactive run for scripts | none |
| **Web server and API** (`/api/v1`, SSE progress) | **Stable release** | v1.2.0 | Standard-library server, localhost only, token auth, 114-test suite covers it | Local use only by design; not for hosting |
| **Web UI** (front page, Files, Services, Health, Your data, info pages, themes) | **Stable release** | v1.2.0 | Used in Chrome end to end; contrast tested in both themes | **Not yet audited with VoiceOver or other screen readers** (planned) |
| **Project and docs** (README, API, architecture, security policy, templates, CI) | **Stable release** | v1.2.0 | Open-source hygiene in place | GitHub Release pages not yet created |
| **File health check** (detect damaged or partial decks, verify only alt text changed) | **Planned** (next) | n/a | Designed in `docs/web-ui-plan.md` section 7 | Not built |
| **Accessibility polish and screen-reader audit** | **Planned** | n/a | Keyboard, VoiceOver, axe, zoom pass | Not done |
| **npm package** (`npx cappv1` launcher that checks Python 3.11+, prepares the environment, starts cappv1) | **Not started** | n/a | Proposed, in scope for distribution; no `package.json` exists | Must not be advertised as available |
| **PyPI package / Homebrew formula** | **Not started** | n/a | Proposed alternative distribution | Today install is `git clone` |
| **Windows support** | **Not started** | n/a | README says "Windows isn't supported yet" | n/a |
| **Public showcase site and landing page** | **In progress** | n/a | This brief exists so the portfolio can build it | n/a |
| **Shared campus or team server** | **Not started** (idea only, not planned) | n/a | Discussed, deliberately out of scope | Do not present as a feature |

Overall project status line for the card: **Stable release, v1.2.0**, with the web UI's screen-reader audit and the file health check still ahead.

---

## 3. What it is

### The problem
Screen readers read a slide's pictures, charts and tables aloud only if they have **alt text**. Most decks have little or none, and writing it for every item in a long deck is slow, so it often doesn't happen. A blind or low-vision student, colleague or audience member then gets silence, or just "Chart".

### The product
cappv1 reads a `.pptx`, sends each picture, table, chart, diagram and embedded object (with the slide's title, text and notes for context) to a vision-capable AI model, and writes the answer into that shape's alt-text field: the same field PowerPoint's own **Edit Alt Text** panel uses. The result is saved as a separate finished copy. Nothing else in the file changes.

### Who it is for
- Instructors, instructional designers and accessibility staff who prepare slides for students who use assistive technology.
- Anyone required to meet accessibility rules for presentations (a conformance or institutional requirement), who wants a fast first draft to then review.
- People who handle sensitive material and need the AI to run locally.
- Developers who want an open, small, readable example of a local-first AI tool.

### What makes it different (claims that are true)
1. **Strict scope.** The only field it ever writes is alt text. Layout, text, fonts, pictures and slide order come out byte-for-byte equivalent in what you see. Originals are never modified. (Enforced as the project's one rule, `skills.md`.)
2. **Private mode.** With Ollama the AI runs on your computer. No slide content leaves it, and it works offline after the model is downloaded.
3. **Respects authors.** If someone already wrote alt text, cappv1 keeps it or improves it; it replaces nothing unless asked (`--force`, with confirmation).
4. **Crash-safe and thrifty.** Progress and written alt text are saved as it goes. A repeat run, a stopped run or an edited deck only pays for what is new or changed.
5. **Honest about data.** In-app Privacy page states exactly what is sent and stored, and an automated test keeps the page in step with the code.
6. **One core, two front ends.** The terminal and the browser use the same service layer, see the same run, and never disagree.
7. **Accessible itself.** Built with Atkinson Hyperlegible (designed for low-vision readers), keyboard operable, light and dark themes with tested contrast.

### What it is not
- Not a guarantee of accurate descriptions. Review is part of the workflow.
- Not a hosted service or an account-based product. There is no server of its own.
- Not a PowerPoint add-in. It processes files.
- Not WCAG-certified, not audited by a third party, not tested with every screen reader.

---

## 4. Feature inventory

### Engine
- Describes **pictures, tables, charts, SmartArt diagrams and embedded OLE objects** (Word, Excel, Visio).
- Marks provably invisible shapes (no fill, no outline, no text) as **decorative**, like PowerPoint's own "Mark as decorative"; also tiny pictures below a size threshold (`MIN_IMAGE_SIZE_PX`, default 40) when no author text exists.
- Pictures are sent as images; tables, charts and objects as text. Context sent with each item: slide title, section name, slide text, speaker notes, and any existing alt text.
- Alt text length capped (`MAX_ALT_TEXT_CHARS`, default 125).
- **Existing alt text policy:** under 30 characters (`MIN_EXISTING_ALT_CHARS`) counts as unfinished and is improved; longer text is kept if the model judges it adequate (it replies `KEEP`), otherwise improved while building on the author's wording; a bare file name like `image1.png` counts as empty. `--force` replaces everything (asks first).
- **Caching and identity:** per-deck state in `.state/`, content-hash identity for decks (statuses `done`, `changed`, `partial`, `new`), caption cache keyed by exact content hash (SHA-256 of picture bytes; hashes of table, chart, object content), author-text hash included in the key.
- **Crash safety:** atomic writes (temporary `.part` then replace), tolerant state loading (a corrupt state file is set aside as `*.corrupt`), resume re-walks every slide and reapplies saved captions, finished decks saved one by one.
- **Providers:** OpenRouter, OpenAI, Anthropic, and Ollama via its OpenAI-compatible endpoint. Primary plus fallback model, retries, concurrency (default 4 requests at a time, 1 for Ollama).
- **Private-mode guard:** Ollama address must be local unless `OLLAMA_ALLOW_REMOTE=1`.
- Progress **event bus** (`file_start`, `file_open`, `slide_start`, `element_start/end`, `alt_written`, `slide_end`, `file_saving`, `file_saved`, `file_failed`, `file_skipped`, `run_done`, `run_empty`) that any interface can subscribe to.

### Service layer (`src/services`)
- `settings` (service, model, keys, never returns a key), `models` (curated lists; live OpenRouter catalog with free, cheapest and by-maker views; Ollama vision models), `files` (validated safe storage, listing, download, clean), `runs` (one run at a time, start, stop, resume, event log), `health` (environment checks), `storage` (what is kept, where, erase), `workspace` and `envfile`.
- Errors are `ServiceError(code, message, fix)`: every failure has plain words and a next step.

### Terminal UI
- `cappv1` opens a Claude-Code-style session with a `❯` prompt, slash-command completion, a status toolbar, drag-a-file-in to add decks.
- Commands: `/run` (`--resume`, `--force`), `/files`, `/init`, `/models`, `/web` (`/web stop`), `/doctor`, `/status`, `/open`, `/clean`, `/clear`, `/help`, `/exit`.
- **Live run view** with context-aware animations (looking at a picture, reading a chart, saving the deck), menus with keyboard selection, spinners during checks. Animations off with `CAPPV1_NO_ANIMATION=1` or `NO_COLOR`.
- `/init` shows the current service and model first; it ends by offering to continue in the browser or the terminal. `/models` goes straight to service and model choice; each service remembers its last model.
- Shell has exactly one command: `cappv1` (plus `--batch`, `--version`, `--help`, `--web`); everything else is slash commands inside.

### Web server and API (`src/web`)
- Standard-library `http.server` (no framework), bound to `127.0.0.1`, port 8765 with fallback to the next free port.
- Security: per-launch random token required on every API call (`X-Cappv1-Token`), `Host` header allowlist (DNS rebinding), no CORS, strict Content-Security-Policy (no inline script or style, nothing from outside), streamed size-limited uploads (200 MB) validated as real `.pptx`, safe file names, path-escape tests.
- JSON API under `/api/v1` (list in section 11); live progress via Server-Sent Events that resume from `Last-Event-ID`.
- Pages are fragments wrapped in a layout by the server (no build step).

### Web UI
- **Front page `/`:** introduction (before/after demo, three steps, private versus cloud, "careful with your files") and an **Overview** (next-step bar, five stat tiles, panels for AI service, Health, Your data). New visitors see the introduction first; once cappv1 is set up and has files, the Overview moves to the top and the introduction below it. Full-width.
- **Files:** drag or choose decks, per-file state (New, Unfinished, Edited since last run, Done), run, **live feed of the alt text being written**, stop after this slide, download results, remove files, "replace alt text that people already wrote" option.
- **Services:** choose service, model (including OpenRouter free, cheapest and by-maker lists) and key; each service says what it does with slides and links to its privacy policy; real key check before saving; remove a saved key.
- **Health:** the same checks as the terminal with plain-language fixes.
- **Your data:** where everything is stored, sizes, and an erase button (two-step).
- **Information pages:** How it works, Privacy, FAQ, About (includes accessibility statement and credits).
- **Themes:** System / Light / Dark switch in the side panel, remembered and applied before first paint.
- Responsive: sidebar collapses to a Menu button on small screens.

---

## 5. How it works (flow, good for a diagram)

1. You add `.pptx` decks. cappv1 stores a copy; your originals stay where they are.
2. For each slide it finds pictures, tables, charts, diagrams, embedded objects.
3. For each item it checks the cache (same bytes already described? reuse). If not, it asks the chosen AI model, passing the item plus slide context. If the author already wrote text, the model decides to keep it or improve it.
4. The answer is written into that shape's alt-text (`descr` attribute on `cNvPr`), the only write path into the file.
5. The deck is saved atomically as a finished copy in `output/`. Progress is saved after each slide.
6. You review the alt text in PowerPoint (right-click, Edit Alt Text) and download or open the output.

## 6. Architecture

```
  terminal (src/tui)        browser (src/web)
            \                 /
        services (src/services)       settings, models, files, runs, health, storage
                    |
        engine (src/pipeline.py and friends)   reads decks, calls the AI, writes alt text
```

- Each layer depends only on the one below it. The engine is a library; the only network boundary is browser to local web server.
- The terminal and the web server share one `RunManager`, so a run started in one is visible in the other.
- Repo layout: `src/` (engine modules, `services/`, `tui/`, `web/` with `pages/`, `templates/`, `static/`), `tests/`, `docs/` (API.md, ARCHITECTURE.md, web-ui-plan.md, this brief), `bin/cappv1` launcher, `run.sh`, `.github/` (CI, issue and PR templates), `skills.md` (the one rule), `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE`.
- **Stack:** Python 3.11+; `python-pptx`, `httpx`, `Pillow`, `ImageHash`, `olefile`, `python-docx`, `python-dotenv`, `rich`, `prompt_toolkit`; tests with `pytest`. Web front end is plain HTML, CSS and JavaScript (ES modules), no framework, no build step, no external requests. Font: Atkinson Hyperlegible (SIL OFL), bundled.

## 7. Quality and size (approximate, as of v1.2.0)

- **114 automated tests**, run in CI (GitHub Actions) on Python 3.11, 3.12 and 3.13.
- Tests cover: service layer, existing-alt-text behavior, resume and crash recovery, the web API (token, Host check, path escape, upload limits, error shape, SSE replay), page content policy (no inline script or style), every internal link resolving, theme contrast of every color pair in both themes, no one-sided border strokes, and the Privacy page matching what the code actually sends.
- About 4,200 lines of Python (engine ≈ 1,500; services ≈ 700; terminal ≈ 1,050; web server ≈ 500), ≈ 1,100 lines of HTML, CSS and JS across 10 pages, ≈ 900+ lines of tests. Present these as approximate.
- 65 commits in history at v1.2.0; first commit 3 Sep 2026.

## 8. Privacy and data facts (authoritative; reuse wording carefully)

- **What cappv1 collects:** nothing. No account, analytics, telemetry or cookies. The web page keeps one random code in the browser tab's session storage (forgotten when the tab closes). Theme choice and a "has used it" flag are stored in the browser's local storage.
- **What is sent to a cloud AI service** (only if one is chosen): for a picture, the picture; for a table, its text; for a chart, its text and numbers; for every item, the slide's title, section name, slide text, speaker notes, any alt text already there, and cappv1's instructions. **Not** sent: the whole file, other slides, file names.
- **Per service:** Ollama: nowhere (local). OpenRouter: to OpenRouter, which forwards to the model's provider; free models may log. OpenAI and Anthropic: to their APIs. Their own privacy policies then apply. API keys are sent only to the service they belong to.
- **Stored locally in one folder:** `input/` (copies of decks), `output/` (finished decks), `.state/` (progress and written alt text), `logs/` (file names, slide counts, errors, not slide content), `.env` (settings and keys, owner-only permissions). Relocatable with `CAPPV1_HOME`.
- **Other network use:** key validation against the chosen service; OpenRouter's public model list (no key, no slide content); the first install downloads Python packages from PyPI. No update checks, no error reporting.
- **Web page reach:** `127.0.0.1` only; unreachable from other devices; new random token each launch.
- **Controls:** erase from the Your data page; remove keys from Services; delete the folder to remove everything.

## 9. Design system (for pages that should look like cappv1)

Principles: calm, paper-like, flat. Whole subtle 1px borders on boxes; **no colored bar down one side of anything**; no gradients, no shadows, no all-caps labels, sentence-case copy; one accent color; status always has words and an icon, never color alone. One memorable element: the before/after demo (what a screen reader says without alt text, then with it).

Type: **Atkinson Hyperlegible** 400 and 700 (bundled woff2 in `src/web/static/fonts/`, SIL OFL; credit Braille Institute). Fallback `system-ui, sans-serif`. Base 17px/1.6; h1 about 1.75rem; hero heading up to 3rem, tight tracking; body measure about 62ch.

Radius 6px (`--r`). Targets at least 44px. Focus ring: 3px solid accent, 2px offset.

| Token | Light | Dark |
|---|---|---|
| paper (page) | `#fbfcfe` | `#10151e` |
| tint (panels, sidebar) | `#eef2f9` | `#1a2231` |
| ink (text) | `#17202e` | `#eef2f9` |
| muted | `#4b5668` | `#a9b4c6` |
| line (borders) | `#d3d9e4` | `#2b3650` |
| blue (accent) | `#1b4fd6` | `#7ea2ff` |
| blue-ink (text on accent) | `#ffffff` | `#10151e` |
| ok | `#0b6b45` | `#5fd3a0` |
| warn | `#7a4f00` | `#f0c15c` |
| bad | `#a6261c` | `#ff8f84` |

All text pairs in this table meet at least 4.5:1 (verified by a test in the repo). Dark follows the device unless the person chooses; light is the default. Favicon: blue rounded square with a white picture frame and caption bar (`src/web/static/favicon.svg`).

Demo content (use as the hero visual): a five-bar chart titled "Enrolment by year". Without alt text a screen reader says "Chart." With cappv1: "Bar chart of enrolment by year, rising from 410 in 2021 to 640 in 2025." (This is an illustrative example, not a measured result; label it as an example.)

## 10. Install and usage (accurate as of v1.2.0)

Needs: macOS or Linux, Python 3.11+, and either an API key (OpenRouter has free models; OpenAI and Anthropic are paid, a fraction of a cent per image) or Ollama for fully local use.

```
git clone https://github.com/srsuiux/cappv1.git
cd cappv1
cp .env.example .env            # choose PROVIDER, paste a key (Ollama needs none)
mkdir -p ~/.local/bin
ln -sf "$(pwd)/bin/cappv1" ~/.local/bin/cappv1
cappv1                          # opens the session; /init walks through setup
```

Then: drag `.pptx` files into the window, type `/run`, collect results in `output/` (or `/web` for the browser). First launch installs dependencies once. `cappv1 --web [--port N] [--no-open]` runs only the browser interface.

Config (`.env`): `PROVIDER`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MODEL`, `FALLBACK_MODEL`, `CONCURRENCY`, `MIN_IMAGE_SIZE_PX`, `MIN_EXISTING_ALT_CHARS`, `MAX_ALT_TEXT_CHARS`, `OLLAMA_BASE_URL`, `OLLAMA_ALLOW_REMOTE`, `REQUEST_TIMEOUT`; workspace `CAPPV1_HOME`; display `CAPPV1_NO_ANIMATION`, `NO_COLOR`.

Default models: OpenRouter `minimax/minimax-m3:free` (fallback `google/gemma-3-12b-it`); OpenAI `gpt-4o-mini`; Anthropic `claude-haiku-5-5`; Ollama `gemma3:4b` (must be pulled first). Local models are slower than cloud services (seconds to a minute per image) and plainer; say so.

## 11. API summary (for a "developers" section; full doc is `docs/API.md`)

All under `/api/v1`, token header `X-Cappv1-Token`, errors as `{"error": {"code","message","fix"}}`.

`GET/PUT /settings` · `POST /settings/test` · `DELETE /settings/keys/<id>` · `GET /services` · `GET /services/<id>/models` · `GET /files` · `PUT /files/<name>` (raw body) · `DELETE /files/<name>` · `GET /files/<name>/download` · `POST /runs` · `GET /runs/current` · `POST /runs/<id>/cancel` · `GET /runs/<id>/events` (SSE) · `GET /doctor` · `GET /storage` · `POST /storage/clear`.

Pages served by the same server: `/`, `/files`, `/services`, `/health`, `/data`, `/how-it-works`, `/privacy`, `/faq`, `/about`.

## 12. Timeline, releases, assets

| Date | Event |
|---|---|
| 3 Sep 2026 | First commit: PPTX alt-text automation with an OpenRouter engine |
| 26 Oct 2026 | Engine tagged `engine-cappv1-1.0.0`; v1.1.0 released (Ollama private mode, terminal session, unified service switching, crash-safe resume, author alt-text handling, MIT license) |
| 26 to 27 Oct 2026 | Service layer, local web server and API, web UI (dashboard and information pages), themes |
| 27 Oct 2026 | **v1.2.0** released (tag `v1.2.0`) |

Release highlights to quote: v1.1.0 added private local mode, the interactive terminal session, crash-safe resume with content-hash identity, building on authors' alt text, and the MIT license. v1.2.0 added the service layer, the local web server and API, and the full web UI with themes, privacy and data controls. Full text in `CHANGELOG.md`.

**Assets that exist:** `src/web/static/favicon.svg`; Atkinson Hyperlegible font files; the demo chart can be rebuilt in HTML/CSS.
**Assets that do not exist yet (capture before building the pages; ask the owner or run the app):** screenshots of the front page (new visitor, light and dark), the in-use Overview, Files mid-run with the live feed, Services, Your data, the terminal session with the live run view, and `/doctor`. Capture from a clean workspace with a small non-sensitive sample deck. Provide light and dark variants and meaningful alt text.

## 13. Page specifications

### 13.1 Project card
Title `cappv1`; status badge `Stable release · v1.2.0`; one-liner from section 1; four chips from the highlights; tags; two links (App page, GitHub). Card image: the before/after demo or the Overview screenshot. No metrics beyond verifiable ones (114 tests, MIT, Python 3.11+).

### 13.2 Project details page (case study)
Suggested order:
1. **Summary:** problem, role (designer and developer), duration (first commit 3 Sep 2026, releases 26 to 27 Oct 2026), stack, status board (section 2).
2. **Problem and audience** (section 3).
3. **Constraints that shaped the design:** the one-write rule; privacy for sensitive slides; non-technical users on campus Macs; no ability to test local models on the author's own machine; must be open source and easy to read.
4. **Key decisions and trade-offs** (use these, they are real):
   - *Engine as a library, not a service.* The only network boundary is browser to local server, which keeps privacy simple and the attack surface small.
   - *A service layer between engine and screens.* Added before the web UI so the terminal and browser can't disagree; the terminal was refactored onto it with tests first.
   - *Standard-library web server, no framework, no build step.* Fewer dependencies to trust, easy to read and audit; pages are fragments wrapped by one layout.
   - *Local-first privacy as a feature, backed by tests.* Ollama private mode; a localhost-only guard; a test that fails if the Privacy page stops matching what the code sends.
   - *Content-hash identity and a caption cache instead of a database.* Decided a database wasn't needed; exact-bytes hashing, atomic writes and tolerant state files cover resume and "don't pay twice".
   - *Build on the author's alt text.* Short text is improved; adequate text is kept; the model must reply `KEEP` to leave text alone.
   - *Accessibility as a product requirement, not polish:* accessible typeface, keyboard use, tested contrast in light and dark, a user-controlled theme.
   - *Scope discipline.* The web UI was deliberately not a data manager: no database, history or file manager. "Your data" only shows what is kept and offers one erase action.
5. **Real problems found and fixed** (good honest content): resume lost earlier captions after a crash and a corrupt state file blocked everything (found by a before/after test; fixed with atomic writes, tolerant loading, re-walk and cache); a perceptual hash let two flat-color images share a caption (fixed by exact-byte hashing); a bare file name such as `image1.png` was mistaken for author text; the terminal toolbar re-hashed every deck on each keystroke; browser testing found small targets (36px raised to 44px) and a missing favicon.
6. **Design** (section 9) with screenshots; the before/after demo as the signature idea.
7. **Outcomes:** what exists and works (section 2), quality numbers (section 7).
8. **What is unfinished and what is next:** file health check, screen-reader audit, npm and other packaging, Windows (section 2 and 14).
9. **Process note (owner's choice to include):** recent development was done with Claude Code as a pair-programming assistant; commits carry a `Co-Authored-By: Claude` trailer. Include or omit at the owner's discretion, but do not hide it if asked.
10. Links: repo, issues, changelog, license, security policy.

### 13.3 App page (`…/apps/cappv1`)
Sections: header (name, tagline, status badge, version, license, buttons Install and GitHub) · what it does in three steps · status board (section 2, with labels) · interfaces (terminal and web, side by side) · private versus cloud services (table) · install (section 10) · commands · privacy at a glance (section 8, link to repo) · FAQ (section 15) · changelog excerpt (v1.2.0 and v1.1.0) · roadmap (Planned and Not started items only) · links. Keep the status board prominent; it is the portfolio's main data point across projects.

### 13.4 Marketing landing page
Goal: a visitor understands in ten seconds what it does, trusts it with their slides, and starts. Primary call to action: **Get cappv1** (GitHub / install section). Secondary: **See how it works**.
Order: hero (headline, subhead, the before/after demo) → three steps → "You decide where your slides go" (private versus cloud) → "Careful with your files" (four promises) → screenshots (terminal and browser, light and dark) → who it is for → short FAQ → install → footer (MIT, GitHub, privacy, accessibility statement). Use only true claims from section 3.

Copy bank (all true as of v1.2.0):
- Headline: **Alt text for every slide, written for you.**
- Subhead: cappv1 describes the pictures, charts and tables in your PowerPoint files, so people who use screen readers aren't left with silence. Your original files are never changed.
- Three steps: **Add your decks** (Drop in .pptx files. Your originals stay where they are.) · **Choose who describes them** (A model on your own computer, or a cloud service you have a key for.) · **Download the finished copies** (Same slides, now with alt text. Review them before you share.)
- Private: **Stay private.** Use Ollama and everything happens on your computer. Pictures and slide text never leave it, and it works offline once a model is downloaded.
- Cloud: **Use a cloud service.** OpenRouter, OpenAI and Anthropic are faster and often better, but the pictures and text they describe are sent to them. cappv1 always says which one is active.
- Care: It only writes the alt text field. · If someone already wrote alt text, it keeps or improves it. · If a run stops, nothing is lost. · AI can get things wrong, so read the results.
- Meta description (under 160 chars): "Open-source tool that writes alt text for PowerPoint pictures, charts and tables. Runs on your computer; your originals are never changed."
- Open Graph title: "cappv1: alt text for every slide, written for you".

## 14. Roadmap (use the status labels)

| Item | Status | Notes |
|---|---|---|
| File health check: classify decks as healthy, minor issues, damaged before running; skip damaged ones with a plain reason and repair steps | Planned (next) | Also "verify only alt text changed" by comparing original and finished copy |
| Accessibility polish: VoiceOver, keyboard-only and zoom audit, axe | Planned | Ends with a public accessibility statement update |
| npm launcher package | Not started | Thin wrapper; would require Python 3.11+ already installed |
| PyPI / Homebrew distribution | Not started | Would replace `git clone` for non-technical users |
| Windows support | Not started | |
| GitHub Release pages for v1.1.0 and v1.2.0 | Not done | `gh` isn't installed on the dev machine; create from the tags and paste the changelog |
| Real-Ollama test on a second machine | Not done | Local-model path has only been tested against a fake local server |

## 15. FAQ bank (true answers; trim as needed)

- **Does it change my original files?** No. It works from a copy and saves a separate finished file; only alt text changes in it.
- **What files?** `.pptx` up to 200 MB. Older `.ppt` must be saved as `.pptx` first; Google Slides and Keynote can export `.pptx`.
- **What does it describe?** Pictures, tables, charts, SmartArt diagrams and embedded objects; invisible empty shapes and tiny pictures are marked decorative.
- **Are the descriptions accurate?** Usually a good start, not a guarantee. Review them, especially charts with exact figures and anything public or required.
- **Do my slides leave my computer?** Not with Ollama. With OpenRouter, OpenAI or Anthropic, the item being described and the slide's context go to that service. The whole file is never uploaded.
- **What does it cost?** cappv1 is free. Ollama is free to run. OpenRouter has free models. Paid services charge you directly, usually a fraction of a cent per picture; check current prices. Repeat runs cost nothing for slides already described.
- **What if it stops or crashes?** Finished slides are saved; run again and it continues. The finished copy is never left half-written.
- **Can others on my network use it?** No. The web page answers only to the computer it runs on.
- **Works offline?** With Ollama, yes, after the model is downloaded.
- **Does it work on Windows?** Not yet.
- **Is it accessible?** Built for keyboard and screen-reader use with tested contrast and a user-controlled theme; not yet audited with every screen reader (planned).

## 16. Claims to avoid

- No claim of WCAG conformance or certification; no "fully accessible".
- No accuracy rates, speed or cost-saving numbers (none have been measured).
- No user counts, testimonials, institutions or "used by".
- Do not say an npm package, PyPI package, Homebrew formula or Windows build exists.
- Do not say "works offline" without "with Ollama, after the model is downloaded".
- Do not say "no data leaves your computer" without "when using Ollama".
- Do not present the before/after demo as a real measured result; it is an illustrative example.
- Do not add third-party scripts, fonts, analytics or embeds to cappv1 pages without saying so on the page.

## 17. Open questions for the owner (the builder may ask)

1. Where do the pages live, and what builds the portfolio (static HTML, a generator, a framework)?
2. Screenshots: should they be captured now from a clean workspace, in light and dark?
3. Include the "built with Claude Code" process note on the case-study page?
4. A contact or maintainer email for the Privacy and Security pages (currently GitHub only).
5. Whether to publish the GitHub Release pages first so the app page can link to downloads.
