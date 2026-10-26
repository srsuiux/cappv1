import os

ACCENT = "#d97757"
OK = "green"
WARN = "yellow"
BAD = "red"
MUTED = "grey62"

# Motion is purely decorative; honor the usual opt-outs.
ANIMATE = not (os.environ.get("CAPPV1_NO_ANIMATION") or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb")

TICK, CROSS, DOT, ARROW = "✔", "✗", "•", "❯"

PROVIDER_LABELS = {
    "ollama": "Ollama",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
}
