import asyncio
import base64
import logging

import httpx

from src.config import Config
from src.pptx_reader import SlideContext

logger = logging.getLogger("pptx_alt_text")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = (
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


def _build_messages(image_bytes: bytes, ext: str, context: SlideContext, max_chars: int) -> list[dict]:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = _ext_to_mime(ext)
    context_lines = [f"Slide title: {context.title}" if context.title else None]
    if context.section:
        context_lines.append(f"Section: {context.section}")
    if context.body_text:
        context_lines.append(f"Slide text: {context.body_text}")
    if context.notes:
        context_lines.append(f"Speaker notes: {context.notes}")
    context_text = "\n".join(line for line in context_lines if line)

    return [
        {"role": "system", "content": _SYSTEM_PROMPT.format(max_chars=max_chars)},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Slide context:\n{context_text}\n\nWrite alt-text for this image.",
                },
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        },
    ]


async def generate_caption(
    client: httpx.AsyncClient,
    config: Config,
    image_bytes: bytes,
    ext: str,
    context: SlideContext,
    max_retries: int = 3,
) -> str | None:
    """Returns caption text, "" for a decorative image, or None on permanent failure."""
    messages = _build_messages(image_bytes, ext, context, config.max_alt_text_chars)
    payload = {"model": config.model, "messages": messages, "max_tokens": 200}
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return "" if text.upper() == "DECORATIVE" else text
        except Exception as exc:
            if attempt == max_retries:
                logger.error("caption generation failed permanently: %s", exc)
                return None
            backoff = 2 ** attempt
            logger.warning(
                "caption attempt %d/%d failed (%s), retrying in %ds",
                attempt, max_retries, exc, backoff,
            )
            await asyncio.sleep(backoff)
    return None
