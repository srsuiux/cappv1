# AI services

## Choosing an AI service

An API key is like a password that lets this tool use an AI service. You only need **one** of these:

| Service | Cost | Where to get a key |
|---|---|---|
| **OpenRouter** | Has free models (the default) | [openrouter.ai](https://openrouter.ai) → account settings → API Keys. Keys start with `sk-or-v1-`. |
| **OpenAI** | Paid, a fraction of a cent per image | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Anthropic** | Paid, a fraction of a cent per image | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| **Ollama** (runs on your computer) | Free, no key, works offline | [ollama.com/download](https://ollama.com/download). See [Private mode](#private-mode-run-everything-on-your-own-computer). |

Each key only works with its own service. For example, an OpenAI key can't be used through OpenRouter.

> **Privacy:** free OpenRouter models send your slide content through shared third-party providers that may log or train on it. If your slides contain anything sensitive (student names, grades, ID numbers, unpublished research), use [Private mode](#private-mode-run-everything-on-your-own-computer) (nothing leaves your computer), or a paid OpenAI or Anthropic key.

## Private mode: run everything on your own computer

With Ollama, the AI model runs on your computer. Your slides, images, and text are never sent to OpenRouter, OpenAI, Anthropic, or anyone else, and after the one-time model download it works with no internet at all. Use this for anything sensitive (student names, grades, ID numbers, unpublished research).

**1. Install Ollama.** Download it from [ollama.com/download](https://ollama.com/download) and open it once. It then runs quietly in the background (look for the llama icon in your menu bar).

**2. Download a model (one time, needs internet).** In Terminal:

```
ollama pull gemma3:4b
```

This is about 3 GB and works on most laptops with 8 GB of memory. The model must be able to read images ("vision"). Other good choices are `qwen2.5vl:7b` and `llama3.2-vision`, which write better descriptions but need more memory and run slower.

**3. Point cappv1 at it.** Open `.env` and set:

```
PROVIDER=ollama
```

If you downloaded a different model in step 2, also set `MODEL=` to its name, for example `MODEL=qwen2.5vl:7b`. Leave all the key lines blank.

**4. Check and run.**

```
cappv1
```

Then type `/doctor`. It should show green checks for "Ollama address is this computer", "Ollama is running", and "model is downloaded". Type `/run` to start. `/models` lists the vision models you have installed and lets you pick one.

**What to expect.** Local models are slower than the online services: roughly several seconds to a minute per image, depending on your computer. They process one image at a time. Small models also write plainer descriptions and are weaker on embedded Word/Excel objects, so read the results before sharing. If quality matters more than privacy, use a bigger local model or an online service.

**Safety check.** cappv1 only talks to Ollama on your own computer (`localhost`). If `OLLAMA_BASE_URL` in `.env` points to any other machine, it refuses to run, so you can't accidentally send slides elsewhere. If you really do run Ollama on another machine you control, set `OLLAMA_ALLOW_REMOTE=1` to allow it.

## Switching AI service or model

Open `.env` and change `PROVIDER=` to another service (make sure that service's key is filled in). Leave `MODEL=` blank to use the service's default, or set a model from that same service:

| Service | Default model |
|---|---|
| OpenRouter | `minimax/minimax-m3:free` (falls back to `google/gemma-3-12b-it`) |
| OpenAI | `gpt-4o-mini` |
| Anthropic | `claude-haiku-5-5` |
| Ollama | `gemma3:4b` (must be downloaded first with `ollama pull`) |
