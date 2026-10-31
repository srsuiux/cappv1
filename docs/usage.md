# Using cappv1

## Session flow

1. **Open cappv1.** In Terminal, type:
   ```
   cappv1
   ```
   A session opens with a `❯` prompt, like a chat. The first time, it offers to walk you through choosing an AI service.
2. **Add your files.** Drag your `.pptx` or `.docx` files (or a whole folder of them) into the Terminal window, and press Enter. They are copied into the `input` folder for you. You can also copy them there yourself.
3. **Run it.** Type `/run` and press Enter. A live display shows which file and slide it's on and what it's doing right now (looking at a picture, reading a chart, saving the deck). Press `Ctrl+C` to stop; finished slides are remembered.
4. **Collect your files.** Each run saves its finished files, under their original names, in its own folder inside `output`, named for the time it ran (for example `output/2026-10-29_21-28-38/`), so an earlier run is never overwritten. Type `/open` to open `output`, or `/history` to list the runs.
5. **Check the result.** Open a file from `output` in PowerPoint, right-click a picture, table, or chart, and choose **Edit Alt Text**. The descriptions are usually good, but give them a quick read before sharing anything important.

If one file fails, the others still run, and the failed file names are listed at the end. If the run is interrupted (laptop closes, network drops), open cappv1 and type `/run` again. It skips finished files and picks up where it left off.

Type `/` at any time to see the available commands. Animations can be turned off by setting `CAPPV1_NO_ANIMATION=1` (they are also off when `NO_COLOR` is set).

## Commands

Inside the session (type `/` to see them as you type):

<img src="images/terminal-help.png" alt="The /help output: each command with its aliases and a one-line description." width="760">

| Type this | What it does |
|---|---|
| `/run` | Processes every `.pptx` and `.docx` in `input`, one by one. Add `--resume` to only continue unfinished files, or `--force` to redo everything and replace alt text that authors wrote themselves (it asks first). |
| `/files` | Shows the files waiting in `input` and how far along each is. |
| `/init` | Sets up cappv1 (service, key, model). If it's already set up, it shows what you're using and lets you keep it, change just the model, or switch service. Safe to run again. |
| `/models` | Goes straight to picking an AI service and model. For OpenRouter you can choose free models, the cheapest paid ones, or browse by maker (OpenAI, Google, DeepSeek and more) with prices shown. Each service remembers the model you used last. |
| `/web` | Opens cappv1 in your browser, on this computer only. `/web stop` turns it off. It is a small local site: a front page with an overview, and Files, Services, Health and Your data pages, and pages on how it works, privacy, FAQ and about. The API behind it is in `docs/API.md`. |
| `/audit` | Reports text that is hard to read against its background and slides whose reading order doesn't follow the layout. Reports only; it never changes your file. |
| `/doctor` | Checks your setup. Safe to run any time; it changes nothing. |
| `/status` | Shows the service, model, and whether your slides stay on your computer. |
| `/history` | Lists the finished copies kept from each run. |
| `/remove` | Takes a file off the list (`/remove deck.pptx`), or deletes a finished copy or a whole run (`/remove 2026-10-29_21-28-38`). Asks first. |
| `/open` | Opens the `output` folder. |
| `/clean` | **Permanently deletes** everything in `input` and `output`, plus saved progress. It asks first, but there's no undo. |
| `/clear`, `/help`, `/exit` | Clear the screen, list commands, leave (or press `Ctrl+D`). |

In your normal Terminal prompt there is just one command:

| Type this | What it does |
|---|---|
| `cappv1` | Opens cappv1. Everything above is typed inside it. |
| `cappv1 --batch` | For scripts only: no prompt, processes `input` in the background and shows the log. Add `--resume` or `--force` as in `/run`. |
| `cappv1 --version`, `cappv1 --help` | Show the version, or a short reminder of the above. |

Anything else, like `cappv1 doctor`, is refused with a reminder to open cappv1 first.

## How it works

For each file, the tool goes through the slides one at a time. For each picture, table, chart, or embedded object (a pasted-in Word, Excel, or Visio file, or a SmartArt diagram) it sends the content to the AI along with the slide's title and notes, so the description fits its context. Pictures are sent as images; everything else is sent as text. The AI's answer is written into that shape's alt-text field, the same one PowerPoint's **Edit Alt Text** uses.


Word documents are covered in [Word documents](word-support.md).

Shapes that are completely invisible (no fill, no outline, no text) are marked as decorative, like PowerPoint's own "Mark as decorative" button, so screen readers skip them. Everything else in the file stays exactly as it was.

## Alt text that's already there, and picking up where it stopped

**If you already wrote alt text, cappv1 builds on it; it never silently replaces it.** For each picture, table, chart, or diagram that already has alt text:

- If it's very short (under 30 characters by default, such as just "Logo"), it's treated as unfinished. The AI writes an improved version that keeps your wording and adds what's missing.
- Otherwise the AI judges it. If it already says what the item shows and why it matters, it's left exactly as you wrote it. If not, an improved version that keeps your wording is used.

The run summary counts these separately ("improved", "kept as written"), so you can see what changed. Change the 30-character cutoff with `MIN_EXISTING_ALT_CHARS` in `.env`. To replace everything with fresh descriptions anyway, use `/run --force`.

**Crashes and interruptions don't cost you finished work.** Each finished file is saved to `output` on its own, and progress is saved as it goes. If cappv1 stops partway through a batch (laptop closes, a crash, `Ctrl+C`), run `/run` again: finished files are skipped, and the file it stopped on continues with its saved descriptions, so nothing is paid for twice. A file that you edit and drop in again is recognised as changed; only the new or edited items are sent to the AI. A file that hasn't changed is reported as already captioned.
