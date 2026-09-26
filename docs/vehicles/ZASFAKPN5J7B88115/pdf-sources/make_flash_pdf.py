"""wiTECH ECM flash procedure PDF for the 2018 Stelvio 2.0T, from W05 and TSB 18-026-20."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

OUT = r"C:\Users\User\Desktop\Stelvio ECM Flash Procedure (wiTECH).pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6")
WARN_BG, WARN_EDGE = colors.HexColor("#fbf1e4"), colors.HexColor("#c07a1c")
STOP_BG, STOP_EDGE = colors.HexColor("#fbeaea"), colors.HexColor("#9e1b21")

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
    return ListFlowable([ListItem(P(t, s), leftIndent=14) for t in items],
                        bulletType="bullet", start="-", leftIndent=14, bulletFontSize=10)


def box(flow, bg, edge):
    t = Table([[flow]], colWidths=[7.0 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
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
    c.drawString(0.75 * inch, 0.5 * inch,
                 "Stelvio 2.0T ECM flash  |  VIN ZASFAKPN5J7B88115  |  from FCA CSN W05 and TSB 18-026-20  |  2026-09-26")
    c.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    c.restoreState()


s = []
s += [P("ECM Flash Procedure (wiTECH 2)", title),
      P("Check the engine computer calibration and update it if a newer one exists", sub),
      Spacer(1, 4),
      P("2018 Alfa Romeo Stelvio 2.0T (GU), 2.0L GME-T4, sales code EC2  |  VIN ZASFAKPN5J7B88115", small),
      Spacer(1, 10)]

s += [P("Where this comes from", h2),
      P("The steps are transcribed from FCA's own dealer instructions for this exact car: "
        "<b>Customer Satisfaction Notification W05</b> (March 2020, 2018 GU Stelvio 2.0L EC2: "
        "\"Reprogram PCM, perform PROXI Alignment and Phonic Wheel Replacement routine\") and "
        "<b>TSB 18-026-20</b> (March 25, 2020, 2018 GU Stelvio 2.0L EC2, North America). "
        "Items marked <i>[practice]</i> are general flashing precautions, not from those documents."),
      Spacer(1, 6),
      P("TSB 18-026-20's fix list includes two EVAP-related codes: <b>P1CEA</b> (boost-side EVAP "
        "purge performance) and <b>P24D6</b> (EVAP system pressure sensor/switch circuit). "
        "No FCA bulletin publishes calibration numbers; wiTECH shows the current and newest part "
        "numbers on the Flash tab (step 7), which is the only way to know if this car is current.")]

s += [P("Installed now (read from this car)", h3),
      grid([["Field", "Value"],
            ["ECU software number", "52170619"],
            ["Supplier software", "P235QB39, version 0000"],
            ["Hardware", "MM10JAHW232 (FIAT drawing 52055320)"],
            ["ECU spare part number", "50544870"]], [2.6 * inch, 4.4 * inch])]

s += [P("Before you start", h2),
      box([bullets([
          "<b>Battery support is mandatory.</b> Charger set so the battery stays between <b>13.2 and "
          "13.5 V</b> for the whole flash; set any charger timer to continuous. Measure with an "
          "accurate stand-alone voltmeter, not the charger's meter. If the voltage is too high, "
          "switch on the park lamps, headlamps or HVAC blower to add load. (W05 step 1; TSB 18-026-20)",
          "<b>Do not interrupt the flash.</b> If it is aborted or interrupted, restart it. (W05; TSB 18-026-20)",
          "<i>[practice]</i> Laptop on mains power with sleep and hibernate disabled; stable, wired "
          "internet (wiTECH 2 is web-based); close other diagnostic software.",
          "<i>[practice]</i> Unplug the vLinker and close MultiEcuScan and cuore's live link: only "
          "the wiTECH interface may be on the OBD port.",
          "<i>[practice]</i> Doors closed, lights and accessories off unless used for load, key "
          "fob in the car, park brake on.",
      ], cell)], WARN_BG, WARN_EDGE),
      Spacer(1, 6),
      P("<b>Interface:</b> W05 lists the wiTECH MicroPod II, a laptop and wiTECH software as the "
        "special tools. If you use another interface, confirm wiTECH lists it as supported for "
        "flashing before you start.", small)]

s += [P("Procedure", h2)]
s += [step(1, "Battery support", [P("Open the hood. Connect the charger and confirm 13.2 to 13.5 V "
                                    "at the battery with a stand-alone voltmeter.")])]
s += [step(2, "Connect", [P("Connect the wiTECH interface to the OBD data link connector.")])]
s += [step(3, "Ignition RUN", [P("Place the ignition in RUN (engine off).")])]
s += [step(4, "Sign in", [P("Open wiTECH 2 and sign in with your account. (W05 shows the dealer "
                            "sign-in: user ID, password and dealer code, then Accept.)")])]
s += [step(5, "Select the vehicle", [P("On the Vehicle Selection screen select this car. Confirm "
                                       "the VIN reads ZASFAKPN5J7B88115.")])]
s += [step(6, "Open the ECM", [P("On the Topology screen click the <b>ECM</b> icon. (2018 Stelvio: "
                                 "PCM only; W05 adds the TCM only for 2019 cars.)")])]
s += [step(7, "Compare part numbers: this answers the version question", [
    P("On the ECM screen select the <b>Flash</b> tab and compare the <b>Current ECU Part Number</b> "
      "with the <b>New ECU Part Number</b>. Write both down on the record sheet."),
    bullets([
        "<b>Same:</b> the ECM is already on the latest calibration. Do not flash. Go to step 16 "
        "(W05: \"proceed to Step 22\"). The software lead is closed.",
        "<b>Different:</b> a newer calibration exists. Continue with step 8.",
    ])])]
s += [step(8, "Accept and flash", [P("On the flash agreement page tick the box, select "
                                     "<b>Flash ECU</b>, and follow the on-screen instructions to "
                                     "completion. Expected flash time is about 8 minutes "
                                     "(TSB 18-026-20). Watch the voltmeter throughout.")])]
s += [step(9, "PROXI Alignment (BCM)", [P("From Topology select <b>BCM</b>, then <b>Misc. Functions</b>, "
                                          "and run <b>PROXI Alignment</b>.")])]
s += [step(10, "View and clear DTCs", [P("When the flash is complete select <b>View DTCs</b>. From "
                                         "Topology go to <b>Action Items</b>, <b>All DTCs</b>, "
                                         "<b>Clear All DTCs</b>. The flash sets codes in other "
                                         "modules; that is expected.")])]
s += [step(11, "Phonic Wheel Replacement (ECM)", [
    P("From Topology select <b>ECM</b>, <b>Misc. Functions</b>, <b>Phonic Wheel Replacement</b>, "
      "and follow the prompts to completion."),
    box([P("If this routine is not done correctly, <b>DTC P1300 Flywheel Self Learning</b> will stay "
           "active. (W05; TSB 18-026-20)", cell)], STOP_BG, STOP_EDGE)])]
s += [step(12, "Clear DTCs again", [P("Topology, <b>All DTCs</b>, <b>Clear All DTCs</b>.")])]
s += [step(13, "Confirm the new part number", [P("Re-open the ECM <b>Flash</b> tab and confirm the "
                                                 "Current ECU Part Number now equals the New ECU "
                                                 "Part Number. Record it.")])]
s += [step(14, "BCM software", [P("TSB 18-026-20: the BCM must be at the latest available software "
                                  "after this repair. On the BCM Flash tab compare current and new "
                                  "part numbers the same way, and update if different.")])]
s += [step(15, "Record identity", [P("<i>[practice]</i> After sign-out, a MultiEcuScan read of the "
                                     "engine ECU records the new Software number in its log, so "
                                     "cuore picks up the new version automatically.")])]
s += [step(16, "Finish", [P("Ignition OFF, disconnect the wiTECH interface, remove the charger, "
                            "close the hood.")])]

s += [P("After the flash: checking the EVAP result", h2),
      bullets([
          "Drive normally over several days: fuel between about 15 and 85 percent, and include cold "
          "starts after the car has sat overnight. The leak tests only run under those conditions.",
          "Then read the ECM: cuore's <b>verify_repair</b> for P0455, P0456 and P0440, or an MES scan. "
          "All three showing <b>passed since clear</b> means the calibration fixed it.",
          "The check-engine light cannot confirm it on this car: the ECM stored these codes without "
          "requesting the light.",
          "If the part numbers matched in step 7, or the codes return after the flash, the next "
          "suspects are the ESIM part number fitted (04861961AD, never checked against the VIN) and "
          "the ESIM-to-ECM wiring.",
      ])]

s += [P("Record sheet", h2),
      grid([["Item", "Result"],
            ["Date / odometer", " "],
            ["Battery voltage during flash (min / max)", " "],
            ["ECM Current ECU Part Number (before)", " "],
            ["ECM New ECU Part Number", " "],
            ["Flash performed? (yes / not needed)", " "],
            ["PROXI Alignment completed", " "],
            ["Phonic Wheel Replacement completed", " "],
            ["DTCs present after flash (before clearing)", " "],
            ["ECM part number after flash", " "],
            ["BCM current / new part number", " "],
            ["Notes", " "]], [3.3 * inch, 3.7 * inch], row_h=0.34 * inch)]

s += [Spacer(1, 8),
      P("Sources: FCA US LLC Customer Satisfaction Notification W05, Dealer Service Instructions, "
        "March 2020 (static.nhtsa.gov/odi/tsbs/2020/MC-10175111-9999.pdf); TSB 18-026-20, March 25, "
        "2020 (static.nhtsa.gov/odi/tsbs/2020/MC-10174245-9999.pdf).", small)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.8 * inch,
                        title="Stelvio ECM Flash Procedure (wiTECH)", author="cuore / Claude")
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print(OUT)
