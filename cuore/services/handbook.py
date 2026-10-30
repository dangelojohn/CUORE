"""Mechanic handbook for /handbook: docs/handbook/*.md rendered to safe HTML. Pure, read only.

No raw HTML ever passes through: every text is HTML-escaped first, then a small set of markdown
shapes (headings, paragraphs, lists, code blocks, tables, links, bold, italic) is turned into tags.
Slugs come only from the file names found in the handbook folder (no path from the request is used).
"""
from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Any


def handbook_dir() -> Path | None:
    env = os.environ.get("CUORE_HANDBOOK_DIR")
    here = Path(__file__).resolve()
    for d in ([Path(env)] if env else [here.parents[2] / "docs" / "handbook", here.parents[1] / "docs" / "handbook"]):
        if d.is_dir():
            return d
    return None


def slugs() -> dict[str, Path]:
    d = handbook_dir()
    return {f.stem: f for f in sorted(d.glob("*.md"))} if d else {}


def _plain(s: str) -> str:
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return re.sub(r"[`*_]+", "", s).strip()


def heading_id(text: str, seen: dict[str, int]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _plain(text).lower()).strip("-") or "section"
    n = seen.get(base, 0)
    seen[base] = n + 1
    return base if n == 0 else f"{base}-{n + 1}"


_HEAD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LIST = re.compile(r"^\s*([-*+]|\d+[.)])\s+(.*)$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def headings(md: str) -> list[dict[str, Any]]:
    """Headings outside code fences, with the same ids the page uses."""
    out, seen, fence = [], {}, False
    for ln in _COMMENT.sub("", md).splitlines():
        if _FENCE.match(ln):
            fence = not fence
            continue
        m = None if fence else _HEAD.match(ln)
        if m:
            t = _plain(m.group(2))
            out.append({"level": len(m.group(1)), "text": t, "id": heading_id(t, seen)})
    return out


def _safe_href(u: str) -> bool:
    u = u.strip()
    return bool(re.match(r"^(https?://|mailto:|/|#)", u, re.I)) or not re.match(r"^[a-z][a-z0-9+.-]*:", u, re.I)


def _inline(raw: str) -> str:
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append("<code>" + html.escape(m.group(1)) + "</code>")
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, raw)
    s = html.escape(s, quote=True)

    def link(m: re.Match) -> str:
        label, url = m.group(1), html.unescape(m.group(2)).strip()
        if not _safe_href(url):
            return label
        ext = ' rel="noopener noreferrer"' if re.match(r"^https?://", url, re.I) else ""
        return f'<a href="{html.escape(url, quote=True)}"{ext}>{label}</a>'

    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


def _cells(ln: str) -> list[str]:
    return [c.strip() for c in ln.strip().strip("|").split("|")]


_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def render(md: str) -> str:
    lines = _COMMENT.sub("", md).splitlines()  # generated-block markers never show as text
    out: list[str] = []
    seen: dict[str, int] = {}
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if _FENCE.match(ln):
            i += 1
            buf = []
            while i < n and not _FENCE.match(lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue
        m = _HEAD.match(ln)
        if m:
            lv = min(len(m.group(1)) + 1, 6)  # the page title is the h1
            t = _plain(m.group(2))
            if len(m.group(1)) == 1 and not out:  # the page template already shows the title
                heading_id(t, seen)
                i += 1
                continue
            out.append(f'<h{lv} id="{heading_id(t, seen)}">{_inline(m.group(2))}</h{lv}>')
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", ln):
            out.append("<hr>")
            i += 1
            continue
        if "|" in ln and i + 1 < n and _SEP.match(lines[i + 1]):
            head = _cells(ln)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            t = '<div class="tbl"><table><thead><tr>' + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            for r in rows:
                t += "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table></div>")
            continue
        lm = _LIST.match(ln)
        if lm:
            tag = "ol" if lm.group(1)[0].isdigit() else "ul"
            items: list[str] = []
            while i < n:
                mm = _LIST.match(lines[i])
                if mm:
                    items.append(mm.group(2))
                    i += 1
                elif lines[i].strip() and lines[i].startswith((" ", "\t")) and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if ln.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append("<blockquote><p>" + _inline(" ".join(buf)) + "</p></blockquote>")
            continue
        buf = []
        while i < n and lines[i].strip() and not _HEAD.match(lines[i]) and not _FENCE.match(lines[i]) \
                and not _LIST.match(lines[i]) and not lines[i].lstrip().startswith(">"):
            buf.append(lines[i].strip())
            i += 1
        if not buf:
            buf = [ln.strip()]
            i += 1
        out.append("<p>" + _inline(" ".join(buf)) + "</p>")
    return "\n".join(out)


def _summary(md: str) -> str:
    para: list[str] = []
    fence = False
    for ln in _COMMENT.sub("", md).splitlines():
        if _FENCE.match(ln):
            fence = not fence
            continue
        s = ln.strip()
        if fence or not s or _HEAD.match(ln) or s.startswith(("|", ">", "---")) or _LIST.match(ln):
            if para:
                break
            continue
        para.append(s)
    t = _plain(" ".join(para))
    return t if len(t) <= 200 else t[:197].rsplit(" ", 1)[0] + "..."


def _title(md: str, slug: str) -> str:
    return next((h["text"] for h in headings(md) if h["level"] == 1), slug)


def guides() -> list[dict[str, Any]]:
    out = []
    for slug, f in slugs().items():
        try:
            md = f.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append({"slug": slug, "title": _title(md, slug), "summary": _summary(md), "file": f.name})
    return out


def guide(slug: str) -> dict[str, Any] | None:
    f = slugs().get(slug)  # lookup among known names only: a request path never reaches the file system
    if f is None:
        return None
    md = f.read_text(encoding="utf-8")
    return {"slug": slug, "title": _title(md, slug), "toc": [h for h in headings(md) if h["level"] in (2, 3)],
            "body": render(md), "file": f.name}
