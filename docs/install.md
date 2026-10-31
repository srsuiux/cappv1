# Install

A full walkthrough, one time only.

## What you need

| You need | How to check |
|---|---|
| **A Mac or Linux computer** (Windows isn't supported directly; see [Windows through WSL](#windows-through-wsl)) | |
| **Python 3.11 or newer** | Open **Terminal** (`Cmd + Space`, type `Terminal`, press Enter) and type `python3 --version`. If it shows 3.11 or higher, you're set. Otherwise install Python from [python.org/downloads](https://www.python.org/downloads/). |
| **An AI service** (an API key from one, or Ollama to run it all on your own computer) | See [Choosing an AI service](providers.md#choosing-an-ai-service). |

## Install (one time)

**1. Install pipx** if you don't have it. pipx installs command-line tools in their own space so they can't clash with anything else. On a Mac with [Homebrew](https://brew.sh): `brew install pipx`. On Linux, use your package manager (for example `sudo apt install pipx`). Then run `pipx ensurepath` and open a new Terminal window.

**2. Install cappv1.**

```
pipx install cappv1
```

To update later, run `pipx upgrade cappv1`.

If that fails, or you want the newest unreleased code, install straight from GitHub instead:

```
pipx install git+https://github.com/srsuiux/cappv1.git
```

**3. Open it and check that it works.**

```
cappv1
```

The first time, it offers to walk you through choosing an AI service and pasting your key (`/init`). Then type `/doctor` and press Enter. You should see a list of green checkmarks. A red ✗ means something needs fixing, and the line next to it says what.

`cappv1` is the only command you type in Terminal. Everything else (`/run`, `/doctor`, `/models`, ...) is typed inside it.

**Where your files go.** cappv1 keeps your settings (`.env`), `input`, `output`, saved progress and logs in a folder called `cappv1` in your home folder (`~/cappv1`). Set `CAPPV1_HOME` to use another folder. If you run it from a cloned copy of the project (see [Development](development.md)), that folder is the project folder instead.

You can also edit `~/cappv1/.env` by hand; [Configuration](configuration.md) lists every setting.

## Windows through WSL

cappv1 does not run on Windows itself yet, but it should work inside the Windows Subsystem for Linux (WSL), which gives you a Linux terminal on Windows. This has not been tested by the author, so treat it as a starting point and report what you find.

1. Install WSL with Ubuntu. In PowerShell, run `wsl --install -d Ubuntu-24.04`, restart if asked, and open **Ubuntu** from the Start menu.
2. In the Ubuntu window, install Python and pipx: `sudo apt update && sudo apt install -y python3 python3-pip pipx`, then `pipx ensurepath` and open a new Ubuntu window. Ubuntu 22.04 ships Python 3.10, which is too old.
3. Install and open cappv1 as above: `pipx install cappv1`, then `cappv1`.

Your files live inside Linux, in `~/cappv1`. To add your Windows files, copy them in from Ubuntu (for example `cp /mnt/c/Users/<you>/Documents/deck.pptx ~/cappv1/input/`), or open `\\wsl$\Ubuntu\home\<you>\cappv1` in File Explorer and drag files in. Finished copies appear under `output` in the same place.

In the browser, `/web` prints an address on `127.0.0.1`. If a browser does not open by itself, copy the address into one on Windows.
