"""CHANGELOG.md as the Changelog page. The file stays the one source: no second copy to keep in step."""
import html
import re
from datetime import date
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
_HEAD = re.compile(r"(?P<version>Unreleased|\d+\.\d+\.\d+)(?: - (?P<date>\d{4}-\d{2}-\d{2}))?(?: \((?P<note>.*)\))?\s*$")
_KINDS = {"new": "new", "added": "new", "improved": "improved", "changed": "improved", "fixed": "fixed"}


def parse(text: str) -> list[dict]:
    """[{version, date, note, groups: [{title, kind, items: [str]}]}], newest first as written."""
    releases, group = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            m = _HEAD.match(line[3:].strip())
            if not m:
                releases.append(None)  # not a release heading: skip until the next one
                continue
            releases.append({"version": m["version"], "date": m["date"], "note": m["note"], "groups": []})
            group = None
        elif line.startswith("### ") and releases and releases[-1]:
            title = line[4:].strip()
            group = {"title": title, "kind": _KINDS.get(title.lower(), "improved"), "items": []}
            releases[-1]["groups"].append(group)
        elif line.startswith("- ") and releases and releases[-1]:
            if group is None:
                group = {"title": "Changes", "kind": "improved", "items": []}
                releases[-1]["groups"].append(group)
            group["items"].append(line[2:].strip())
    return [r for r in releases if r]


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    return re.sub(r"\[([^\]]+)\]\((https://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1<span class="sr"> (opens in a new tab)</span></a>', out)


def _nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def render(text: str | None = None) -> str:
    releases = parse(CHANGELOG.read_text(encoding="utf-8") if text is None else text)
    if not releases:
        return "<p class=\"muted\">No release notes yet.</p>"
    latest = next((r["version"] for r in releases if r["version"] != "Unreleased"), "")
    body = []
    for r in releases:
        v = r["version"]
        when = f'<time datetime="{r["date"]}">{_nice_date(r["date"])}</time>' if r["date"] else "<span>Not released yet</span>"
        chip = ' <span class="chip">Latest release</span>' if v == latest else (' <span class="chip soon">Next</span>' if v == "Unreleased" else "")
        note = f'<span>{_inline(r["note"])}</span>' if r["note"] else ""
        groups = "".join(
            f'<h3 class="kind {g["kind"]}">{html.escape(g["title"])}</h3><ul>' + "".join(f"<li>{_inline(i)}</li>" for i in g["items"]) + "</ul>"
            for g in r["groups"])
        label = "Unreleased" if v == "Unreleased" else f"Version {v}"
        body.append(f'<section class="panelbox release" id="v-{v}" aria-labelledby="h-{v}"><div class="relhead">'
                    f'<h2 id="h-{v}">{html.escape(label)}{chip}</h2><span class="meta">{when}{note}</span></div>{groups}</section>')
    return f'<div class="cards releases">{"".join(body)}</div>'
