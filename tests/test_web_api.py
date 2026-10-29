import http.client
import json
import time

import pytest

from src.web.server import TOKEN_HEADER, WebServer
from tests.helpers import make_deck


class Client:
    def __init__(self, server: WebServer) -> None:
        self.server = server

    def call(self, method, path, body=None, token=True, host=None, raw=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=10)
        h = dict(headers or {})
        if token:
            h[TOKEN_HEADER] = self.server.token
        if host:
            h["Host"] = host
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        conn.request(method, path, body=data, headers=h)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(payload), resp
        except ValueError:
            return resp.status, payload, resp


@pytest.fixture
def web(configured):
    server = WebServer(configured, port=0)
    server.start()
    yield Client(server)
    server.stop()


@pytest.fixture
def deck(configured, tmp_path):
    return make_deck(tmp_path / "talk.pptx").read_bytes()


def upload(web, name, data):
    return web.call("PUT", f"/api/v1/files/{name}", raw=data)


# ---- doors -------------------------------------------------------------------
def test_api_needs_the_token(web):
    status, body, _ = web.call("GET", "/api/v1/settings", token=False)
    assert status == 401 and body["error"]["code"] == "unauthorized"
    status, _, _ = web.call("GET", "/api/v1/settings", headers={TOKEN_HEADER: "wrong"}, token=False)
    assert status == 401


def test_a_foreign_host_header_is_refused(web):
    status, _, _ = web.call("GET", "/api/v1/settings", host="evil.example.com")
    assert status == 403
    status, _, _ = web.call("GET", "/", host="evil.example.com")
    assert status == 403


def test_pages_load_without_a_token_and_carry_safety_headers(web):
    status, body, resp = web.call("GET", "/", token=False)
    assert status == 200 and b"cappv1" in body
    assert "default-src 'self'" in resp.getheader("Content-Security-Policy")
    assert resp.getheader("Access-Control-Allow-Origin") is None


def test_static_files_cannot_escape_their_folder(web):
    for path in ("/../server.py", "/%2e%2e/server.py", "/..%2fapi.py", "/../pages/privacy.html", "/%2e%2e/templates/app.html"):
        status, _, _ = web.call("GET", path, token=False)
        assert status == 404


def test_unknown_routes_and_methods(web):
    assert web.call("GET", "/api/v1/nope")[0] == 404
    assert web.call("DELETE", "/api/v1/settings")[0] == 405
    assert web.call("POST", "/")[0] == 405


# ---- settings -----------------------------------------------------------------
def test_settings_never_contain_keys(web, configured):
    status, _, _ = web.call("PUT", "/api/v1/settings", {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-secret-123"})
    assert status == 200
    status, body, resp = web.call("GET", "/api/v1/settings")
    assert body["provider"] == "openai" and body["keys_saved"]["openai"] is True
    assert "sk-secret-123" not in json.dumps(body)
    assert "sk-secret-123" not in json.dumps(web.call("GET", "/api/v1/services")[1])


def test_errors_use_one_shape(web):
    status, body, _ = web.call("PUT", "/api/v1/settings", {"provider": "openai", "model": "gpt-4o-mini"})
    assert status == 400 and set(body["error"]) == {"code", "message", "fix"} and body["error"]["code"] == "no_key"
    status, body, _ = web.call("PUT", "/api/v1/settings", {"provider": "nope", "model": "x"})
    assert body["error"]["code"] == "bad_service"
    status, body, _ = web.call("PUT", "/api/v1/settings", raw=b"not json", headers={"Content-Length": "8"})
    assert status == 400 and body["error"]["code"] == "bad_request"


def test_services_and_models(web):
    status, body, _ = web.call("GET", "/api/v1/services")
    assert {s["id"] for s in body["services"]} == {"ollama", "openrouter", "openai", "anthropic"}
    status, body, _ = web.call("GET", "/api/v1/services/openai/models")
    assert body["models"][0]["id"] == "gpt-4o-mini"
    status, body, _ = web.call("GET", "/api/v1/services/ollama/models")
    assert [m["id"] for m in body["models"]] == ["gemma3:4b"]
    assert web.call("GET", "/api/v1/services/bogus/models")[1]["error"]["code"] == "bad_service"


# ---- files --------------------------------------------------------------------
def test_upload_list_download_delete(web, deck):
    status, body, _ = upload(web, "talk.pptx", deck)
    assert status == 201 and body["name"] == "talk.pptx" and body["state"] == "new"
    assert web.call("GET", "/api/v1/files")[1]["files"][0]["name"] == "talk.pptx"
    assert web.call("GET", "/api/v1/files/talk.pptx/download")[1]["error"]["code"] == "no_output"
    assert web.call("DELETE", "/api/v1/files/talk.pptx")[0] == 200
    assert web.call("GET", "/api/v1/files")[1]["files"] == []


def test_bad_uploads_are_refused(web, deck, monkeypatch):
    assert upload(web, "notes.txt", b"hello")[1]["error"]["code"] == "unsupported_file"
    assert upload(web, "fake.pptx", b"not a zip")[1]["error"]["code"] == "unsupported_file"
    status, body, _ = upload(web, "..%2Fescape.pptx", deck)  # only the file name part is ever used
    assert status == 201 and body["name"] == "escape.pptx" and not (web.server.ws.root / "escape.pptx").exists()
    web.call("DELETE", "/api/v1/files/escape.pptx")
    from src.services import files
    monkeypatch.setattr(files, "MAX_UPLOAD_BYTES", 10)
    assert upload(web, "big.pptx", deck)[1]["error"]["code"] == "too_big"
    assert not list(web.server.ws.input_dir.iterdir())  # nothing half-saved


def test_upload_without_length_is_refused(web):
    conn = http.client.HTTPConnection("127.0.0.1", web.server.port, timeout=5)
    conn.putrequest("PUT", "/api/v1/files/a.pptx")
    conn.putheader(TOKEN_HEADER, web.server.token)
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 411
    conn.close()


# ---- runs ---------------------------------------------------------------------
def wait_done(web, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        run = web.call("GET", "/api/v1/runs/current")[1]
        if run["state"] != "running":
            return run
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_run_streams_progress_and_produces_a_download(web, deck):
    upload(web, "talk.pptx", deck)
    status, run, _ = web.call("POST", "/api/v1/runs", {})
    assert status == 202 and run["pending"] == ["talk.pptx"]
    conn = http.client.HTTPConnection("127.0.0.1", web.server.port, timeout=30)
    conn.request("GET", f"/api/v1/runs/{run['id']}/events", headers={TOKEN_HEADER: web.server.token})
    resp = conn.getresponse()
    assert resp.getheader("Content-Type").startswith("text/event-stream")
    stream = resp.read().decode()
    conn.close()
    assert "event: slide_end" in stream and "event: run_finished" in stream
    assert "event: alt_written" in stream and "A short test description." in stream
    assert wait_done(web)["state"] == "done"
    status, body, resp = web.call("GET", "/api/v1/files/talk.pptx/download")
    assert status == 200 and body[:2] == b"PK" and "attachment" in resp.getheader("Content-Disposition")


def test_events_replay_from_last_event_id(web, deck):
    upload(web, "talk.pptx", deck)
    run = web.call("POST", "/api/v1/runs", {})[1]
    wait_done(web)
    conn = http.client.HTTPConnection("127.0.0.1", web.server.port, timeout=10)
    conn.request("GET", f"/api/v1/runs/{run['id']}/events", headers={TOKEN_HEADER: web.server.token, "Last-Event-ID": "3"})
    stream = conn.getresponse().read().decode()
    conn.close()
    ids = [int(line[4:]) for line in stream.splitlines() if line.startswith("id: ")]
    assert ids and ids[0] == 4


def test_run_rules(web, deck):
    assert web.call("POST", "/api/v1/runs", {})[1]["error"]["code"] == "no_files"
    upload(web, "talk.pptx", deck)
    assert web.call("POST", "/api/v1/runs", {"force": True})[1]["error"]["code"] == "bad_request"  # needs confirm
    web.call("POST", "/api/v1/runs", {})
    wait_done(web)
    assert web.call("POST", "/api/v1/runs", {})[1]["error"]["code"] == "nothing_to_do"
    assert web.call("POST", "/api/v1/runs/999/cancel")[1]["error"]["code"] == "not_found"


def test_doctor(web):
    status, body, _ = web.call("GET", "/api/v1/doctor")
    assert status == 200 and {"checks", "ok"} <= set(body) and body["checks"][0]["label"]


def test_audit_endpoint(web, deck):
    upload(web, "talk.pptx", deck)
    status, body, _ = web.call("GET", "/api/v1/files/talk.pptx/audit")
    assert status == 200 and body["file"] == "talk.pptx" and {"groups", "problems", "checked_text"} <= set(body)
    assert web.call("GET", "/api/v1/files/nope.pptx/audit")[1]["error"]["code"] == "not_found"


# ---- your data and keys -----------------------------------------------------------
def test_services_describe_what_happens_to_slides(web):
    services = {s["id"]: s for s in web.call("GET", "/api/v1/services")[1]["services"]}
    assert "never leave" in services["ollama"]["handling"] and services["ollama"]["policy_url"] == ""
    for name in ("openrouter", "openai", "anthropic"):
        assert services[name]["handling"] and services[name]["policy_url"].startswith("https://")


def test_a_saved_key_can_be_removed_but_never_read(web):
    web.call("PUT", "/api/v1/settings", {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-secret-123"})
    status, body, _ = web.call("DELETE", "/api/v1/settings/keys/openai")
    assert status == 200 and body["keys_saved"]["openai"] is False
    assert "sk-secret-123" not in (web.server.ws.env_path.read_text())
    assert web.call("DELETE", "/api/v1/settings/keys/ollama")[1]["error"]["code"] == "bad_request"
    assert web.call("DELETE", "/api/v1/settings/keys/nope")[1]["error"]["code"] == "bad_service"


def test_storage_lists_what_is_kept_and_erases_on_request(web, deck):
    upload(web, "talk.pptx", deck)
    web.call("POST", "/api/v1/runs", {})
    wait_done(web)
    status, body, _ = web.call("GET", "/api/v1/storage")
    places = {p["id"]: p for p in body["places"]}
    assert set(places) == {"input", "output", "state", "logs", "settings"}
    assert places["input"]["files"] == 1 and places["output"]["files"] == 1 and places["state"]["files"] >= 1
    assert places["settings"]["has_slides"] is False and places["input"]["has_slides"] is True
    assert web.call("POST", "/api/v1/storage/clear", {})[1]["error"]["code"] == "bad_request"  # needs confirm
    status, body, _ = web.call("POST", "/api/v1/storage/clear", {"confirm": True})
    assert status == 200 and body["erased"]["input"] == 1 and body["erased"]["output"] == 1
    after = {p["id"]: p for p in web.call("GET", "/api/v1/storage")[1]["places"]}
    assert after["input"]["files"] == after["output"]["files"] == after["state"]["files"] == 0
    assert after["settings"]["files"] == 1  # settings and keys stay


def test_erasing_is_refused_during_a_run(web, deck, fake_ollama):
    fake_ollama.delay = 0.5
    upload(web, "talk.pptx", deck)
    web.call("POST", "/api/v1/runs", {})
    assert web.call("POST", "/api/v1/storage/clear", {"confirm": True})[1]["error"]["code"] == "busy"
    web.call("POST", f"/api/v1/runs/{web.call('GET', '/api/v1/runs/current')[1]['id']}/cancel")
    wait_done(web)


def test_a_word_document_goes_through_the_whole_web_api(web, tmp_path):
    from tests.test_docx import make_docx

    status, body, _ = upload(web, "paper.docx", make_docx(tmp_path / "paper.docx").read_bytes())
    assert status == 201 and body["name"] == "paper.docx"
    assert web.call("GET", "/api/v1/files/paper.docx/audit")[1]["error"]["code"] == "audit_unsupported"
    assert web.call("POST", "/api/v1/runs", {})[0] in (200, 201, 202)
    web.server.runs.wait(30)
    assert web.call("GET", "/api/v1/files")[1]["files"][0]["state"] == "done"
    status, _, headers = web.call("GET", "/api/v1/files/paper.docx/download")
    assert status == 200 and "wordprocessingml" in headers.getheader("Content-Type")
