"""One-page drivetrain torque and fluid sheet for the 2018 Stelvio 2.0T (from cuore data)."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import drivetrain_specs as D  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio Drivetrain Torque Settings (1 page).pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CONFIRMED": colors.HexColor("#dcefe1"), "CORROBORATED": colors.HexColor("#e6f0f8"),
           "SINGLE-SOURCE": colors.HexColor("#fbf1e4"), "UNKNOWN": colors.HexColor("#fbeaea")}
SHORT = {"SINGLE-SOURCE": "SINGLE", "CORROBORATED": "CORROB.", "CONFIRMED": "CONFIRM."}

ss = getSampleStyleSheet()
cell = ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=6.2, leading=7.1, textColor=INK)
cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
small = ParagraphStyle("s", parent=cell, fontSize=7, leading=8.6, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=13, leading=15)
sec_style = ParagraphStyle("h", parent=cellb, fontSize=8.2, leading=10, textColor=ACCENT)

SECTIONS = [("transmission", "Transmission (ZF 8HP)"), ("transfer_case", "Transfer case (Q4)"),
            ("differentials", "Differentials (front and rear)"), ("driveline", "Driveline"),
            ("mounts", "Mounts")]


def esc(v) -> str:
    s = "" if v is None else str(v)
    return (s.replace("\ufffd", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def short(t, n):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "..."


def row_dict(r):
    return r if isinstance(r, dict) else r.__dict__


def torque_val(r):
    if r.get("display"):
        v = r["display"]
    else:
        v = f"{r.get('value', '')} {r.get('unit', '')}".strip()
    if r.get("value_lbft") and "lb" not in v:
        v += f" ({r['value_lbft']} lb-ft)"
    if r.get("angle") and "+" not in v:
        v += f" + {r['angle']}"
    return v


def is_fluid(spec):
    name = str(spec.get("component", "")).lower()
    if "reference only" in name or "2.9" in name:
        return False
    return any(k in name for k in ("fluid", "capacity", "temperature window", "service interval"))


def section_block(key, label):
    torques = [row_dict(r) for r in D.TORQUES if row_dict(r).get("section") == key]
    specs = [row_dict(r) for r in D.SPECS if row_dict(r).get("section") == key and is_fluid(row_dict(r))]
    data = [[Paragraph(label.upper(), sec_style), "", "", ""],
            [Paragraph(h, cellb) for h in ("Fastener", "Torque", "Conf.", "Note")]]
    st = [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 1), (-1, 1), SHADE),
          ("GRID", (0, 1), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
          ("TOPPADDING", (0, 0), (-1, -1), 0.9), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9)]
    for r in torques:
        note = r.get("notes") or ""
        if r.get("single_use"):
            note = "SINGLE-USE. " + note
        if r.get("platform_note"):
            note = f"[{r['platform_note']}] " + note
        data.append([Paragraph(esc(r.get("component")), cell), Paragraph("<b>" + esc(torque_val(r)) + "</b>", cell),
                     Paragraph(esc(SHORT.get(r.get("confidence"), r.get("confidence"))), cell),
                     Paragraph(esc(short(note, 70)), cell)])
        if r.get("confidence") in CONF_BG:
            st.append(("BACKGROUND", (2, len(data) - 1), (2, len(data) - 1), CONF_BG[r["confidence"]]))
    if specs:
        data.append([Paragraph("<b>Fluid / capacity / interval</b>", cell), "", "", ""])
        st += [("SPAN", (0, len(data) - 1), (-1, len(data) - 1)),
               ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), SHADE)]
        for sp in specs:
            data.append([Paragraph(esc(sp.get("component")), cell),
                         Paragraph(esc(short(f"{sp.get('value', '')} {sp.get('unit', '')}", 90)), cell),
                         Paragraph(esc(SHORT.get(sp.get("confidence"), sp.get("confidence"))), cell),
                         Paragraph(esc(short(sp.get("notes"), 40)), cell)])
            st.append(("SPAN", (1, len(data) - 1), (1, len(data) - 1)))
            if sp.get("confidence") in CONF_BG:
                st.append(("BACKGROUND", (2, len(data) - 1), (2, len(data) - 1), CONF_BG[sp["confidence"]]))
    t = Table(data, colWidths=[1.85 * inch, 1.9 * inch, 0.55 * inch, 3.2 * inch])
    t.setStyle(TableStyle(st))
    return KeepTogether([t, Spacer(1, 3)])


warn = Table([[Paragraph(
    "<b>Only CONFIRMED is manufacturer data</b> (here: ZF 8HP pan/filter bolts and fill window, from ZF/FCA text). "
    "SINGLE = one forum/aggregator source; UNKNOWN = use the FCA service manual (TechAuthority). "
    "Rows marked [BMW G30...] are the same ZF 8HP in a BMW, for reference only. Fact-checked 2026-09-26: the "
    "propshaft flange figure seen online (72-101 lb-ft) is from a 1970s Alfa manual and must not be used.", cell)]],
    colWidths=[7.5 * inch])
warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [Paragraph("Drivetrain Torque Settings - 2018 Stelvio 2.0T (Q4 AWD, ZF 8HP)", title),
         Paragraph("VIN ZASFAKPN5J7B88115  |  transmission, transfer case, differentials, driveline, mounts  |  "
                   "from cuore, 2026-09-26", small), Spacer(1, 3), warn, Spacer(1, 4)]
story += [section_block(k, label) for k, label in SECTIONS]
story += [Paragraph("Also relevant: TSB 21-035-20 (TCM flash, shift quality) applies to this VIN. After a "
                    "transmission fluid service run the adaptation relearn; fill/level check only in the "
                    "30-50 C fluid window.", small)]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.3 * inch, "Calibrated torque wrench; angle steps after torque; replace single-use "
                 "fasteners. Full sources: docs/reference/STELVIO_20T_DRIVETRAIN_SPECS.md")
    c.drawRightString(8.0 * inch, 0.3 * inch, f"Page {doc.page}")
    c.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                        topMargin=0.4 * inch, bottomMargin=0.45 * inch, title="Stelvio Drivetrain Torque Settings")
doc.build(story, onFirstPage=foot, onLaterPages=foot)
print(OUT)
