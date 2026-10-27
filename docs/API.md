# Local web API (v1)

The web UI is a thin page over this API. It is meant for the browser on the same computer, not for other programs or other machines: the server only listens on `127.0.0.1`.

## Reaching it

`cappv1 --web` (or `/web` inside cappv1) prints an address like `http://127.0.0.1:8765/#t=<token>`. The token is random and new on every start. The page keeps it and sends it with each call:

```
X-Cappv1-Token: <token>
```

Without the right token every `/api/` call returns `401`. A request whose `Host` header isn't `127.0.0.1:<port>` or `localhost:<port>` gets `403` (this blocks DNS-rebinding). There are no CORS headers, so other websites can't call it.

## Pages

The same server serves the web pages: `/` (landing), `/dashboard`, `/files`, `/services`, `/health`, `/data`, `/how-it-works`, `/privacy`, `/faq`, `/about`. Pages need no token; only `/api/` does.

## Errors

Every failure has the same shape, with a plain-language message and what to do next:

```json
{"error": {"code": "no_key", "message": "OpenAI needs an API key.", "fix": "Get one at …"}}
```

| Status | Codes |
|---|---|
| 400 | `bad_name`, `not_pptx`, `bad_service`, `no_model`, `no_key`, `bad_request` |
| 401 | `unauthorized` |
| 404 | `not_found`, `no_output` |
| 409 | `busy`, `nothing_to_do`, `no_files`, `not_configured`, `model_missing` |
| 411 / 413 | `length_required`, `too_big` |
| 502 / 503 | `network`, `ollama_down` |

## Endpoints

All paths start with `/api/v1`. Bodies are JSON unless noted.

| Method and path | What it does |
|---|---|
| `GET /settings` | Current service, model, and which services have a saved key. Never returns a key. |
| `PUT /settings` | `{provider, model, api_key?}`: make this the active choice. |
| `POST /settings/test` | `{provider, api_key}` → `{ok, detail}`: ask the service whether it accepts the key. |
| `GET /services` | The four services: whether each is private, what it does with slides (`handling`), its privacy policy link, whether it needs a key and has one saved, and the model last used. |
| `DELETE /settings/keys/<id>` | Forget a saved key. |
| `GET /storage` | What cappv1 keeps and where: `places` with `label`, `path`, `what`, `files`, `bytes` and `has_slides`. |
| `POST /storage/clear` | `{confirm: true}`: erase decks, finished copies, saved progress and logs. Keeps settings and keys. Refused during a run. |
| `GET /services/<id>/models` | Models to choose from. OpenAI and Anthropic: a short list. Ollama: installed vision models. OpenRouter: `free`, `cheapest`, and `makers`. |
| `GET /files` | Files in the input list: `name`, `size`, `state` (`new`, `partial`, `changed`, `done`), `has_output`. |
| `PUT /files/<name>` | Upload a deck. The body is the raw file (not multipart) and `Content-Length` is required. Up to 200 MB. It is checked to be a real `.pptx` before it is kept. |
| `DELETE /files/<name>` | Remove a deck from the input list (not while a run is going). |
| `GET /files/<name>/download` | The finished copy. |
| `POST /runs` | `{resume?, force?, confirm?}` → `202` with the run and `pending` files. `force` replaces alt text the author wrote, so it also needs `confirm: true`. |
| `GET /runs/current` | The latest run: `id`, `state` (`idle`, `running`, `done`, `cancelled`, `failed`), `failed_files`, `error`. |
| `POST /runs/<id>/cancel` | Stop after the item in flight; finished slides stay saved. |
| `GET /runs/<id>/events` | Server-Sent Events (see below). |
| `GET /doctor` | `{ok, checks: [{label, ok, detail}]}`. |

One run at a time. The terminal and the web page share it, so a run started in one shows up in the other.

## Progress events

`GET /runs/<id>/events` streams `text/event-stream`. Each message has an `id`, an `event` name, and JSON `data`. Names: `file_start`, `slide_start`, `element_start`, `element_end`, `slide_end`, `alt_written` (the text just written, with `outcome`: `captioned`, `enhanced`, `kept` or `cached`), `file_saved`, `file_failed`, `run_done`, and a final `run_finished` with the end state, after which the stream closes.

If the connection drops, the browser reconnects with `Last-Event-ID` and receives only what it missed.
