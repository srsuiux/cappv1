from pptx import Presentation

from src.pptx_reader import get_alt_text, set_alt_text
from src.services import files
from src.services.runs import RunManager
from tests.helpers import make_deck

LONG = "A chart of quarterly sales for each region, used to compare the north and the south"


def deck_with_picture_alt(ws, tmp_path, alt):
    path = make_deck(tmp_path / "a.pptx")
    prs = Presentation(path)
    for shape in prs.slides[0].shapes:
        if shape.shape_type == 13:
            set_alt_text(shape, alt)
    prs.save(path)
    files.store_path(ws, path)


def run_and_get_picture_alt(ws):
    runs = RunManager(ws)
    runs.start()
    assert runs.wait(30)
    slide_one = next(e for e in runs.events_since(0) if e["event"] == "slide_end" and e["slide"] == 0)
    pic = next(s for s in Presentation(ws.output_dir / "a.pptx").slides[0].shapes if s.shape_type == 13)
    return get_alt_text(pic), slide_one


def test_a_file_name_is_not_treated_as_the_authors_alt_text(configured, tmp_path):
    deck_with_picture_alt(configured, tmp_path, "image1.png")
    _, counts = run_and_get_picture_alt(configured)
    assert counts["captioned"] == 1 and counts["enhanced"] == 0 and counts["kept"] == 0


def test_short_author_text_is_improved_not_ignored(configured, fake_ollama, tmp_path):
    fake_ollama.reply = "Logo - the company logo in the header."
    deck_with_picture_alt(configured, tmp_path, "Logo")
    alt, counts = run_and_get_picture_alt(configured)
    assert counts["enhanced"] == 1 and alt == "Logo - the company logo in the header."


def test_adequate_author_text_is_kept_exactly_as_written(configured, fake_ollama, tmp_path):
    fake_ollama.reply = "KEEP"
    deck_with_picture_alt(configured, tmp_path, LONG)
    alt, counts = run_and_get_picture_alt(configured)
    assert counts["kept"] == 1 and alt == LONG


def test_force_replaces_the_authors_text(configured, fake_ollama, tmp_path):
    fake_ollama.reply = "A fresh description."
    deck_with_picture_alt(configured, tmp_path, LONG)
    runs = RunManager(configured)
    runs.start(force=True)
    assert runs.wait(30)
    pic = next(s for s in Presentation(configured.output_dir / "a.pptx").slides[0].shapes if s.shape_type == 13)
    assert get_alt_text(pic) == "A fresh description."


def test_different_images_never_share_a_caption(configured, fake_ollama, tmp_path):
    """Two flat-colored pictures look 'similar' to a perceptual hash; they must not collide."""
    for color, name in (((200, 60, 60), "red.pptx"), ((10, 200, 10), "green.pptx")):
        files.store_path(configured, make_deck(tmp_path / name, color))
    runs = RunManager(configured)
    runs.start()
    assert runs.wait(30)
    pictures = sum(1 for e in runs.events_since(0) if e["event"] == "element_start" and e["kind"] == "picture")
    assert pictures == 2  # both pictures hit the model; neither reused the other's caption
