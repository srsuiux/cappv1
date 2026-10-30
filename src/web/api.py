"""The /api/v1 routes: each one asks a service and returns JSON."""
import json
import time
from urllib.parse import quote

from src.services import audit, files, health, models, settings, storage
from src.services.errors import ServiceError

PREFIX = "/api/v1"
_NAME = r"([^/]+)"


def _need(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ServiceError("bad_request", f"“{key}” is missing.")
    return value


def _flag(body: dict, key: str) -> bool:
    return body.get(key) is True


def _run_dict(req) -> dict:
    status = req.runs.status().as_dict()
    status["id"] = str(int(status["started"] * 1000)) if status["started"] else ""
    return status


def _own_run(req) -> dict:
    run = _run_dict(req)
    if not run["id"] or run["id"] != req.groups[0]:
        raise ServiceError("not_found", "There is no such run.")
    return run


# ---- settings ---------------------------------------------------------------
def get_settings(req):
    req.h.send_json(200, settings.read(req.ws).as_dict())


def put_settings(req):
    body = req.json()
    key = body.get("api_key")
    saved = settings.save(req.ws, _need(body, "provider"), _need(body, "model"), key if isinstance(key, str) else None)
    req.h.send_json(200, saved.as_dict())


def test_settings(req):
    body = req.json()
    ok, detail = settings.check_key(_need(body, "provider"), _need(body, "api_key"))
    req.h.send_json(200, {"ok": ok, "detail": detail})


def forget_key(req):
    req.h.send_json(200, settings.remove_key(req.ws, req.groups[0]).as_dict())


# ---- your data ----------------------------------------------------------------------
def get_storage(req):
    req.h.send_json(200, {"places": [p.as_dict() for p in storage.describe(req.ws)], "workspace": str(req.ws.root)})


def clear_storage(req):
    if not _flag(req.json(), "confirm"):
        raise ServiceError("bad_request", "Erasing needs confirmation.", "Send “confirm”: true.")
    if req.runs.running:
        raise ServiceError("busy", "Wait for the run to finish first.")
    req.h.send_json(200, {"erased": storage.erase(req.ws)})


# ---- services and models ----------------------------------------------------------
def get_services(req):
    current = settings.read(req.ws)
    req.h.send_json(200, {"services": [
        {"id": s.id, "label": s.label, "private": s.private, "needs_key": bool(s.key_var), "key_help": s.key_help,
         "note": s.note, "handling": s.handling, "policy_url": s.policy_url, "key_saved": bool(current.keys_saved.get(s.id)), "model": current.remembered.get(s.id, "")}
        for s in settings.SERVICES]})


def _options(items) -> list[dict]:
    return [{"id": o.id, "note": o.note, "price": o.price, "price_text": models.price_text(o.price)} for o in items]


def get_models(req):
    name = req.groups[0]
    settings.service(name)  # raises bad_service
    if name in models.CURATED:
        out = {"models": _options(models.CURATED[name])}
    elif name == "ollama":
        out = {"models": _options(models.ollama_vision(req.ws)), "installed": models.ollama_installed(req.ws)}
    else:
        catalog = models.openrouter_catalog()
        out = {"free": _options(catalog.free), "cheapest": _options(catalog.cheapest(10)),
               "makers": {maker: _options(items) for maker, items in catalog.makers().items()}}
    req.h.send_json(200, out)


# ---- files ----------------------------------------------------------------------
def list_files(req):
    req.h.send_json(200, {"files": [f.as_dict() for f in files.list_files(req.ws)]})


def put_file(req):
    info = files.store(req.ws, req.groups[0], req.upload_chunks())
    req.h.send_json(201, info.as_dict())


def delete_file(req):
    name = files.safe_name(req.groups[0])
    if req.runs.running:
        raise ServiceError("busy", "Wait for the run to finish first.")
    path = req.ws.input_dir / name
    if not path.is_file():
        raise ServiceError("not_found", f"{name} isn't in your list.")
    path.unlink()
    req.h.send_json(200, {"removed": name})


def download_file(req):
    path = files.output_file(req.ws, req.groups[0])
    size = path.stat().st_size
    kind = "wordprocessingml.document" if path.suffix.lower() == ".docx" else "presentationml.presentation"
    req.h._headers(200, f"application/vnd.openxmlformats-officedocument.{kind}", size,
                   {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(path.name)}"})
    with path.open("rb") as fh:
        while block := fh.read(1 << 20):
            req.h.wfile.write(block)


def audit_file(req):
    req.h.send_json(200, audit.report(req.ws, req.groups[0]))


# ---- runs -----------------------------------------------------------------------
def start_run(req):
    body = req.json()
    force = _flag(body, "force")
    if force and not _flag(body, "confirm"):
        raise ServiceError("bad_request", "Replacing the author's own alt text needs confirmation.",
                           "Send “confirm”: true along with “force”: true.")
    only = body.get("files")
    if only is not None and not (isinstance(only, list) and all(isinstance(n, str) for n in only)):
        raise ServiceError("bad_request", "“files” must be a list of file names.", "Send the names exactly as the files list shows them.")
    plan = req.runs.start(resume=_flag(body, "resume"), force=force, console_logs=True, only=only)
    req.h.send_json(202, {**_run_dict(req), "pending": plan.pending})


def current_run(req):
    req.h.send_json(200, _run_dict(req))


def cancel_run(req):
    _own_run(req)
    req.runs.cancel()
    req.h.send_json(202, _run_dict(req))


def run_events(req):
    """Server-Sent Events. A page that reconnects sends Last-Event-ID and gets what it missed."""
    _own_run(req)
    h = req.h
    try:
        sent = int(h.headers.get("Last-Event-ID") or req.arg("after", "0"))
    except ValueError:
        sent = 0
    h.close_connection = True
    h._headers(200, "text/event-stream; charset=utf-8", None, {"Connection": "close"})
    idle = 0.0
    while True:
        batch = req.runs.events_since(sent)
        for ev in batch:
            h.wfile.write(f"id: {ev['id']}\nevent: {ev['event']}\ndata: {json.dumps(ev)}\n\n".encode())
            sent = ev["id"]
        if batch:
            h.wfile.flush()
            idle = 0.0
            if batch[-1]["event"] == "run_finished":
                return
        elif not req.runs.running and req.runs.status().state != "running":
            return  # finished and fully sent
        else:
            idle += 0.25
            if idle >= 15:  # keep proxies and browsers from timing the stream out
                h.wfile.write(b": keep-alive\n\n")
                h.wfile.flush()
                idle = 0.0
        time.sleep(0.25)


# ---- doctor ---------------------------------------------------------------------
def doctor_checks(req):
    checks = [c.as_dict() for c in health.run_all(req.ws)]
    req.h.send_json(200, {"checks": checks, "ok": all(c["ok"] for c in checks)})


ROUTES = [
    ("GET", f"{PREFIX}/settings", get_settings),
    ("PUT", f"{PREFIX}/settings", put_settings),
    ("POST", f"{PREFIX}/settings/test", test_settings),
    ("DELETE", f"{PREFIX}/settings/keys/{_NAME}", forget_key),
    ("GET", f"{PREFIX}/storage", get_storage),
    ("POST", f"{PREFIX}/storage/clear", clear_storage),
    ("GET", f"{PREFIX}/services", get_services),
    ("GET", f"{PREFIX}/services/{_NAME}/models", get_models),
    ("GET", f"{PREFIX}/files", list_files),
    ("PUT", f"{PREFIX}/files/{_NAME}", put_file),
    ("DELETE", f"{PREFIX}/files/{_NAME}", delete_file),
    ("GET", f"{PREFIX}/files/{_NAME}/download", download_file),
    ("GET", f"{PREFIX}/files/{_NAME}/audit", audit_file),
    ("POST", f"{PREFIX}/runs", start_run),
    ("GET", f"{PREFIX}/runs/current", current_run),
    ("POST", f"{PREFIX}/runs/{_NAME}/cancel", cancel_run),
    ("GET", f"{PREFIX}/runs/{_NAME}/events", run_events),
    ("GET", f"{PREFIX}/doctor", doctor_checks),
]
