"""Color maths and theme colors for the read-only accessibility check (see audit.py)."""

from pptx.oxml.ns import qn

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


# ---- colors ----------------------------------------------------------------------
def _lum(hex6: str) -> float:
    chan = [int(hex6[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    chan = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chan]
    return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]


def contrast_ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _hls(hex6):
    import colorsys

    r, g, b = (int(hex6[i : i + 2], 16) / 255 for i in (0, 2, 4))
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
