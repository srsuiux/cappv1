# GitHub Repository Metadata

Copy-paste reference for setting up the GitHub repo — name, description, and topics.

## Repository name

**`cappv1`**

Matches the CLI command itself (`cappv1 start`, `cappv1 doctor`, ...), so the repo name and the tool name stay the same thing — no "what's this called again" gap between install and usage.

*Alternative*, if you'd rather optimize for discoverability/search over brand consistency: `pptx-alt-text-automation`.

## Title

For the GitHub repo's display name / README H1 (already set in `README.md`):

> **cappv1 — PPTX Alt-Text Automation**

## Description

For the repo's "About" field (GitHub allows up to ~350 characters; keep it near one line — this is what shows in search results and the repo list):

> Generates accessibility alt-text for PowerPoint images automatically using a vision LLM via OpenRouter — chunked, resumable, self-healing, and free-tier friendly.

*Shorter alternative* (~90 chars, if you want it tighter):

> Automates PowerPoint alt-text generation with a vision LLM — one command, resumable, free-tier friendly.

## Topics (keywords)

GitHub topics are lowercase, hyphenated, no spaces. Suggested set (paste into the repo's Topics field):

```
accessibility
alt-text
powerpoint
pptx
python-pptx
openrouter
llm
vision-model
automation
cli
wcag
screen-reader
image-captioning
python
claude
```

## Website / homepage field

Leave blank, or point to `README.md` — there's no separate hosted site for this project.

## Suggested "About" checklist when creating the repo

- [ ] Repository name: `cappv1`
- [ ] Description: pasted from above
- [ ] Topics: pasted from above
- [ ] License: none chosen yet — decide before making the repo public (MIT is the common default for a small CLI tool like this if you want one)
- [ ] `.env`, `.venv/`, `logs/`, `.state/`, `input/*.pptx`, `output/*.pptx` are already gitignored — confirm nothing sensitive is staged before the first push (`git status`)
