from dataclasses import dataclass
from pathlib import Path

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
