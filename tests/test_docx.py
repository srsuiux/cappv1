import asyncio
import io
import zipfile

import pytest
from docx import Document
from docx.shared import Inches
from lxml import etree
from PIL import Image

from src import pipeline
from src.config import load_config
from src.docx_reader import (
    extract_pictures,
    extract_tables,
    get_alt_text,
    get_context,
    get_table_alt_text,
    mark_decorative,
    set_table_alt_text,
)

LONG = "A bar chart of quarterly sales for each region, used to compare the north and the south"


def png(color=(200, 60, 60), size=(300, 200)) -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    buf.seek(0)
    return buf


def make_docx(path, *, tiny=False):
    doc = Document()
    doc.add_heading("Results", level=1)
    doc.add_paragraph("Sales rose in the north.")
    doc.add_picture(png(), width=Inches(2))
    doc.add_paragraph("Figure 1 shows the trend.")
    if tiny:
        doc.add_picture(png(size=(10, 10)), width=Inches(0.2))
    table = doc.add_table(rows=2, cols=2)
    for i, text in enumerate(["Region", "Sales", "North", "40"]):
        table.cell(i // 2, i % 2).text = text
    doc.save(path)
    return path


def docx_config(tmp_path, fake_ollama, monkeypatch):
    for k, v in {"PROVIDER": "ollama", "OLLAMA_BASE_URL": fake_ollama.url, "MODEL": "gemma3:4b"}.items():
        monkeypatch.setenv(k, v)
    config = load_config(tmp_path / "work")
    config.input_dir.mkdir(parents=True)
    return config


def run(config, **kw):
    return asyncio.run(pipeline.run(config, **kw))


def out_doc(config, name="a.docx"):
    return Document(str(config.output_dir / name))


def test_finds_pictures_and_tables_with_their_context(tmp_path):
    doc = Document(str(make_docx(tmp_path / "a.docx")))
    pics, tables = extract_pictures(doc), extract_tables(doc)
    assert len(pics) == 1 and len(tables) == 1
    ctx = get_context(doc, pics[0].block)
    assert ctx.title == "Results" and ctx.kind == "document"
    assert "Sales rose in the north." in ctx.body_text and "Figure 1" in ctx.body_text


def test_a_run_writes_alt_text_for_pictures_and_tables(tmp_path, fake_ollama, monkeypatch):
    config = docx_config(tmp_path, fake_ollama, monkeypatch)
    make_docx(config.input_dir / "a.docx")
    assert run(config) == []
    doc = out_doc(config)
    assert get_alt_text(extract_pictures(doc)[0].doc_pr) == fake_ollama.reply
    assert get_table_alt_text(extract_tables(doc)[0].table) == fake_ollama.reply
    assert fake_ollama.calls == 2
    # finished and unchanged: a second run does nothing
    run(config)
    assert fake_ollama.calls == 2


def test_only_alt_text_changes_in_the_document(tmp_path, fake_ollama, monkeypatch):
    """The skills.md invariant: everything but the alt-text fields comes out the same."""
    config = docx_config(tmp_path, fake_ollama, monkeypatch)
    src = make_docx(config.input_dir / "a.docx")
    run(config)

    def canon(zf, name):
        root = etree.fromstring(zf.read(name))
        for el in root.iter():
            el.attrib.pop("descr", None)
        for el in list(root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblDescription")):
            el.getparent().remove(el)
        return etree.tostring(root, method="c14n")

    with zipfile.ZipFile(src) as a, zipfile.ZipFile(config.output_dir / "a.docx") as b:
        assert sorted(a.namelist()) == sorted(b.namelist())
        for name in a.namelist():
            if name.endswith((".xml", ".rels")):
                assert canon(a, name) == canon(b, name), name
            else:
                assert a.read(name) == b.read(name), name


def test_tiny_pictures_are_marked_decorative_without_a_model_call(tmp_path, fake_ollama, monkeypatch):
    config = docx_config(tmp_path, fake_ollama, monkeypatch)
    make_docx(config.input_dir / "a.docx", tiny=True)
    run(config)
    pics = extract_pictures(out_doc(config))
    tiny = next(p for p in pics if len(p.image_bytes) < 500)
    assert get_alt_text(tiny.doc_pr) == ""
    assert tiny.doc_pr.xpath(".//*[local-name()='decorative']")
    assert fake_ollama.calls == 2  # the big picture and the table only


def test_the_authors_alt_text_is_kept_when_the_model_says_keep(tmp_path, fake_ollama, monkeypatch):
    config = docx_config(tmp_path, fake_ollama, monkeypatch)
    src = make_docx(config.input_dir / "a.docx")
    doc = Document(str(src))
    pic = extract_pictures(doc)[0]
    pic.doc_pr.set("descr", LONG)
    set_table_alt_text(extract_tables(doc)[0].table, LONG)
    doc.save(str(src))
    fake_ollama.reply = "KEEP"
    run(config)
    out = out_doc(config)
    assert get_alt_text(extract_pictures(out)[0].doc_pr) == LONG
    assert get_table_alt_text(extract_tables(out)[0].table) == LONG


def test_table_description_goes_in_schema_order(tmp_path):
    doc = Document(str(make_docx(tmp_path / "a.docx")))
    table = extract_tables(doc)[0].table
    pr = table._tbl.tblPr
    etree.SubElement(pr, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblPrChange")
    set_table_alt_text(table, "x")
    tags = [etree.QName(c).localname for c in pr]
    assert tags.index("tblDescription") < tags.index("tblPrChange")


def test_decorative_marking_is_not_added_twice(tmp_path):
    doc = Document(str(make_docx(tmp_path / "a.docx")))
    doc_pr = extract_pictures(doc)[0].doc_pr
    mark_decorative(doc_pr)
    mark_decorative(doc_pr)
    assert len(doc_pr.xpath(".//*[local-name()='decorative']")) == 1


def test_a_failed_model_call_leaves_the_file_to_retry(tmp_path, fake_ollama, monkeypatch):
    async def no_wait(_):
        pass

    monkeypatch.setattr("src.llm_client.asyncio.sleep", no_wait)
    config = docx_config(tmp_path, fake_ollama, monkeypatch)
    make_docx(config.input_dir / "a.docx")
    fake_ollama.stop()
    fake_ollama.server.server_close()  # every call now fails to connect
    run(config)
    from src.state import load_state

    state = load_state(config.state_dir, "a.docx")
    assert state.status == "in_progress" and state.completed_slide_indices == []
    assert (config.output_dir / "a.docx").exists()  # saved as far as it got


# ---- services, runs and the web server --------------------------------------------
def test_docx_uploads_are_accepted_and_checked(ws, tmp_path):
    from src.services import files
    from src.services.errors import ServiceError

    info = files.store_path(ws, make_docx(tmp_path / "paper.docx"))
    assert info.name == "paper.docx" and info.state == "new"
    assert [f.name for f in files.list_files(ws)] == ["paper.docx"]
    with pytest.raises(ServiceError) as err:
        files.store(ws, "fake.docx", [b"not a zip"])
    assert err.value.code == "unsupported_file"
    # a deck renamed to .docx is not a Word document
    from tests.helpers import make_deck

    with pytest.raises(ServiceError):
        files.store_path(ws, make_deck(tmp_path / "d.pptx").rename(tmp_path / "d.docx"))
    assert files.safe_name("Paper.DOCX") == "Paper.docx"


def test_word_lock_files_are_ignored(ws, tmp_path):
    from src.services import files

    files.store_path(ws, make_docx(tmp_path / "paper.docx"))
    (ws.input_dir / "~$paper.docx").write_bytes(b"lock")
    assert [f.name for f in files.list_files(ws)] == ["paper.docx"]


def test_a_run_through_the_service_captions_a_docx(configured, tmp_path):
    from src.services import files
    from src.services.runs import RunManager

    files.store_path(configured, make_docx(tmp_path / "paper.docx"))
    runs = RunManager(configured)
    runs.start()
    assert runs.wait(30)
    assert runs.status().state == "done" and runs.status().failed_files == []
    assert files.list_files(configured)[0].state == "done"
    assert files.output_file(configured, "paper.docx").is_file()
    assert get_alt_text(extract_pictures(out_doc_at(configured.output_dir / "paper.docx"))[0].doc_pr)


def out_doc_at(path):
    return Document(str(path))


def test_the_accessibility_check_says_it_is_decks_only(configured, tmp_path):
    from src.services import audit, files
    from src.services.errors import ServiceError

    files.store_path(configured, make_docx(tmp_path / "paper.docx"))
    with pytest.raises(ServiceError) as err:
        audit.report(configured, "paper.docx")
    assert err.value.code == "audit_unsupported"


def test_clean_removes_documents_too(configured, tmp_path):
    from src.services import files

    files.store_path(configured, make_docx(tmp_path / "paper.docx"))
    assert files.clean(configured)["input"] == 1
    assert files.list_files(configured) == []
