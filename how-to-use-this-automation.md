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
   If this file or key is ever missing, the tool will tell you immediately when you try to run it, rather than failing partway through.

That's it. You never need to touch Python, virtual environments, or even `cd` into the project folder — the `cappv1` command below handles all of that.

## 2. The basic workflow (every time you use it)

### Step 1 — Add your PowerPoint files
Drag and drop, or copy, your `.pptx` file(s) into the project's `input/` folder. Any filename works, and you can drop in one file or many at once — every `.pptx` sitting there gets processed.

> Only `.pptx` works (the modern PowerPoint format). Old `.ppt` files need to be re-saved as `.pptx` from PowerPoint first (File → Save As → PowerPoint Presentation).

### Step 2 — Run it
Open a terminal — from anywhere, no `cd` needed — and type:
```
cappv1
```
That's it. It starts the job in the background and hands your terminal right back:
```
cappv1 started in background (pid 20195)
watch progress: tail -f "/Users/ssharma33/Desktop/cappv1/logs"/run-*.log
startup/errors:  tail -f "/Users/ssharma33/Desktop/cappv1/logs/cappv1-launcher.log"
```
You're free to close that terminal, open other things, or run `cappv1` again later — it keeps working in the background.

**Want to watch it live instead?** Run this once to follow along:
```
tail -f /Users/ssharma33/Desktop/cappv1/logs/run-*.log
```
You'll see progress slide by slide:
```
[file: quarterly-review.pptx] [slide 4/12] [section: "Financials"] captioned 2/2 images
[file: quarterly-review.pptx] [slide 5/12] skipped 1 decorative image, captioned 1/1
[file: quarterly-review.pptx] saved to output/quarterly-review.pptx
```
(`Ctrl+C` just stops watching the log — it does not stop the background job.)

### Step 3 — Get your finished file
Once `output/<same filename>.pptx` shows up, it's done — open it straight from `output/` in PowerPoint. The original in `input/` is never touched.

### Step 4 — Spot-check it (recommended)
Right-click an image → **Edit Alt Text**, and confirm the caption reads well. The model is good but not perfect — for anything going to an external audience, a quick human skim is worth it.

## 3. Other ways to run it

`cappv1` accepts the same flags as the underlying script, so all of these work:

| What you want | Command |
|---|---|
| Process everything new in `input/` (background) | `cappv1` |
| Process just one specific file | `cappv1 --file "my-deck.pptx"` |
| Preview what *would* happen — no API calls, no files written | `cappv1 --dry-run` |
| Pick back up on a file that got interrupted partway | `cappv1 --resume` |
| Run in the current terminal instead of the background (see output directly, blocks until done) | `/Users/ssharma33/Desktop/cappv1/run.sh` |

**When to use `--dry-run`:** before running a big batch of decks for the first time, to sanity-check how many images will be captioned vs. skipped without spending any API calls.

**When to use `--resume`:** if the machine slept, lost power, or you killed the process mid-run. The tool checkpoints after every slide, so just running `cappv1` again automatically picks up where it left off instead of starting the deck over — you don't lose progress or pay for images already captioned.

## 4. What happens to different kinds of images

You don't need to sort your images beforehand — the tool figures this out automatically per image:

- **Real content** (charts, photos, diagrams, screenshots) → sent to the model, gets a real descriptive caption.
- **Tiny images** (small icons, bullet graphics, dividers — under ~40px) → automatically skipped, no API call spent.
- **Repeated images** (the same logo/icon appearing on multiple slides) → captioned once, then reused everywhere else it appears, so you're not paying to caption the same logo 20 times.
- **Genuinely decorative images** (background textures, purely visual dividers with no informational content) → the model itself recognizes these and marks them as decorative (empty alt-text), which is the correct, accessible thing to do — PowerPoint's own "Mark as Decorative" does the same.

## 5. Checking on a run

- **Is it still running?** `ps aux | grep run.sh`
- **Live/full progress**: `tail -f /Users/ssharma33/Desktop/cappv1/logs/run-*.log` — every run writes a timestamped log here (e.g. `run-20260903-122604.log`), so history is kept across runs, not just the current one.
- **Startup problems** (e.g. missing API key, before the tool's own logging kicks in): `cat /Users/ssharma33/Desktop/cappv1/logs/cappv1-launcher.log`
- **Per-file status**: `.state/<filename>.pptx.json` tracks whether each file is `in_progress` or `complete`. You don't need to open these — the tool reads and updates them automatically — but they're there if you're curious why a file did or didn't get reprocessed.

## 6. Troubleshooting

| Symptom | What's going on | Fix |
|---|---|---|
| `cappv1: command not found` | The `~/.local/bin/cappv1` symlink is missing or `~/.local/bin` isn't on your `PATH` | Run `ln -sf /Users/ssharma33/Desktop/cappv1/bin/cappv1 ~/.local/bin/cappv1`, then open a new terminal |
| `OPENROUTER_API_KEY is not set` | `.env` is missing or the key line is empty | Open `.env`, make sure `OPENROUTER_API_KEY=...` has a real value |
| A file logs `already complete, skipping` | The tool already fully processed this file in a previous run | If you want to redo it, delete `.state/<filename>.pptx.json` and run again |
| `caption generation failed permanently` for a specific image | The API call failed 3 times in a row (rate limit, network blip, temporary outage) | Alt-text is left blank for that image; just run `cappv1` again — it'll retry only what's missing |
| A whole file fails and gets skipped | The `.pptx` is corrupted or not a valid PowerPoint file | Re-save the file from PowerPoint and drop it back into `input/` |
| Nothing happens / "nothing to process" | `input/` is empty, or every file in it is already marked complete | Check that your files are actually in `input/` and end in `.pptx` |

## 7. Quick reference

```
# 1. drop .pptx files into:
/Users/ssharma33/Desktop/cappv1/input/

# 2. from anywhere, run:
cappv1

# 3. watch it (optional):
tail -f /Users/ssharma33/Desktop/cappv1/logs/run-*.log

# 4. collect finished files (same names as input) from:
/Users/ssharma33/Desktop/cappv1/output/
```
