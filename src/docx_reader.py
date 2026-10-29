import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree

from src.pptx_reader import SlideContext

_WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_A16_DECORATIVE_URI = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
_ADEC_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_MAX_CONTEXT_CHARS = 600


@dataclass
class DocPicture:
    doc_pr: etree._Element  # wp:docPr, which holds the alt text Word's "Edit Alt Text" pane edits
    image_bytes: bytes | None  # None when the file points to an image that isn't in it
    ext: str
    block: etree._Element  # the top-level body child that contains it, for context


@dataclass
class DocObject:
    shape: etree._Element  # the v:shape that previews the object; its alt attribute is the alt text
    blob: bytes | None  # the embedded file; None for a linked object or a part missing from the file
    prog_id: str
    block: etree._Element


@dataclass
class DocTable:
    table: Table
    block: etree._Element


def open_document(path: Path):
    return Document(str(path))


def save_document(doc, source: Path, dest: Path) -> None:
    """Writes the finished copy by taking the original file as it is and replacing only the
    document body. Saving through python-docx would repackage every part (order, content
    types, XML declarations), which some readers such as Blackboard's previewer refuse."""
    name = doc.part.partname.lstrip("/")
    body = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + etree.tostring(
        doc.part._element, encoding="UTF-8")
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(dest, "w") as out:
        for info in src.infolist():
            # a fresh entry rather than the source's, which the writer would otherwise modify
            entry = zipfile.ZipInfo(info.filename, info.date_time)
            entry.compress_type = info.compress_type
            entry.external_attr = info.external_attr
            out.writestr(entry, body if info.filename == name else src.read(info.filename))


def _wp(tag: str) -> str:
    return f"{{{_WP_NS}}}{tag}"


def _top_block(el, body):
    while el.getparent() is not body:
        el = el.getparent()
    return el


def _in_fallback(el) -> bool:
    # mc:Fallback carries a VML copy of what mc:Choice already drew
    return any(anc.tag == _MC_FALLBACK for anc in el.iterancestors())


def extract_pictures(doc) -> list[DocPicture]:
    """Pictures in the document body, matched on the XML (wp:docPr whose drawing
    holds an a:blip), so text boxes and shapes that share wp:docPr are not
    mistaken for pictures. Headers, footers and footnotes are not walked."""
    body = doc.element.body
    related = doc.part.related_parts
    found = []
    for doc_pr in body.iter(_wp("docPr")):
        if _in_fallback(doc_pr):
            continue
        blips = doc_pr.getparent().xpath(".//a:blip[@r:embed]")
        if not blips:
            continue
        part = related.get(blips[0].get(qn("r:embed")))  # None: the image is missing from the file
        found.append(DocPicture(
            doc_pr=doc_pr,
            image_bytes=part.blob if part is not None else None,
            ext=Path(str(part.partname)).suffix.lstrip(".") if part is not None else "",
            block=_top_block(doc_pr, body),
        ))
    return found


_VML_NS = "urn:schemas-microsoft-com:vml"
_OFFICE_NS = "urn:schemas-microsoft-com:office:office"


def extract_objects(doc) -> list[DocObject]:
    """Embedded objects (Visio drawings, Excel sheets, ...) in the body. Word shows each as a
    preview picture inside w:object; the description lives on that VML shape's alt attribute,
    which is what Word's Edit Alt Text pane edits for it."""
    body = doc.element.body
    related = doc.part.related_parts
    found = []
    for obj in body.iter(qn("w:object")):
        if _in_fallback(obj):
            continue
        shape = obj.find(f".//{{{_VML_NS}}}shape")
        if shape is None:
            continue
        ole = obj.find(f"{{{_OFFICE_NS}}}OLEObject")
        rid = ole.get(qn("r:id")) if ole is not None else None
        part = related.get(rid) if rid else None
        found.append(DocObject(
            shape=shape,
            blob=part.blob if part is not None else None,
            prog_id=(ole.get("ProgID") or "") if ole is not None else "",
            block=_top_block(obj, body),
        ))
    return found


def get_object_alt_text(shape) -> str:
    return shape.get("alt", "") or ""


def set_object_alt_text(shape, text: str) -> None:
    shape.set("alt", text)


def extract_tables(doc) -> list[DocTable]:
    body = doc.element.body
    return [DocTable(Table(tbl, doc._body), _top_block(tbl, body)) for tbl in body.iter(qn("w:tbl"))]


def get_alt_text(doc_pr) -> str:
    return doc_pr.get("descr", "") or ""


def set_alt_text(doc_pr, text: str) -> None:
    doc_pr.set("descr", text)


def mark_decorative(doc_pr) -> None:
    """Empty alt text plus the flag Word 365 reads for 'Mark as decorative'
    (an empty description alone just reads as 'not described yet')."""
    set_alt_text(doc_pr, "")
    if doc_pr.xpath(f".//*[local-name()='decorative' and namespace-uri()='{_ADEC_NS}']"):
        return
    ext_lst = doc_pr.find(qn("a:extLst"))
    if ext_lst is None:
        ext_lst = etree.SubElement(doc_pr, qn("a:extLst"), nsmap={"a": _A_NS})
    ext = etree.SubElement(ext_lst, qn("a:ext"), uri=_A16_DECORATIVE_URI)
    etree.SubElement(ext, f"{{{_ADEC_NS}}}decorative", {"val": "1"}, nsmap={"adec": _ADEC_NS})


_FIRST_MODE_WITH_TABLE_ALT_TEXT = 14  # Word 2010


def table_alt_text_unsupported(doc) -> str | None:
    """Word refuses to open a file that has a table title or description while it is in
    compatibility mode 11 or 12 (what LibreOffice and old Word write); tested on real files.
    Raising the mode would re-lay-out the pages, so such documents get no table alt text."""
    mode = 12  # no setting means Word 2007 behaviour
    for el in doc.settings.element.iter(qn("w:compatSetting")):
        if el.get(qn("w:name")) == "compatibilityMode":
            try:
                mode = int(el.get(qn("w:val")))
            except (TypeError, ValueError):
                pass
    if mode >= _FIRST_MODE_WITH_TABLE_ALT_TEXT:
        return None
    return (f"this document is saved in Word compatibility mode {mode}, where Word cannot open a file "
            "that has table alt text; open it in Word and use Save As to bring it up to date, then run again")


def get_table_alt_text(table: Table) -> str:
    pr = table._tbl.tblPr
    el = pr.find(qn("w:tblDescription")) if pr is not None else None
    return (el.get(qn("w:val")) or "") if el is not None else ""


def set_table_alt_text(table: Table, text: str) -> None:
    """Writes w:tblDescription, the field behind Word's table Alt Text 'Description'.
    The table's title (w:tblCaption) is the author's and is left alone."""
    pr = table._tbl.tblPr  # python-docx adds it when missing
    el = pr.find(qn("w:tblDescription"))
    if el is None:
        el = etree.Element(qn("w:tblDescription"))
        # schema order: tblCaption, tblDescription, then tblPrChange last
        anchor = pr.find(qn("w:tblPrChange"))
        if anchor is not None:
            anchor.addprevious(el)
        else:
            pr.append(el)
    el.set(qn("w:val"), text)


_MAX_TABLE_ROWS_IN_TEXT = 20


def table_to_text(table: Table) -> str:
    rows = list(table.rows)
    lines = []
    for row in rows[:_MAX_TABLE_ROWS_IN_TEXT]:
        cells, last = [], None
        for cell in row.cells:
            if cell._tc is not last:  # a merged cell is reported once
                cells.append(cell.text.strip().replace("\n", " "))
            last = cell._tc
        lines.append(" | ".join(cells))
    if len(rows) > _MAX_TABLE_ROWS_IN_TEXT:
        lines.append(f"... ({len(rows) - _MAX_TABLE_ROWS_IN_TEXT} more rows)")
    return "\n".join(lines)


def _paragraph_text(p_el) -> str:
    return "".join(t.text or "" for t in p_el.iter(qn("w:t"))).strip()


def _is_heading(doc, p_el) -> bool:
    name = Paragraph(p_el, doc._body).style.name or ""
    return name == "Title" or name.startswith("Heading")


def get_context(doc, block, index: int = 0) -> SlideContext:
    """Where an element sits in the document, in the shape the prompts already
    take: the nearest heading above it, and the text around it. Read-only."""
    siblings = list(doc.element.body)
    at = siblings.index(block)
    title = ""
    for el in reversed(siblings[:at + 1]):
        if el.tag == qn("w:p") and _paragraph_text(el) and _is_heading(doc, el):
            title = _paragraph_text(el)
            break

    def nearest(candidates) -> str:
        for el in candidates:
            if el.tag == qn("w:p") and _paragraph_text(el):
                return _paragraph_text(el)
        return ""

    parts = [
        nearest(reversed(siblings[:at])),
        _paragraph_text(block) if block.tag == qn("w:p") else "",
        nearest(siblings[at + 1:]),
    ]
    text = "\n".join(p for p in parts if p and p != title)[:_MAX_CONTEXT_CHARS]
    return SlideContext(index=index, section=None, title=title, body_text=text, notes="", kind="document")
