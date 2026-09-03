# How to Use: PPTX Alt-Text Automation

This is the day-to-day guide for running the tool — no code reading required. For the technical spec, see `product.md`.

## What it does, in one line

You drop PowerPoint files into `input/`, run one command, and get the same files back in `output/` with accessibility alt-text automatically written onto every meaningful image.

## 1. One-time setup

Do this once per machine.

1. Open a terminal in the project folder:
   ```
   cd /Users/ssharma33/Desktop/cappv1
   ```
2. Activate the project's Python environment:
   ```
   source .venv/bin/activate
   ```
   (You'll see `(.venv)` appear at the start of your terminal prompt — that means it worked.)
3. Confirm your API key is in place. Open `.env` and make sure this line has a real key (it should already be set up):
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
   If this file or key is ever missing, the tool will tell you immediately when you try to run it, rather than failing partway through.

That's it for setup — steps 4+ below are what you'll repeat every time.

## 2. The basic workflow (every time you use it)

### Step 1 — Add your PowerPoint files
Drag and drop, or copy, your `.pptx` file(s) into the `input/` folder. You can drop in one file or many at once — the tool processes every `.pptx` it finds there.

> Only `.pptx` works (the modern PowerPoint format). Old `.ppt` files need to be re-saved as `.pptx` from PowerPoint first (File → Save As → PowerPoint Presentation).

### Step 2 — Run the tool
In your terminal (with `(.venv)` active):
```
python -m src.main
```
You'll see live progress in the terminal, slide by slide:
```
[file: quarterly-review.pptx] [slide 4/12] [section: "Financials"] captioned 2/2 images
[file: quarterly-review.pptx] [slide 5/12] skipped 1 decorative image, captioned 1/1
[file: quarterly-review.pptx] saved to output/quarterly-review.pptx
```

### Step 3 — Get your finished file
Once you see the `saved to output/...` line, your captioned deck is in the `output/` folder, ready to open in PowerPoint. The original file in `input/` is untouched — the tool never edits it in place.

### Step 4 — Spot-check it (recommended)
Open the file from `output/` in PowerPoint, right-click an image → **Edit Alt Text**, and confirm the caption reads well. The model is good but not perfect — for anything going to an external audience, a quick human skim is worth it.

## 3. Other ways to run it

| What you want | Command |
|---|---|
| Process everything new in `input/` | `python -m src.main` |
| Process just one specific file | `python -m src.main --file "my-deck.pptx"` |
| Preview what *would* happen — no API calls, no files written | `python -m src.main --dry-run` |
| Pick back up on a file that got interrupted partway | `python -m src.main --resume` |

**When to use `--dry-run`:** before running a big batch of decks for the first time, to sanity-check how many images will be captioned vs. skipped without spending any API calls.

**When to use `--resume`:** if you closed the terminal, lost power, or hit `Ctrl+C` mid-run. The tool checkpoints after every slide, so re-running (even a plain `python -m src.main`) automatically picks up where it left off instead of starting the deck over — you don't lose progress or pay for images already captioned.

## 4. What happens to different kinds of images

You don't need to sort your images beforehand — the tool figures this out automatically per image:

- **Real content** (charts, photos, diagrams, screenshots) → sent to the model, gets a real descriptive caption.
- **Tiny images** (small icons, bullet graphics, dividers — under ~40px) → automatically skipped, no API call spent.
- **Repeated images** (the same logo/icon appearing on multiple slides) → captioned once, then reused everywhere else it appears, so you're not paying to caption the same logo 20 times.
- **Genuinely decorative images** (background textures, purely visual dividers with no informational content) → the model itself recognizes these and marks them as decorative (empty alt-text), which is the correct, accessible thing to do — PowerPoint's own "Mark as Decorative" does the same.

## 5. Checking on a run

- **Live progress**: printed to your terminal as it runs.
- **Full history**: every run also writes a timestamped log file to `logs/`, e.g. `logs/run-20260903-114347.log` — useful if you want to check what happened after the fact, or share a log with someone debugging an issue.
- **Per-file status**: `.state/<filename>.pptx.json` tracks whether each file is `in_progress` or `complete`. You don't need to open these — the tool reads and updates them automatically — but they're there if you're curious why a file did or didn't get reprocessed.

## 6. Troubleshooting

| Symptom | What's going on | Fix |
|---|---|---|
| `OPENROUTER_API_KEY is not set` | `.env` is missing or the key line is empty | Open `.env`, make sure `OPENROUTER_API_KEY=...` has a real value |
| A file logs `already complete, skipping` | The tool already fully processed this file in a previous run | If you want to redo it, delete `.state/<filename>.pptx.json` and run again |
| `caption generation failed permanently` for a specific image | The API call failed 3 times in a row (rate limit, network blip, temporary outage) | Alt-text is left blank for that image; just run the tool again — it'll retry only what's missing |
| A whole file fails and gets skipped | The `.pptx` is corrupted or not a valid PowerPoint file | Re-save the file from PowerPoint and drop it back into `input/` |
| Nothing happens / "nothing to process" | `input/` is empty, or every file in it is already marked complete | Check that your files are actually in `input/` and end in `.pptx` |

## 7. Quick reference

```
cd /Users/ssharma33/Desktop/cappv1
source .venv/bin/activate

# 1. drop .pptx files into input/
# 2. run:
python -m src.main

# 3. collect finished files from output/
```
