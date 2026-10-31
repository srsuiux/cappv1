# Configuration

Settings live in `.env` in the project folder (copy [`.env.example`](../.env.example) to start). Write `NAME=value` with no spaces around the `=`. Blank or missing means the default. The `/init` and `/models` commands and the Services page edit this file for you.

| Variable | Default | What it does |
|---|---|---|
| `PROVIDER` | The first service below that has a key filled in, otherwise `openrouter` | Which AI service to use: `openrouter`, `openai`, `anthropic` or `ollama`. See [AI services](providers.md). |
| `OPENROUTER_API_KEY` | blank | Key for OpenRouter. Only used when the service is `openrouter`. |
| `OPENAI_API_KEY` | blank | Key for OpenAI. Only used when the service is `openai`. |
| `ANTHROPIC_API_KEY` | blank | Key for Anthropic. Only used when the service is `anthropic`. |
| `MODEL` | The service's default model (see [AI services](providers.md#switching-ai-service-or-model)) | The model to use. Must be a model from the chosen service. |
| `FALLBACK_MODEL` | `google/gemma-3-12b-it` on OpenRouter, none elsewhere | Tried when `MODEL` is unavailable, rate-limited or out of credits. Must be from the same service. |
| `CONCURRENCY` | `4`, or `1` for Ollama | How many requests run at the same time. |
| `MIN_IMAGE_SIZE_PX` | `40` | Pictures narrower or shorter than this many pixels, or that cannot be read, are marked decorative instead of described. |
| `MIN_EXISTING_ALT_CHARS` | `30` | Alt text already in a file that is shorter than this is treated as unfinished and improved. Longer text is kept unless the AI judges it inadequate. |
| `MAX_ALT_TEXT_CHARS` | `125` | The length the AI is asked to stay under for each description. It is a request in the prompt, not a hard cut-off. |
| `REQUEST_TIMEOUT` | `60` seconds, or `300` for Ollama | How long to wait for one answer from the AI service before giving up. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama is running. Anything that is not on this computer is refused unless `OLLAMA_ALLOW_REMOTE=1`. |
| `OLLAMA_ALLOW_REMOTE` | unset | Set to `1` to allow an `OLLAMA_BASE_URL` on another machine you control. Slides are then sent to that machine. |
| `CAPPV1_HOME` | The project folder | Keeps `.env`, `input/`, `output/`, saved progress (`.state/`) and `logs/` in another folder. This one is read from the environment, not from `.env`, because it says where `.env` is. |
| `CAPPV1_NO_ANIMATION` | unset | Set to any value to turn off the terminal animations. They are also off when `NO_COLOR` is set or the terminal is `dumb`. |
