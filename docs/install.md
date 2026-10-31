# Install

A full walkthrough, one time only.

## What you need

| You need | How to check |
|---|---|
| **A Mac or Linux computer** (Windows isn't supported yet) | |
| **Python 3.11 or newer** | Open **Terminal** (`Cmd + Space`, type `Terminal`, press Enter) and type `python3 --version`. If it shows 3.11 or higher, you're set. Otherwise install Python from [python.org/downloads](https://www.python.org/downloads/). |
| **An AI service** (an API key from one, or Ollama to run it all on your own computer) | See [Choosing an AI service](providers.md#choosing-an-ai-service). |

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
- Paste your key after the matching line, for example `OPENAI_API_KEY=sk-...`. (Ollama needs no key. Follow [Private mode](providers.md#private-mode-run-everything-on-your-own-computer) instead.)

Leave everything else as it is, then save (`Cmd + S`) and close the window.

**3. Turn on the `cappv1` command.**

```
mkdir -p ~/.local/bin
ln -sf "$(pwd)/bin/cappv1" ~/.local/bin/cappv1
```

**4. Open it and check that it works.**

```
cappv1
```

The first time, it offers to walk you through choosing an AI service. Then type `/doctor` and press Enter. You should see a list of green checkmarks. A red ✗ means something needs fixing, and the line next to it says what.

`cappv1` is the only command you type in Terminal. Everything else (`/run`, `/doctor`, `/models`, ...) is typed inside it.

The first time you open cappv1, it pauses for a few extra seconds to install what it needs. That's normal and only happens once.
