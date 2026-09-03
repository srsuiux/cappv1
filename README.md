# cappv1: PPTX Alt-Text Automation

This tool looks at the pictures inside a PowerPoint file and writes a short description for each one, called "alt text," so that people using screen readers can understand what's in the images. You give it PowerPoint files, and it gives you back the same files with those descriptions added. Nothing else about your slides changes: no layout, text, fonts, or colors are touched.

## Who this is for

If you have a stack of presentations that need image descriptions for accessibility, and writing them by hand for every slide isn't realistic, this does that work for you. You don't need to know how to code to use it. For example, an instructor preparing lecture slides for a class with a blind or low-vision student could use this to make sure every chart, photo, and diagram has a proper description before sharing the deck.

## Before you start

You'll need three things.

**A Mac or Linux computer.** This doesn't currently run on Windows.

**Python, version 3.11 or newer.** Most Macs already have this installed. To check:

1. Open the **Terminal** app: press `Cmd + Space`, type `Terminal`, and press Enter.
2. Type this and press Enter:
   ```
   python3 --version
   ```
3. If you see `Python 3.11` or higher, you're set. If you see an error, or an older version, install Python from [python.org/downloads](https://www.python.org/downloads/) and check again.

**A free OpenRouter account and API key.** OpenRouter is the service this tool uses to reach the AI that writes the descriptions. An API key is like a password just for this tool.

1. Go to [openrouter.ai](https://openrouter.ai) and create a free account.
2. In your account settings, find **API Keys** and create a new one.
3. Copy the key somewhere safe. It's a long string starting with `sk-or-v1-`, and you'll need it in the next step.

## Setup (do this once)

1. Open Terminal and go to the project folder:
   ```
   cd /Users/ssharma33/Desktop/cappv1
   ```
2. Create your settings file from the template, and open it:
   ```
   cp .env.example .env
   open -e .env
   ```
   A text editor window opens. Find the line `OPENROUTER_API_KEY=your-key-here` and replace `your-key-here` with the key you copied earlier. Don't add spaces, and don't change anything else. Save (`Cmd + S`) and close the window.
3. Turn on the `cappv1` command so you can type it from anywhere:
   ```
   mkdir -p ~/.local/bin
   ln -sf "$(pwd)/bin/cappv1" ~/.local/bin/cappv1
   ```
4. Check that everything is working:
   ```
   cappv1 doctor
   ```
   You should see a list of green checkmarks. If anything shows a red X, the line next to it explains what to fix in plain language.

The first time you run `cappv1 doctor` or `cappv1 start`, it may pause for a few extra seconds to finish setting itself up. That's normal and only happens once.

## How to use it

Every time you have PowerPoint files to process:

1. **Add your files.** Drag your `.pptx` files into the `input` folder inside the project. Any filename works, and you can add more than one at a time.
2. **Run it.** In Terminal, type:
   ```
   cappv1 start
   ```
3. **Wait.** You'll see progress printed for each slide as it works. This can take anywhere from a few seconds to a few minutes, depending on how many images there are.
4. **Get your files.** Once you see a line saying `saved to output/...`, your finished file is in the `output` folder, under the same name it had before.
5. **Check it.** Open the file from `output` in PowerPoint. Right-click an image and choose **Edit Alt Text** to see what was written. The descriptions are usually good, but it's worth a quick read-through before sharing anything important.

Your original files in `input` are never changed or deleted.

## The commands

| Type this | What it does |
|---|---|
| `cappv1 start` | Processes everything in the `input` folder. |
| `cappv1 doctor` | Checks that everything is set up correctly. Safe to run any time, since it doesn't change anything. |
| `cappv1 models` | Lets you switch which AI model is used, in case the current one stops working or runs out of free usage. |
| `cappv1 clean` | Empties the `input` and `output` folders completely, so you can start fresh. There's no undo, so only use this once you've saved anything you need. |

## If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `command not found` when typing `cappv1` | The command isn't linked yet, or Terminal doesn't know where to find it | Run `mkdir -p ~/.local/bin && ln -sf /Users/ssharma33/Desktop/cappv1/bin/cappv1 ~/.local/bin/cappv1`. Still not working? Run `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc`, then try again. |
| A red X in `cappv1 doctor` | Something in setup needs attention | The message next to the X explains what's wrong |
| An image has no description after running | The AI service had a temporary hiccup | Run `cappv1 start` again. It retries only what didn't finish, not the whole file. |
| A message mentioning "billing" or "402" | The AI model you're using needs payment | Run `cappv1 models` and pick a free one instead |
| A file doesn't process at all | The PowerPoint file may be damaged | Re-save it from PowerPoint and add it to `input` again |

## How it works, briefly

The tool opens each PowerPoint file and goes through it one slide at a time. For each picture it finds, it sends the image to the AI along with that slide's title and notes, so the description fits the context instead of being a generic guess. The AI's response is written into that picture's alt-text field, the same field PowerPoint's own **Edit Alt Text** tool uses. Everything else in the file stays exactly as it was.

If the process is interrupted partway through (the laptop closes, the network drops, power is lost), running `cappv1 start` again picks up where it left off instead of starting over.

## For developers

Settings live in `.env` (model choice, how many images to process at once, and so on; see `.env.example` for the full list). Source code is in `src/`. `skills.md` documents the one rule any change here has to follow: this tool only ever writes to a picture's alt-text field, nothing else in the file. `TODO-security.md` tracks known hardening work that hasn't been done yet, including that `bin/cappv1` currently has this machine's file path hardcoded into it, so cloning this repo onto a different computer needs that updated first.
