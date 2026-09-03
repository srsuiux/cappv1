# PPTX Alt-Text Captioner

Automates accessibility alt-text generation for images in PowerPoint decks using a vision-capable LLM (Claude, via OpenRouter).

## 1. Problem

Images in `.pptx` files usually ship with no (or bad) alt-text, which breaks screen-reader accessibility. Writing alt-text by hand for every image in every deck doesn't scale. This tool watches an `input/` folder, processes every deck automatically, and writes an `output/` folder with the same decks — image content unchanged, alt-text filled in.

## 2. Goals

- Drop `.pptx` files into `input/`, get the same files in `output/` with alt-text populated on every meaningful image.
- Use slide context (title, body text, notes) so captions describe *why the image is there*, not just what's in it.
- Handle large decks without loading everything into memory at once — process in chunks, log progress as it goes, and survive a crash without starting over.
- Skip decorative images (logos, icons, background shapes) instead of forcing a caption on them.

## 3. Non-Goals (v1)

- No editing of image content, slide layout, or text.
- No UI — this is a CLI/script tool.
- No support for `.ppt` (legacy binary format) — `.pptx` (OOXML) only.
- No multi-user/queue system — single machine, single run at a time.

## 4. High-Level Flow

```
input/*.pptx
     │
     ▼
┌─────────────────┐
│ 1. Discover      │  scan input/, skip already-completed files (via output/ + state log)
└────────┬─────────┘
         ▼
┌─────────────────┐
│ 2. Parse         │  open pptx, walk slides, group by PowerPoint "section" if present
└────────┬─────────┘
         ▼
┌─────────────────┐
│ 3. Extract       │  per slide: pull images + slide title/body/notes as context
└────────┬─────────┘
         ▼
┌─────────────────┐
│ 4. Filter        │  drop decorative/tiny/duplicate images (icons, logos, hash dupes)
└────────┬─────────┘
         ▼
┌─────────────────┐
│ 5. Caption       │  send image + context to Claude (via OpenRouter), chunked/batched
└────────┬─────────┘
         ▼
┌─────────────────┐
│ 6. Write-back    │  set alt-text (descr) on each picture shape's XML
└────────┬─────────┘
         ▼
┌─────────────────┐
│ 7. Save + Log    │  write to output/, append progress/state, move to next slide/file
└──────────────────┘
```

Processing unit is **one slide at a time**, not the whole deck — this is the "chunk." Since sections/pages don't share images in practice, each slide's images can be captioned independently and in parallel, and a crash mid-deck only loses the in-progress slide, not the whole file.

## 5. Architecture

```
cappv1/
├── input/                  # user drops .pptx files here
├── output/                 # finished .pptx files land here, same filename as input
├── .state/                 # per-file progress (json) so a rerun resumes instead of restarting
├── .env                    # OPENROUTER_API_KEY=... (gitignored, never committed)
├── bin/
│   └── cappv1               # symlinked onto PATH (~/.local/bin/cappv1); subcommands below
├── run.sh                   # sets up/activates .venv, then runs python -m src.main "$@"
├── src/
│   ├── main.py              # CLI entrypoint
│   ├── config.py            # env/config loading, model name, concurrency, thresholds
│   ├── pipeline.py           # orchestrates discover → parse → caption → write → save
│   ├── pptx_reader.py         # python-pptx wrapper: slides, sections, images, context text,
│   │                          # and alt-text (descr attribute) read/write
│   ├── image_filter.py        # decorative/tiny/duplicate detection (perceptual hash + size)
│   ├── llm_client.py           # OpenRouter API client (vision request, retries, backoff)
│   ├── state.py                # per-file progress tracking, resume support
│   └── doctor.py                # stdlib-only setup diagnostics for `cappv1 doctor`
├── logs/                    # per-run logs (run-<timestamp>.log) + cappv1-launcher.log
├── requirements.txt
└── product.md
```

## 6. Tech Stack

| Concern | Choice | Why |
|---|---|---|
| PPTX read/write | `python-pptx` | Standard library for OOXML; gives shape/image/text access and lets us set `descr` directly |
| LLM access | OpenRouter API (OpenAI-compatible `/chat/completions`) | User has no direct Anthropic API key but does have OpenRouter, which proxies Claude |
| Model | `minimax/minimax-m3:free` (configurable) | Vision-capable, free tier - the account's OpenRouter key is free-tier and paid Claude models 402'd; swap to `anthropic/claude-sonnet-5` (or another paid model) via config once credits are added, for higher caption quality |
| HTTP | `httpx` (async) | Lets slide-level captioning run concurrently with a bounded pool |
| Image hashing (dedup) | `imagehash` + `Pillow` | Detect the same logo/icon repeated across slides so it's captioned once |
| Logging | stdlib `logging`, rotating file handler + stdout | Real-time progress visibility during long runs |
| Config | `.env` via `python-dotenv` | Keeps the API key out of source and out of `product.md`/git |

## 7. Detailed Pipeline

### 7.1 Discover
- Scan `input/` for `*.pptx`.
- For each file, check `.state/<filename>.json`. If it exists and is marked `complete`, skip (idempotent reruns). If it exists and is `in_progress`, resume from the last completed slide index.

### 7.2 Parse & Section Grouping
- Open with `python-pptx`.
- PowerPoint's "Sections" (the ones visible in the Slide Sorter view) aren't exposed by `python-pptx` directly — they live in `presentation.xml` under `<p:sectionLst>`. Parse that XML directly to map slide index → section name. Used only for logging/grouping ("Section 'Intro' — slide 3/5 done"), not for caption context.

### 7.3 Extract (per slide)
For each slide:
- Pull every `Picture` shape (`shape.shape_type == MSO_SHAPE_TYPE.PICTURE`), plus images inside grouped shapes.
- Build slide context: title placeholder text, body placeholder text, speaker notes (`slide.notes_slide`), and the section name from 7.2.

### 7.4 Filter
Skip captioning (leave alt-text blank or mark `decorative`) when:
- Image is below a size threshold (e.g. < 40x40 px) — almost always a bullet icon or divider.
- Image's perceptual hash matches one already captioned in this file — reuse the existing caption instead of a new API call.
- Image is in a background/master slide layout, not the slide content itself.

### 7.5 Caption (LLM call)
- Build a prompt: system instructions on WCAG-style alt-text (concise, describes content *and* function, avoid "image of…", target ~125 characters, no redundant restating of adjacent slide text) + the slide context from 7.3 + the image as base64.
- Call OpenRouter's chat completions endpoint with the configured Claude model, `images` content block.
- Run slide-level caption batches concurrently (bounded `asyncio.Semaphore`, default 4) rather than one image at a time — keeps large-deck runtime reasonable without hammering the API.
- Retry on 429/5xx with exponential backoff (max 3 attempts); on permanent failure, log and leave that image's alt-text blank rather than failing the whole file.

### 7.6 Write-back
- For each captioned picture, set the `descr` attribute on the shape's `<p:nvPicPr><p:cNvPr>` element (this is what `python-pptx`'s `shape.name`/accessibility fields map to — PowerPoint reads this as the alt-text field).
- Leave image bytes, position, and formatting untouched.

### 7.7 Save + Progress
- After each slide finishes, update `.state/<filename>.json` with the completed slide index (this is the resume checkpoint).
- After all slides in a file finish, save the deck to `output/<filename>.pptx` and mark state `complete`.
- Log per-slide and per-image progress, colorized, to both stdout and `logs/run-<timestamp>.log` (see §9 for the color/progress-bar mechanics):
  ```
  [file: quarterly-review.pptx] [████--------------] 4/12 [section: "Financials"] captioned 2/2 images
  [file: quarterly-review.pptx] [██████████---------] 5/12 [section: "Financials"] captioned 0, decorative 1, cached 0, failed 0 (of 1 images)
  ✓ [file: quarterly-review.pptx] saved to output/quarterly-review.pptx
  ```

## 8. Config & Secrets

- `OPENROUTER_API_KEY` loaded from `.env`, never hardcoded, never written into logs or state files. `.env` and `keys.txt` are both gitignored.
- Other config in `.env` / `config.py`: `MODEL` (default `minimax/minimax-m3:free`), `CONCURRENCY` (default 4), `MIN_IMAGE_SIZE_PX` (default 40), `MAX_ALT_TEXT_CHARS` (default 125).

## 9. CLI

`run.sh` wraps `python -m src.main` and creates/activates the `.venv` automatically on first run. `bin/cappv1` is symlinked onto `PATH` (`~/.local/bin/cappv1`) as a subcommand dispatcher requiring an explicit subcommand:

| Command | Behavior |
|---|---|
| `cappv1 start [--file/--resume]` | Runs `src/doctor.py --quick` as a pre-flight (env/key present, folders writable); on failure, prints the failing checks and exits without launching anything — no raw traceback. If `input/` has no `.pptx` files, prints a one-line message and exits. Otherwise launches `run.sh` detached (`nohup … &`), then auto-attaches (`tail -f`) to that run's fresh `logs/run-<timestamp>.log` once it appears (polls up to 30s, to cover first-run venv bootstrap) so progress is visible immediately without a separate command. `Ctrl+C` stops only the attached view (`disown`ed job keeps running). |
| `cappv1 doctor` | Runs `src/doctor.py` (stdlib-only, works even without `.venv`): checks `.env`, key presence, a **live** OpenRouter key validation (`GET /api/v1/auth/key`), venv/dependency health, and folder writability. Prints a colored ✓/✗ report; exit code reflects pass/fail. |
| `cappv1 clean` | Deletes every `.pptx` in `input/` and `output/` plus all `.state/*.json`, printing a ✓ summary of what was removed. Leaves `logs/` untouched. |
| `cappv1` (no args) / unknown subcommand | Prints usage and exits — does **not** start anything. `start` must be typed explicitly. |
| `./run.sh [flags]` | Same pipeline, foregrounded (blocks, prints directly to terminal) instead of backgrounded — useful when actively watching a run. |

**Progress display**: each per-slide log line embeds an inline bar (`pipeline.progress_bar()`, e.g. `[████--------------] 3/12`) rather than a redrawing/in-place terminal bar — this keeps it equally readable live (`tail -f`) or as static history in the log file. Output is colorized via a custom `logging.Formatter` (`_ColorFormatter` in `src/pipeline.py`): colored by log level (INFO cyan, WARNING yellow, ERROR red), with message-aware overrides (`saved to` → bold green with ✓, `already complete`/`nothing to process` → dim gray). The **console** handler colors only when `sys.stdout.isatty()` (so output redirected/piped, e.g. under `nohup`, stays plain); the **file** handler (`logs/run-<timestamp>.log`) is always colored, since it's meant to be tailed live in a terminal rather than opened in a plain-text editor.

Output files keep the same filename as their input (`input/x.pptx` → `output/x.pptx`).

See `how-to-use-this-automation.md` for the user-facing walkthrough.

## 10. Error Handling

- Corrupt/unreadable `.pptx` → log error, skip file, continue with the rest of `input/`.
- Single image caption failure → log, leave blank, continue deck.
- API key missing/invalid → fail fast at startup with a clear message, before touching any files.
- Partial run (crash, kill) → next run picks up from `.state/` at the last completed slide.

## 11. Open Questions / Future Enhancements

- Batch multiple images from the same slide into a single LLM call (one request, multiple images) to cut API calls further, if the chosen model supports multi-image messages well.
- Optional human review step: dump a CSV/HTML of `slide → image → generated caption` for spot-checking before trusting output/ wholesale.
- Support `.ppt` via LibreOffice conversion pass before the pipeline.
- Swap-in a cheaper/faster model for a first pass and Claude only for a review pass, if cost becomes a concern on very large batches of decks.
