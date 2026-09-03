from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

_NV_PR_TAGS = ("p:nvPicPr", "p:nvSpPr", "p:nvGrpSpPr", "p:nvGraphicFramePr", "p:nvCxnSpPr")


@dataclass
class SlideContext:
    index: int  # 0-based
    section: str | None
    title: str
    body_text: str
    notes: str


@dataclass
class PictureRef:
    shape: object  # pptx.shapes.picture.Picture
    slide_index: int


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


def _placeholder_text(slide, idx_types: set[int]) -> str:
    parts = []
    for shape in slide.placeholders:
        if shape.placeholder_format.idx is not None and shape.has_text_frame:
            parts.append(shape.text_frame.text)
    return "\n".join(p for p in parts if p.strip())


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


def _walk_pictures(shapes, slide_index: int) -> list[PictureRef]:
    refs = []
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            refs.append(PictureRef(shape=shape, slide_index=slide_index))
        elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            refs.extend(_walk_pictures(shape.shapes, slide_index))
    return refs


def extract_pictures(slide, slide_index: int) -> list[PictureRef]:
    return _walk_pictures(slide.shapes, slide_index)


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
