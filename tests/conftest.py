import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cappv1.services import settings
from cappv1.services.workspace import Workspace

_WATCHED = ("PROVIDER", "MODEL", "FALLBACK_MODEL", "CONCURRENCY", "MIN_", "MAX_ALT", "OLLAMA_", "REQUEST_TIMEOUT")


@pytest.fixture(autouse=True)
def isolated_env():
    """Tests never see the developer's real .env settings or keys."""
    saved = dict(os.environ)
    for key in list(os.environ):
        if key.endswith("_API_KEY") or key.startswith(_WATCHED) or key.startswith("MODEL_"):
            del os.environ[key]
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def ws(tmp_path) -> Workspace:
    w = Workspace(tmp_path / "work")
    w.ensure()
    return w


class FakeOllama:
    """A stand-in for a local Ollama: answers model-list and chat requests."""

    def __init__(self) -> None:
        self.calls = 0
        self.delay = 0.0
        self.reply = "A short test description."
        self.models = {"gemma3:4b": ["completion", "vision"], "textonly:1b": ["completion"]}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send({"models": [{"name": n} for n in fake.models]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/show":
                    return self._send({"capabilities": fake.models.get(body["model"], [])})
                if fake.delay:
                    import time
                    time.sleep(fake.delay)
                fake.calls += 1
                self._send({"choices": [{"message": {"content": fake.reply}}]})

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()


@pytest.fixture
def fake_ollama():
    f = FakeOllama()
    yield f
    f.stop()


@pytest.fixture
def configured(ws, fake_ollama):
    """A workspace set up to use the fake local model."""
    from cappv1.services import envfile

    envfile.set_values(ws, {"OLLAMA_BASE_URL": fake_ollama.url})
    settings.save(ws, "ollama", "gemma3:4b")
    return ws
