import asyncio
import base64
import io
import json
import logging

import httpx

from src.config import Config
from src.pptx_reader import SlideContext

logger = logging.getLogger("pptx_alt_text")

_CHAT_URLS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
}
_PROVIDER_LABELS = {"openrouter": "OpenRouter", "openai": "OpenAI", "anthropic": "Anthropic", "ollama": "Ollama"}
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

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
_VERDICT_TOO_SHORT = (
    "It is very short, so it is probably incomplete. Do NOT reply KEEP. Reply with an improved "
    "version that builds on it."
)


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


def _review(config: Config, messages: list[dict], existing: str) -> list[dict]:
    if not existing:
        return messages
    return _with_existing(messages, existing, too_short=len(existing) < config.min_existing_alt_chars)


def _error_detail(resp: httpx.Response) -> str:
    """Pulls the useful part out of a provider error body, if present."""
    try:
        err = resp.json().get("error", {})
    except (json.JSONDecodeError, ValueError):
        return resp.text[:200]
    if not isinstance(err, dict):
        return resp.text[:200]
    metadata = err.get("metadata", {})
    parts = [err.get("message", "")]
    if metadata.get("provider_name"):
        parts.append(f"provider={metadata['provider_name']}")
    if metadata.get("raw"):
        parts.append(metadata["raw"])
    if metadata.get("remedy_hint"):
        parts.append(f"remedy: {metadata['remedy_hint']}")
    return " | ".join(p for p in parts if p) or resp.text[:200]


def _ext_to_mime(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "webp": "image/webp",
    }.get(ext, "image/png")


def _context_label(context: SlideContext) -> str:
    return "Document context" if context.kind == "document" else "Slide context"


def _context_text(context: SlideContext) -> str:
    context_lines = [f"{'Heading' if context.kind == 'document' else 'Slide title'}: {context.title}" if context.title else None]
    if context.section:
        context_lines.append(f"Section: {context.section}")
    if context.body_text:
        context_lines.append(f"{'Nearby text' if context.kind == 'document' else 'Slide text'}: {context.body_text}")
    if context.notes:
        context_lines.append(f"Speaker notes: {context.notes}")
    return "\n".join(line for line in context_lines if line)


def _for_document(text: str, context: SlideContext) -> str:
    """The prompts are written for slides; for a Word file they say document instead."""
    if context.kind != "document":
        return text
    return (text.replace("PowerPoint slides", "Word documents").replace("on the slide", "in the document")
            .replace("on this slide", "in this document").replace("on slide", "in the document")
            .replace("slide's author", "document's author").replace("the slide", "the document"))


def _build_image_messages(image_bytes: bytes, ext: str, context: SlideContext, max_chars: int) -> list[dict]:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = _ext_to_mime(ext)
    return [
        {"role": "system", "content": _for_document(_IMAGE_SYSTEM_PROMPT, context).format(max_chars=max_chars)},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"{_context_label(context)}:\n{_context_text(context)}\n\nWrite alt-text for this image.",
                },
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        },
    ]


def _build_text_messages(system_prompt: str, element_text: str, context: SlideContext, max_chars: int, label: str) -> list[dict]:
    return [
        {"role": "system", "content": _for_document(system_prompt, context).format(max_chars=max_chars)},
        {
            "role": "user",
            "content": (
                f"{_context_label(context)}:\n{_context_text(context)}\n\n"
                f"{label}:\n{element_text}\n\nWrite alt-text for this {label.lower()}."
            ),
        },
    ]


def _to_anthropic_image(url: str) -> dict:
    """Converts an OpenAI-style data-URL image part to an Anthropic image block,
    re-encoding to PNG when the format (e.g. BMP) isn't one Anthropic accepts."""
    header, b64 = url.split(",", 1)
    mime = header[len("data:"):].split(";")[0]
    if mime not in _ANTHROPIC_IMAGE_MIMES:
        try:
            from PIL import Image

            with Image.open(io.BytesIO(base64.b64decode(b64))) as img:
                out = io.BytesIO()
                img.convert("RGBA").save(out, format="PNG")
            mime, b64 = "image/png", base64.b64encode(out.getvalue()).decode("ascii")
        except Exception:
            pass
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}


def _build_request(config: Config, model: str, messages: list[dict]) -> tuple[str, dict, dict]:
    """Returns (url, headers, payload) for the configured provider. Messages are
    built once in OpenAI chat format and translated here for Anthropic."""
    if config.provider == "ollama":
        url = f"{config.base_url}/v1/chat/completions"
    else:
        url = _CHAT_URLS[config.provider]

    if config.provider == "anthropic":
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        converted = []
        for m in messages:
            if m["role"] == "system":
                continue
            content = m["content"]
            if isinstance(content, list):
                content = [
                    _to_anthropic_image(part["image_url"]["url"]) if part["type"] == "image_url" else part
                    for part in content
                ]
            converted.append({"role": m["role"], "content": content})
        payload = {"model": model, "system": system, "messages": converted, "max_tokens": 200}
        return url, headers, payload

    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    payload = {"model": model, "messages": messages}
    # OpenAI's newer models reject max_tokens in favor of max_completion_tokens
    payload["max_completion_tokens" if config.provider == "openai" else "max_tokens"] = 200
    return url, headers, payload


def _parse_completion(config: Config, data: dict) -> str:
    if config.provider == "anthropic":
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()
    return data["choices"][0]["message"]["content"].strip()


class _ModelUnavailable(Exception):
    """Raised for failures worth falling back to another model for."""


async def _request_completion(
    client: httpx.AsyncClient,
    config: Config,
    model: str,
    messages: list[dict],
    max_retries: int,
) -> str | None:
    """Returns the raw completion text, or raises _ModelUnavailable."""
    url, headers, payload = _build_request(config, model, messages)
    label = _PROVIDER_LABELS[config.provider]

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=config.request_timeout)
        except httpx.RequestError as exc:
            if attempt == max_retries:
                raise _ModelUnavailable(str(exc)) from exc
            backoff = 2 ** attempt
            logger.warning(
                "caption attempt %d/%d on '%s' failed (%s), retrying in %ds",
                attempt, max_retries, model, exc, backoff,
            )
            await asyncio.sleep(backoff)
            continue

        if resp.status_code == 200:
            return _parse_completion(config, resp.json())

        if resp.status_code == 402:
            raise _ModelUnavailable(f"billing error (402) - '{model}' needs credits: {_error_detail(resp)}")

        if resp.status_code in (401, 403):
            logger.error(
                "caption generation failed: %s rejected the request (%d) - "
                "check your API key with /doctor.",
                label, resp.status_code,
            )
            return None

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries:
                raise _ModelUnavailable(f"HTTP {resp.status_code} - {_error_detail(resp)}")
            backoff = 2 ** attempt
            logger.warning(
                "caption attempt %d/%d on '%s' failed (HTTP %d), retrying in %ds - %s",
                attempt, max_retries, model, resp.status_code, backoff, _error_detail(resp),
            )
            await asyncio.sleep(backoff)
            continue

        # other 4xx (e.g. model not found) - not retryable on this model, but try fallback
        raise _ModelUnavailable(f"HTTP {resp.status_code} - {_error_detail(resp)}")
    return None


async def _complete_with_fallback(
    client: httpx.AsyncClient,
    config: Config,
    messages: list[dict],
    max_retries: int,
    primary_max_retries: int,
) -> str | None:
    """Tries config.model first (typically a free model) with only `primary_max_retries`
    attempt(s) - free-tier failures are usually shared-pool congestion that a few
    seconds of backoff won't clear, so we fail over to config.fallback_model (a cheap
    paid model, given the full `max_retries`) quickly instead of stalling on retries.

    Returns the raw completion text, or None on permanent failure.
    """
    has_fallback = bool(config.fallback_model) and config.fallback_model != config.model
    try:
        # with nothing to fail over to, the primary gets the full retry budget
        return await _request_completion(
            client, config, config.model, messages, primary_max_retries if has_fallback else max_retries
        )
    except _ModelUnavailable as exc:
        logger.warning("'%s' unavailable (%s)", config.model, exc)

    if not has_fallback:
        logger.error("caption generation failed permanently: no usable fallback model configured")
        return None

    logger.info("falling back to '%s'", config.fallback_model)
    try:
        return await _request_completion(client, config, config.fallback_model, messages, max_retries)
    except _ModelUnavailable as exc:
        logger.error(
            "caption generation failed permanently: fallback model '%s' also unavailable (%s)",
            config.fallback_model, exc,
        )
        return None


async def generate_caption(
    client: httpx.AsyncClient,
    config: Config,
    image_bytes: bytes,
    ext: str,
    context: SlideContext,
    max_retries: int = 3,
    primary_max_retries: int = 1,
    existing: str = "",
) -> str | None:
    """Returns caption text, "" for a decorative image, or None on permanent failure."""
    messages = _review(config, _build_image_messages(image_bytes, ext, context, config.max_alt_text_chars), existing)
    text = await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)
    if text is None:
        return None
    return "" if text.upper() == "DECORATIVE" else text


async def generate_table_alt_text(
    client: httpx.AsyncClient,
    config: Config,
    table_text: str,
    context: SlideContext,
    max_retries: int = 3,
    primary_max_retries: int = 1,
    existing: str = "",
) -> str | None:
    """Returns a text description of a table's content, or None on permanent failure."""
    messages = _review(config, _build_text_messages(
        _TABLE_SYSTEM_PROMPT, table_text, context, config.max_alt_text_chars, "Table"
    ), existing)
    return await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)


async def generate_chart_alt_text(
    client: httpx.AsyncClient,
    config: Config,
    chart_text: str,
    context: SlideContext,
    max_retries: int = 3,
    primary_max_retries: int = 1,
    existing: str = "",
) -> str | None:
    """Returns a text description of a chart's data, or None on permanent failure."""
    messages = _review(config, _build_text_messages(
        _CHART_SYSTEM_PROMPT, chart_text, context, config.max_alt_text_chars, "Chart data"
    ), existing)
    return await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)


async def generate_ole_alt_text(
    client: httpx.AsyncClient,
    config: Config,
    ole_text: str,
    context: SlideContext,
    max_retries: int = 3,
    primary_max_retries: int = 1,
    existing: str = "",
) -> str | None:
    """Returns a text description of an embedded OLE object's content, the
    literal string "UNKNOWN" if the model found no usable signal in the
    heuristically-extracted text, or None on permanent failure. The caller
    decides what to do with "UNKNOWN" (e.g. a progId-based fallback string) -
    this function doesn't guess at that."""
    messages = _review(config, _build_text_messages(
        _OLE_SYSTEM_PROMPT, ole_text, context, config.max_alt_text_chars, "Embedded object content"
    ), existing)
    return await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)


async def generate_smartart_alt_text(
    client: httpx.AsyncClient,
    config: Config,
    smartart_text: str,
    context: SlideContext,
    max_retries: int = 3,
    primary_max_retries: int = 1,
    existing: str = "",
) -> str | None:
    """Returns a text description of a SmartArt diagram's structure, or None
    on permanent failure."""
    messages = _review(config, _build_text_messages(
        _SMARTART_SYSTEM_PROMPT, smartart_text, context, config.max_alt_text_chars, "Diagram outline"
    ), existing)
    return await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)
