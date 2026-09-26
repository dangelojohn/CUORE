"""One-page torque sheet for the 2018 Stelvio 2.0T from cuore's spec tables (draft)."""
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import drivetrain_specs, service_specs  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio Torque Settings (1 page).pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CONFIRMED": colors.HexColor("#dcefe1"), "CORROBORATED": colors.HexColor("#e6f0f8"),
           "SINGLE-SOURCE": colors.HexColor("#fbf1e4"), "UNKNOWN": colors.HexColor("#fbeaea")}

ss = getSampleStyleSheet()
cell = ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=5.9, leading=6.6, textColor=INK)
cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
small = ParagraphStyle("s", parent=cell, fontSize=7.2, leading=9, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=16, textColor=INK)


def clean(v) -> str:
    s = "" if v is None else str(v)
    return (s.replace("\ufffd", "").replace("N·m", "Nm").replace("N\u00b7m", "Nm")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def src_short(src: str) -> str:
    s = str(src or "")
    if s.startswith("http"):
        return urlparse(s).netloc.replace("www.", "")
    return s.split("#")[0].split("/")[-1][:28]


rows = []
for r in service_specs.TORQUES:
    r = r if isinstance(r, dict) else r.__dict__
    cats = r.get("categories") or ()
    section = ", ".join(cats) if isinstance(cats, (list, tuple)) else str(cats)
    val = r.get("display") or f"{r.get('value', '')} {r.get('unit', '')}".strip()
    if r.get("value_lbft"):
        val += f" ({r['value_lbft']} lb-ft)"
    note = r.get("notes") or ""
    if r.get("angle"):
        note = f"+ {r['angle']}. " + note
    if r.get("single_use"):
        note = "SINGLE-USE bolt. " + note
    rows.append((section.replace("_", " "), r.get("component", ""), val, note, r.get("confidence", ""),
                 src_short(r.get("source"))))
for r in drivetrain_specs.TORQUES:
    r = r if isinstance(r, dict) else r.__dict__
    val = f"{r.get('value', '')} {clean(r.get('unit', ''))}".strip()
    note = r.get("notes") or ""
    if r.get("single_use"):
        note = "SINGLE-USE bolt. " + note
    rows.append((str(r.get("section", "")).replace("_", " "), r.get("component", ""), val, note,
                 r.get("confidence", ""), src_short(r.get("source"))))

order = {"oil change": 0, "wheels": 1, "brakes": 2}
rows.sort(key=lambda x: (order.get(x[0].split(",")[0], 5), x[0], x[1]))


def short(note: str, n: int = 58) -> str:
    note = " ".join(str(note).split())
    return note if len(note) <= n else note[:n - 1].rsplit(" ", 1)[0] + "..."


def half(part):
    d = [[Paragraph(h, cellb) for h in ("Fastener", "Torque", "Conf.", "Note")]]
    st = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("BACKGROUND", (0, 0), (-1, 0), SHADE),
          ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
          ("TOPPADDING", (0, 0), (-1, -1), 0.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8)]
    last = None
    for sec, comp, val, note, conf, src in part:
        if sec != last:
            d.append([Paragraph("<b>" + clean(sec.upper()) + "</b>", cell), "", "", ""])
            st.append(("SPAN", (0, len(d) - 1), (-1, len(d) - 1)))
            st.append(("BACKGROUND", (0, len(d) - 1), (-1, len(d) - 1), SHADE))
            last = sec
        d.append([Paragraph(clean(comp), cell), Paragraph("<b>" + clean(val) + "</b>", cell),
                  Paragraph(clean({"SINGLE-SOURCE": "SINGLE", "CORROBORATED": "CORROB."}.get(conf, conf)), cell),
                  Paragraph(clean(short(note)), cell)])
        if conf in CONF_BG:
            st.append(("BACKGROUND", (2, len(d) - 1), (2, len(d) - 1), CONF_BG[conf]))
    t = Table(d, colWidths=[1.45 * inch, 0.95 * inch, 0.55 * inch, 2.12 * inch], repeatRows=1)
    t.setStyle(TableStyle(st))
    return t


def _h(part):
    return half(part).wrap(5.12 * inch, 5000)[1]


# pick the split that makes the taller column as short as possible
mid = min(range(1, len(rows)), key=lambda m: max(_h(rows[:m]), _h(rows[m:])))
# keep a section together across the split where possible
tbl = Table([[half(rows[:mid]), half(rows[mid:])]], colWidths=[5.12 * inch, 5.12 * inch])
tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                         ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))

warn = Table([[Paragraph(
    "<b>DRAFT - not yet independently fact-checked.</b> Values come from cuore's spec tables "
    "(owner's manual, ZF literature, forums and parts sources). Use the confidence column: only "
    "CONFIRMED is manufacturer data. UNKNOWN means use the FCA service manual (TechAuthority). "
    "Replace single-use bolts. Full sources: cuore torque page and docs/reference/*_SPECS.md.", cell)]],
    colWidths=[10.2 * inch])
warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN), ("LINEBEFORE", (0, 0), (0, -1), 3,
                                                                      colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [Paragraph("Torque Settings - 2018 Alfa Romeo Stelvio 2.0T (GU, EC2, Q4, ZF 8HP)", title),
         Paragraph(f"VIN ZASFAKPN5J7B88115  |  {len(rows)} fasteners  |  generated 2026-09-26 from cuore",
                   small),
         Spacer(1, 3), warn, Spacer(1, 4), tbl]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.4 * inch, 0.3 * inch, "Always use a calibrated torque wrench; angle steps after the torque "
                 "value where listed. cuore / VIN ZASFAKPN5J7B88115")
    c.drawRightString(10.6 * inch, 0.3 * inch, f"Page {doc.page}")
    c.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=landscape(letter), leftMargin=0.4 * inch, rightMargin=0.4 * inch,
                        topMargin=0.35 * inch, bottomMargin=0.45 * inch, title="Stelvio Torque Settings")
doc.build(story, onFirstPage=foot, onLaterPages=foot)
print(OUT, len(rows))
