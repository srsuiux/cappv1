"""Structure fixes for Word files that Blackboard Ally scores: heading levels, text contrast, the
document Title. Headings are fixed without changing how a page looks: a heading style is a copy of
the style it replaces, so only its name and outline level differ. Contrast is the one visible
change, and it is always reported."""
import colorsys
import copy
import re

from docx.oxml.ns import qn
from lxml import etree

from cappv1.docx_reader import CAPTION as _CAPTION
from cappv1.docx_check import CONTRAST_AA, CONTRAST_AAA, _HEX, contrast, run_background

_MAX_TITLE_CHARS = 120


def _level(style: etree._Element) -> int | None:
    name = style.find(qn("w:name"))
    m = re.fullmatch(r"heading\s*(\d)", (name.get(qn("w:val")) if name is not None else style.get(qn("w:styleId"))).lower())
    return int(m.group(1)) if m else None


def _text(el) -> str:
    # not itertext(): python-docx overrides .text on its element classes, which makes it repeat text
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def _style_of(p) -> str | None:
    ps = p.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    return ps.get(qn("w:val")) if ps is not None else None


def _set_style(p, style_id: str) -> None:
    ppr = p.find(qn("w:pPr"))
    if ppr is None:
        ppr = etree.Element(qn("w:pPr"))
        p.insert(0, ppr)
    ps = ppr.find(qn("w:pStyle"))
    if ps is None:
        ps = etree.Element(qn("w:pStyle"))
        ppr.insert(0, ps)
    ps.set(qn("w:val"), style_id)


def _outline(style: etree._Element, level0: int) -> None:
    """Sets the outline level in a style's paragraph properties (0 = Heading 1, 9 = body text)."""
    ppr = style.find(qn("w:pPr"))
    if ppr is None:
        ppr = etree.Element(qn("w:pPr"))
        anchor = style.find(qn("w:rPr"))
        (anchor.addprevious(ppr) if anchor is not None else style.append(ppr))
    for el in ppr.findall(qn("w:outlineLvl")):
        ppr.remove(el)
    el = etree.Element(qn("w:outlineLvl"))
    el.set(qn("w:val"), str(level0))
    anchor = next((c for c in ppr if etree.QName(c).localname in ("divId", "cnfStyle", "rPr", "sectPr", "pPrChange")), None)
    (anchor.addprevious(el) if anchor is not None else ppr.append(el))


def _rename(style: etree._Element, style_id: str, name: str) -> None:
    style.set(qn("w:styleId"), style_id)
    name_el = style.find(qn("w:name"))
    if name_el is None:
        name_el = etree.Element(qn("w:name"))
        style.insert(0, name_el)
    name_el.set(qn("w:val"), name)
    for tag in ("w:link", "w:uiPriority", "w:semiHidden", "w:unhideWhenUsed"):
        for el in style.findall(qn(tag)):
            style.remove(el)


def _in_flow(p) -> bool:
    """A paragraph in the body text. Ally ignores headings inside table cells and text boxes (a column
    label styled Heading 4 is not a heading of the document), so only these count."""
    return not any(a.tag in (qn("w:tc"), qn("w:txbxContent")) for a in p.iterancestors())


def normalize_headings(doc) -> str:
    """Gives the body text real headings that start at Heading 1 with no gaps and no empty ones,
    without changing how anything looks. Returns a short description of what was done, or ""."""
    styles_el = doc.styles.element
    body = doc.element.body
    by_id = {s.get(qn("w:styleId")): s for s in styles_el.iter(qn("w:style"))}
    paragraphs = list(body.iter(qn("w:p")))
    flow = [p for p in paragraphs if _in_flow(p)]
    done = []

    def is_heading(p) -> bool:
        return _style_of(p) in by_id and _level(by_id[_style_of(p)]) is not None

    # empty headings read as noise to a screen reader: keep their spacing, drop their heading-ness
    for p in flow:
        sid = _style_of(p)
        if is_heading(p) and not _text(p):
            plain_id = sid + "Plain"
            if plain_id not in by_id:
                plain = copy.deepcopy(by_id[sid])
                _rename(plain, plain_id, "Plain " + by_id[sid].find(qn("w:name")).get(qn("w:val")))
                _outline(plain, 9)
                styles_el.append(plain)
                by_id[plain_id] = plain
            _set_style(p, plain_id)
            done.append("empty heading made plain")

    headings = [(p, _style_of(p)) for p in flow if is_heading(p) and _text(p)]
    if headings:
        used = sorted({_level(by_id[sid]) for _, sid in headings})
        if len(used) > 6 or _level(by_id[headings[0][1]]) != used[0]:
            return "; ".join(done)  # the first heading is deeper than a later one: can't fix without moving text
        if used == list(range(1, len(used) + 1)):
            return "; ".join(done)  # already starts at Heading 1 with no gaps
        rank = {lvl: i + 1 for i, lvl in enumerate(used)}
        used_ids = {sid for _, sid in headings}
        targets = {sid: rank[_level(by_id[sid])] for sid in used_ids}
        new_ids = {f"Heading{n}" for n in targets.values()}
        affected = new_ids & set(by_id)  # existing styles a new heading style would overwrite
        remapped = {id(p) for p, _ in headings}
        pointed_at = set()
        for st in styles_el.iter(qn("w:style")):
            for tag in ("w:basedOn", "w:next"):
                el = st.find(qn(tag))
                if el is not None:
                    pointed_at.add(el.get(qn("w:val")))
        if affected & pointed_at or any(_style_of(p) in affected for p in paragraphs if id(p) not in remapped):
            return "; ".join(done)  # renumbering would restyle something else; leave the document alone
        snapshots = {sid: copy.deepcopy(by_id[sid]) for sid in used_ids}
        for sid in affected:
            styles_el.remove(by_id[sid])
        id_map = {}
        for sid, snap in snapshots.items():
            n = targets[sid]
            _rename(snap, f"Heading{n}", f"heading {n}")
            _outline(snap, n - 1)
            styles_el.append(snap)
            id_map[sid] = f"Heading{n}"
        for p, sid in headings:
            _set_style(p, id_map[sid])
        done.append("heading styles renumbered: " + ", ".join(f"{s} to {v}" for s, v in sorted(id_map.items())))
        return "; ".join(done)

    # no headings in the body text (a column label in a table does not count): the figure and table
    # captions are what a reader navigates by
    captions = [p for p in flow if _CAPTION.match(_text(p)) and len(_text(p)) <= 200 and p.getparent() is body]
    if len(captions) >= 2:
        counts = {}
        for p in captions:
            counts[_style_of(p) or "Normal"] = counts.get(_style_of(p) or "Normal", 0) + 1
        base = max(counts, key=counts.get)
        if "Heading1" not in by_id or not any(_style_of(p) == "Heading1" for p in paragraphs):
            if "Heading1" in by_id:
                styles_el.remove(by_id["Heading1"])
            style = etree.SubElement(styles_el, qn("w:style"))
            style.set(qn("w:type"), "paragraph")
            style.set(qn("w:styleId"), "Heading1")
            for tag, val in (("w:name", "heading 1"), ("w:basedOn", base), ("w:next", base)):
                etree.SubElement(style, qn(tag)).set(qn("w:val"), val)
            etree.SubElement(style, qn("w:qFormat"))
            _outline(style, 0)
            n = 0
            for p in captions:
                if (_style_of(p) or "Normal") == base:
                    _set_style(p, "Heading1")
                    n += 1
            done.append(f"{n} captions made Heading 1")
    return "; ".join(done)


def fix_contrast(doc) -> list[str]:
    """Darkens text colors that fail 4.5:1 against what is behind them to 7:1, keeping the hue. Returns a
    note per color changed. This is the one fix that changes how a page looks."""
    notes = {}
    for run in doc.element.body.iter(qn("w:r")):
        color = run.find(f"{qn('w:rPr')}/{qn('w:color')}")
        if color is None or not _HEX.fullmatch(color.get(qn("w:val")) or "") or not _text(run):
            continue
        old, back = color.get(qn("w:val")).upper(), run_background(run)
        if contrast(old, back) >= CONTRAST_AA:
            continue
        r, g, b = (int(old[i:i + 2], 16) / 255 for i in (0, 2, 4))
        h, light, sat = colorsys.rgb_to_hls(r, g, b)
        new = old
        while contrast(new, back) < CONTRAST_AAA and light > 0:  # only failing text is touched, but it is fixed generously
            light = max(0.0, light - 0.01)
            new = "".join(f"{round(c * 255):02X}" for c in colorsys.hls_to_rgb(h, light, sat))
        color.set(qn("w:val"), new)
        for attr in ("w:themeColor", "w:themeTint", "w:themeShade"):
            color.attrib.pop(qn(attr), None)
        notes[(old, new, back.upper())] = notes.get((old, new, back.upper()), 0) + 1
    return [f"text color #{o} darkened to #{n} on #{b} to pass the contrast check ({c} place{'s' if c != 1 else ''})"
            for (o, n, b), c in notes.items()]


def set_title(doc) -> str | None:
    """Fills the Title property when it is empty or names something not in the document (Ally and
    screen readers announce it). It is invisible on the page. Returns the new title, or None."""
    props = doc.core_properties
    text = " ".join(_text(p) for p in doc.element.body.iter(qn("w:p"))).lower()
    current = (props.title or "").strip()
    if current and current.lower() in text:
        return None
    first = next((_text(p) for p in doc.element.body.iter(qn("w:p")) if _text(p)), "")
    title = re.sub(r"\s+", " ", first)[:_MAX_TITLE_CHARS].strip()
    if not title or title == current:
        return None
    props.title = title
    return title
