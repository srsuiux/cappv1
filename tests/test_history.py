import time

import pytest

from cappv1.services import files
from cappv1.services.errors import ServiceError
from cappv1.services.runs import RunManager
from tests.helpers import make_deck


def run_once(ws, **kw):
    runs = RunManager(ws)
    runs.start(**kw)
    assert runs.wait(30)


def test_every_run_saves_into_a_folder_of_its_own(configured, tmp_path):
    files.store_path(configured, make_deck(tmp_path / "a.pptx"))
    run_once(configured)
    time.sleep(1.1)  # run folders are named to the second
    run_once(configured, force=True)
    runs = files.history(configured)
    assert len(runs) == 2 and all(r["files"][0]["name"] == "a.pptx" for r in runs)
    assert runs[0]["run"] > runs[1]["run"]  # newest first
    assert files.describe(configured, "a.pptx").output_run == runs[0]["run"]


def test_a_file_still_counts_as_done_when_its_copy_is_in_a_run_folder(configured, tmp_path):
    files.store_path(configured, make_deck(tmp_path / "a.pptx"))
    run_once(configured)
    info = files.describe(configured, "a.pptx")
    assert info.state == "done" and info.has_output and info.output_size > 0 and info.modified > 0


def test_copies_and_whole_runs_can_be_deleted(configured, tmp_path):
    files.store_path(configured, make_deck(tmp_path / "a.pptx"))
    files.store_path(configured, make_deck(tmp_path / "b.pptx"))
    run_once(configured)
    run = files.history(configured)[0]["run"]
    assert files.delete_copy(configured, run, "a.pptx") == 1
    assert [f["name"] for f in files.history(configured)[0]["files"]] == ["b.pptx"]
    assert files.delete_copy(configured, run) == 1
    assert files.history(configured) == [] and not (configured.output_dir / run).exists()
    with pytest.raises(ServiceError):
        files.delete_copy(configured, run)


def test_a_run_name_cannot_point_outside_output(ws):
    with pytest.raises(ServiceError):
        files.delete_copy(ws, "../input")
    with pytest.raises(ServiceError):
        files.output_file(ws, "a.pptx", "../input")


def test_copies_from_older_versions_count_as_the_oldest_run(ws):
    (ws.output_dir / "old.pptx").write_bytes(b"x")
    runs = files.history(ws)
    assert runs[-1]["legacy"] and files.output_file(ws, "old.pptx").name == "old.pptx"
    assert files.delete_copy(ws, "", "old.pptx") == 1


def test_remove_takes_a_file_out_of_the_list(ws, tmp_path):
    files.store_path(ws, make_deck(tmp_path / "a.pptx"))
    assert files.remove(ws, "a.pptx") == "a.pptx" and files.list_files(ws) == []
    with pytest.raises(ServiceError):
        files.remove(ws, "a.pptx")


class _Session:
    def __init__(self, ws):
        from rich.console import Console

        self.ws, self.console = ws, Console(record=True, width=120)
        self.runs = type("R", (), {"running": False})()

    def said(self):
        return self.console.export_text(clear=False)


def test_terminal_lists_and_removes_what_the_web_page_shows(ws, tmp_path, monkeypatch):
    from cappv1.tui import commands

    files.store_path(ws, make_deck(tmp_path / "a.pptx"))
    (ws.output_dir / "2026-01-02_03-04-05").mkdir()
    (ws.output_dir / "2026-01-02_03-04-05" / "a.pptx").write_bytes(b"x")
    s = _Session(ws)
    commands.cmd_files(s, "")
    commands.cmd_history(s, "")
    assert "a.pptx" in s.said() and "2026-01-02_03-04-05" in s.said()
    monkeypatch.setattr(commands, "select", lambda *a, **k: 1)  # answer "Yes, delete"
    commands.cmd_remove(s, "2026-01-02_03-04-05/a.pptx")
    assert files.history(ws) == []
    commands.cmd_remove(s, "a.pptx")
    assert files.list_files(ws) == []
