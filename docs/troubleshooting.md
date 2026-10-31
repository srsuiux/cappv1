# Troubleshooting

## If something goes wrong

| What you see | What to do |
|---|---|
| `command not found: cappv1` | Run `pipx ensurepath`, then open a new Terminal window. If it still fails, run `pipx install git+https://github.com/srsuiux/cappv1.git` again. |
| A red ✗ in `/doctor` | Read the message beside it. It says what to fix. |
| `API key is not set` or `rejected this key (401)` | Re-check the key in `.env`: no spaces or quotes, and it's on the line that matches your `PROVIDER`. |
| Some images, tables, or charts have no description | The AI service had a temporary hiccup. Type `/run` again; it retries only what's missing. |
| `Ollama is running` shows a red ✗ | Open the Ollama app (or run `ollama serve` in Terminal), then type `/doctor` again. |
| `model ... is downloaded` shows a red ✗ | Run the `ollama pull ...` command shown next to it. |
| Private mode is very slow, or a request times out | Use a smaller model (`gemma3:4b`), close other heavy apps, or raise `REQUEST_TIMEOUT=` in `.env`. |
| A message mentioning "billing" or "402" | That model needs payment. On OpenRouter type `/models` and pick a free one. On OpenAI or Anthropic, add credit to your account. |
| A file doesn't process at all | The file may be damaged. Re-save it from PowerPoint and add it to `input` again. |
