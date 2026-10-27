# Security

## Reporting a vulnerability

Please report security problems privately, not in a public issue. On GitHub, open the repository's **Security** tab and choose **Report a vulnerability**. Include what you found, how to reproduce it, and the cappv1 version (`cappv1 --version`). You'll get a reply within a few days.

## What we consider in scope

- The local web server (`src/web`): access control, request handling, file upload and download, path handling.
- Handling of API keys and of decks and their contents.
- Anything that lets a deck be changed beyond its alt text.

## How the web server is protected

- It listens on `127.0.0.1` only.
- Every API request needs a random per-launch token; requests with an unexpected `Host` header are refused; there are no CORS headers.
- Pages are served with a strict content policy (no inline script, no outside resources).
- Uploads are streamed, size-limited and validated as `.pptx` before they are kept; names are reduced to a safe file name.
- API keys are stored in a file readable only by the owner and are never returned by the API.

Reports that need an attacker to already control the computer or the user's account are out of scope.

## Supported versions

Only the latest release receives fixes.
