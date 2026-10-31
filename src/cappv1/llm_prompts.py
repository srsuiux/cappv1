"""The instructions sent to the model, and how the author's existing alt text is added to a request."""

_IMAGE_SYSTEM_PROMPT = (
    "You write alt-text for images embedded in PowerPoint slides, for screen-reader "
    "accessibility. Rules:\n"
    "- Describe the image's content AND its function/purpose on the slide.\n"
    "- Be concise: aim for under {max_chars} characters.\n"
    "- Never start with 'Image of', 'Picture of', or similar - screen readers already "
    "announce it as an image.\n"
    "- Don't restate text that's already on the slide verbatim; describe what the "
    "image itself shows.\n"
    "- If the image is purely decorative (a divider, background texture, generic "
    "icon with no informational content), respond with exactly: DECORATIVE\n"
    "- Output only the alt-text (or DECORATIVE). No quotes, no preamble."
)


_TABLE_SYSTEM_PROMPT = (
    "You write alt-text for tables embedded in PowerPoint slides, for screen-reader "
    "accessibility. Rules:\n"
    "- Summarize what the table shows and its purpose on the slide - don't just "
    "restate every cell, a screen reader will read those separately.\n"
    "- Be concise: aim for under {max_chars} characters.\n"
    "- Never start with 'Table of' or 'A table showing' - screen readers already "
    "announce it as a table.\n"
    "- Output only the alt-text. No quotes, no preamble."
)


_CHART_SYSTEM_PROMPT = (
    "You write alt-text for charts embedded in PowerPoint slides, for screen-reader "
    "accessibility. You are given the chart's type, title, categories, and series "
    "data (not an image). Rules:\n"
    "- Describe the key trend or takeaway the chart conveys, not every data point.\n"
    "- Be concise: aim for under {max_chars} characters.\n"
    "- Never start with 'Chart of' or 'A chart showing' - screen readers already "
    "announce it as a chart.\n"
    "- Output only the alt-text. No quotes, no preamble."
)


_OLE_SYSTEM_PROMPT = (
    "You write alt-text for embedded objects (a Word document, an Excel sheet, a "
    "Visio drawing, etc.) in PowerPoint slides, for screen-reader accessibility. "
    "The text you're given was extracted by a best-effort heuristic scrape of the "
    "embedded file's raw internal data, not a clean transcript - it will likely "
    "contain garbled fragments, repeated font/metadata noise (e.g. 'System', font "
    "names, author names), and text in a strange order. Rules:\n"
    "- Use only the fragments that clearly make sense together; ignore metadata "
    "noise and anything you can't confidently interpret.\n"
    "- Describe what the object shows and its purpose on the slide, the same way "
    "you would for a table or chart.\n"
    "- Be concise: aim for under {max_chars} characters.\n"
    "- Never start with 'Embedded object' or 'A document showing' - screen readers "
    "already announce it as an object.\n"
    "- If the extracted text gives no usable signal at all - it's entirely noise, "
    "you cannot tell what the object contains - respond with exactly: UNKNOWN\n"
    "- Output only the alt-text (or UNKNOWN). No quotes, no preamble."
)


_SMARTART_SYSTEM_PROMPT = (
    "You write alt-text for SmartArt diagrams embedded in PowerPoint slides, for "
    "screen-reader accessibility. You are given the diagram's node text as an "
    "indented outline reflecting its actual hierarchy (not an image). Rules:\n"
    "- Describe the structure and relationships the diagram conveys - who reports "
    "to whom, what leads to what - not just a flat list of every node's text.\n"
    "- Be concise: aim for under {max_chars} characters.\n"
    "- Never start with 'Diagram of' or 'SmartArt showing' - screen readers "
    "already announce it as a diagram.\n"
    "- Output only the alt-text. No quotes, no preamble."
)


_REVIEW_SUFFIX = (
    "\n\nThe author already wrote alt-text for this element; it is shown after the "
    "context. Respect it:\n"
    "- {verdict}\n"
    "- When you improve it, keep the author's wording, facts and intent wherever they are "
    "accurate. Add only what is missing (what it shows, and why it matters on this slide). "
    "Never contradict the author.\n"
    "- Never respond with DECORATIVE or UNKNOWN."
)


_VERDICT_ADEQUATE = (
    "If it already tells a screen-reader user what this shows and why it matters, reply with "
    "exactly: KEEP. Otherwise reply with the improved alt-text only."
)


_VERDICT_TOO_SHORT = "It is very short, so it is probably incomplete. Do NOT reply KEEP. Reply with an improved version that builds on it."


def _with_existing(messages: list[dict], existing: str, too_short: bool) -> list[dict]:
    """Adds the author's own alt-text, and the rules for building on it, to a request."""
    suffix = _REVIEW_SUFFIX.format(verdict=_VERDICT_TOO_SHORT if too_short else _VERDICT_ADEQUATE)
    note = f"\n\nAuthor's existing alt-text: {existing}"
    out = []
    for m in messages:
        m = dict(m)
        if m["role"] == "system":
            m["content"] += suffix
        elif isinstance(m["content"], list):
            m["content"] = [dict(part, text=part["text"] + note) if part["type"] == "text" else part for part in m["content"]]
        else:
            m["content"] += note
        out.append(m)
    return out
