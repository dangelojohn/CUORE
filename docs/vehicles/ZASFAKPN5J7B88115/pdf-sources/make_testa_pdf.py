"""wiTECH Test A (ESIM switch seen by the ECU) PDF for the 2018 Stelvio."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

OUT = r"C:\Users\User\Desktop\Stelvio wiTECH Test A - ESIM Switch.pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6")
WARN_BG, WARN_EDGE = colors.HexColor("#fbf1e4"), colors.HexColor("#c07a1c")
KEY_BG, KEY_EDGE = colors.HexColor("#e8f2ec"), colors.HexColor("#1e6b3f")

ss = getSampleStyleSheet()
base = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=INK)
small = ParagraphStyle("s", parent=base, fontSize=8.5, leading=11.5, textColor=MUTED)
title = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24)
sub = ParagraphStyle("st", parent=base, fontSize=11, leading=15, textColor=MUTED)
h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                    textColor=ACCENT, spaceBefore=14, spaceAfter=6)
h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                    spaceBefore=7, spaceAfter=2)
cell = ParagraphStyle("c", parent=base, fontSize=9, leading=12)
cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")


def P(t, s=base):
    return Paragraph(t, s)


def bullets(items, s=base):
    return ListFlowable([ListItem(P(t, s), leftIndent=14) for t in items], bulletType="bullet",
                        start="-", leftIndent=14, bulletFontSize=10)


def box(flow, bg, edge):
    t = Table([[flow]], colWidths=[7.0 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def grid(rows, widths, row_h=None):
    data = [[P(c, cellb if r == 0 else cell) for c in row] for r, row in enumerate(rows)]
    heights = None if row_h is None else [None] + [row_h] * (len(rows) - 1)
    t = Table(data, colWidths=widths, rowHeights=heights, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def step(n, head, body):
    return KeepTogether([P(f"{n}. {head}", h3)] + body)


def footer(c, doc):
    c.saveState()
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawString(0.75 * inch, 0.5 * inch, "Stelvio 2.0T wiTECH Test A  |  VIN ZASFAKPN5J7B88115  |  2026-09-26")
    c.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    c.restoreState()


s = [P("wiTECH Test A: ESIM Switch", title),
     P("Does the engine computer see the ESIM switch close under vacuum?", sub), Spacer(1, 4),
     P("2018 Alfa Romeo Stelvio 2.0T (GU)  |  VIN ZASFAKPN5J7B88115", small), Spacer(1, 10)]

s += [box([P("<b>What this decides.</b> The EVAP system is sealed (three clean smoke tests) and every EVAP "
             "part is new, yet P0455, P0456 and P0440 keep setting. The ECU calls a leak when it does not "
             "see the ESIM switch close. This test makes the switch close with a hand pump while you watch "
             "the ECU's own reading in wiTECH. It checks the switch, connector, wiring and ECU input in one "
             "go, without unplugging anything.", cell)], KEY_BG, KEY_EDGE),
      Spacer(1, 6),
      box([P("<b>Note on wiTECH screens.</b> Tab and parameter names below are as commonly shown in wiTECH 2 "
             "and may differ slightly by software release. The exact name of the ESIM / EVAP switch "
             "parameter for this ECU is not known here: search the ECU's data list for it (step 6). Apply "
             "vacuum gently; never use shop air.", cell)], WARN_BG, WARN_EDGE)]

s += [P("You need", h2),
      bullets(["wiTECH 2 account, laptop and your wiTECH interface.",
               "Hand vacuum pump with a short rubber hose that fits the ESIM's canister-side port.",
               "Flat trim tool and torch to open the driver-side rear wheel liner.",
               "Optional: a phone to video the wiTECH screen during the test."])]

s += [P("Steps", h2)]
s += [step(1, "Prepare the car", [bullets([
    "Car parked, engine off and cool, park brake on.",
    "MultiEcuScan and cuore's live link disconnected: only wiTECH on the OBD port.",
    "Battery healthy; connect a battery maintainer if the session will be long (ignition on for "
    "several minutes).",
])])]
s += [step(2, "Reach the ESIM", [bullets([
    "Open the driver-side rear wheel liner. The ESIM sits on the vent side of the EVAP canister.",
    "Leave the ESIM <b>plugged in</b>. Identify its canister-side hose and its fresh-air side.",
])])]
s += [step(3, "Connect wiTECH", [P("Connect the interface to the OBD port. Ignition <b>RUN</b>, engine "
                                   "<b>off</b>.")])]
s += [step(4, "Sign in and select the car", [P("Open wiTECH 2, sign in, select the vehicle and confirm "
                                               "the VIN reads ZASFAKPN5J7B88115.")])]
s += [step(5, "Open the engine computer", [P("From <b>Topology</b>, select the <b>ECM</b> icon.")])]
s += [step(6, "Find the ESIM switch parameter", [
    P("Open the ECM's live data (<b>Data Display</b> / data tab). Search or scroll the list for a "
      "parameter reporting the <b>ESIM switch</b> or <b>EVAP pressure / leak-detection switch</b> "
      "state. Useful search words: ESIM, EVAP, leak, pressure switch, NVLD. Add it to the display. "
      "Also add <b>fuel level</b> for the record."),
    P("If no such parameter exists in the list, note that on the record sheet: the test then has to be "
      "done with the meter (Test B in the 'Stelvio ESIM Wiring Test' PDF).", small)])]
s += [step(7, "Baseline", [P("With nothing connected to the ESIM hose, record what the switch parameter "
                             "shows (expected: <b>open</b> / not sealed).")])]
s += [step(8, "Apply vacuum", [bullets([
    "Disconnect the ESIM's canister-side hose and fit the hand pump to that port. Fresh-air side "
    "stays open.",
    "Pump <b>slowly</b>. Watch wiTECH. Note whether and when the switch shows <b>closed</b>.",
    "Stop and hold for about 30 seconds: it should stay closed.",
    "Release the vacuum: it should return to <b>open</b>.",
    "Repeat three times. Note any delay between the pump and the wiTECH reading.",
])])]
s += [step(9, "Wiggle test", [P("Hold the switch closed with vacuum. Gently flex the ESIM connector and "
                                "the harness along the wheel well while watching wiTECH. Any flicker to "
                                "open is an intermittent connection.")])]
s += [step(10, "Finish", [P("Release vacuum, reconnect the ESIM hose firmly, refit the wheel liner, "
                            "ignition OFF, disconnect wiTECH. Do not clear codes unless you intend to "
                            "start a new verification drive.")])]

s += [P("Reading the result", h2),
      grid([["What wiTECH shows", "Meaning", "Next step"],
            ["Closes with vacuum, opens on release, every time, no flicker",
             "The whole signal path works: switch, connector, wiring, ECU input.",
             "Fault is the ECU calibration or test logic. Do the Flash tab check; if already current, "
             "this sheet plus three clean smoke tests is the dealer case."],
            ["Never changes", "The ECU does not see the switch.",
             "Wiring PDF Test B: connector, signal voltage, ground, resistance, jumper test."],
            ["Changes, but flickers when wiggled", "Intermittent connection at the connector or harness.",
             "Repair the connector or wiring; wiring PDF B1 and B5 find the spot."],
            ["Changes only after a long delay or at hard vacuum", "Sluggish switch.",
             "Bench-test the ESIM against a new unit (ESIM Bench Test PDF)."]],
           [2.0 * inch, 2.5 * inch, 2.5 * inch])]

s += [P("Record sheet", h2),
      grid([["Item", "Result"],
            ["Date / odometer / fuel level", " "],
            ["wiTECH parameter name used", " "],
            ["Baseline state (no vacuum)", " "],
            ["Run 1: closed under vacuum? / opened on release?", " "],
            ["Run 2", " "],
            ["Run 3", " "],
            ["Held closed for 30 s?", " "],
            ["Wiggle test: any flicker?", " "],
            ["Conclusion", " "]], [3.3 * inch, 3.7 * inch], row_h=0.34 * inch),
      Spacer(1, 6),
      P("Enter the result in cuore (dealer results page or evidence gate): a clean pass is the measurement "
        "that clears the ESIM wiring; a failure localises the fault.", small)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.8 * inch,
                        title="Stelvio wiTECH Test A - ESIM Switch", author="cuore / Claude")
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print(OUT)
