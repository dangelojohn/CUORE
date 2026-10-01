"""wiTECH Test A (ESIM switch seen by the ECU), one page, 2018 Stelvio 2.0T. Same content as the 3-page sheet."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio wiTECH Test A - ESIM Switch (1 page).pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6")
KEY_BG, KEY_EDGE = colors.HexColor("#e8f2ec"), colors.HexColor("#2f7a4a")
WARN_BG, WARN_EDGE = colors.HexColor("#fbf1e4"), colors.HexColor("#c07a1c")

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.4, leading=9.1, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=ACCENT,
                   spaceBefore=2, spaceAfter=2)
sm = ParagraphStyle("sm", parent=b, fontSize=6.7, leading=8.2, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


def box(text, bg, edge, w=7.5):
    t = Table([[P(text)]], colWidths=[w * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def grid(rows, widths, heights=None):
    data = [[P(c, bb if r == 0 else b) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, rowHeights=heights)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


steps = [
    ("Prepare", "Parked, engine off and cool, park brake on. MultiEcuScan and cuore disconnected: only wiTECH on "
                "the OBD port. Battery maintainer if the session is long."),
    ("Reach the ESIM", "Open the driver-side rear wheel liner; the ESIM sits on the vent side of the EVAP canister. "
                       "Leave it <b>plugged in</b>. Identify its canister-side hose and its fresh-air side."),
    ("Connect wiTECH", "Interface on the OBD port. Ignition <b>RUN</b>, engine <b>off</b>."),
    ("Select the car", "Sign in to wiTECH 2, select the vehicle, confirm VIN ZASFAKPN5J7B88115."),
    ("Open the ECM", "From <b>Topology</b>, select the <b>ECM</b>."),
    ("Find the switch", "In the ECM's live data, search for the <b>ESIM switch</b> or <b>EVAP pressure / leak-detection "
                        "switch</b> (words: ESIM, EVAP, leak, pressure switch, NVLD). Add it and <b>fuel level</b>. "
                        "None listed: note it, and use the meter test (Test B, ESIM Wiring Test sheet)."),
    ("Baseline", "Nothing on the ESIM hose: record the switch state (expected <b>open</b> / not sealed)."),
    ("Apply vacuum", "Remove the ESIM's canister-side hose, fit the hand pump to that port (fresh-air side open). "
                     "Pump <b>slowly</b> and note when wiTECH shows <b>closed</b>. Hold about 30 s: it should stay "
                     "closed. Release: it should return to <b>open</b>. Do it three times; note any delay."),
    ("Wiggle test", "Hold it closed with vacuum and gently flex the ESIM connector and harness along the wheel well. "
                    "Any flicker to open is an intermittent connection."),
    ("Finish", "Release vacuum, refit the hose firmly and the wheel liner, ignition OFF, disconnect wiTECH. "
               "<b>Do not clear codes.</b>"),
]
srows = [[P(f"<b>{i}</b>"), P(f"<b>{head}</b>"), P(body)] for i, (head, body) in enumerate(steps, start=1)]
step_t = Table(srows, colWidths=[0.25 * inch, 1.05 * inch, 6.2 * inch])
step_t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6)]))

results = grid([["What wiTECH shows", "Meaning", "Next step"],
                ["Closes with vacuum, opens on release, every time, no flicker",
                 "The whole signal path works: switch, connector, wiring, ECU input.",
                 "Fault is ECU calibration or test logic. Do the Flash check; if already current, this plus "
                 "three clean smoke tests is the dealer case."],
                ["Never changes", "The ECU does not see the switch.",
                 "ESIM Wiring Test (Test B): connector, signal voltage, ground, resistance, jumper."],
                ["Changes, but flickers when wiggled", "Intermittent connection at connector or harness.",
                 "Repair the connector or wiring; wiring tests B1 and B5 find the spot."],
                ["Changes only after a long delay or at hard vacuum", "Sluggish switch.",
                 "Bench-test the ESIM against a new unit (ESIM Bench Test sheet)."]],
               [2.0 * inch, 2.4 * inch, 3.1 * inch])

record = grid([["Item", "Result", "Item", "Result"],
               ["Date / odometer / fuel level", "", "Run 2", ""],
               ["wiTECH parameter name", "", "Run 3", ""],
               ["Baseline (no vacuum)", "", "Held closed 30 s?", ""],
               ["Run 1: closed? opened on release?", "", "Wiggle: any flicker?", ""],
               ["Conclusion", "", "", ""]],
              [1.75 * inch, 2.0 * inch, 1.25 * inch, 2.5 * inch], [None] + [0.27 * inch] * 5)

story = [P("wiTECH Test A: ESIM Switch", title),
         P("Does the engine computer see the ESIM switch close under vacuum?  |  2018 Alfa Romeo Stelvio 2.0T  |  "
           "VIN ZASFAKPN5J7B88115", sm), Spacer(1, 5),
         box("<b>What this decides.</b> The EVAP system is sealed (three clean smoke tests) and every EVAP part is "
             "new, yet the codes keep setting: P0440 came back within a day of the 2026-09-28 and 09-29 clears. The "
             "ECU calls a fault when it does not see the ESIM switch close. A hand pump closes the switch while you "
             "watch the ECU's own reading, testing switch, connector, wiring and ECU input at once, without "
             "unplugging anything.", KEY_BG, KEY_EDGE),
         Spacer(1, 3),
         box("<b>Note.</b> wiTECH tab and parameter names are as commonly shown in wiTECH 2 and may differ by release; "
             "the exact switch parameter name for this ECU is not known, so search for it (step 6). Apply vacuum "
             "gently; never use shop air.", WARN_BG, WARN_EDGE),
         Spacer(1, 4),
         P("You need: wiTECH 2 account, laptop and interface; hand vacuum pump with a short hose that fits the "
           "ESIM's canister-side port; flat trim tool and torch for the wheel liner; optionally a phone to video "
           "the wiTECH screen."),
         P("Steps", h), step_t,
         P("Reading the result", h), results,
         P("Record sheet", h), record, Spacer(1, 3),
         P("Enter the result in cuore (dealer results or the evidence gate). A clean pass clears the ESIM wiring; a "
           "failure localises the fault.", sm)]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "Stelvio 2.0T wiTECH Test A  |  related sheets: wiTECH Flash Check, ESIM "
                 "Wiring Test, ESIM Bench Test  |  2026-10-01")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.45 * inch,
                  bottomMargin=0.55 * inch, title="Stelvio wiTECH Test A (1 page)").build(story, onFirstPage=foot,
                                                                                        onLaterPages=foot)
print(OUT)
