"""The product rule, checked on the shipped sample deck: a run changes alt text and nothing else.

Every XML part of the original and the finished copy is compared as canonical XML (C14N), which ignores
serialization (whitespace, attribute order, quote style in the XML declaration). The only attributes
allowed to differ are the alt-text field `descr` and a table's `firstRow` flag (docs/scope.md).
"""

import zipfile
from pathlib import Path

from lxml import etree

from cappv1 import outputs
from cappv1.services import files
from cappv1.services.runs import RunManager

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.pptx"
ALLOWED = ("descr", "firstRow")


def canonical(data: bytes) -> bytes:
    root = etree.fromstring(data)
    for el in root.iter():
        for name in ALLOWED:
            el.attrib.pop(name, None)
    return etree.tostring(root, method="c14n")


def test_a_run_on_the_sample_deck_changes_only_alt_text(configured, fake_ollama, tmp_path):
    fake_ollama.reply = "A test description."
    files.store_path(configured, SAMPLE)
    runs = RunManager(configured)
    runs.start()
    assert runs.wait(60)

    original = zipfile.ZipFile(SAMPLE)
    finished = zipfile.ZipFile(outputs.latest(configured.output_dir, SAMPLE.name))

    assert finished.namelist() == original.namelist()
    changed = []
    for name in original.namelist():
        before, after = original.read(name), finished.read(name)
        if before == after:
            continue
        assert name.endswith((".xml", ".rels")), f"{name} is not XML but was changed"
        assert canonical(before) == canonical(after), f"{name} changed beyond alt text"
        changed.append(name)

    # the run did write alt text, so this is not passing because nothing happened
    assert changed == ["ppt/slides/slide1.xml", "ppt/slides/slide2.xml", "ppt/slides/slide3.xml"]
    descrs = [d for n in changed for d in etree.fromstring(finished.read(n)).xpath("//@descr")]
    assert descrs == ["A test description."] * 3
