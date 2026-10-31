"""What differs between AI services: URLs, headers, payload shape and reply parsing."""

import base64
import io

from cappv1.config import Config

_CHAT_URLS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
}


_PROVIDER_LABELS = {"openrouter": "OpenRouter", "openai": "OpenAI", "anthropic": "Anthropic", "ollama": "Ollama"}


_ANTHROPIC_VERSION = "2023-06-01"


_ANTHROPIC_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _to_anthropic_image(url: str) -> dict:
    """Converts an OpenAI-style data-URL image part to an Anthropic image block,
    re-encoding to PNG when the format (e.g. BMP) isn't one Anthropic accepts."""
    header, b64 = url.split(",", 1)
    mime = header[len("data:") :].split(";")[0]
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
                content = [_to_anthropic_image(part["image_url"]["url"]) if part["type"] == "image_url" else part for part in content]
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
    content = data["choices"][0]["message"]["content"]
    if content is None:  # some free models answer with null; try the fallback model instead of crashing
        raise _ModelUnavailable("the model sent an empty reply")
    return content.strip()


class _ModelUnavailable(Exception):
    """Raised for failures worth falling back to another model for."""
