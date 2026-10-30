import time

import pytest

from src.services import files
from src.services.errors import ServiceError
from src.services.runs import RunManager
from tests.helpers import alt_texts, make_deck


def add_deck(ws, tmp_path, name="a.pptx", color=(200, 60, 60)):
    files.store_path(ws, make_deck(tmp_path / name, color))


def test_cannot_run_before_setup(ws, tmp_path):
    add_deck(ws, tmp_path)
    with pytest.raises(ServiceError) as err:
        RunManager(ws).prepare()
    assert err.value.code == "not_configured"


def test_cannot_run_with_no_files(configured):
    with pytest.raises(ServiceError) as err:
        RunManager(configured).prepare()
    assert err.value.code == "no_files"


def test_a_run_captions_the_deck_and_reports_progress(configured, tmp_path):
    add_deck(configured, tmp_path)
    runs = RunManager(configured)
    runs.start()
    assert runs.wait(30)
    status = runs.status()
    assert status.state == "done" and status.failed_files == []
    names = [e["event"] for e in runs.events_since(0)]
    assert names[0] == "file_start" and "slide_end" in names and names[-1] == "run_finished"
    assert len(alt_texts(configured.output_dir / "a.pptx")) == 3  # picture, table, chart
    assert files.list_files(configured)[0].state == "done"


def test_events_can_be_read_from_where_a_page_left_off(configured, tmp_path):
    add_deck(configured, tmp_path)
    runs = RunManager(configured)
    runs.start()
    runs.wait(30)
    everything = runs.events_since(0)
    assert runs.events_since(len(everything) - 1) == everything[-1:]
    assert [e["id"] for e in everything] == list(range(1, len(everything) + 1))


def test_running_again_when_nothing_changed_is_refused_not_redone(configured, fake_ollama, tmp_path):
    add_deck(configured, tmp_path)
    runs = RunManager(configured)
    runs.start()
    runs.wait(30)
    calls = fake_ollama.calls
    with pytest.raises(ServiceError) as err:
        runs.prepare()
    assert err.value.code == "nothing_to_do" and fake_ollama.calls == calls


def test_an_edited_deck_only_pays_for_what_changed(configured, fake_ollama, tmp_path):
    add_deck(configured, tmp_path)
    runs = RunManager(configured)
    runs.start()
    runs.wait(30)
    first = fake_ollama.calls
    add_deck(configured, tmp_path, color=(10, 200, 10))  # a different picture, same name
    runs.start()
    runs.wait(30)
    assert fake_ollama.calls - first == 1  # table and chart came from saved captions


def test_only_one_run_at_a_time(configured, fake_ollama, tmp_path):
    fake_ollama.delay = 0.4
    add_deck(configured, tmp_path)
    runs = RunManager(configured)
    runs.start()
    with pytest.raises(ServiceError) as err:
        runs.start()
    assert err.value.code == "busy"
    runs.cancel()
    runs.wait(30)


def test_cancel_stops_promptly_and_work_can_resume(configured, fake_ollama, tmp_path):
    fake_ollama.delay = 0.5
    add_deck(configured, tmp_path)
    runs = RunManager(configured)
    runs.start()
    time.sleep(0.3)
    runs.cancel()
    assert runs.wait(10)
    assert runs.status().state == "cancelled"
    fake_ollama.delay = 0
    runs.start()
    assert runs.wait(30) and runs.status().state == "done"
    assert len(alt_texts(configured.output_dir / "a.pptx")) == 3


def test_missing_local_model_is_explained_before_starting(configured, tmp_path):
    from src.services import settings

    add_deck(configured, tmp_path)
    settings.save(configured, "ollama", "not-downloaded:7b")
    with pytest.raises(ServiceError) as err:
        RunManager(configured).prepare()
    assert err.value.code == "model_missing" and "ollama pull" in err.value.fix


def test_a_run_can_be_limited_to_chosen_files(configured, tmp_path):
    add_deck(configured, tmp_path, "a.pptx")
    add_deck(configured, tmp_path, "b.pptx", (10, 200, 10))
    runs = RunManager(configured)
    plan = runs.start(only=["b.pptx"])
    assert plan.pending == ["b.pptx"]
    assert runs.wait(30)
    assert (configured.output_dir / "b.pptx").exists() and not (configured.output_dir / "a.pptx").exists()
    states = {f.name: f.state for f in files.list_files(configured)}
    assert states == {"a.pptx": "new", "b.pptx": "done"}  # the other file was left alone


def test_choosing_no_files_or_an_unknown_file_is_refused(configured, tmp_path):
    add_deck(configured, tmp_path)
    runs = RunManager(configured)
    with pytest.raises(ServiceError) as err:
        runs.prepare(only=[])
    assert err.value.code == "no_files"
    with pytest.raises(ServiceError) as err:
        runs.prepare(only=["nope.pptx"])
    assert err.value.code == "not_found"


def test_force_with_chosen_files_only_replaces_those(configured, tmp_path):
    add_deck(configured, tmp_path, "a.pptx")
    add_deck(configured, tmp_path, "b.pptx", (10, 200, 10))
    runs = RunManager(configured)
    runs.start()
    assert runs.wait(30)
    plan = runs.prepare(force=True, only=["a.pptx"])
    assert plan.pending == ["a.pptx"]
