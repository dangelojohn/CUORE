"""Reportlab builders for the printable PDFs.

Same house style as ``docs/vehicles/ZASFAKPN5J7B88115/pdf-sources/
make_dossier_pdf.py``: Helvetica, plain sentences, no em dashes, status
colours red/amber/green/grey, a muted footer with page numbers. Everything
drawn here comes from ``report_routes``'s context dicts, which are
themselves built from ``dossier_bridge.build_view`` and friends -- this
module lays type out, it does not decide what the car's history says.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

INK = colors.HexColor("#1b2227")
MUTED = colors.HexColor("#5b6770")
ACCENT = colors.HexColor("#9e1b21")
RULE = colors.HexColor("#c9d1d6")
SHADE = colors.HexColor("#f1f4f6")
RED = colors.HexColor("#f4dedf")
AMBER = colors.HexColor("#f5e8cd")
GREEN = colors.HexColor("#dcefe1")
GREY = colors.HexColor("#e2e6e9")

_SS = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_SS["Normal"], fontName="Helvetica",
                      fontSize=8.3, leading=10.4, textColor=INK)
BOLD = ParagraphStyle("bold", parent=BODY, fontName="Helvetica-Bold")
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=16,
                    leading=19, textColor=INK, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=10.5,
                    leading=13, textColor=ACCENT, spaceBefore=8, spaceAfter=3)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.3, leading=9,
                       textColor=MUTED)
BIG = ParagraphStyle("big", parent=BODY, fontName="Helvetica-Bold", fontSize=11,
                     leading=13.5)

_PAGESIZES = {"letter": LETTER, "a4": A4}

_VERDICT_BG = {"ACTIVE_FAULTS": RED, "UNVERIFIED_REPAIR": AMBER,
              "VERIFIED_CLEAN": GREEN, "NO_DATA": GREY}
_STATUS_BG = {"ACTIVE": RED, "CLEARED_UNVERIFIED": AMBER, "STALE": GREY}

GRID = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), SHADE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]


def P(text: Any, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(esc(text), style)


def esc(value: Any) -> str:
    return str(value if value is not None else "").replace("&", "&amp;") \
        .replace("<", "&lt;").replace(">", "&gt;")


def table(rows: list[list[Any]], widths: list[float],
         extra: list[tuple] = ()) -> Table:
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle(GRID + list(extra)))
    return t


def _pagesize(size: str):
    return _PAGESIZES.get((size or "letter").strip().lower(), LETTER)


# --- page scaffolding: repeated header + footer with page numbers ---------


def _make_doc(out_name: str, size: str, header_text: str) -> tuple[BaseDocTemplate, list]:
    pagesize = _pagesize(size)
    margin = 0.55 * inch
    width, height = pagesize

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(INK)
        canvas.drawString(margin, height - 0.38 * inch, header_text)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(width - margin, height - 0.38 * inch,
                               "CUORE report -- clearing is not fixing")
        canvas.setLineWidth(0.4)
        canvas.setStrokeColor(RULE)
        canvas.line(margin, height - 0.44 * inch, width - margin, height - 0.44 * inch)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(width / 2, 0.32 * inch, f"Page {doc.page}")
        canvas.restoreState()

    frame = Frame(margin, margin, width - 2 * margin, height - 2 * margin - 0.22 * inch,
                  id="main", topPadding=0.3 * inch)
    doc = BaseDocTemplate(out_name, pagesize=pagesize,
                          leftMargin=margin, rightMargin=margin,
                          topMargin=margin, bottomMargin=margin,
                          title=header_text)
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame], onPage=on_page)])
    return doc, []


def _stamp_line(stamp: dict[str, Any]) -> Paragraph:
    return P(f"As of {stamp.get('generated')}, data through {stamp.get('data_through')}.",
            SMALL)


def _verdict_block(verdict: dict[str, Any]) -> Table:
    bg = _VERDICT_BG.get(verdict.get("state"), GREY)
    rows = [[P(verdict.get("label", ""), BIG), P(verdict.get("summary", ""), BODY)]]
    if verdict.get("basis"):
        rows.append([P("Basis", BOLD), P("; ".join(verdict["basis"]), SMALL)])
    if verdict.get("cleared_at"):
        rows.append([P("Cleared", BOLD),
                    P(f"{verdict['cleared_at']}"
                      f"{' by ' + verdict['cleared_by'] if verdict.get('cleared_by') else ''}", SMALL)])
    t = Table(rows, colWidths=[1.1 * inch, 5.6 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBEFORE", (0, 0), (0, -1), 4, ACCENT),
    ]))
    return t


def _open_work_block(open_work: list[dict[str, Any]]) -> list:
    out = []
    for card in open_work:
        prog = card.get("progress") or {}
        rows = [[P(f"{card.get('title', '')}  ({' '.join(card.get('codes', []))})"
                  f"  -- {prog.get('done', 0)}/{prog.get('total', 0)} done", BOLD), ""]]
        for i, step in enumerate(card.get("steps", []), start=1):
            mark = "[x]" if step.get("done") else "[ ]"
            who = f" ({step['done_by']}, {step['done_at']})" if step.get("done") and step.get("done_by") else ""
            rows.append([P(f"{mark} {i}. {step.get('text', '')}{who}"),
                        P(step.get("ref") or "", SMALL)])
        t = table(rows, [4.7 * inch, 1.3 * inch],
                 [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), SHADE)])
        out.append(t)
        out.append(Spacer(1, 3))
    return out


def _codes_table(codes: list[dict[str, Any]]) -> Table:
    rows = [[P(x, BOLD) for x in ("Code", "Description", "System", "Status", "xN",
                                  "Last seen", "km")]]
    extra = []
    for c in codes:
        rows.append([P(c["code"], BOLD), P((c.get("description") or "")[:70], BODY),
                    P(c.get("system") or ""), P(c.get("status_label") or ""),
                    P(str(c.get("sessions") or "")), P(c.get("last_seen_short") or ""),
                    P(f"{c['distance_km']:,}" if c.get("distance_km") is not None else "-")])
        extra.append(("BACKGROUND", (3, len(rows) - 1), (3, len(rows) - 1),
                     _STATUS_BG.get(c.get("status"), GREY)))
    return table(rows, [0.6 * inch, 2.55 * inch, 0.6 * inch, 1.15 * inch, 0.35 * inch,
                       0.7 * inch, 0.55 * inch], extra)


def _pattern_line(pattern: dict[str, Any]) -> str:
    if not pattern:
        return ""
    near = pattern.get("symptom_reports_near", 0)
    if not near:
        return "no symptom reports near these occurrences yet"
    tags = {t: c for t, c in (pattern.get("by_tag") or {}).items()
           if t != "drives_normally" and c > 0}
    if not tags:
        return f"{near} symptom report(s) nearby, none tagged beyond normal driving"
    top = sorted(tags, key=lambda t: (-tags[t], t))[:3]
    return f"{near} symptom report(s) nearby, co-occurs with " + ", ".join(top)


def _feels_block(feels: list[dict[str, Any]], correlation: list[str]) -> list:
    out = []
    for f in feels:
        feel = f.get("feel") or {}
        pattern = f.get("pattern") or {}
        text = feel.get("feel") or "No description on file for this code."
        conf = feel.get("confidence")
        label = f"{esc(f.get('code'))} ({esc(f.get('family_title') or f.get('family') or '')})"
        out.append(Paragraph(f"<b>{label}</b>: {esc(text)}"
                             f"{' [confidence: ' + esc(conf) + ']' if conf else ''}", BODY))
        pline = _pattern_line(pattern)
        if pline:
            out.append(P(f"This car's own data: {pline}", SMALL))
        out.append(Spacer(1, 2))
    if correlation:
        out.append(P("Symptom correlation", BOLD))
        for line in correlation:
            out.append(P(f"- {line}", SMALL))
    return out or [P("No open-work codes to describe.", SMALL)]


def _freeze_frames_block(frames: list[dict[str, Any]]) -> list:
    out = []
    for ff in frames:
        rows = [[P("PID", BOLD), P("Value", BOLD)]]
        extra = []
        for p in ff.get("key", []):
            rows.append([P(p.get("name", "")), P(str(p.get("value", "")))])
            if p.get("flag"):
                extra.append(("BACKGROUND", (1, len(rows) - 1), (1, len(rows) - 1), AMBER))
        label = ff.get("code", "")
        if ff.get("set_km_ago") is not None:
            label += f" -- set {ff['set_km_ago']} km ago"
        out.append(P(label, BOLD))
        out.append(table(rows, [2.2 * inch, 3.2 * inch], extra))
        out.append(Spacer(1, 3))
    return out or [P("No freeze frames captured.", SMALL)]


def _attempted_table(attempted: list[dict[str, Any]]) -> Table:
    rows = [[P(x, BOLD) for x in ("Operation", "Outcome", "xN", "First", "Last")]]
    extra = []
    for a in attempted:
        rows.append([P(a.get("operation") or ""), P((a.get("outcome") or "").title()),
                    P(str(a.get("count") or "")), P(a.get("first_short") or ""),
                    P(a.get("last_short") or "")])
        if a.get("outcome") and "FAIL" in a["outcome"].upper():
            extra.append(("BACKGROUND", (1, len(rows) - 1), (1, len(rows) - 1), AMBER))
    return table(rows, [1.9 * inch, 1.3 * inch, 0.4 * inch, 0.8 * inch, 0.8 * inch], extra)


def _bulletins_table(bulletins: list[dict[str, Any]]) -> Table:
    rows = [[P(x, BOLD) for x in ("Bulletin", "What it says", "Codes", "Confidence")]]
    extra = []
    for b in bulletins:
        conf = "confirmed" if b.get("verified") else "unverified"
        rows.append([P(b.get("id") or ""), P(b.get("title") or ""),
                    P(" ".join(b.get("codes") or [])), P(conf)])
        if not b.get("verified"):
            extra.append(("BACKGROUND", (3, len(rows) - 1), (3, len(rows) - 1), AMBER))
    return table(rows, [0.9 * inch, 3.0 * inch, 0.9 * inch, 0.9 * inch], extra)


def _blind_spots_table(blind_spots: list[dict[str, Any]]) -> Table:
    rows = [[P(x, BOLD) for x in ("Question", "What answers it")]]
    for b in blind_spots:
        rows.append([P(b.get("question") or ""), P(b.get("action") or b.get("why") or "")])
    return table(rows, [2.5 * inch, 3.0 * inch])


def _fixes_block(open_work: list[dict[str, Any]], bulletins: list[dict[str, Any]]) -> list:
    """Possible fixes: exactly the family checklist steps and bulletin
    actions the dossier already carries. Never a new recommendation."""
    out = []
    for card in open_work:
        out.append(P(card.get("title", ""), BOLD))
        for step in card.get("steps", []):
            src = step.get("ref") or "procedure"
            out.append(P(f"- {step.get('text', '')} (source: {src}, status: "
                         f"{'done' if step.get('done') else 'open'})", SMALL))
    for b in bulletins:
        if b.get("action"):
            conf = "confirmed" if b.get("verified") else "unverified"
            out.append(P(f"- {b['id']}: {b['action']} (source: bulletin, confidence: {conf})", SMALL))
    return out or [P("No sourced fix steps for this vehicle's open codes.", SMALL)]


def _parts_table(parts: list[dict[str, Any]]) -> list:
    out = []
    for group in parts:
        rows = [[P(x, BOLD) for x in ("Part", "OEM #", "Confidence", "Source")]]
        for p in group.get("parts", []):
            oem = ", ".join(o.get("number", "") for o in (p.get("oem") or []) if o.get("number")) or "-"
            conf = "OEM confirmed" if p.get("oem") else (
                "aftermarket only" if p.get("aftermarket") else "unconfirmed")
            source = ", ".join((x.get("label") or x.get("url") or "") if isinstance(x, dict) else str(x)
                               for x in (p.get("buy") or [])) or "-"
            rows.append([P(p.get("name") or ""), P(oem), P(conf), P(source, SMALL)])
        out.append(P(group.get("code", ""), BOLD))
        out.append(table(rows, [1.7 * inch, 1.3 * inch, 1.1 * inch, 1.8 * inch]))
        out.append(Spacer(1, 3))
    return out or [P("No parts data on file for these codes.", SMALL)]


def _experience_block(experience: list[dict[str, Any]]) -> list:
    out = []
    for group in experience:
        out.append(P(group.get("label") or group.get("family") or group.get("code") or "", BOLD))
        for link in group.get("links", []):
            out.append(P(f"- {link.get('title') or link.get('url') or ''}: "
                         f"{link.get('url', '')}", SMALL))
    return out or [P("No experience links matched this vehicle's open codes.", SMALL)]


def _legend() -> Table:
    rows = [[P("Colour", BOLD), P("Meaning", BOLD)],
           [P("Red"), P("Active -- current evidence, not resolved")],
           [P("Amber"), P("Cleared but unverified, or a bulletin action not yet confirmed")],
           [P("Green"), P("Verified clean on a live read")],
           [P("Grey"), P("Stale -- no data, or not seen recently")]]
    extra = [("BACKGROUND", (0, 1), (0, 1), RED), ("BACKGROUND", (0, 2), (0, 2), AMBER),
            ("BACKGROUND", (0, 3), (0, 3), GREEN), ("BACKGROUND", (0, 4), (0, 4), GREY)]
    return table(rows, [1.0 * inch, 4.9 * inch], extra)


# --- vehicle report ----------------------------------------------------------


def build_vehicle_pdf(ctx: dict[str, Any], size: str = "letter") -> bytes:
    import io
    bar, view, stamp = ctx["bar"], ctx["view"], ctx["stamp"]
    header = f"{bar.get('name', '')} -- VIN {ctx['vin']}"
    buf = io.BytesIO()
    doc, _ = _make_doc(buf, size, header)
    odo_text = f"{int(bar['odo_last']):,} km" if bar.get("odo_last") is not None else "no odometer on file"

    story: list[Any] = [
        P(f"{bar.get('name', '')}", H1),
        P(f"VIN {ctx['vin']}  |  {odo_text}", BODY),
        _stamp_line(stamp), Spacer(1, 6),
        P("Verdict", H2), _verdict_block(view["verdict"]), Spacer(1, 6),
        P("Open work", H2), *_open_work_block(view["open_work"]),
        P("Codes", H2), _codes_table(view["codes"]), Spacer(1, 6),
        P("What the driver would feel", H2),
        *_feels_block(ctx.get("feels", []), ctx.get("correlation_findings", [])),
        Spacer(1, 4),
        P("Freeze frames", H2), *_freeze_frames_block(view["freeze_frames"]),
        P("Already attempted", H2), _attempted_table(view["attempted"]) if view["attempted"]
            else P("Nothing on record.", SMALL),
        Spacer(1, 6),
        P("Bulletins", H2), _bulletins_table(view["bulletins"]) if view["bulletins"]
            else P("No bulletins matched.", SMALL),
        Spacer(1, 6),
        P("Blind spots", H2), _blind_spots_table(view["blind_spots"]) if view["blind_spots"]
            else P("No open questions on record.", SMALL),
        Spacer(1, 6),
        P("Possible fixes", H2), *_fixes_block(view["open_work"], view["bulletins"]),
        Spacer(1, 4),
        P("Parts for the open codes", H2), *_parts_table(ctx.get("parts", [])),
        P("Others' experience", H2), *_experience_block(ctx.get("experience", [])),
        P("Mechanic notes", H2),
        *([P(f"- {n.get('text', '')} ({n.get('created_at', '')})", SMALL)
          for n in ctx.get("notes", [])] or [P("No notes on file.", SMALL)]),
    ]
    photos = ctx.get("photos", [])
    if photos:
        story += [P("Photos", H2)]
        for ph in photos[:6]:
            story.append(P(f"- {ph.get('caption') or ph.get('filename') or ''} "
                          f"({ph.get('captured_at', '')})", SMALL))
    story += [P("Sources and confidence legend", H2), _legend()]

    doc.build(story)
    return buf.getvalue()


# --- single-code report ------------------------------------------------------


def build_code_pdf(ctx: dict[str, Any], size: str = "letter") -> bytes:
    import io
    bar, code = ctx["bar"], ctx["code"]
    header = f"{bar.get('name', '')} -- {code} -- VIN {ctx['vin']}"
    buf = io.BytesIO()
    doc, _ = _make_doc(buf, size, header)
    row = ctx.get("row") or {}
    feel = ctx.get("feel") or {}

    story: list[Any] = [
        P(f"{code}", H1), P(row.get("description") or "", BODY),
        _stamp_line(ctx["stamp"]), Spacer(1, 6),
        P("Status / history", H2),
        P(f"Status: {row.get('status_label', 'unknown')}  |  seen {row.get('sessions', 0)} "
          f"session(s)  |  last seen {row.get('last_seen_short', '-')}  |  "
          f"{row.get('distance_km', '-')} km span", BODY),
        Spacer(1, 4),
        P("What you would feel", H2),
        P(((feel.get("feel") or {}).get("feel") or "No description on file for this code.")
         + ((" [confidence: " + str((feel.get("feel") or {}).get("confidence")) + "]")
            if (feel.get("feel") or {}).get("confidence") else ""), BODY),
        P(f"This car's own data: {_pattern_line(feel.get('pattern') or {})}", SMALL)
        if feel.get("pattern") else P("", SMALL),
        Spacer(1, 4),
        P("Freeze frame", H2), *_freeze_frames_block(ctx.get("frames", [])),
        P("Bulletins", H2), _bulletins_table(ctx.get("bulletins", [])) if ctx.get("bulletins")
            else P("No bulletins matched.", SMALL),
        Spacer(1, 6),
        P("Fixes", H2),
        *_fixes_block([ctx["card"]] if ctx.get("card") else [], ctx.get("bulletins", [])),
        Spacer(1, 4),
        P("Parts", H2), *_parts_table([{"code": code, "parts": ctx.get("parts", [])}]),
        P("Experience links", H2),
        *([P(f"- {l.get('title') or l.get('url') or ''}: {l.get('url', '')}", SMALL)
          for l in ctx.get("experience", [])] or [P("No experience links matched.", SMALL)]),
        P("Notes", H2),
        *([P(f"- {n.get('text', '')} ({n.get('created_at', '')})", SMALL)
          for n in ctx.get("notes", [])] or [P("No notes on file.", SMALL)]),
    ]
    doc.build(story)
    return buf.getvalue()


__all__ = ["build_vehicle_pdf", "build_code_pdf"]
