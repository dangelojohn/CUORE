"""One-page pending-items sheet for the 2018 Stelvio 2.0T (as of 2026-10-01)."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio Pending Items (1 page).pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
PRI_BG = {"1": colors.HexColor("#f6d5d5"), "2": colors.HexColor("#fbe7c6"), "3": colors.HexColor("#eef1f4")}
YES_BG, GONE_BG = colors.HexColor("#f6d5d5"), colors.HexColor("#dcefe1")

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.3, leading=9, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=ACCENT)
sm = ParagraphStyle("sm", parent=b, fontSize=6.7, leading=8.2, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


GRID = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), SHADE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]

# --- latest scans ---------------------------------------------------------------
scan_rows = [
    ("Engine (ECM)", "P0440 evaporation control valve", True, True),
    ("Body (BCM)", "B1176 rear left window riser obstructed", True, True),
    ("Body (BCM)", "U1713 engine message erratic", True, False),
    ("Transfer case (DTCM)", "U0100 no communication with engine module", True, False),
    ("Key fob hub (RFHUB)", "B1040 message from BCM implausible", True, False),
    ("Driver assist radar (DASM)", "C141B camera blocked", True, False),
]
srows = [[P(x, bb) for x in ("Module", "Code", "28 Sep scan", "29 Sep scan")]]
sst = list(GRID)
for i, (m, c, a, z) in enumerate(scan_rows, start=1):
    srows.append([P(m), P(c), P("present, cleared"), P("<b>back after the clear</b>" if z else "gone")])
    sst.append(("BACKGROUND", (3, i), (3, i), YES_BG if z else GONE_BG))
scans = Table(srows, colWidths=[1.6 * inch, 2.8 * inch, 1.2 * inch, 1.9 * inch])
scans.setStyle(TableStyle(sst))

# --- pending items -------------------------------------------------------------------
items = [
    ("1", "EVAP: check engine-module software", "wiTECH Flash tab: compare P235QB39 with the latest calibration; "
     "recall 18V636000 is a 2.0L engine-software update.", "You, wiTECH"),
    ("1", "EVAP: run Test A (ESIM switch)", "Vacuum on the ESIM while watching its switch reading in wiTECH. Decides "
     "ESIM signal path versus engine software.", "You, wiTECH"),
    ("1", "Stop clearing codes", "Each clear resets the EVAP self-test. Let P0440 (and any P0455 / P0456) set and "
     "keep the evidence until Test A is done.", "You"),
    ("1", "Recalls and bulletins", "25V586000 (fuel pump), 18V636000 (2.0L engine software), TSB 21-035-20 "
     "(transmission software): check open status by VIN.", "You, wiTECH / dealer"),
    ("2", "Transfer case oil", "Due at 80,000 mi / 128,000 km / 8 yr (owner's manual). Car is past it: replace "
     "unless records show it was done.", "Shop"),
    ("2", "Drive belt", "Due every 36,000 mi / 4 yr. Overdue unless replaced.", "Shop"),
    ("2", "Air filter and spark plugs", "Next mark 90,000 mi: about 1,585 mi away. Plugs NGK 90219 / Mopar 68292346AA, "
     "19.5 Nm.", "Shop"),
    ("2", "Brake fluid", "Every 2 years regardless of mileage (DOT 4, MS.90039). Overdue unless changed since 2024-09.",
     "Shop"),
    ("2", "Rear left window (B1176)", "Window riser reports obstructed, back after the clear. Separate from EVAP.",
     "You / shop"),
    ("3", "Enter records in cuore", "A baseline maintenance visit with odometer, and the 2026-09-15 oil change "
     "(brand, filter, odometer) so due dates can be tracked.", "You, cuore"),
    ("3", "Label print check", "Print the sample sheet and test grids; report offsets for the 6576 / 6578 plastic "
     "ID labels (margins not published).", "You"),
    ("3", "Chassis bus read", "Grey cable (A6) read of ABS, steering and other chassis modules; follow the network "
     "fault tree if codes appear.", "You, cuore"),
    ("3", "Unsourced values", "EVAP purge and vapour-pressure limits, peak boost: need the service manual "
     "(TechAuthority). Tyre pressures: read the door placard.", "You"),
]
prows = [[P(x, bb) for x in ("Pri.", "Item", "What to do", "Who")]]
pst = list(GRID)
for i, (pri, item, what, who) in enumerate(items, start=1):
    prows.append([P(f"<b>{pri}</b>"), P(f"<b>{item}</b>"), P(what), P(who)])
    pst.append(("BACKGROUND", (0, i), (0, i), PRI_BG[pri]))
pending = Table(prows, colWidths=[0.35 * inch, 1.7 * inch, 4.4 * inch, 1.05 * inch])
pending.setStyle(TableStyle(pst))

note = Table([[P("<b>Reading the scans:</b> P0440 came back within a day of being cleared, so the engine module's "
                 "EVAP self-test is still failing. The system passed three smoke tests and every EVAP part is new, "
                 "so the suspects are the ESIM switch signal path or the engine-module software. B1176 is real but "
                 "unrelated. The four network codes on 28 Sep were gone the next day: one power or bus event.")]],
             colWidths=[7.5 * inch])
note.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [P("Pending Items - 2018 Alfa Romeo Stelvio 2.0T", title),
         P("VIN ZASFAKPN5J7B88115  |  about 142,290 km / 88,415 mi  |  as of 2026-10-01  |  newest MES logs: "
           "all-systems scans 2026-09-28 and 2026-09-29 (none since)", sm),
         Spacer(1, 6), P("Latest MES scans", h), scans, Spacer(1, 4), note, Spacer(1, 7),
         P("Pending items (priority 1 = do first)", h), pending, Spacer(1, 4),
         P("Priority 1: diagnosis and safety recalls. Priority 2: overdue or due-soon maintenance from the 2018 owner's "
           "manual schedule (no maintenance records exist in cuore yet, so these assume the work was not done). "
           "Priority 3: records and open checks.", sm)]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "cuore: /v/ZASFAKPN5J7B88115 (dossier), /service-hub, /maintenance, /tree  |  "
                 "related sheets: Service Hub, Routine Maintenance, wiTECH Test A, wiTECH Flash Check")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.45 * inch,
                  bottomMargin=0.55 * inch, title="Stelvio Pending Items").build(story, onFirstPage=foot,
                                                                              onLaterPages=foot)
print(OUT)
