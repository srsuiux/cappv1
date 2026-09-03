# Skill: Caption-Only, Nothing Else Changes

This file is guidance for any LLM or coding agent (Claude, or otherwise) working on this repository — as a runtime captioning model, or as a developer extending the code. Read this before touching anything that reads or writes a `.pptx`.

## The one invariant

This tool has exactly one job: read images out of a `.pptx`, generate alt-text for them, and write that alt-text back. Every other byte of the file — layout, positions, formatting, images, text, slide order — must come out of `output/` identical to what went into `input/`.

A correct run, diffed against its input (ignoring the one XML attribute described below), should show **zero visual differences** when both are opened in PowerPoint.

## What "untouched" means, concretely

- **Image bytes** — never re-encoded, resized, cropped, or replaced.
- **Position, size, rotation, z-order** of every shape — unchanged.
- **Slide layout, slide master, theme, fonts, colors** — unchanged.
- **Text content** (titles, body, speaker notes) — read-only. It's used *as context* for writing better captions, never rewritten or "improved."
- **Slide order, slide count, sections** — unchanged.
- The **only** field this tool ever modifies is the `descr` attribute on a picture shape's `<p:cNvPr>` element — i.e. exactly the field PowerPoint's own "Edit Alt Text" panel edits. See `set_alt_text()` in `src/pptx_reader.py`; it's the single write path into the presentation XML.

## The captioning model (called via OpenRouter)

It never sees or touches the `.pptx` file itself. It receives one base64-encoded image plus slide-context text (title/body/notes), and returns a caption string — nothing more. See the system prompt in `src/llm_client.py`, which explicitly asks for alt-text only, no formatting, no extra commentary. It has no mechanism to alter the file; this section documents the constraint rather than guarding against a real risk.

## If you're extending this codebase

- Don't add features that reformat, reposition, restyle, resize, or "clean up" slides — that is out of scope for this tool, full stop.
- Don't touch any shape's formatting API (`.left`, `.top`, `.width`, `.height`, `.fill`, `.line`, text runs' `.font`, etc.) for any reason.
- Don't rewrite slide text, even to "fix" something that looks like a typo — this tool reads text, it never writes it.
- If a feature genuinely needs to touch layout or add new visual content (e.g. the v2 idea of a human-review export), it must write to a **separate file**, never mutate the original presentation beyond the alt-text field.
- When in doubt: if a change would show up as a visual diff when the output is opened in PowerPoint (anything other than an image now having alt-text), it doesn't belong in this tool.
