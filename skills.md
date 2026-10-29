# Skill: Caption-Only, Nothing Else Changes

This file is guidance for any LLM or coding agent (Claude, or otherwise) working on this repository — as a runtime captioning model, or as a developer extending the code. Read this before touching anything that reads or writes a `.pptx`.

## The one invariant

This tool has exactly one job: read accessibility-relevant elements (images, tables, charts) out of a `.pptx`, generate alt-text for them, and write that alt-text back. Every other byte of the file — layout, positions, formatting, images, text, slide order — must come out of `output/` identical to what went into `input/`.

Accessibility fixes beyond alt text are allowed only from a short, named list, and each must be **visually inert**: opened in PowerPoint, the slide looks identical. Today the list has one entry: flagging a table's first row as its header (`firstRow="1"` on `a:tblPr`, see `mark_table_header()` in `src/pptx_reader.py`). It is applied only when no table style is attached (so nothing is restyled), the table has two or more rows, every first-row cell has text, and nothing in that row is merged; otherwise the table is left alone and the reason is logged. Anything that changes how a slide looks (colors, fonts, sizes, bolding, table styles, layout) is out of scope. Low contrast and reading order, for example, are reported by `src/audit.py` (read-only) but never changed. To add an entry, it must meet the same bar and get a test.

A correct run, diffed against its input (ignoring the one XML attribute described below), should show **zero visual differences** when both are opened in PowerPoint.

## What "untouched" means, concretely

- **Image bytes** — never re-encoded, resized, cropped, or replaced.
- **Position, size, rotation, z-order** of every shape — unchanged.
- **Slide layout, slide master, theme, fonts, colors** — unchanged.
- **Text content** (titles, body, speaker notes) — read-only. It's used *as context* for writing better captions, never rewritten or "improved."
- **Slide order, slide count, sections** — unchanged.
- The field this tool writes is the `descr` attribute on a shape's `<p:cNvPr>` element — i.e. exactly the field PowerPoint's own "Edit Alt Text" panel edits. This applies to picture, table, chart, and embedded-OLE-object shapes, plus a narrow, provably-safe decorative-marking pass on zero-pixel AutoShapes (see below) — never anything else on the shape, apart from the listed visually inert fixes above. See `set_alt_text()` in `src/pptx_reader.py`; it's the single write path for alt text.

## Shape extraction — match on the XML element tag, never `shape.shape_type`

`shape.shape_type` (python-pptx) is not a neutral read of the XML. For any shape wrapped in a slide placeholder (`<p:ph>` — e.g. a picture inserted via a layout's "click icon to add picture" content placeholder), python-pptx's `_InheritsDimensions.shape_type` unconditionally returns `MSO_SHAPE_TYPE.PLACEHOLDER`, masking the real type. This isn't an edge case — it's how PowerPoint layouts commonly place images. It silently dropped 2 of 45 slides' pictures from `extract_pictures()` in production before it was caught, purely because `shape.shape_type == MSO_SHAPE_TYPE.PICTURE` was false for them.

**Rule: identify shapes by `shape._element.tag` (e.g. `qn("p:pic")`, `qn("p:grpSp")`), never by `shape.shape_type`.** `extract_tables`/`extract_charts` were never affected by this bug because they duck-type on `has_table`/`has_chart` (backed by `graphicData_uri`, not `shape_type`) — that's a second-safe pattern, not just tag-matching, worth keeping in mind for future extraction functions.

Two sharp edges this tag-matching approach creates, both already handled in `_is_picture()`/`_count_raw_pictures()` in `src/pptx_reader.py` — don't re-introduce them if you touch this code:
- **`Movie` shapes share the `p:pic` tag with real pictures** but have no `.image` (calling it raises `AttributeError`). Excluded by checking for an `a:videoFile` child under `nvPicPr/nvPr`, matching python-pptx's own Picture-vs-Movie dispatch.
- **An embedded OLE object's fallback preview lives as a `p:pic` nested inside `p:oleObj`/`mc:AlternateContent`.** It has `id="0"`, isn't reachable via `slide.shapes`, and isn't an independently alt-textable shape — it's part of the OLE object's own compatibility rendering. Excluded via `ancestor::p:oleObj`.

`extract_pictures()` also independently recounts real `<p:pic>` elements straight from the slide's raw XML (bypassing `_walk_shapes` entirely) and raises loudly if the candidate list doesn't match. Keep this guard if you refactor extraction — it's what would have caught the placeholder bug immediately instead of after a full support investigation, and it already caught a second class of false positive (OLE fallback pics) during that same investigation.

## The captioning model (OpenRouter, OpenAI, Anthropic, or local Ollama)

It never sees or touches the `.pptx` file itself. For images it receives one base64-encoded image plus slide-context text (title/body/notes); for tables and charts it receives a text rendering of their content/data instead (no image exists to send) — see `table_to_text()`/`chart_to_text()` in `src/pptx_reader.py`. Either way it returns a caption string — nothing more. See the system prompts in `src/llm_client.py`, which explicitly ask for alt-text only, no formatting, no extra commentary. It has no mechanism to alter the file; this section documents the constraint rather than guarding against a real risk.

## Embedded OLE objects — heuristic text extraction, not a real parser

`extract_ole_objects()`/`ole_object_to_text()`/`generate_ole_alt_text()` in `src/pptx_reader.py`/`src/llm_client.py` handle embedded Word/Excel/Visio objects (`p:graphicFrame` with `has_oleobj`) — common in decks pasted together from Word docs on old software. This was a known gap earlier in this tool's life; it's now handled, but by a real, evidence-tested compromise worth understanding before you touch it:

- **The OLE fallback preview image is a dead end, confirmed, don't revisit it.** Its `p:pic` (nested inside `p:oleObj`/`mc:AlternateContent`, see above) is a Windows vector metafile (WMF/EMF). Pillow can't rasterize it (`.load()` fails), and every vision backend tried through OpenRouter (Anthropic, Google, Amazon, Azure) rejected it outright with "Could not process image." There is no image to send here.
- **Modern OOXML embeds** (`progId` like `Word.Document.12`) are real `.docx` zip files — read properly via `python-docx` (`_docx_to_text()`), clean and accurate.
- **Legacy OLE2-binary embeds** (`Word.Document.8`, `Word.Picture.8`, `Visio.Drawing.11`/`.6` — the majority in an old deck) have no lightweight Python parser for their actual binary format. `_ole2_binary_to_text()` instead opens the container with `olefile` and regex-scrapes every stream for plausible cp1252 text runs. This is **not a transcript** — it comes back as noisy, out-of-order fragments mixed with font-table and metadata junk (`"System System System Times New Roman FacNo..."`). It works anyway: tested against this tool's own real embeds (a Faculty Data table, five Visio relational-algebra diagrams), the resulting captions were accurate and specific in every case, because the prompt (`_OLE_SYSTEM_PROMPT`) explicitly tells the model the input is noisy and to use only what makes sense. If you change that prompt, keep that instruction — without it this approach doesn't work.
- If the extracted text is pure noise, the model returns the literal string `UNKNOWN`, and `handle_ole()` in `src/pipeline.py` substitutes an honest, non-invented fallback (`"Embedded {progId} (automatic description unavailable)"`) rather than inventing content or leaving `descr` empty (empty would read as "reviewed, decorative," which an undescribed OLE object is not).
- No LibreOffice or other external-binary dependency was needed for any of this — `olefile` and `python-docx` are both pure-Python, pip-installable. If a future deck's embeds genuinely defeat this heuristic (all-noise extraction, no signal), that's the point to reconsider a heavier dependency, not before.

## SmartArt diagrams — clean XML, easier than OLE objects

`extract_smartart()`/`smartart_to_text()`/`generate_smartart_alt_text()` handle SmartArt graphics — the OOXML spec calls this content type a "Diagram" (`p:graphicFrame` with `graphicData uri=".../drawingml/2006/diagram"`), a fourth `graphicData` type alongside table/chart/ole that **python-pptx has zero support for** (no `GRAPHIC_DATA_URI_DIAGRAM` constant, no `.diagram` property anywhere in the library — confirmed by reading its source, not assumed).

Unlike an OLE object, there's nothing heuristic here — a SmartArt's content lives in a separate XML part (`data1.xml`, found via `<dgm:relIds r:dm="rIdN"/>` on the graphicFrame) that's clean, well-formed DrawingML: plain `<a:t>` text runs per node (`<dgm:pt>`), with real parent-child edges (`<dgm:cxn>`, default/`type="parOf"` — other `type` values like `presOf`/`presParOf` are presentation-layer plumbing, not data relationships, and must be filtered out or the hierarchy comes out wrong). `smartart_to_text()` walks this into an indented outline, and the prompt is told to describe the *relationships* the outline encodes, not just list the node text.

This covers the common case (a single connected hierarchy/list layout). It will NOT handle a SmartArt with multiple disconnected root nodes meaningfully beyond outputting them as separate top-level entries — no deck has exercised that case yet, so it's untested, not proven broken.

## Known gaps (deliberately unhandled, not oversights)

- **Decorative-marking exists for pictures and for a narrow class of AutoShapes, not tables/charts/OLE objects/SmartArt.** `mark_decorative()` triggers for pictures via `is_too_small()` or the vision model's own `DECORATIVE` response, and for AutoShapes/connectors via `extract_invisible_shapes()`/`_is_invisible_shape()` — which only matches a shape with an **explicit** `<a:noFill/>` on both fill and line and no text: provably zero rendered pixels, not a judgment call. It deliberately does *not* match a shape that merely omits a fill/line element (which could inherit a visible theme style) — verified against a real deck's diagram connectors (arrows with `cx=0` because they're vertical, but a real `solidFill` stroke) to make sure those aren't caught. An inserted table/chart/OLE/SmartArt essentially always carries real data, so none of those get a decorative path.
- **Grouped native-PowerPoint diagrams** — a `p:grpSp` containing AutoShapes with no picture/table/chart/OLE/SmartArt inside (e.g. a set of ovals+lines forming a Venn-style diagram drawn by hand in PowerPoint) — are still unhandled. There's no image to send (it's not a picture) and no single coherent text source (its content is scattered across sibling shapes' individual text runs, not one XML part like the cases above). The practical workaround in use is manually flattening this specific case to a picture in PowerPoint first, which routes it through the already-solid picture-captioning path.

## Word documents (.docx)

`src/docx_reader.py` and `src/docx_pipeline.py` apply the same invariant to Word files. The only fields written are the ones Word's own "Edit Alt Text" pane edits: `descr` on a picture's `wp:docPr`, `alt` on an embedded object's `v:shape` (plus Word 365's `adec:decorative` flag for tiny or model-judged decorative pictures) and `w:tblDescription` on a table. The finished copy is the original zip with only `word/document.xml` replaced (`save_document()`); re-saving through python-docx repackages every part. A table's title (`w:tblCaption`) is the author's and is never touched. Everything else must come out identical; `tests/test_docx.py` diffs the output against the input with those fields removed.

- Pictures are matched on the XML (a `wp:docPr` whose drawing holds an `a:blip`), not on python-docx shape types. `mc:Fallback` copies are skipped.
- Embedded objects (`w:object`, for example a Visio drawing) get their description on the preview shape's `alt` attribute, from the same text scrape as in decks.
- **Table alt text is skipped in Word compatibility mode 11/12** (what LibreOffice and old Word write): Word refuses to open a file that has a table title or description in that mode (tested on real files), and raising the mode would re-lay-out pages. `table_alt_text_unsupported()` checks it; the file gets one skip note saying to use Save As in Word first.
- Not handled yet: charts, SmartArt, headers/footers/footnotes, and EMF/WMF/SVG/TIFF pictures (logged and left alone). Table header rows are not flagged: `w:tblHeader` repeats the row across pages, which is visible.
- Context for the model is the nearest heading above the element and the paragraphs next to it. Read-only.
- **Old `.doc` is deliberately not supported.** It is a binary format no pure-Python library can write, so it would need a converter installed on the person's computer. LibreOffice does it faithfully but is a large separate install; macOS `textutil` is built in but silently drops pictures (checked on real files); driving Microsoft Word stalls on its own dialogs. A feature that depends on software cappv1 cannot ship was judged not worth it: people save the file as `.docx` in Word instead.

## Errors never stop a file

An item or slide that cannot be read (for example an embedded object whose part is missing from a damaged file, which makes python-pptx raise `no relationship with key ...`) is **skipped**, not fatal: `record_skip()` in `src/pipeline.py` adds a `{where, kind, error}` note to the file's saved progress (`FileState.skipped`), logs it and emits `element_skipped`; the rest of the file is processed and saved. A skip is not a failure to retry (it would fail the same way), so the file still finishes; the notes are how someone finds it later. A failed model call is different: it is retried on the next run. Cancelling (`CancelledError`) is never swallowed. Keep every new element handler inside this guard.

## If you're extending this codebase

- Don't add features that reformat, reposition, restyle, resize, or "clean up" slides — that is out of scope for this tool, full stop.
- Don't touch any shape's formatting API (`.left`, `.top`, `.width`, `.height`, `.fill`, `.line`, text runs' `.font`, etc.) for any reason.
- Don't rewrite slide text, even to "fix" something that looks like a typo — this tool reads text, it never writes it.
- If a feature genuinely needs to touch layout or add new visual content (e.g. the v2 idea of a human-review export), it must write to a **separate file**, never mutate the original presentation beyond the alt-text field.
- When in doubt: if a change would show up as a visual diff when the output is opened in PowerPoint (anything other than an image now having alt-text), it doesn't belong in this tool.
