"""One-page Routine Maintenance sheet for the 2018 Stelvio 2.0T, built from mes.maintenance_specs."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import maintenance_specs as M  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

OUT = r"C:\Users\User\Desktop\Stelvio Routine Maintenance (1 page).pdf"
ODO_KM = 142290
ODO_MI = round(ODO_KM / 1.60934)

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CONFIRMED": colors.HexColor("#dcefe1"), "CORROBORATED": colors.HexColor("#e6f0f8"),
           "SINGLE-SOURCE": colors.HexColor("#fbf1e4"), "UNKNOWN": colors.HexColor("#fbeaea")}
STATUS_BG = {"OVERDUE": colors.HexColor("#f6d5d5"), "DUE SOON": colors.HexColor("#fbe7c6"),
             "CHECK": colors.HexColor("#eef1f4"), "OK": colors.HexColor("#dcefe1")}
SHORT = {"CONFIRMED": "CONFIRM.", "CORROBORATED": "CORROB.", "SINGLE-SOURCE": "SINGLE", "UNKNOWN": "UNKNOWN"}

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=6.8, leading=8.2, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
sm = ParagraphStyle("sm", parent=b, fontSize=6.6, leading=8.2, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


def esc(v):
    return ("" if v is None else str(v)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def short(t, n):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "..."


# Where the car stands on the owner's-manual schedule at ~88,400 mi, with no records in cuore.
# (status, text). Derived only from the intervals above; "unless done" because history is unknown.
SCHEDULE = {
    "engine_air_filter": ("DUE SOON", f"Next mark 90,000 mi: about {90000 - ODO_MI:,} mi away."),
    "cabin_air_filter": ("CHECK", "Every 20k mi / 2 yr: 80k mark passed; replace unless done in the last 2 years."),
    "spark_plugs": ("DUE SOON", f"Next mark 90,000 mi: about {90000 - ODO_MI:,} mi away. Mileage only."),
    "ignition_coils_inspect": ("CHECK", "No schedule: inspect when plugs are out."),
    "coolant": ("OK", "First change at 150,000 mi / 15 yr."),
    "brake_fluid": ("CHECK", "Every 2 years regardless of mileage: overdue unless changed since 2024-09."),
    "drive_belt": ("OVERDUE", "36k mi / 4 yr: due at 36k and 72k mi (or years 4 and 8). Overdue unless replaced."),
    "battery_12v": ("CHECK", "Test charge state every year / 10k mi."),
    "wipers": ("CHECK", "Replace about yearly."),
    "fuel_filter": ("OK", "No serviceable filter on the US 2.0T."),
    "pcv_system": ("CHECK", "No schedule: inspect on symptoms."),
    "throttle_body_clean": ("CHECK", "No schedule: clean on symptoms, then relearn."),
    "intake_boost_hoses_inspect": ("CHECK", "No schedule: inspect on underboost codes or hiss."),
    "washer_fluid": ("CHECK", "Top up monthly / 600 mi."),
    "a_c_cabin_service": ("CHECK", "Yearly A/C check."),
    "power_steering": ("OK", "Electric steering: no fluid."),
    "hood_and_door_lubrication": ("CHECK", "Every 20k mi / 2 yr: lubricate hood and tailgate locks."),
}


def interval_text(i):
    bits = []
    if i["interval_miles"]:
        bits.append(f"{i['interval_miles']:,} mi")
    if i["interval_km"]:
        bits.append(f"{i['interval_km']:,} km")
    if i["interval_months"]:
        m = i["interval_months"]
        bits.append(f"{m // 12} yr" if m % 12 == 0 and m >= 12 else f"{m} mo")
    return " / ".join(bits) if bits else "no schedule"


def parts_text(i):
    out = []
    for p in i["parts"][:2]:
        pn = p.get("part_number") or "size only"
        out.append(f"{esc(short(pn, 60))} <font color='#5b6770'>({SHORT.get(p['confidence'], p['confidence'])})</font>")
    f = i.get("fluid")
    if f and f.get("spec"):
        cap = f"{f['capacity']} {f.get('unit') or ''}".strip() if f.get("capacity") else ""
        out.append(f"{esc(short(f['spec'], 90))}{'; ' + esc(cap) if cap else ''} "
                   f"<font color='#5b6770'>({SHORT.get(f['confidence'], f['confidence'])})</font>")
    return "<br/>".join(out) or "-"


def after_text(i):
    s = [x for x in i["post_service"] if not x.lower().startswith("none")]
    tk = ", ".join(i["torque_keys"])
    txt = short(s[0], 170) if s else "-"
    if tk:
        txt += f"<br/><font color='#5b6770'>torque: {esc(tk)}</font>"
    return txt


rows = [[P(h, bb) for h in ("Item", "Interval (owner's manual)", "Conf.", "Parts / fluid (confidence)",
                            f"At about {ODO_MI:,} mi ({ODO_KM:,} km)", "After service")]]
st = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
      ("BACKGROUND", (0, 0), (-1, 0), SHADE),
      ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
      ("TOPPADDING", (0, 0), (-1, -1), 1.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4)]
for key, i in M.ITEMS.items():
    status, note = SCHEDULE[key]
    rows.append([P(f"<b>{esc(i['label'])}</b>"), P(esc(interval_text(i))),
                 P(SHORT.get(i["interval_confidence"], i["interval_confidence"])),
                 P(parts_text(i)), P(f"<b>{status}</b>: {esc(note)}"), P(after_text(i))])
    r = len(rows) - 1
    st.append(("BACKGROUND", (2, r), (2, r), CONF_BG.get(i["interval_confidence"], SHADE)))
    st.append(("BACKGROUND", (4, r), (4, r), STATUS_BG[status]))

t = Table(rows, colWidths=[0.95 * inch, 0.95 * inch, 0.62 * inch, 1.83 * inch, 1.5 * inch, 1.65 * inch], repeatRows=1)
t.setStyle(TableStyle(st))

also = Table([[P("<b>Also due from the same schedule:</b> transfer case oil (Q4) at 80,000 mi / 128,000 km / 8 yr "
                 "(CONFIRMED). The car is past it: replace unless records show it was done. Engine oil: FCA maximum "
                 "1 yr / 10,000 mi (severe duty 4,000 mi); cuore's shop interval is 8,000 mi / 12 mo. The manual lists "
                 "no automatic transmission or differential oil change. Coolant 8.8 L is the engine circuit only; the "
                 "intercooler has its own circuit.")]], colWidths=[7.5 * inch])
also.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [P("Routine Maintenance - 2018 Alfa Romeo Stelvio 2.0T", title),
         P(f"VIN ZASFAKPN5J7B88115  |  about {ODO_KM:,} km / {ODO_MI:,} mi  |  no maintenance records in cuore yet: "
           "statuses are from the schedule alone  |  2026-09-26", sm),
         Spacer(1, 4), t, Spacer(1, 5), also, Spacer(1, 4),
         P("Source: 2018 Alfa Romeo Stelvio US owner's manual (Mopar), Maintenance Plan and Fluids tables; parts from Mopar "
           "catalogs and forums as graded. CONFIRM. = manufacturer document; CORROB. = two independent sources; SINGLE = "
           "one source; UNKNOWN = use the FCA service manual (TechAuthority). Full detail and procedures: cuore Maintenance "
           "page and docs/reference/STELVIO_20T_MAINTENANCE_SPECS.md.", sm)]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "cuore Maintenance: /v/ZASFAKPN5J7B88115/maintenance  |  record a baseline "
                 "visit with the odometer so cuore can track due dates")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.45 * inch,
                  bottomMargin=0.55 * inch, title="Stelvio Routine Maintenance").build(story, onFirstPage=foot,
                                                                                    onLaterPages=foot)
print(OUT)
