"""Read-only accessibility checks that report problems but never change a deck.

Two checks: text that is hard to read against its background, and slides whose
reading order (the order a screen reader follows, which is the order shapes
appear in the slide's XML) disagrees with how they are laid out. Colors and
layout belong to the author, so nothing here is ever written back."""
from dataclasses import asdict, dataclass
from pathlib import Path

from pptx.oxml.ns import qn

from cappv1.pptx_reader import open_presentation

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NORMAL_MIN, LARGE_MIN = 4.5, 3.0  # WCAG 2.x AA
_EMU_PER_PT = 12700


@dataclass
class Finding:
    slide: int
    kind: str  # contrast | reading_order
    message: str
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    findings: list
    checked_text: int  # text runs whose colors could be resolved and measured
    unmeasured_text: int  # runs on gradients, pictures or unusual colors: not judged

    def grouped(self) -> list:
        """Findings with the same cause collapsed: one entry, many slides."""
        groups: dict = {}
        for f in self.findings:
            key = (f.kind, f.detail if f.kind == "contrast" else f.message + f.detail)
            g = groups.setdefault(key, {"kind": f.kind, "message": f.message, "detail": f.detail, "slides": []})
            g["slides"].append(f.slide)
        return list(groups.values())

    def as_dict(self) -> dict:
        return {"groups": self.grouped(), "problems": len(self.findings), "checked_text": self.checked_text,
                "unmeasured_text": self.unmeasured_text}


# ---- colors ----------------------------------------------------------------------
def _lum(hex6: str) -> float:
    chan = [int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    chan = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chan]
    return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]


def contrast_ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _hls(hex6):
    import colorsys
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _from_hls(h, l, s) -> str:
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h, min(max(l, 0), 1), s)
    return "".join(f"{round(c * 255):02X}" for c in (r, g, b))


class _Theme:
    def __init__(self, prs) -> None:
        self.colors: dict[str, str] = {}
        self.fills: list = []
        master = prs.slide_master
        for rel in master.part.rels.values():
            if rel.reltype.endswith("/theme"):
                from lxml import etree
                root = etree.fromstring(rel.target_part.blob)
                scheme = root.find(f".//{{{_A}}}clrScheme")
                for el in scheme if scheme is not None else []:
                    child = el[0]
                    val = child.get("val") if child.tag.endswith("srgbClr") else child.get("lastClr")
                    if val:
                        self.colors[el.tag.split("}")[1]] = val.upper()
                lst = root.find(f".//{{{_A}}}bgFillStyleLst")
                self.fills = list(lst) if lst is not None else []
        cmap = master._element.find(qn("p:clrMap"))
        self.map = dict(cmap.attrib) if cmap is not None else {"tx1": "dk1", "bg1": "lt1", "tx2": "dk2", "bg2": "lt2"}

    def resolve(self, color_el, phclr: str | None = None) -> str | None:
        """A color element (srgbClr, schemeClr, ...) to 'RRGGBB', or None if it can't be judged."""
        tag = color_el.tag.split("}")[1]
        if tag == "srgbClr":
            base = color_el.get("val").upper()
        elif tag == "schemeClr":
            val = color_el.get("val")
            if val == "phClr":
                base = phclr
            else:
                base = self.colors.get(self.map.get(val, val))
        else:
            return None
        if not base or len(base) != 6:
            return None
        for mod in color_el:
            name, val = mod.tag.split("}")[1], mod.get("val")
            if name == "alpha" and int(val) < 100000:
                return None  # semi-transparent: what shows through is unknown
            if name in ("lumMod", "lumOff"):
                continue
            if name in ("tint", "shade", "satMod", "hueMod", "satOff", "hueOff", "comp", "inv", "gray"):
                return None
        h, l, s = _hls(base)
        mod = next((int(m.get("val")) for m in color_el if m.tag.endswith("}lumMod")), 100000)
        off = next((int(m.get("val")) for m in color_el if m.tag.endswith("}lumOff")), 0)
        if mod != 100000 or off:
            return _from_hls(h, l * mod / 100000 + off / 100000, s)
        return base

    def solid(self, fill_parent, phclr=None) -> str | None:
        sf = fill_parent.find(f"{{{_A}}}solidFill") if fill_parent is not None else None
        return self.resolve(sf[0], phclr) if sf is not None and len(sf) else None


def _fill_colors(theme: _Theme, pr, phclr=None) -> list | None:
    """Every color a fill can show: one for solid, the stops for a gradient, both
    colors for a pattern. None when it can't be judged (a picture, or odd colors)."""
    if pr is None:
        return None
    for tag, path in (("solidFill", "."), ("gradFill", ".//" + f"{{{_A}}}gs"), ("pattFill", None)):
        el = pr.find(f"{{{_A}}}{tag}")
        if el is None:
            continue
        if tag == "pattFill":
            parts = [c[0] for c in (el.find(f"{{{_A}}}fgClr"), el.find(f"{{{_A}}}bgClr")) if c is not None and len(c)]
        elif tag == "gradFill":
            parts = [gs[0] for gs in el.iter(f"{{{_A}}}gs") if len(gs)]
        else:
            parts = [el[0]] if len(el) else []
        colors = [theme.resolve(p, phclr) for p in parts]
        return colors if colors and all(colors) else None
    return None


def _has_nonsolid_fill(el) -> bool:
    return el is not None and any(el.find(f"{{{_A}}}{t}") is not None for t in ("gradFill", "blipFill", "pattFill"))


def _background(theme: _Theme, slide) -> str | None:
    """The slide's background color: its own, else its layout's, else the master's."""
    for part in (slide, slide.slide_layout, slide.slide_layout.slide_master):
        bg = part._element.find(f".//{qn('p:bg')}")
        if bg is None:
            continue
        pr = bg.find(qn("p:bgPr"))
        if pr is not None:
            return _fill_colors(theme, pr)
        ref = bg.find(qn("p:bgRef"))
        if ref is not None and len(ref):
            phclr = theme.resolve(ref[0])
            idx = int(ref.get("idx", "0"))
            if 1001 <= idx < 1001 + len(theme.fills) and phclr:
                style = theme.fills[idx - 1001]
                if style.tag.endswith("solidFill") and len(style):
                    return [theme.resolve(style[0], phclr)]
            return None
    return ["FFFFFF"]


def _shape_fill(theme: _Theme, el) -> tuple[bool, list | None]:
    """(has_own_fill, colors). Own fills on a text shape replace the slide background."""
    sp_pr = el.find(qn("p:spPr"))
    if sp_pr is None or sp_pr.find(f"{{{_A}}}noFill") is not None:
        return False, None
    if not any(sp_pr.find(f"{{{_A}}}{t}") is not None for t in ("solidFill", "gradFill", "blipFill", "pattFill")):
        ref = el.find(f"{qn('p:style')}/{{{_A}}}fillRef")
        if ref is not None and ref.get("idx", "0") != "0":
            return True, None  # filled by the theme's shape style: not judged
        return False, None
    return True, _fill_colors(theme, sp_pr)


# ---- contrast --------------------------------------------------------------------
def _placeholder_chain(slide, sp):
    """The shape's own element, then the layout's and master's matching placeholders."""
    chain = [sp]
    ph = sp.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}")
    if ph is None:
        return chain, None
    for part in (slide.slide_layout, slide.slide_layout.slide_master):
        for cand in part._element.iter(qn("p:sp")):
            cph = cand.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}")
            if cph is None:
                continue
            same_idx = ph.get("idx") is not None and cph.get("idx") == ph.get("idx")
            same_type = ph.get("idx") is None and (cph.get("type") or "obj") == (ph.get("type") or "obj")
            title = {"title", "ctrTitle"}
            if same_idx or same_type or (ph.get("type") in title and cph.get("type") in title):
                chain.append(cand)
                break
    return chain, ph.get("type") or "body"


def _run_color(theme: _Theme, run, para, slide, sp) -> str | None:
    rpr = run.find(qn("a:rPr"))
    if rpr is not None and _has_nonsolid_fill(rpr):
        return None
    color = theme.solid(rpr) if rpr is not None else None
    if color:
        return color
    ppr = para.find(qn("a:pPr"))
    lvl = f"lvl{int(ppr.get('lvl', '0')) + 1 if ppr is not None else 1}pPr"
    dflt = ppr.find(qn("a:defRPr")) if ppr is not None else None
    color = theme.solid(dflt) if dflt is not None else None
    if color:
        return color
    chain, kind = _placeholder_chain(slide, sp)
    for shape in chain:
        node = shape.find(f".//{qn('p:txBody')}/{{{_A}}}lstStyle/{{{_A}}}{lvl}/{{{_A}}}defRPr")
        color = theme.solid(node) if node is not None else None
        if color:
            return color
    styles = slide.slide_layout.slide_master._element.find(qn("p:txStyles"))
    group = "titleStyle" if kind in ("title", "ctrTitle") else ("bodyStyle" if kind else "otherStyle")
    node = styles.find(f"{qn('p:' + group)}/{{{_A}}}{lvl}/{{{_A}}}defRPr") if styles is not None else None
    color = theme.solid(node) if node is not None else None
    if color:
        return color
    ref = sp.find(f"{qn('p:style')}/{{{_A}}}fontRef")
    if ref is not None and len(ref):
        return theme.resolve(ref[0])
    return theme.resolve(_synthetic("tx1"))


def _synthetic(name):
    from lxml import etree
    return etree.Element(f"{{{_A}}}schemeClr", val=name)


def _size_pt(run) -> float:
    rpr = run.find(qn("a:rPr"))
    sz = rpr.get("sz") if rpr is not None else None
    return int(sz) / 100 if sz else 18.0  # PowerPoint's default body size


def _bold(run) -> bool:
    rpr = run.find(qn("a:rPr"))
    return rpr is not None and rpr.get("b") in ("1", "true")


def _through_groups(el, box):
    """Maps a box from a group's own coordinate space out to the slide, group by group."""
    x, y, w, h = box
    parent = el.getparent()
    while parent is not None and parent.tag == qn("p:grpSp"):
        xf = parent.find(f"{qn('p:grpSpPr')}/{{{_A}}}xfrm")
        if xf is not None and all(xf.find(f"{{{_A}}}{t}") is not None for t in ("off", "ext", "chOff", "chExt")):
            g = {t: xf.find(f"{{{_A}}}{t}") for t in ("off", "ext", "chOff", "chExt")}
            cw, ch = int(g["chExt"].get("cx")) or 1, int(g["chExt"].get("cy")) or 1
            sx, sy = int(g["ext"].get("cx")) / cw, int(g["ext"].get("cy")) / ch
            x = int(g["off"].get("x")) + (x - int(g["chOff"].get("x"))) * sx
            y = int(g["off"].get("y")) + (y - int(g["chOff"].get("y"))) * sy
            w, h = w * sx, h * sy
        parent = parent.getparent()
    return x, y, w, h


def _box(chain):
    """(x, y, w, h) of a shape on the slide, taken from the first of its placeholder chain that sets one."""
    for el in chain:
        xfrm = el.find(f"{qn('p:spPr')}/{{{_A}}}xfrm")
        if xfrm is not None and xfrm.find(f"{{{_A}}}off") is not None and xfrm.find(f"{{{_A}}}ext") is not None:
            off, ext = xfrm.find(f"{{{_A}}}off"), xfrm.find(f"{{{_A}}}ext")
            raw = (int(off.get("x")), int(off.get("y")), int(ext.get("cx")), int(ext.get("cy")))
            return _through_groups(el, raw) if el is chain[0] else raw
    return None


def _covers(el, point) -> bool:
    box = _box([el])
    if box is None:
        return False
    x, y, w, h = box
    px, py = point
    geom = el.find(f"{qn('p:spPr')}/{{{_A}}}prstGeom")
    if geom is not None and geom.get("prst") == "ellipse":
        return w > 0 and h > 0 and ((px - x - w / 2) / (w / 2)) ** 2 + ((py - y - h / 2) / (h / 2)) ** 2 <= 1
    return x <= px <= x + w and y <= py <= y + h


def _behind(theme: _Theme, slide, sp, fallback):
    """The colors a text shape sits on: the topmost filled shape beneath its center
    (master, then layout, then earlier shapes on the slide), else the slide background."""
    chain, _ = _placeholder_chain(slide, sp)
    box = _box(chain)
    if box is None:
        return fallback
    return _behind_point(theme, slide, sp, (box[0] + box[2] / 2, box[1] + box[3] / 2), fallback)


def _behind_point(theme: _Theme, slide, sp, point, fallback):
    if point is None:
        return fallback
    found = fallback
    layers = [slide.slide_layout.slide_master._element, slide.slide_layout._element]
    for root in layers:
        for cand in root.iter(qn("p:sp")):
            if cand.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}") is not None:
                continue
            has, colors = _shape_fill(theme, cand)
            if has and _covers(cand, point):
                found = colors
    for cand in slide._element.iter(qn("p:sp")):
        if cand is sp:
            break
        has, colors = _shape_fill(theme, cand)
        if has and _covers(cand, point):
            found = colors
    return found


def check_contrast(prs) -> tuple[list, int, int]:
    theme = _Theme(prs)
    findings, measured, unmeasured = [], 0, 0
    for number, slide in enumerate(prs.slides, 1):
        bg = _background(theme, slide)
        seen: set = set()
        for sp in slide._element.iter(qn("p:sp")):
            own, fill = _shape_fill(theme, sp)
            backdrop = fill if own else _behind(theme, slide, sp, bg)
            for para in sp.iter(f"{{{_A}}}p"):
                for run in para.findall(qn("a:r")):
                    text = (run.findtext(qn("a:t")) or "").strip()
                    if not text:
                        continue
                    fg = _run_color(theme, run, para, slide, sp)
                    if not fg or not backdrop:
                        unmeasured += 1
                        continue
                    measured += 1
                    ratio = min(contrast_ratio(fg, b) for b in backdrop)
                    size = _size_pt(run)
                    need = LARGE_MIN if size >= 18 or (size >= 14 and _bold(run)) else NORMAL_MIN
                    shown = ", ".join("#" + b for b in backdrop)
                    if ratio < need and (fg, tuple(backdrop), text[:30]) not in seen:
                        seen.add((fg, tuple(backdrop), text[:30]))
                        findings.append(Finding(number, "contrast", f"“{text[:50]}” is hard to read.",
                                                f"Contrast {ratio:.1f}:1, needs {need}:1 (text #{fg} on {shown})."))
        # table cells: each cell's own fill, else the table frame's backdrop
        for frame in slide._element.iter(qn("p:graphicFrame")):
            tbl = frame.find(f".//{{{_A}}}tbl")
            if tbl is None:
                continue
            styled = tbl.find(f"{{{_A}}}tblPr/{{{_A}}}tableStyleId") is not None
            xf = frame.find(qn("p:xfrm"))
            where = None
            if xf is not None:
                off, ext = xf.find(f"{{{_A}}}off"), xf.find(f"{{{_A}}}ext")
                where = (int(off.get("x")) + int(ext.get("cx")) // 2, int(off.get("y")) + int(ext.get("cy")) // 2)
            frame_bg = _behind_point(theme, slide, frame, where, bg)
            for cell in tbl.iter(f"{{{_A}}}tc"):
                pr = cell.find(f"{{{_A}}}tcPr")
                own = pr is not None and any(pr.find(f"{{{_A}}}{t}") is not None for t in ("solidFill", "gradFill", "blipFill", "pattFill"))
                if pr is not None and pr.find(f"{{{_A}}}noFill") is not None:
                    own = False
                backdrop = _fill_colors(theme, pr) if own else (None if styled else frame_bg)
                for para in cell.iter(f"{{{_A}}}p"):
                    for run in para.findall(qn("a:r")):
                        text = (run.findtext(qn("a:t")) or "").strip()
                        if not text:
                            continue
                        rpr = run.find(qn("a:rPr"))
                        fg = theme.solid(rpr) if rpr is not None else None
                        if not fg and not styled:
                            fg = theme.resolve(_synthetic("tx1"))
                        if not fg or not backdrop:
                            unmeasured += 1
                            continue
                        measured += 1
                        ratio = min(contrast_ratio(fg, b) for b in backdrop)
                        size = _size_pt(run)
                        need = LARGE_MIN if size >= 18 or (size >= 14 and _bold(run)) else NORMAL_MIN
                        shown = ", ".join("#" + b for b in backdrop)
                        if ratio < need and (fg, tuple(backdrop), text[:30]) not in seen:
                            seen.add((fg, tuple(backdrop), text[:30]))
                            findings.append(Finding(number, "contrast", f"“{text[:50]}” is hard to read.",
                                                    f"Contrast {ratio:.1f}:1, needs {need}:1 (text #{fg} on {shown})."))
    return findings, measured, unmeasured


# ---- reading order ---------------------------------------------------------------
def _meaningful(shape) -> bool:
    el = shape._element
    if el.tag in (qn("p:pic"), qn("p:graphicFrame"), qn("p:grpSp")):
        return True
    return el.tag == qn("p:sp") and bool(shape.has_text_frame and shape.text_frame.text.strip())


def check_reading_order(prs) -> list:
    findings = []
    for number, slide in enumerate(prs.slides, 1):
        items = [s for s in slide.shapes if _meaningful(s) and None not in (s.top, s.height, s.left)]
        title = slide.shapes.title
        if title is not None and title.text_frame.text.strip() and items and items[0].shape_id != title.shape_id:
            findings.append(Finding(number, "reading_order", "The title is not read first.",
                                    f"A screen reader starts with “{_label(items[0])}”."))
            continue
        for i, first in enumerate(items):
            above = next((later for later in items[i + 1:] if later.top + later.height <= first.top), None)
            if above is not None:
                findings.append(Finding(number, "reading_order", "Reading order does not follow the layout.",
                                        f"“{_label(first)}” is read before “{_label(above)}”, which sits above it."))
                break
    return findings


def _label(shape) -> str:
    text = shape.text_frame.text.strip() if shape.has_text_frame else ""
    return (text or shape.name)[:40]


# ---- entry point -----------------------------------------------------------------
def audit_deck(path: Path) -> Report:
    prs = open_presentation(path)
    contrast, measured, unmeasured = check_contrast(prs)
    return Report(contrast + check_reading_order(prs), measured, unmeasured)
