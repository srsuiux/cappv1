import io
import re
from dataclasses import dataclass
from pathlib import Path

import olefile
from docx import Document
from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn

_NV_PR_TAGS = ("p:nvPicPr", "p:nvSpPr", "p:nvGrpSpPr", "p:nvGraphicFramePr", "p:nvCxnSpPr")


@dataclass
class SlideContext:
    index: int  # 0-based
    section: str | None
    title: str
    body_text: str
    notes: str
    kind: str = "slide"  # "document" for a Word file: the prompts then talk about a document


def open_presentation(path: Path) -> Presentation:
    return Presentation(str(path))


def get_section_map(prs: Presentation) -> dict[int, str]:
    """Best-effort slide_index -> section name, parsed from presentation.xml's
    p14:sectionLst extension (not exposed by python-pptx's public API)."""
    try:
        sld_id_lst = prs.slides._sldIdLst
        order = [el.get("id") for el in sld_id_lst.findall(qn("p:sldId"))]
        id_to_index = {sid: i for i, sid in enumerate(order)}

        element = prs.slides._sldIdLst.getroottree().getroot()
        section_lst = element.find(
            ".//{http://schemas.microsoft.com/office/powerpoint/2010/main}sectionLst"
        )
        if section_lst is None:
            return {}

        ns = {"p14": "http://schemas.microsoft.com/office/powerpoint/2010/main"}
        mapping: dict[int, str] = {}
        for section in section_lst.findall("p14:section", ns):
            name = section.get("name", "")
            for sld_id in section.findall(".//p14:sldId", ns):
                sid = sld_id.get("id")
                if sid in id_to_index:
                    mapping[id_to_index[sid]] = name
        return mapping
    except Exception:
        return {}


def get_slide_context(slide, index: int, section: str | None) -> SlideContext:
    title = ""
    if slide.shapes.title is not None:
        title = slide.shapes.title.text_frame.text

    body_parts = []
    for shape in slide.shapes:
        if shape.has_text_frame and shape is not slide.shapes.title:
            text = shape.text_frame.text.strip()
            if text:
                body_parts.append(text)
    body_text = "\n".join(body_parts)

    notes = ""
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame.text

    return SlideContext(index=index, section=section, title=title, body_text=body_text, notes=notes)


def _walk_shapes(shapes, predicate) -> list:
    """Recurses into groups by XML tag, not `shape.shape_type` - python-pptx
    unconditionally reports MSO_SHAPE_TYPE.PLACEHOLDER for any shape (picture,
    table, chart, ...) that's wrapped in a slide placeholder, which masks its
    real type. Matching on the element tag instead sidesteps that entirely."""
    refs = []
    for shape in shapes:
        if shape._element.tag == qn("p:grpSp"):
            refs.extend(_walk_shapes(shape.shapes, predicate))
        elif predicate(shape):
            refs.append(shape)
    return refs


def _is_picture(shape) -> bool:
    """True for a real embedded picture. Excludes `p:pic` elements that are
    actually video shapes (python-pptx's `Movie`, which has no `.image`) -
    same XML tag, discriminated by an `a:videoFile` child, matching
    python-pptx's own Picture-vs-Movie dispatch in shapetree.py."""
    element = shape._element
    if element.tag != qn("p:pic"):
        return False
    return len(element.xpath("./p:nvPicPr/p:nvPr/a:videoFile")) == 0


def _count_raw_pictures(slide) -> int:
    """Independent, low-level recount of real (non-video) `p:pic` elements
    straight from the slide's XML tree, bypassing python-pptx shape wrappers
    and _walk_shapes. Used as a cross-check so a future extraction bug - the
    same class as the placeholder shape_type bug - fails loudly instead of
    silently dropping a shape.

    Excludes `p:pic` elements nested inside a `p:oleObj` - an embedded OLE
    object (e.g. a Word doc) carries a `<p:pic>` fallback preview image inside
    its `mc:AlternateContent` for viewers that can't activate the object.
    That `p:pic` has no real shape id (id="0") and isn't reachable via
    `slide.shapes` at all - it's not an independently addressable shape, it's
    part of the OLE object's own representation. The OLE object itself (a
    GraphicFrame) is a separate, currently-unhandled alt-text target - not
    this fallback picture.
    """
    return sum(
        1
        for pic in slide.shapes._element.iter(qn("p:pic"))
        if len(pic.xpath("./p:nvPicPr/p:nvPr/a:videoFile")) == 0
        and len(pic.xpath("ancestor::p:oleObj")) == 0
    )


def extract_pictures(slide) -> list:
    pictures = _walk_shapes(slide.shapes, _is_picture)
    expected = _count_raw_pictures(slide)
    if len(pictures) != expected:
        raise RuntimeError(
            f"picture extraction mismatch: {expected} real <p:pic> element(s) "
            f"found in slide XML but only {len(pictures)} entered the "
            f"candidate list - a picture is being silently dropped"
        )
    return pictures


def extract_tables(slide) -> list:
    return _walk_shapes(slide.shapes, lambda s: getattr(s, "has_table", False))


def extract_charts(slide) -> list:
    return _walk_shapes(slide.shapes, lambda s: getattr(s, "has_chart", False))


def _is_ole_object(shape) -> bool:
    graphic_frame = getattr(shape, "_graphicFrame", None)
    return graphic_frame is not None and graphic_frame.has_oleobj


def extract_ole_objects(slide) -> list:
    return _walk_shapes(slide.shapes, _is_ole_object)


_MAX_OLE_TEXT_CHARS = 4000
# Matches plausible words/numbers, not punctuation/symbol noise - keeps the
# heuristic scrape below from flooding the LLM prompt with binary garbage.
_OLE_TEXT_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ,.\-_/]{3,}")


def _docx_to_text(blob: bytes) -> str:
    doc = Document(io.BytesIO(blob))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)[:_MAX_OLE_TEXT_CHARS]


def _ole2_binary_to_text(blob: bytes) -> str:
    """Scrapes plausible text runs out of every stream in a legacy OLE2
    container (Word 97-2003 .doc, Visio .vsd, etc.). This does NOT parse
    those binary formats - there's no lightweight pure-Python reader for
    them. It's a crude heuristic (cp1252-decode + regex for printable runs),
    not a faithful transcript: verified against a real embedded Word table
    (extracted its column headers and row values correctly) and a real
    embedded Visio drawing (extracted fragmented but legible text from its
    PRINT stream). Good enough for an LLM to describe what the object shows,
    which is all this is used for - never shown to a user directly.
    """
    try:
        ole = olefile.OleFileIO(io.BytesIO(blob))
    except Exception:
        return ""
    fragments = []
    for stream_path in ole.listdir():
        try:
            data = ole.openstream(stream_path).read()
        except Exception:
            continue
        fragments.extend(_OLE_TEXT_RUN_RE.findall(data.decode("cp1252", errors="ignore")))
    ole.close()
    return " ".join(fragments)[:_MAX_OLE_TEXT_CHARS]


def ole_object_to_text(blob: bytes) -> str:
    """Best-effort text for LLM captioning input from an embedded OLE
    object's raw bytes (shape.ole_format.blob). Modern OOXML embeds (.docx)
    are read properly; legacy OLE2-binary embeds get the heuristic scrape.
    """
    if blob[:2] == b"PK":
        return _docx_to_text(blob)
    if blob[:4] == b"\xd0\xcf\x11\xe0":
        return _ole2_binary_to_text(blob)
    return ""


# SmartArt ("Diagram" in the OOXML spec) is a fourth p:graphicFrame content
# type alongside table/chart/ole - python-pptx has no support for it at all
# (no GRAPHIC_DATA_URI_DIAGRAM constant, no .diagram property), so this
# reaches the relationship and XML directly, the same way _is_ole_object
# does for OLE fallback pics.
_DIAGRAM_GRAPHIC_DATA_URI = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
_DGM_NS = "http://schemas.openxmlformats.org/drawingml/2006/diagram"


def _dgm_qn(tag: str) -> str:
    return f"{{{_DGM_NS}}}{tag}"


def _is_smartart(shape) -> bool:
    graphic_frame = getattr(shape, "_graphicFrame", None)
    return graphic_frame is not None and graphic_frame.graphicData_uri == _DIAGRAM_GRAPHIC_DATA_URI


def extract_smartart(slide) -> list:
    return _walk_shapes(slide.shapes, _is_smartart)


def smartart_to_text(shape) -> str:
    """Renders a SmartArt diagram's node text and hierarchy as indented text
    for an LLM prompt. Unlike an OLE object, the diagram's data model
    (data1.xml, found via the <dgm:relIds r:dm="..."/> relationship on the
    graphicFrame) is clean, well-structured XML - no heuristic scrape needed,
    same as table_to_text()/chart_to_text(). Returns "" if the data model
    can't be found or parsed (caller treats that as no signal).
    """
    rel_ids = shape._element.find(f".//{_dgm_qn('relIds')}")
    if rel_ids is None:
        return ""
    dm_rid = rel_ids.get(qn("r:dm"))
    if not dm_rid:
        return ""
    try:
        data_root = etree.fromstring(shape.part.related_part(dm_rid).blob)
    except (KeyError, etree.XMLSyntaxError):
        return ""

    points = {}
    for pt in data_root.iter(_dgm_qn("pt")):
        model_id = pt.get("modelId")
        text = " ".join(t.text for t in pt.findall(f".//{qn('a:t')}") if t.text)
        if text:
            points[model_id] = text

    # Parent-child edges: a <dgm:cxn> with no "type" attribute, or an
    # explicit type="parOf", represents the actual data hierarchy - other
    # types (presOf, presParOf, ...) are presentation-layer plumbing, not
    # content relationships.
    children: dict[str, list[str]] = {}
    all_children: set[str] = set()
    for cxn in data_root.iter(_dgm_qn("cxn")):
        if cxn.get("type") not in (None, "parOf"):
            continue
        src, dst = cxn.get("srcId"), cxn.get("destId")
        if src in points and dst in points:
            children.setdefault(src, []).append(dst)
            all_children.add(dst)

    roots = [pid for pid in points if pid not in all_children]

    lines = []

    def walk(point_id, depth):
        lines.append("  " * depth + points[point_id])
        for child_id in children.get(point_id, []):
            walk(child_id, depth + 1)

    for root_id in roots:
        walk(root_id, 0)

    return "\n".join(lines)


def _is_invisible_shape(shape) -> bool:
    """True for an AutoShape/connector that renders zero visible pixels:
    explicit no-fill AND explicit no-line AND no text. Provably decorative
    by construction - there's nothing to see - not a judgment call like
    "this AutoShape looks unimportant."

    Deliberately narrow: a shape that merely *omits* a fill/line element
    (which then inherits from a theme/shape-style reference and could still
    render visibly) is NOT matched here - only an explicit <a:noFill/> on
    both fill and line. Real diagram connectors (e.g. an arrow with cx=0
    because it's drawn as a vertical line) keep a real <a:ln> stroke with a
    solidFill, so they're correctly left alone by this check.
    """
    element = shape._element
    if element.tag not in (qn("p:sp"), qn("p:cxnSp")):
        return False
    if shape.has_text_frame and shape.text_frame.text.strip():
        return False
    spPr = element.find(qn("p:spPr"))
    if spPr is None:
        return False
    has_explicit_nofill = spPr.find(qn("a:noFill")) is not None
    ln = spPr.find(qn("a:ln"))
    has_explicit_noline = ln is not None and ln.find(qn("a:noFill")) is not None
    return has_explicit_nofill and has_explicit_noline


def extract_invisible_shapes(slide) -> list:
    """Top-level only - not recursing into groups like _walk_shapes does for
    pictures/tables/charts. A shape nested inside a meaningful group isn't
    independently announced by a screen reader anyway, so there's no
    accessibility reason to reach into groups for this check."""
    return [s for s in slide.shapes if _is_invisible_shape(s)]


def _find_cnvpr(shape_element):
    for tag in _NV_PR_TAGS:
        nv = shape_element.find(qn(tag))
        if nv is not None:
            cnvpr = nv.find(qn("p:cNvPr"))
            if cnvpr is not None:
                return cnvpr
    return None


def get_alt_text(shape) -> str:
    cnvpr = _find_cnvpr(shape._element)
    if cnvpr is None:
        return ""
    return cnvpr.get("descr", "") or ""


def set_alt_text(shape, text: str) -> None:
    cnvpr = _find_cnvpr(shape._element)
    if cnvpr is None:
        raise ValueError("Shape has no cNvPr element to set alt-text on")
    cnvpr.set("descr", text)


def mark_decorative(shape) -> None:
    """Mark an image as decorative (empty alt-text) rather than skip alt-text
    entirely, matching how PowerPoint's own 'Mark as decorative' works."""
    set_alt_text(shape, "")


def mark_table_header(shape) -> str:
    """Flags a table's first row as its header (`firstRow="1"`), which is what
    screen readers and checkers such as Blackboard Ally read to announce column
    names. Returns "set", "already", or "skipped: <reason>".

    The flag only changes how a table *style* paints row 1, so it is applied
    only when it is visually inert: no table style is attached, and row 1 is
    plainly a header (two or more rows, every cell has text, nothing merged).
    Anything else is left alone and reported."""
    tbl = shape.table._tbl
    pr = tbl.tblPr
    if pr.get("firstRow") in ("1", "true"):
        return "already"
    if pr.find(qn("a:tableStyleId")) is not None:
        return "skipped: a table style would restyle row 1"
    rows = tbl.findall(qn("a:tr"))
    if len(rows) < 2:
        return "skipped: only one row"
    cells = rows[0].findall(qn("a:tc"))
    if any(c.get(a) for c in cells for a in ("gridSpan", "rowSpan", "hMerge", "vMerge")):
        return "skipped: first row has merged cells"
    if not all("".join(c.itertext()).strip() for c in cells):
        return "skipped: first row has empty cells"
    pr.set("firstRow", "1")
    return "set"


_MAX_TABLE_ROWS_IN_TEXT = 20


def table_to_text(table) -> str:
    """Renders a table's cell text as pipe-delimited rows for an LLM prompt.

    Truncates very long tables since only enough rows to convey structure and
    a representative sample of content are needed for a description.
    """
    rows = list(table.rows)
    lines = [" | ".join(cell.text.strip() for cell in row.cells) for row in rows[:_MAX_TABLE_ROWS_IN_TEXT]]
    if len(rows) > _MAX_TABLE_ROWS_IN_TEXT:
        lines.append(f"... ({len(rows) - _MAX_TABLE_ROWS_IN_TEXT} more rows)")
    return "\n".join(lines)


def chart_to_text(chart) -> str:
    """Renders a chart's type, title, and data as text for an LLM prompt.

    No image of the chart exists to send to a vision model, but python-pptx
    exposes the underlying data directly, which is enough to describe it.
    """
    lines = [f"Chart type: {chart.chart_type.name}"]
    if chart.has_title:
        lines.append(f"Title: {chart.chart_title.text_frame.text}")
    try:
        categories = [str(c) for c in chart.plots[0].categories]
    except (IndexError, ValueError):
        categories = []
    if categories:
        lines.append("Categories: " + ", ".join(categories))
    for series in chart.series:
        values = ", ".join("" if v is None else str(v) for v in series.values)
        lines.append(f"Series '{series.name}': {values}")
    return "\n".join(lines)
