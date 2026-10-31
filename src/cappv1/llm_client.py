import asyncio
import base64
import json
import logging

import httpx

from cappv1.config import Config
from cappv1.llm_prompts import (
    _CHART_SYSTEM_PROMPT,
    _IMAGE_SYSTEM_PROMPT,
    _OLE_SYSTEM_PROMPT,
    _SMARTART_SYSTEM_PROMPT,
    _TABLE_SYSTEM_PROMPT,
    _with_existing,
)
from cappv1.llm_providers import _PROVIDER_LABELS, _build_request, _ModelUnavailable, _parse_completion
from cappv1.pptx_reader import SlideContext

logger = logging.getLogger("pptx_alt_text")


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
    return (
        text.replace("PowerPoint slides", "Word documents")
        .replace("on the slide", "in the document")
        .replace("on this slide", "in this document")
        .replace("on slide", "in the document")
        .replace("slide's author", "document's author")
        .replace("the slide", "the document")
    )


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
            backoff = 2**attempt
            logger.warning(
                "caption attempt %d/%d on '%s' failed (%s), retrying in %ds",
                attempt,
                max_retries,
                model,
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
            continue

        if resp.status_code == 200:
            try:
                return _parse_completion(config, resp.json())
            except _ModelUnavailable as exc:  # an empty reply is usually momentary: ask the same model again
                if attempt == max_retries:
                    raise
                backoff = 2**attempt
                logger.warning("caption attempt %d/%d on '%s' failed (%s), retrying in %ds", attempt, max_retries, model, exc, backoff)
                await asyncio.sleep(backoff)
                continue

        if resp.status_code == 402:
            raise _ModelUnavailable(f"billing error (402) - '{model}' needs credits: {_error_detail(resp)}")

        if resp.status_code in (401, 403):
            logger.error(
                "caption generation failed: %s rejected the request (%d) - check your API key with /doctor.",
                label,
                resp.status_code,
            )
            return None

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries:
                raise _ModelUnavailable(f"HTTP {resp.status_code} - {_error_detail(resp)}")
            backoff = 2**attempt
            logger.warning(
                "caption attempt %d/%d on '%s' failed (HTTP %d), retrying in %ds - %s",
                attempt,
                max_retries,
                model,
                resp.status_code,
                backoff,
                _error_detail(resp),
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
        return await _request_completion(client, config, config.model, messages, primary_max_retries if has_fallback else max_retries)
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
            config.fallback_model,
            exc,
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
    messages = _review(
        config, _build_text_messages(_TABLE_SYSTEM_PROMPT, table_text, context, config.max_alt_text_chars, "Table"), existing
    )
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
    messages = _review(
        config, _build_text_messages(_CHART_SYSTEM_PROMPT, chart_text, context, config.max_alt_text_chars, "Chart data"), existing
    )
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
    messages = _review(
        config, _build_text_messages(_OLE_SYSTEM_PROMPT, ole_text, context, config.max_alt_text_chars, "Embedded object content"), existing
    )
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
    messages = _review(
        config,
        _build_text_messages(_SMARTART_SYSTEM_PROMPT, smartart_text, context, config.max_alt_text_chars, "Diagram outline"),
        existing,
    )
    return await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)
