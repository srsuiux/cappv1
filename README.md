# cappv1: PPTX Alt-Text Automation

cappv1 looks at the pictures, tables, charts, and other embedded content (like a pasted-in Word document or diagram) in your PowerPoint files and writes a short description for each one. These descriptions are called "alt text," and screen readers read them aloud to people who can't see the slide.

You drop in `.pptx` files and get the same files back with the descriptions added. Nothing else changes: no layout, text, fonts, or colors. Your originals are never modified.

**Example:** an instructor preparing lecture slides for a blind or low-vision student can use this to make sure every chart, photo, and diagram has a description before sharing the deck.

## What you need

| You need | How to check |
|---|---|
| **A Mac or Linux computer** (Windows isn't supported yet) | |
| **Python 3.11 or newer** | Open **Terminal** (`Cmd + Space`, type `Terminal`, press Enter) and type `python3 --version`. If it shows 3.11 or higher, you're set. Otherwise install Python from [python.org/downloads](https://www.python.org/downloads/). |
| **An AI service** (an API key from one, or Ollama to run it all on your own computer) | See the next section. |

### Choosing an AI service

An API key is like a password that lets this tool use an AI service. You only need **one** of these:

| Service | Cost | Where to get a key |
|---|---|---|
| **OpenRouter** | Has free models (the default) | [openrouter.ai](https://openrouter.ai) → account settings → API Keys. Keys start with `sk-or-v1-`. |
| **OpenAI** | Paid, a fraction of a cent per image | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Anthropic** | Paid, a fraction of a cent per image | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| **Ollama** (runs on your computer) | Free, no key, works offline | [ollama.com/download](https://ollama.com/download). See [Private mode](#private-mode-run-everything-on-your-own-computer). |

Each key only works with its own service. For example, an OpenAI key can't be used through OpenRouter.

> **Privacy:** free OpenRouter models send your slide content through shared third-party providers that may log or train on it. If your slides contain anything sensitive (student names, grades, ID numbers, unpublished research), use [Private mode](#private-mode-run-everything-on-your-own-computer) (nothing leaves your computer), or a paid OpenAI or Anthropic key.

## Install (one time)

**1. Download the project and open it in Terminal.**

```
git clone https://github.com/srsuiux/cappv1.git
cd cappv1
```

**2. Create your settings file and open it.**

```
cp .env.example .env
open -e .env
```

A text editor opens. Make two edits, with no spaces around the `=`:

- Set `PROVIDER=` to `openrouter`, `openai`, `anthropic`, or `ollama`.
- Paste your key after the matching line, for example `OPENAI_API_KEY=sk-...`. (Ollama needs no key. Follow [Private mode](#private-mode-run-everything-on-your-own-computer) instead.)

Leave everything else as it is, then save (`Cmd + S`) and close the window.

**3. Turn on the `cappv1` command.**

```
mkdir -p ~/.local/bin
ln -sf "$(pwd)/bin/cappv1" ~/.local/bin/cappv1
```

**4. Check that it works.**

```
cappv1 doctor
```

You should see a list of green checkmarks. A red ✗ means something needs fixing, and the line next to it says what.

The first time you run `cappv1 doctor` or `cappv1 start`, it pauses for a few extra seconds to install what it needs. That's normal and only happens once.

## Using it

1. **Add your files.** Drag your `.pptx` files into the `input` folder inside the project. Add as many as you like, with any filenames.
2. **Run it.** In Terminal, type:
   ```
   cappv1 start
   ```
3. **Wait.** It processes the files one after another, in alphabetical order, and prints progress for each file and slide (for example `file 2/5`). Each file can take from a few seconds to a few minutes.
4. **Collect your files.** Each finished file appears in the `output` folder under its original name, and the log shows a `saved to output/...` line.
5. **Check the result.** Open a file from `output` in PowerPoint, right-click a picture, table, or chart, and choose **Edit Alt Text**. The descriptions are usually good, but give them a quick read before sharing anything important.

If one file fails, the others still run, and the failed file names are listed at the end. If the run is interrupted (laptop closes, network drops), run `cappv1 start` again. It skips finished files and picks up where it left off.

## Commands

| Type this | What it does |
|---|---|
| `cappv1 start` | Processes every `.pptx` in `input`, one by one. Add `--resume` to only continue unfinished files. |
| `cappv1 doctor` | Checks your setup. Safe to run any time; it changes nothing. |
| `cappv1 models` | Lets you pick a different free OpenRouter model, or, in Private mode, one of your installed Ollama models. (For OpenAI or Anthropic, set `MODEL=` in `.env` instead.) |
| `cappv1 clean` | **Permanently deletes** everything in `input` and `output`, plus saved progress. There's no undo, so save anything you need first. |

## Private mode: run everything on your own computer

With Ollama, the AI model runs on your computer. Your slides, images, and text are never sent to OpenRouter, OpenAI, Anthropic, or anyone else, and after the one-time model download it works with no internet at all. Use this for anything sensitive (student names, grades, ID numbers, unpublished research).

**1. Install Ollama.** Download it from [ollama.com/download](https://ollama.com/download) and open it once. It then runs quietly in the background (look for the llama icon in your menu bar).

**2. Download a model (one time, needs internet).** In Terminal:

```
ollama pull gemma3:4b
```

This is about 3 GB and works on most laptops with 8 GB of memory. The model must be able to read images ("vision"). Other good choices are `qwen2.5vl:7b` and `llama3.2-vision`, which write better descriptions but need more memory and run slower.

**3. Point cappv1 at it.** Open `.env` and set:

```
PROVIDER=ollama
```

If you downloaded a different model in step 2, also set `MODEL=` to its name, for example `MODEL=qwen2.5vl:7b`. Leave all the key lines blank.

**4. Check and run.**

```
cappv1 doctor
cappv1 start
```

`cappv1 doctor` should show green checks for "Ollama address is this computer", "Ollama is running", and "model is downloaded". `cappv1 models` lists the vision models you have installed and lets you pick one.

**What to expect.** Local models are slower than the online services: roughly several seconds to a minute per image, depending on your computer. They process one image at a time. Small models also write plainer descriptions and are weaker on embedded Word/Excel objects, so read the results before sharing. If quality matters more than privacy, use a bigger local model or an online service.

**Safety check.** cappv1 only talks to Ollama on your own computer (`localhost`). If `OLLAMA_BASE_URL` in `.env` points to any other machine, it refuses to run, so you can't accidentally send slides elsewhere. If you really do run Ollama on another machine you control, set `OLLAMA_ALLOW_REMOTE=1` to allow it.

## Switching AI service or model

Open `.env` and change `PROVIDER=` to another service (make sure that service's key is filled in). Leave `MODEL=` blank to use the service's default, or set a model from that same service:

| Service | Default model |
|---|---|
| OpenRouter | `minimax/minimax-m3:free` (falls back to `google/gemma-3-12b-it`) |
| OpenAI | `gpt-4o-mini` |
| Anthropic | `claude-haiku-5-5` |
| Ollama | `gemma3:4b` (must be downloaded first with `ollama pull`) |

## If something goes wrong

| What you see | What to do |
|---|---|
| `command not found: cappv1` | Run step 3 of Install again from the project folder. If it still fails, run `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc`, then try again. |
| A red ✗ in `cappv1 doctor` | Read the message beside it. It says what to fix. |
| `API key is not set` or `rejected this key (401)` | Re-check the key in `.env`: no spaces or quotes, and it's on the line that matches your `PROVIDER`. |
| Some images, tables, or charts have no description | The AI service had a temporary hiccup. Run `cappv1 start` again; it retries only what's missing. |
| `Ollama is running` shows a red ✗ | Open the Ollama app (or run `ollama serve` in Terminal), then run `cappv1 doctor` again. |
| `model ... is downloaded` shows a red ✗ | Run the `ollama pull ...` command shown next to it. |
| Private mode is very slow, or a request times out | Use a smaller model (`gemma3:4b`), close other heavy apps, or raise `REQUEST_TIMEOUT=` in `.env`. |
| A message mentioning "billing" or "402" | That model needs payment. On OpenRouter run `cappv1 models` and pick a free one. On OpenAI or Anthropic, add credit to your account. |
| A file doesn't process at all | The file may be damaged. Re-save it from PowerPoint and add it to `input` again. |

## How it works

For each file, the tool goes through the slides one at a time. For each picture, table, chart, or embedded object (a pasted-in Word, Excel, or Visio file, or a SmartArt diagram) it sends the content to the AI along with the slide's title and notes, so the description fits its context. Pictures are sent as images; everything else is sent as text. The AI's answer is written into that shape's alt-text field, the same one PowerPoint's **Edit Alt Text** uses.

Shapes that are completely invisible (no fill, no outline, no text) are marked as decorative, like PowerPoint's own "Mark as decorative" button, so screen readers skip them. Everything else in the file stays exactly as it was.

## For developers

Settings live in `.env`; see `.env.example` for the full list (provider, model, fallback model, concurrency, Ollama address and timeout, minimum image size, maximum alt-text length). Source code is in `src/`. `skills.md` documents the one rule any change must follow: this tool only ever writes to a shape's alt-text field, nothing else in the file.
