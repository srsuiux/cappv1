"""Starting, watching and cancelling a captioning run.

One run at a time, shared by whoever started it: the terminal and the web UI
look at the same RunManager, so each sees the other's run.
"""
import asyncio
import threading
import time
from dataclasses import asdict, dataclass, field, replace

from src import doctor, events
from src.config import Config, load_config
from src.pipeline import inspect_file, run, setup_logging
from src.services import envfile
from src.services.errors import ServiceError
from src.services.workspace import Workspace


@dataclass
class RunPlan:
    config: Config
    resume: bool
    force: bool
    pending: list[str]


@dataclass
class RunStatus:
    state: str = "idle"  # idle | running | done | cancelled | failed
    failed_files: list[str] = field(default_factory=list)
    error: str = ""
    started: float = 0.0
    finished: float = 0.0
    events: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _pending(config: Config, resume: bool, force: bool) -> list[str]:
    """Which files a run would process. Looks only; changes nothing. (Mirrors
    pipeline.discover_files, which also logs and, with force, forgets progress.)"""
    out = []
    for f in sorted(config.input_dir.glob("*.pptx")):
        kind = inspect_file(config, f)[0]
        if force or (kind != "done" and not (resume and kind in ("new", "changed"))):
            out.append(f.name)
    return out


class RunManager:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self._lock = threading.Lock()
        self._status = RunStatus()
        self._log: list[dict] = []
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._cancel = False

    # ---- starting ----------------------------------------------------------
    def prepare(self, resume: bool = False, force: bool = False) -> RunPlan:
        """Checks everything a run needs, so a problem shows up now, not mid-deck."""
        if self.running:
            raise ServiceError("busy", "A run is already in progress.", "Wait for it to finish, or cancel it.")
        try:
            config = load_config(self.ws.root)
        except Exception as exc:
            raise ServiceError("not_configured", str(exc), "Open /init (or the Setup page) to choose an AI service.") from None
        if force:
            config = replace(config, overwrite_existing=True)

        if config.provider == "ollama":
            try:
                installed = doctor.ollama_installed_models(doctor.ollama_base_url(envfile.read(self.ws)))
            except Exception:
                raise ServiceError("ollama_down", "Ollama isn't running.", "Open the Ollama app, then try again.") from None
            if not doctor.model_is_installed(config.model, installed):
                raise ServiceError("model_missing", f"{config.model} isn't downloaded.",
                                   f"Run: ollama pull {config.model}  (or pick another model)")

        names = [p.name for p in config.input_dir.glob("*.pptx")]
        if not names:
            raise ServiceError("no_files", "There are no files to process yet.", "Add a .pptx file first.")
        pending = _pending(config, resume, force)
        if not pending:
            shown = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
            raise ServiceError("nothing_to_do", f"Already captioned and unchanged: {shown}.",
                               "Add new files, or edit a deck and add it again.")
        return RunPlan(config, resume, force, pending)

    def launch(self, plan: RunPlan) -> None:
        with self._lock:
            if self.running:
                raise ServiceError("busy", "A run is already in progress.")
            self._log = []
            self._cancel = False
            self._status = RunStatus(state="running", started=time.time())
            setup_logging(plan.config.logs_dir, console=False)
            unsubscribe = events.subscribe(self._on_event)
            self._thread = threading.Thread(target=self._work, args=(plan, unsubscribe), daemon=True, name="cappv1-run")
            self._thread.start()

    def start(self, resume: bool = False, force: bool = False) -> RunPlan:
        plan = self.prepare(resume, force)
        self.launch(plan)
        return plan

    # ---- running (background thread) ----------------------------------------
    def _work(self, plan: RunPlan, unsubscribe) -> None:
        loop = asyncio.new_event_loop()
        try:
            self._loop = loop
            self._task = loop.create_task(run(plan.config, resume_only=plan.resume, force=plan.force))
            if self._cancel:
                self._task.cancel()
            failed = loop.run_until_complete(self._task)
            self._finish("done", failed_files=list(failed or []))
        except asyncio.CancelledError:
            self._finish("cancelled")
        except Exception as exc:
            self._finish("failed", error=str(exc))
        finally:
            unsubscribe()
            loop.close()
            self._loop = self._task = None

    def _finish(self, state: str, failed_files: list[str] | None = None, error: str = "") -> None:
        with self._lock:
            self._status.state, self._status.error = state, error
            self._status.failed_files = failed_files or []
            self._status.finished = time.time()
            self._log.append({"id": len(self._log) + 1, "event": "run_finished", "state": state})
            self._status.events = len(self._log)

    def _on_event(self, name: str, data: dict) -> None:
        with self._lock:
            self._log.append({"id": len(self._log) + 1, "event": name, **data})
            self._status.events = len(self._log)

    # ---- watching ----------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> RunStatus:
        with self._lock:
            return replace(self._status, failed_files=list(self._status.failed_files))

    def events_since(self, after: int = 0) -> list[dict]:
        """Events with id > after, so a page that reconnects can catch up."""
        with self._lock:
            return list(self._log[after:])

    def cancel(self) -> None:
        """Stops after the item in flight; finished slides stay saved."""
        self._cancel = True
        loop, task = self._loop, self._task
        if loop and task:
            loop.call_soon_threadsafe(task.cancel)

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread:
            self._thread.join(timeout)
        return not self.running
