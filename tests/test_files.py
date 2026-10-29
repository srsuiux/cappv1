import pytest

from src.services import files
from src.services.errors import ServiceError
from tests.helpers import make_deck


def good_bytes(tmp_path):
    return make_deck(tmp_path / "src.pptx").read_bytes()


def test_store_saves_a_valid_deck(ws, tmp_path):
    info = files.store(ws, "lecture.pptx", [good_bytes(tmp_path)])
    assert info.name == "lecture.pptx" and info.state == "new" and not info.has_output
    assert (ws.input_dir / "lecture.pptx").exists()


@pytest.mark.parametrize("name", ["../../evil.pptx", "/etc/passwd.pptx", "..\\..\\x.pptx", "a/b/c.pptx"])
def test_folders_in_a_name_are_dropped_not_followed(ws, tmp_path, name):
    info = files.store(ws, name, [good_bytes(tmp_path)])
    assert "/" not in info.name and "\\" not in info.name
    assert (ws.input_dir / info.name).exists()
    assert not (ws.root.parent / "evil.pptx").exists()


@pytest.mark.parametrize("name", ["notes.txt", "deck.ppt", ".hidden.pptx", "", "bad\x00name.pptx"])
def test_bad_names_are_refused(ws, name):
    with pytest.raises(ServiceError):
        files.safe_name(name)


def test_a_file_that_is_not_a_deck_is_refused_and_leaves_nothing(ws):
    with pytest.raises(ServiceError) as err:
        files.store(ws, "fake.pptx", [b"this is not a zip"])
    assert err.value.code == "unsupported_file"
    assert list(ws.input_dir.iterdir()) == []


def test_oversized_upload_is_refused_and_leaves_nothing(ws, monkeypatch):
    monkeypatch.setattr(files, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(ServiceError) as err:
        files.store(ws, "big.pptx", [b"x" * 6, b"x" * 6])
    assert err.value.code == "too_big"
    assert list(ws.input_dir.iterdir()) == []


def test_output_file_only_serves_finished_decks_inside_output(ws):
    with pytest.raises(ServiceError):
        files.output_file(ws, "missing.pptx")
    (ws.output_dir / "done.pptx").write_bytes(b"x")
    assert files.output_file(ws, "done.pptx").name == "done.pptx"
    with pytest.raises(ServiceError):
        files.output_file(ws, "../../etc/passwd")


def test_clean_removes_decks_and_progress_only(ws, tmp_path):
    files.store(ws, "a.pptx", [good_bytes(tmp_path)])
    (ws.output_dir / "a.pptx").write_bytes(b"x")
    (ws.state_dir / "a.pptx.json").write_text("{}")
    ws.env_path.write_text("PROVIDER=ollama\n")
    assert files.clean(ws) == {"input": 1, "output": 1, "progress": 1}
    assert ws.env_path.exists()  # settings are not data
