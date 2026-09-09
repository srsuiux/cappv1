import asyncio
import base64
import json
import logging

import httpx

from src.config import Config
from src.pptx_reader import SlideContext

logger = logging.getLogger("pptx_alt_text")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

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


def _error_detail(resp: httpx.Response) -> str:
    """Pulls the useful part out of an OpenRouter error body, if present."""
    try:
        err = resp.json().get("error", {})
    except (json.JSONDecodeError, ValueError):
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


def _context_text(context: SlideContext) -> str:
    context_lines = [f"Slide title: {context.title}" if context.title else None]
    if context.section:
        context_lines.append(f"Section: {context.section}")
    if context.body_text:
        context_lines.append(f"Slide text: {context.body_text}")
    if context.notes:
        context_lines.append(f"Speaker notes: {context.notes}")
    return "\n".join(line for line in context_lines if line)


def _build_image_messages(image_bytes: bytes, ext: str, context: SlideContext, max_chars: int) -> list[dict]:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = _ext_to_mime(ext)
    return [
        {"role": "system", "content": _IMAGE_SYSTEM_PROMPT.format(max_chars=max_chars)},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Slide context:\n{_context_text(context)}\n\nWrite alt-text for this image.",
                },
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        },
    ]


def _build_text_messages(system_prompt: str, element_text: str, context: SlideContext, max_chars: int, label: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt.format(max_chars=max_chars)},
        {
            "role": "user",
            "content": (
                f"Slide context:\n{_context_text(context)}\n\n"
                f"{label}:\n{element_text}\n\nWrite alt-text for this {label.lower()}."
            ),
        },
    ]


class _ModelUnavailable(Exception):
    """Raised for failures worth falling back to another model for."""


async def _request_completion(
    client: httpx.AsyncClient,
    model: str,
    messages: list[dict],
    headers: dict,
    max_retries: int,
) -> str | None:
    """Returns the raw completion text, or raises _ModelUnavailable."""
    payload = {"model": model, "messages": messages, "max_tokens": 200}

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
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
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        if resp.status_code == 402:
            raise _ModelUnavailable(f"billing error (402) - '{model}' needs credits: {_error_detail(resp)}")

        if resp.status_code in (401, 403):
            logger.error(
                "caption generation failed: OpenRouter rejected the request (%d) - "
                "check your API key with 'cappv1 doctor'.",
                resp.status_code,
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
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    try:
        return await _request_completion(client, config.model, messages, headers, primary_max_retries)
    except _ModelUnavailable as exc:
        logger.warning("'%s' unavailable (%s)", config.model, exc)

    if not config.fallback_model or config.fallback_model == config.model:
        logger.error("caption generation failed permanently: no usable fallback model configured")
        return None

    logger.info("falling back to '%s'", config.fallback_model)
    try:
        return await _request_completion(client, config.fallback_model, messages, headers, max_retries)
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
) -> str | None:
    """Returns caption text, "" for a decorative image, or None on permanent failure."""
    messages = _build_image_messages(image_bytes, ext, context, config.max_alt_text_chars)
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
) -> str | None:
    """Returns a text description of a table's content, or None on permanent failure."""
    messages = _build_text_messages(
        _TABLE_SYSTEM_PROMPT, table_text, context, config.max_alt_text_chars, "Table"
    )
    return await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)


async def generate_chart_alt_text(
    client: httpx.AsyncClient,
    config: Config,
    chart_text: str,
    context: SlideContext,
    max_retries: int = 3,
    primary_max_retries: int = 1,
) -> str | None:
    """Returns a text description of a chart's data, or None on permanent failure."""
    messages = _build_text_messages(
        _CHART_SYSTEM_PROMPT, chart_text, context, config.max_alt_text_chars, "Chart data"
    )
    return await _complete_with_fallback(client, config, messages, max_retries, primary_max_retries)
