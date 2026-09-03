# How to Use: PPTX Alt-Text Automation

This is the day-to-day guide for running the tool — no code reading required. For the technical spec, see `product.md`.

## What it does, in one line

You drop PowerPoint files into `input/`, run one command, and get the same files back in `output/` — same filename — with accessibility alt-text automatically written onto every meaningful image. `input/quarterly-review.pptx` becomes `output/quarterly-review.pptx`.

## 1. One-time setup

Do this once per machine.

1. Confirm your API key is in place. Open `.env` (in the project folder) and make sure this line has a real key (it should already be set up):
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
2. Run a health check from any terminal:
   ```
   cappv1 doctor
   ```
   This checks your API key (including a live check against OpenRouter), your Python setup, and your folders, and tells you in plain, colored language if anything needs fixing before you touch a real deck.

That's it. You never need to touch Python, virtual environments, or even `cd` into the project folder — `cappv1` handles all of that.

## 2. The basic workflow (every time you use it)

### Step 1 — Add your PowerPoint files
Drag and drop, or copy, your `.pptx` file(s) into the project's `input/` folder. Any filename works, and you can drop in one file or many at once — every `.pptx` sitting there gets processed.

> Only `.pptx` works (the modern PowerPoint format). Old `.ppt` files need to be re-saved as `.pptx` from PowerPoint first (File → Save As → PowerPoint Presentation).

### Step 2 — Run it
Open a terminal — from anywhere, no `cd` needed — and type:
```
cappv1 start
```
`start` is required — plain `cappv1` on its own just prints the help/usage text, it won't kick anything off. That's deliberate: typing `cappv1 start` is an unambiguous "yes, go" action.

Here's what you'll see, in color, in this order:

1. A quick health check (fast, no network call):
   ```
   cappv1 doctor - environment check

     [✓] .env file found
     [✓] OPENROUTER_API_KEY is set
     [-] API key live check - skipped (--quick)
     [✓] Python environment ready - installed
     [✓] input/ folder is ready
     [✓] output/ folder is ready

   All checks passed - ready to run. Type: cappv1 start
   ```
2. Confirmation that it's running, detached from your terminal:
   ```
   ✓ cappv1 started in background (pid 20195)
   ```
3. **Live, colored progress**, automatically — you don't need to run a separate `tail` command yourself:
   ```
   Live progress - Ctrl+C stops watching, the job keeps running in the background

   12:55:00 INFO [file: quarterly-review.pptx] starting
   12:55:03 INFO [file: quarterly-review.pptx] [████--------------] 1/12 [section: "Financials"] captioned 2/2 images
   12:55:06 INFO [file: quarterly-review.pptx] [████████-----------] 2/12 [section: "Financials"] skipped 1 decorative image, captioned 1/1
   ...
   ✓ [file: quarterly-review.pptx] saved to output/quarterly-review.pptx
   ```
   The `[████--------------]` bar fills in as it works through the slides. `INFO` lines are colored, and the final "saved to" line for each file turns bold green with a ✓ so completions jump out.

`Ctrl+C` at this point only stops *watching* — the actual processing keeps running in the background even after you disconnect, close the terminal, or the view times out. To check on it again later, just re-tail the log file directly (path is printed if the view doesn't auto-attach in time):
```
tail -f /Users/ssharma33/Desktop/cappv1/logs/run-*.log
```

### Step 3 — Get your finished file
Once you see the green `✓ ... saved to output/...` line, your captioned deck is ready — open it straight from `output/`. The original in `input/` is never touched.

### Step 4 — Spot-check it (recommended)
Right-click an image → **Edit Alt Text**, and confirm the caption reads well. The model is good but not perfect — for anything going to an external audience, a quick human skim is worth it.

## 3. The three commands

| Command | What it does |
|---|---|
| `cappv1 start` | Starts processing everything in `input/`, in the background, then shows you live colored progress. This is the one you'll use almost every time. |
| `cappv1 doctor` | Checks your setup — API key (live-verified), Python environment, folders — and prints a colored ✓/✗ report. Safe to run any time, changes nothing. |
| `cappv1 clean` | Wipes `input/`, `output/`, and the tracked run history (`.state/`), so you're starting from a totally empty workspace. **Deletes files — see warning below.** |
| `cappv1` (no args) | Prints the usage/help text above. Does not start anything. |

### `cappv1 doctor`
Run this any time something seems off, or just to confirm you're ready before a big batch:
```
cappv1 doctor
```
```
cappv1 doctor - environment check

  [✓] .env file found
  [✓] OPENROUTER_API_KEY is set
  [✓] API key is valid - verified with OpenRouter
  [✓] Python environment ready - installed
  [✓] input/ folder is ready
  [✓] output/ folder is ready

  2 file(s) waiting in input/

All checks passed - ready to run. Type: cappv1 start
```
If something's wrong, each failing line is marked `[✗]` in red with a plain-English reason. `cappv1 start` runs this same check (a faster version, skipping the live API call) before doing anything else — if it fails, it prints the failure and stops, rather than crashing partway through, and tells you to run `cappv1 doctor` for the full picture.

### `cappv1 clean` ⚠️
```
cappv1 clean
```
```
cappv1 clean

  ✓ removed 3 file(s) from input/
  ✓ removed 3 file(s) from output/
  ✓ cleared 3 tracked run(s) from .state/

Workspace is clean and ready to go - drop files into input/, then run: cappv1 start
```
**This permanently deletes every `.pptx` currently sitting in `input/` and `output/`**, plus their tracked run history — there's no undo. Use it to reset between unrelated batches of decks, not mid-batch. It never touches `logs/`, so your run history there is preserved even after a clean.

## 4. Other ways to run it

`cappv1 start` accepts the same flags as the underlying script, so all of these work:

| What you want | Command |
|---|---|
| Process everything new in `input/` (background + live view) | `cappv1 start` |
| Process just one specific file | `cappv1 start --file "my-deck.pptx"` |
| Preview what *would* happen — no API calls, no files written | `cappv1 start --dry-run` |
| Pick back up on a file that got interrupted partway | `cappv1 start --resume` |
| Run in the current terminal, no backgrounding (blocks until done) | `/Users/ssharma33/Desktop/cappv1/run.sh` |

**When to use `--dry-run`:** before running a big batch of decks for the first time, to sanity-check how many images will be captioned vs. skipped without spending any API calls.

**When to use `--resume`:** if the machine slept, lost power, or you killed the process mid-run. The tool checkpoints after every slide, so just running `cappv1 start` again automatically picks up where it left off instead of starting the deck over — you don't lose progress or pay for images already captioned.

## 5. What happens to different kinds of images

You don't need to sort your images beforehand — the tool figures this out automatically per image:

- **Real content** (charts, photos, diagrams, screenshots) → sent to the model, gets a real descriptive caption.
- **Tiny images** (small icons, bullet graphics, dividers — under ~40px) → automatically skipped, no API call spent.
- **Repeated images** (the same logo/icon appearing on multiple slides) → captioned once, then reused everywhere else it appears, so you're not paying to caption the same logo 20 times.
- **Genuinely decorative images** (background textures, purely visual dividers with no informational content) → the model itself recognizes these and marks them as decorative (empty alt-text), which is the correct, accessible thing to do — PowerPoint's own "Mark as Decorative" does the same.

## 6. Checking on a run

- **Is it still running?** `ps aux | grep run.sh`
- **Live/full progress**: `tail -f /Users/ssharma33/Desktop/cappv1/logs/run-*.log` — every run writes a timestamped log here (e.g. `run-20260903-122604.log`), colored and with per-slide progress bars, so history is kept across runs, not just the current one.
- **Startup problems**: `cat /Users/ssharma33/Desktop/cappv1/logs/cappv1-launcher.log`, or just run `cappv1 doctor`.
- **Per-file status**: `.state/<filename>.pptx.json` tracks whether each file is `in_progress` or `complete`. You don't need to open these — the tool reads and updates them automatically — but they're there if you're curious why a file did or didn't get reprocessed.

## 7. Troubleshooting

| Symptom | What's going on | Fix |
|---|---|---|
| `cappv1: command not found` | The `~/.local/bin/cappv1` symlink is missing or `~/.local/bin` isn't on your `PATH` | Run `ln -sf /Users/ssharma33/Desktop/cappv1/bin/cappv1 ~/.local/bin/cappv1`, then open a new terminal |
| Typing `cappv1` alone just prints help and nothing happens | Expected — `start` is required | Type `cappv1 start` |
| `cappv1 start` says "Not ready to run yet" | A quick check failed (usually the API key) | Run `cappv1 doctor` for the full picture and a plain-English reason |
| `No .pptx files in input/ yet` | `input/` is empty — nothing to process | Drop a `.pptx` file into `input/`, then run `cappv1 start` again |
| A file logs `already complete, skipping` (shown dimmed/gray) | The tool already fully processed this file in a previous run | Either that's expected (nothing changed), or run `cappv1 clean` to reset and reprocess everything |
| `caption generation failed permanently` for a specific image | The API call failed 3 times in a row (rate limit, network blip, temporary outage) | Alt-text is left blank for that image; just run `cappv1 start` again — it'll retry only what's missing |
| A whole file fails and gets skipped | The `.pptx` is corrupted or not a valid PowerPoint file | Re-save the file from PowerPoint and drop it back into `input/` |
| Terminal shows raw codes like `[36m` instead of color | Your terminal/log viewer doesn't interpret ANSI color codes (e.g. some editors, or piping to a file) | View it in a normal terminal with `tail -f`; colors are automatically disabled when output isn't a real terminal |

## 8. Quick reference

```
# 0. is everything set up?
cappv1 doctor

# 1. drop .pptx files into:
/Users/ssharma33/Desktop/cappv1/input/

# 2. from anywhere, run:
cappv1 start

# (live progress shows automatically; to reattach later:)
tail -f /Users/ssharma33/Desktop/cappv1/logs/run-*.log

# 3. collect finished files (same names as input) from:
/Users/ssharma33/Desktop/cappv1/output/

# reset the workspace between batches (deletes input/output/state):
cappv1 clean
```
