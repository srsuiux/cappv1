# 0001. A small local web UI beside the terminal

Status: accepted and built (v1.3.0). Written up from the original development plan, which this replaces.

## Context

cappv1 started as a terminal tool. People who are not comfortable in Terminal or `.env` files could not set it up or follow a run. The terminal had to stay a first-class way to use the tool, and the product rule had to hold: the engine writes alt text (plus the few visually inert fixes in [`../scope.md`](../scope.md)) and nothing else.

## Decision

- A web UI that runs on the user's own computer only (`127.0.0.1`). No cloud service, accounts, telemetry or outside requests from the page.
- No web framework and no build step: a standard-library Python server, plain HTML, CSS and JavaScript. Pages are fragments in `src/web/pages/`, wrapped by a template.
- One brain, two faces. Logic lives in a service layer (`src/services/`) that both the terminal and the browser call, so they cannot disagree. The engine stays a library with no UI knowledge and reports progress through an event bus. Both front ends share one `RunManager`, so a run started in one is visible in the other. Only one run is active at a time.
- Localhost is not automatically safe. The server uses a Host-header allowlist (against DNS rebinding), a random per-launch token sent in a header on every API call, no CORS headers, a strict content policy (no inline script or style), and streamed, size-limited, validated uploads.
- The UI must itself be accessible: keyboard operable, semantic HTML, live regions for progress, contrast of at least 4.5:1 for text, light and dark themes, plain language.
- Deliberately small. It is not a data manager: no database, no file manager, no search, no accounts. "Your data" only shows what cappv1 already keeps and offers one erase action. (The one later exception, owner-approved, is that each run keeps its finished copies in `output/<date>_<time>/` until deleted.)
- The API lives under `/api/v1`, errors are `{"error": {"code", "message", "fix"}}`, and the contract is in [`../API.md`](../API.md).

## Consequences

- Both front ends stay thin. New capability means a service function plus a test, then wiring to each front end ([`../ARCHITECTURE.md`](../ARCHITECTURE.md) has the layout).
- Anything that changes what is sent to an AI service or stored on disk must update the Privacy page, the Your data descriptions and the service notes in the same change; tests tie them to the code.
- A hand-written server has a larger security surface than a framework would. The checklist above is tested, and a framework should be reconsidered only if that surface grows.
- Not built from the original plan: a per-file health check with an "only alt text changed" verification, and per-file fix notes. They are not available and should not be described as if they were.
- Out of scope, as a separate project if ever wanted: a shared campus server (needs real login, TLS, per-user workspaces and queueing), a packaged desktop app, Windows, and editing alt text by hand in the browser.
