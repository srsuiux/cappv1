# Skill: Caption-Only, Nothing Else Changes

This file is guidance for any LLM or coding agent (Claude, or otherwise) working on this repository — as a runtime captioning model, or as a developer extending the code. Read this before touching anything that reads or writes a `.pptx`.

## The one invariant

This tool has exactly one job: read accessibility-relevant elements (images, tables, charts) out of a `.pptx`, generate alt-text for them, and write that alt-text back. Every other byte of the file — layout, positions, formatting, images, text, slide order — must come out of `output/` identical to what went into `input/`.

This explicitly rules out things that sound like accessibility fixes but aren't alt-text: e.g. setting a table's "header row" style flag changes visual formatting (bolds/shades row 1) and is out of scope here, even though PowerPoint's own Accessibility Checker flags it. If it's not a write to `descr`, it doesn't belong in this tool.

A correct run, diffed against its input (ignoring the one XML attribute described below), should show **zero visual differences** when both are opened in PowerPoint.

## What "untouched" means, concretely

- **Image bytes** — never re-encoded, resized, cropped, or replaced.
- **Position, size, rotation, z-order** of every shape — unchanged.
- **Slide layout, slide master, theme, fonts, colors** — unchanged.
- **Text content** (titles, body, speaker notes) — read-only. It's used *as context* for writing better captions, never rewritten or "improved."
- **Slide order, slide count, sections** — unchanged.
- The **only** field this tool ever modifies is the `descr` attribute on a shape's `<p:cNvPr>` element — i.e. exactly the field PowerPoint's own "Edit Alt Text" panel edits. This applies to picture shapes, and (as of the table/chart extension) table and chart graphic-frame shapes too — never anything else on the shape. See `set_alt_text()` in `src/pptx_reader.py`; it's the single write path into the presentation XML.

## Shape extraction — match on the XML element tag, never `shape.shape_type`

`shape.shape_type` (python-pptx) is not a neutral read of the XML. For any shape wrapped in a slide placeholder (`<p:ph>` — e.g. a picture inserted via a layout's "click icon to add picture" content placeholder), python-pptx's `_InheritsDimensions.shape_type` unconditionally returns `MSO_SHAPE_TYPE.PLACEHOLDER`, masking the real type. This isn't an edge case — it's how PowerPoint layouts commonly place images. It silently dropped 2 of 45 slides' pictures from `extract_pictures()` in production before it was caught, purely because `shape.shape_type == MSO_SHAPE_TYPE.PICTURE` was false for them.

**Rule: identify shapes by `shape._element.tag` (e.g. `qn("p:pic")`, `qn("p:grpSp")`), never by `shape.shape_type`.** `extract_tables`/`extract_charts` were never affected by this bug because they duck-type on `has_table`/`has_chart` (backed by `graphicData_uri`, not `shape_type`) — that's a second-safe pattern, not just tag-matching, worth keeping in mind for future extraction functions.

Two sharp edges this tag-matching approach creates, both already handled in `_is_picture()`/`_count_raw_pictures()` in `src/pptx_reader.py` — don't re-introduce them if you touch this code:
- **`Movie` shapes share the `p:pic` tag with real pictures** but have no `.image` (calling it raises `AttributeError`). Excluded by checking for an `a:videoFile` child under `nvPicPr/nvPr`, matching python-pptx's own Picture-vs-Movie dispatch.
- **An embedded OLE object's fallback preview lives as a `p:pic` nested inside `p:oleObj`/`mc:AlternateContent`.** It has `id="0"`, isn't reachable via `slide.shapes`, and isn't an independently alt-textable shape — it's part of the OLE object's own compatibility rendering. Excluded via `ancestor::p:oleObj`.

`extract_pictures()` also independently recounts real `<p:pic>` elements straight from the slide's raw XML (bypassing `_walk_shapes` entirely) and raises loudly if the candidate list doesn't match. Keep this guard if you refactor extraction — it's what would have caught the placeholder bug immediately instead of after a full support investigation, and it already caught a second class of false positive (OLE fallback pics) during that same investigation.

## The captioning model (called via OpenRouter)

It never sees or touches the `.pptx` file itself. For images it receives one base64-encoded image plus slide-context text (title/body/notes); for tables and charts it receives a text rendering of their content/data instead (no image exists to send) — see `table_to_text()`/`chart_to_text()` in `src/pptx_reader.py`. Either way it returns a caption string — nothing more. See the system prompts in `src/llm_client.py`, which explicitly ask for alt-text only, no formatting, no extra commentary. It has no mechanism to alter the file; this section documents the constraint rather than guarding against a real risk.

## If you're extending this codebase

- Don't add features that reformat, reposition, restyle, resize, or "clean up" slides — that is out of scope for this tool, full stop.
- Don't touch any shape's formatting API (`.left`, `.top`, `.width`, `.height`, `.fill`, `.line`, text runs' `.font`, etc.) for any reason.
- Don't rewrite slide text, even to "fix" something that looks like a typo — this tool reads text, it never writes it.
- If a feature genuinely needs to touch layout or add new visual content (e.g. the v2 idea of a human-review export), it must write to a **separate file**, never mutate the original presentation beyond the alt-text field.
- When in doubt: if a change would show up as a visual diff when the output is opened in PowerPoint (anything other than an image now having alt-text), it doesn't belong in this tool.
