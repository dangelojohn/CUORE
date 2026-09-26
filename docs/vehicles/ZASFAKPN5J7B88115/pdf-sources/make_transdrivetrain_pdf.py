"""One-page Transmission and Drivetrain sheet for the 2018 Stelvio 2.0T (cuore data, 2026-09-26)."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import drivetrain_specs as D  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio Transmission and Drivetrain (1 page).pdf"

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CONFIRMED": colors.HexColor("#dcefe1"), "CORROBORATED": colors.HexColor("#e6f0f8"),
           "SINGLE-SOURCE": colors.HexColor("#fbf1e4"), "UNKNOWN": colors.HexColor("#fbeaea")}
SHORT = {"CONFIRMED": "CONFIRM.", "CORROBORATED": "CORROB.", "SINGLE-SOURCE": "SINGLE", "UNKNOWN": "UNKNOWN"}

ss = getSampleStyleSheet()
cell = ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=5.8, leading=6.7, textColor=INK)
cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
small = ParagraphStyle("s", parent=cell, fontSize=6.6, leading=7.8, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=17)
sec_style = ParagraphStyle("h", parent=cellb, fontSize=7.6, leading=9, textColor=ACCENT)


def esc(v) -> str:
    s = "" if v is None else str(v)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def short(t, n):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "..."


def conf_cell(c):
    return Paragraph(SHORT.get(c, esc(c)), cell)


# Only the non-BMW-reference, non-duplicate torque rows per section, in a sane order.
SECTION_TORQUE_KEYS = {
    "transmission": ["transmission_pan_bolts", "transmission_drain_plug", "transmission_fill_plug"],
    "transfer_case": ["transfer_case_drain_plug", "transfer_case_fill_plug"],
    "differentials": ["front_diff_drain_plug", "front_diff_fill_plug", "rear_diff_drain_plug",
                       "rear_diff_fill_plug"],
    "driveline": ["propshaft_flange_nut", "axle_hub_nut", "hub_mount_bolts"],
    "mounts": ["engine_mount_bolts", "longitudinal_mount_bolts", "trans_mount_bracket_fasteners"],
}

# Which SPECS keys (component names, via key) to surface as "fluid / capacity / interval" per section.
SECTION_SPEC_KEYS = {
    "transmission": ["fluid_identity", "owner_manual_capacity", "fill_temp_window", "interval_zf"],
    "transfer_case": ["fluid_identity", "capacity", "interval", "adj_routine"],
    "differentials": ["front_fluid_identity", "front_capacity_20t", "rear_fluid_identity_20t",
                       "rear_capacity_20t", "rear_which_unit_fitted"],
    "driveline": ["propshaft_construction", "front_flex_disc"],
    "mounts": [],
}

SECTIONS = [("transmission", "Transmission (ZF 8HP)"), ("transfer_case", "Transfer case (Magna Q4)"),
            ("differentials", "Differentials (front and rear)"), ("driveline", "Driveline"),
            ("mounts", "Mounts")]


def spec_by_key(key, section=None):
    for s in D.SPECS:
        if s["key"] == key and (section is None or s["section"] == section):
            return s
    return None


def section_block(key, label):
    data = [[Paragraph(label.upper(), sec_style), "", "", ""]]
    st = [("SPAN", (0, 0), (-1, 0)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("GRID", (0, 1), (-1, -1), 0.4, RULE), ("BACKGROUND", (0, 1), (-1, 1), SHADE),
          ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
          ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)]

    specs = [spec_by_key(k, key) for k in SECTION_SPEC_KEYS.get(key, [])]
    specs = [s for s in specs if s]
    if specs:
        data.append([Paragraph(h, cellb) for h in ("Fluid / capacity / interval", "", "", "Conf.")])
        st.append(("SPAN", (0, len(data) - 1), (2, len(data) - 1)))
        for sp in specs:
            data.append([Paragraph(f"<b>{esc(sp['component'])}:</b> {esc(short(sp['value'], 100))}", cell),
                        "", "", conf_cell(sp["confidence"])])
            r = len(data) - 1
            st.append(("SPAN", (0, r), (2, r)))
            st.append(("BACKGROUND", (3, r), (3, r), CONF_BG.get(sp["confidence"], SHADE)))

    torques = [D.torque_by_key(k) for k in SECTION_TORQUE_KEYS.get(key, [])]
    torques = [t for t in torques if t]
    if torques:
        data.append([Paragraph(h, cellb) for h in ("Fastener", "Torque", "", "Conf.")])
        r = len(data) - 1
        st.append(("SPAN", (1, r), (2, r)))
        for tq in torques:
            note = tq.get("notes") or ""
            if tq.get("single_use"):
                note = "SINGLE-USE. " + note
            data.append([Paragraph(esc(tq["component"]) + "<br/>" +
                                   f"<font color='#5b6770'>{esc(short(note, 88))}</font>", cell),
                        Paragraph("<b>" + esc(tq["display"]) + "</b>", cell), "", conf_cell(tq["confidence"])])
            r = len(data) - 1
            st.append(("SPAN", (1, r), (2, r)))
            st.append(("BACKGROUND", (3, r), (3, r), CONF_BG.get(tq["confidence"], SHADE)))

    t = Table(data, colWidths=[4.6 * inch, 1.15 * inch, 0.7 * inch, 0.85 * inch])
    t.setStyle(TableStyle(st))
    return KeepTogether([t, Spacer(1, 1.5)])


# --- transmission DTC/TSB callouts ------------------------------------------

tsb = next(t for t in D.TRANSMISSION_TSBS if t["number"] == "21-035-20")
tsb_box = Table([[Paragraph(f"<b>TSB {tsb['number']}</b> ({tsb['date']}) applies to this VIN: "
                            f"{esc(short(tsb['summary'], 320))}", cell)]], colWidths=[7.3 * inch])
tsb_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e6f0f8")),
                             ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#4a7fa8")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

tc_interval = spec_by_key("interval", "transfer_case")
due_box = Table([[Paragraph(f"<b>DUE:</b> transfer case oil, {esc(tc_interval['value'])} "
                            f"({SHORT[tc_interval['confidence']]}, owner's manual). This car is past that "
                            "mileage (about 142,290 km / 88,415 mi) -- replace unless records show it was "
                            "already done. Do not substitute ATF or generic 75W GL-5 -- friction "
                            "characteristics are matched to the Q4 clutch pack.", cell)]], colWidths=[7.3 * inch])
due_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6d5d5")),
                             ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

warn = Table([[Paragraph(
    "<b>Only CONFIRMED is manufacturer data</b> (ZF 8HP pan/filter bolts and fill window; transfer case "
    "interval, from the owner's manual). SINGLE/CORROB. = one or two non-manufacturer sources; UNKNOWN = use "
    "the FCA service manual (TechAuthority). The propshaft flange figure seen online (72-101 lb-ft) is from a "
    "1970s Alfa manual and must not be used on this car.", cell)]], colWidths=[7.3 * inch])
warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

relearn = spec_by_key("adaptation_relearn", "transmission")
relearn_note = Paragraph(f"<b>Relearn:</b> {esc(short(relearn['value'], 220))} Not required for a routine "
                         "fluid+filter change or after a TCM/TCMA re-flash alone; not lost on battery "
                         "disconnect (non-volatile EEPROM).", small)

story = [Paragraph("Transmission and Drivetrain - 2018 Stelvio 2.0T (Q4 AWD, ZF 8HP)", title),
         Paragraph("VIN ZASFAKPN5J7B88115  |  about 142,290 km / 88,415 mi  |  transmission, transfer case, "
                   "differentials, driveline, mounts  |  cuore, 2026-09-26", small),
         Spacer(1, 2), due_box, Spacer(1, 2), tsb_box, Spacer(1, 2), warn, Spacer(1, 3)]
story += [section_block(k, label) for k, label in SECTIONS]
story += [Spacer(1, 1), relearn_note]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.3 * inch, "Calibrated torque wrench; angle steps after torque; replace single-use "
                 "fasteners. cuore: /v/ZASFAKPN5J7B88115/drivetrain")
    c.drawRightString(8.0 * inch, 0.3 * inch, f"Page {doc.page}")
    c.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                        topMargin=0.4 * inch, bottomMargin=0.45 * inch, title="Stelvio Transmission and Drivetrain")
doc.build(story, onFirstPage=foot, onLaterPages=foot)
print(OUT)
