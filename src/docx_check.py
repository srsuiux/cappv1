"""Read-only check of a Word file against the rules Blackboard Ally scores (Anthology's Word
checklist). It proves the rules are met in the file's XML; the real score only appears after the
file is uploaded to Blackboard. Nothing here ever changes a document.

    python -m src.docx_check output/*.docx"""
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_V = "urn:schemas-microsoft-com:vml"
_ADEC = "http://schemas.microsoft.com/office/drawing/2017/decorative"
_DC = "http://purl.org/dc/elements/1.1/"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_OLE2 = b"\xd0\xcf\x11\xe0"  # a password-protected .docx is an OLE container, not a zip

MIN_PARAGRAPHS_FOR_HEADINGS = 12  # Ally only asks for headings in documents this long
CONTRAST_AA, CONTRAST_AAA = 4.5, 7.0


def _w(tag: str) -> str:
    return f"{{{_W}}}{tag}"


@dataclass
class Issue:
    severity: str  # severe | major | minor | note
    item: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.item}: {self.message}"


def _luminance(hex6: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(foreground: str, background: str) -> float:
    a, b = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (a + 0.05) / (b + 0.05)


_HEX = re.compile(r"[0-9A-Fa-f]{6}")
_NAMED = {"black": "000000", "white": "FFFFFF", "yellow": "FFFF00", "lightGray": "C0C0C0", "darkGray": "808080",
          "red": "FF0000", "green": "00FF00", "blue": "0000FF", "cyan": "00FFFF", "magenta": "FF00FF",
          "darkBlue": "000080", "darkRed": "800000", "darkGreen": "008000", "darkYellow": "808000"}


def _heading_level(style_id: str, styles: dict) -> int | None:
    m = re.fullmatch(r"heading\s*(\d)", styles.get(style_id, style_id).lower())
    return int(m.group(1)) if m else None


def run_background(run) -> str:
    """The color behind a run: its highlight, else the shading of the cell or paragraph around it, else white."""
    hl = run.find(f"{_w('rPr')}/{_w('highlight')}")
    if hl is not None and hl.get(_w("val")) in _NAMED:
        return _NAMED[hl.get(_w("val"))]
    for anc in run.iterancestors():
        shd = anc.find(f"{_w('tcPr')}/{_w('shd')}") if anc.tag == _w("tc") else anc.find(f"{_w('pPr')}/{_w('shd')}")
        if shd is not None and _HEX.fullmatch(shd.get(_w("fill")) or ""):
            return shd.get(_w("fill"))
    return "FFFFFF"


def check(path: Path) -> list[Issue]:
    path = Path(path)
    issues: list[Issue] = []
    head = path.read_bytes()[:4]
    if head == _OLE2:
        return [Issue("severe", "file", "the file is password-protected or encrypted; Ally scores it 0")]
    try:
        z = zipfile.ZipFile(path)
        if z.testzip() is not None:
            raise zipfile.BadZipFile("a part is damaged")
        from docx import Document

        Document(str(path))
        body = etree.fromstring(z.read("word/document.xml"))
        styles_xml = etree.fromstring(z.read("word/styles.xml")) if "word/styles.xml" in z.namelist() else None
        core = etree.fromstring(z.read("docProps/core.xml")) if "docProps/core.xml" in z.namelist() else None
    except Exception as exc:  # anything that stops it opening is the severe case
        return [Issue("severe", "file", f"does not open cleanly: {exc}")]

    # 2. images and embedded drawings need a description (or the decorative flag)
    for pr in body.iter(f"{{{_WP}}}docPr"):
        if any(a.tag == _MC_FALLBACK for a in pr.iterancestors()):
            continue
        decorative = pr.xpath(f".//*[local-name()='decorative' and namespace-uri()='{_ADEC}']")
        if not (pr.get("descr") or "").strip() and not decorative:
            issues.append(Issue("major", "alt text", f"picture or shape \"{pr.get('name', '')}\" has no description"))
    for shape in body.iter(f"{{{_V}}}shape"):
        if shape.getparent().tag == _w("object") and not (shape.get("alt") or "").strip():
            issues.append(Issue("major", "alt text", f"embedded object \"{shape.get('id', '')}\" has no description"))

    # 3. contrast of every run against the cell, paragraph or highlight behind it
    style_color, style_fill = {}, {}
    if styles_xml is not None:
        for st in styles_xml.iter(_w("style")):
            c = st.find(f"{_w('rPr')}/{_w('color')}")
            if c is not None and _HEX.fullmatch(c.get(_w("val")) or ""):
                style_color[st.get(_w("styleId"))] = c.get(_w("val"))
    worst = {}
    for run in body.iter(_w("r")):
        if not "".join(run.itertext()).strip():
            continue
        color = run.find(f"{_w('rPr')}/{_w('color')}")
        value = color.get(_w("val")) if color is not None else None
        if not value or not _HEX.fullmatch(value):
            rstyle = run.find(f"{_w('rPr')}/{_w('rStyle')}")
            value = style_color.get(rstyle.get(_w("val"))) if rstyle is not None else None
        if not value:
            continue  # automatic color: Word picks black or white against the background
        back = run_background(run)
        ratio = contrast(value, back)
        if ratio < CONTRAST_AAA:
            worst[(value.upper(), back.upper())] = round(ratio, 1)
    for (fg, bg), ratio in sorted(worst.items(), key=lambda kv: kv[1]):
        issues.append(Issue("major" if ratio < CONTRAST_AA else "note", "contrast",
                            f"text #{fg} on #{bg} is {ratio}:1 ({'fails 4.5:1' if ratio < CONTRAST_AA else 'passes 4.5:1, short of 7:1'})"))

    # 4, 5, 8. headings
    names = {}
    if styles_xml is not None:
        for st in styles_xml.iter(_w("style")):
            n = st.find(_w("name"))
            names[st.get(_w("styleId"))] = n.get(_w("val")) if n is not None else st.get(_w("styleId"))
    def in_tables_or_boxes(p) -> bool:
        return any(a.tag in (_w("tc"), _w("txbxContent")) for a in p.iterancestors())

    paragraphs = [p for p in body.iter(_w("p")) if "".join(t.text or "" for t in p.iter(_w("t"))).strip()]
    levels, in_table = [], 0
    for p in paragraphs:
        ps = p.find(f"{_w('pPr')}/{_w('pStyle')}")
        lvl = _heading_level(ps.get(_w("val")), names) if ps is not None else None
        if lvl and in_tables_or_boxes(p):
            in_table += 1
        elif lvl:
            levels.append(lvl)
    for p in body.iter(_w("p")):
        ps = p.find(f"{_w('pPr')}/{_w('pStyle')}")
        if (ps is not None and _heading_level(ps.get(_w("val")), names) and not in_tables_or_boxes(p)
                and not "".join(t.text or "" for t in p.iter(_w("t"))).strip()):
            issues.append(Issue("minor", "headings", "a heading is empty"))
    if not levels:
        if len(paragraphs) >= MIN_PARAGRAPHS_FOR_HEADINGS:
            extra = f" ({in_table} heading-styled paragraph(s) are inside table cells, which Ally ignores)" if in_table else ""
            issues.append(Issue("major", "headings", f"no Heading styles in the body text of a document of {len(paragraphs)} paragraphs{extra}"))
    else:
        if levels[0] != 1:
            issues.append(Issue("major", "headings", f"the first heading is Heading {levels[0]}, not Heading 1"))
        for before, after in zip(levels, levels[1:]):
            if after > before + 1:
                issues.append(Issue("minor", "headings", f"Heading {before} is followed by Heading {after}"))
                break
        if max(levels) > 6:
            issues.append(Issue("minor", "headings", "a heading goes past level 6"))

    # 6. tables: the first row is a header row
    for i, tbl in enumerate(body.iter(_w("tbl")), 1):
        rows = tbl.findall(_w("tr"))
        if rows and rows[0].find(f"{_w('trPr')}/{_w('tblHeader')}") is None:
            issues.append(Issue("major", "table header", f"table {i} ({len(rows)} rows x {len(rows[0].findall(_w('tc')))} columns) has no header row"))

    # 7. language
    lang = None
    if styles_xml is not None:
        el = styles_xml.find(f".//{_w('docDefaults')}//{_w('lang')}")
        lang = el.get(_w("val")) if el is not None else None
    if not lang:
        issues.append(Issue("minor", "language", "no default language is set in the styles"))
    elif not lang.lower().startswith("en"):
        issues.append(Issue("note", "language", f"the default language is {lang}; check it matches the text"))

    # extras
    title = (core.findtext(f"{{{_DC}}}title") or "").strip() if core is not None else ""
    if not title:
        issues.append(Issue("note", "title", "the document has no Title property"))
    elif title.lower() not in "".join(body.itertext()).lower():
        issues.append(Issue("note", "title", f"the Title property \"{title[:50]}\" does not appear in the document"))
    return issues


def main(argv: list[str]) -> int:
    worst = 0
    for name in argv:
        found = check(Path(name))
        print(f"{Path(name).name}: {'no issues' if not found else str(len(found)) + ' issue(s)'}")
        for issue in found:
            print("   ", issue)
        worst = max(worst, sum(1 for i in found if i.severity in ("severe", "major")))
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
