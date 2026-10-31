# Privacy

cappv1 has no accounts, no analytics and no servers of its own. It runs on your computer. Your slides leave it only if you choose a cloud AI service, and then only the parts that service needs, sent straight from your computer to that service. The same information is on the Privacy page inside the web app.

> **Privacy:** free OpenRouter models send your slide content through shared third-party providers that may log or train on it. If your slides contain anything sensitive (student names, grades, ID numbers, unpublished research), use [Private mode](providers.md#private-mode-run-everything-on-your-own-computer) (nothing leaves your computer), or a paid OpenAI or Anthropic key.

## What is sent to an AI service

When cappv1 describes an item, it sends that service a request made of these parts:

| Item | What is sent |
|---|---|
| A picture | The picture itself |
| A table | The table's text |
| An embedded object, such as a Visio drawing | Text read out of the object's file (rough and out of order), never its picture |
| A chart | The chart's text and numbers |
| Every item | The slide's title, section name, text and speaker notes, any alt text already there, and cappv1's instructions. For a Word document: the nearest heading above the item, the paragraphs just before and after it, any alt text already there, and cappv1's instructions |

The whole file is never uploaded, other slides (or the rest of a Word document) are not included, and file names are not sent. Because speaker notes and slide text are included as context, don't use a cloud service for decks whose notes you wouldn't want it to see.

## Where it goes, per service

| Service | Where it goes |
|---|---|
| Ollama | Nowhere. It runs on this computer. cappv1 refuses a non-local Ollama address unless you explicitly allow it (`OLLAMA_ALLOW_REMOTE=1`). |
| OpenRouter | To OpenRouter, which forwards it to the company that runs the model you picked. Free models may log requests. |
| OpenAI | To OpenAI's API. |
| Anthropic | To Anthropic's API. |

Once content reaches a cloud service, that service's own policy applies, including how long it keeps requests and whether it trains on them. Read it before you use the service: [OpenRouter](https://openrouter.ai/privacy), [OpenAI](https://openai.com/policies/privacy-policy), [Anthropic](https://www.anthropic.com/legal/privacy). Your API key is sent only to the service it belongs to.

## What is stored on your computer

| Where | What |
|---|---|
| `input/` | Copies of the decks and Word documents you added |
| `output/` | The finished decks and documents, one folder per run (named for the time it ran) until you delete it |
| `.state/` | Progress, the alt text already written, and notes on items it could not read (where they are and why), so repeat runs cost nothing |
| `logs/` | File names, slide counts and error messages, not slide content |
| `.env` | Your chosen service and model, and any API keys, readable only by your account |

Delete cappv1's folder to remove everything it has ever stored.

## Other network connections

- **Checking a key:** when you save a new key, cappv1 asks that service whether it accepts it.
- **Browsing OpenRouter models:** cappv1 fetches OpenRouter's public model list. No key and no slide content is sent.
- **Installing:** installing cappv1 (for example with pipx) downloads its Python packages from the Python Package Index. cappv1 itself downloads nothing when you run it.

There is nothing else: no update checks, no error reports, no analytics.

## Who can reach the web page

Only programs on this computer. The server listens on `127.0.0.1`, so other devices on your network can't open it. Each launch creates a new random code that every request must carry, and requests with an unexpected address are refused, which stops other websites from using it.

This page describes how cappv1 behaves. It isn't legal advice, and it can't speak for the AI services you choose.
