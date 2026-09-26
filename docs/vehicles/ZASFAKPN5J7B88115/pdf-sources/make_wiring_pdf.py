"""ESIM-to-ECM circuit test PDF for the 2018 Stelvio."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

OUT = r"C:\Users\User\Desktop\Stelvio ESIM Wiring Test.pdf"
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
    c.drawString(0.75 * inch, 0.5 * inch, "Stelvio 2.0T ESIM circuit test  |  VIN ZASFAKPN5J7B88115  |  2026-09-26")
    c.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    c.restoreState()


s = [P("ESIM Wiring Test", title),
     P("Does the ESIM switch signal reach the engine computer intact?", sub), Spacer(1, 4),
     P("2018 Alfa Romeo Stelvio 2.0T (GU)  |  VIN ZASFAKPN5J7B88115  |  about 142,290 km", small),
     Spacer(1, 10)]

s += [P("Why this test", h2),
      P("Three smoke tests (08/2025, 2026-09-16, 2026-09-26) show the EVAP system is sealed, and the "
        "canister, ESIM (04861961AD), filter, fuel cap and purge valve are all new. Yet the ECU keeps "
        "setting P0455, P0456 and P0440. The ECU decides \"leak\" when the ESIM switch does not report "
        "closed during its test. On a sealed system with a new ESIM, the remaining causes are the ECU's "
        "calibration and the <b>signal path from the ESIM to the ECU</b>: connector, wires, ground, "
        "and the ECU input. This test checks that path."),
      Spacer(1, 6),
      box([P("<b>Do the wiTECH flash check first</b> (ECM Flash tab, Current vs New ECU Part Number; see "
             "the 'Stelvio ECM Flash Procedure (wiTECH)' PDF). It takes minutes and decides whether this "
             "test is needed.", cell)], KEY_BG, KEY_EDGE),
      Spacer(1, 6),
      box([P("<b>What is not known here.</b> The factory pinout, wire colours, ECU connector and pin "
             "numbers, and the switch's rated voltage for this car were not obtainable. Look them up in "
             "the FCA wiring diagram for this VIN (FCA service information via your wiTECH/TechAuthority "
             "access) and write them in the table on page 2 before testing. Every value to compare against "
             "comes from that diagram or from a known-good reading, never from this sheet. General "
             "circuit-test practice below is marked <i>[practice]</i>.", cell)], WARN_BG, WARN_EDGE),
      Spacer(1, 6),
      P("<b>One clue from the codes:</b> the ECU has not set an ESIM <i>circuit</i> code (for example "
        "P24D6, EVAP pressure switch circuit range/performance, which TSB 18-026-20 lists for this car). "
        "A hard open or short usually sets a circuit code, so an intermittent or high-resistance fault "
        "is more likely than a broken wire.", small)]

s += [P("Tools", h2),
      bullets(["wiTECH 2 with your interface (for the ECU's live reading of the switch).",
               "Digital multimeter; back-probe pins or a breakout lead. <i>[practice]</i> Never push probes "
               "into the front of connector terminals; it spreads them.",
               "Hand vacuum pump and short hose (as for the ESIM bench test).",
               "A fused jumper lead (low-amp fuse). <i>[practice]</i>",
               "The FCA wiring diagram for this VIN."])]

s += [KeepTogether([P("Circuit details from the wiring diagram (fill in first)", h2),
      grid([["Item", "Value from the FCA diagram for this VIN"],
            ["ESIM connector ID / location", " "],
            ["Signal pin and wire colour", " "],
            ["Ground pin and wire colour", " "],
            ["ECU connector and signal pin", " "],
            ["Ground point (e.g. G-number)", " "],
            ["Switch reference voltage", " "],
            ["wiTECH parameter name for switch state", " "]], [2.9 * inch, 4.1 * inch], row_h=0.34 * inch)])]

s += [P("Test A: end-to-end, with the ECU as the meter (best first test)", h2),
      P("This proves switch, connector, wires and ECU input in one go, without unplugging anything."),
      step("A1", "Find the switch state in wiTECH", [P("Ignition RUN, engine off. In wiTECH open the ECM "
                                                      "data display and find the parameter that reports the "
                                                      "ESIM / EVAP pressure switch state (name varies; look "
                                                      "under EVAP or leak detection).")]),
      step("A2", "Apply vacuum at the ESIM", [P("Behind the driver-side rear wheel liner, disconnect the hose "
                                                "on the ESIM's canister side and apply gentle vacuum to that "
                                                "port with the hand pump. Leave the ESIM plugged in.")]),
      step("A3", "Watch the ECU's reading", [bullets([
          "<b>Switch shows CLOSED with vacuum and OPEN when released, every time:</b> the whole "
          "signal path works. The wiring is exonerated; the fault is the ECU calibration or its test "
          "logic. Take it to the flash check / dealer.",
          "<b>Never changes:</b> the ECU is not seeing the switch. Go to Test B to find where it is lost.",
          "<b>Changes, but drops out when you wiggle the harness or connector:</b> intermittent "
          "connection. Go to Test B, steps B1 and B5.",
      ])])]

s += [P("Test B: isolate the break", h2),
      step("B1", "Inspect the connector", [bullets([
          "Ignition OFF. Unplug the ESIM connector.",
          "Look for green or white corrosion, water, bent or pushed-back pins, a cracked housing or a "
          "missing seal. <i>[practice]</i> Check terminal grip with a matching test terminal: it should "
          "drag, not slide.",
          "Follow the harness back as far as practical: chafe points on the wheel-well edge and "
          "subframe, and rodent damage.",
      ])]),
      step("B2", "Signal wire: is the ECU sending its reference?", [
          P("Connector unplugged, ignition RUN. Back-probe the harness-side <b>signal</b> pin (from the "
            "diagram) to a good chassis ground."),
          bullets(["<b>Expected:</b> the reference voltage shown in the diagram (the ECU's pull-up on the "
                   "switch line). Record it.",
                   "<b>0 V:</b> open in the signal wire, or the ECU is not driving it: go to B4.",
                   "<b>Battery voltage where the diagram shows a low reference:</b> short to power: go to B4."])]),
      step("B3", "Ground wire", [
          P("Ignition RUN, connector unplugged. Measure between the harness-side <b>ground</b> pin and the "
            "battery negative post."),
          bullets(["<i>[practice]</i> A good ground reads close to 0 V and a few ohms or less (ignition off, "
                   "for the ohms reading). Record it and compare with a known-good ground on the car."])]),
      step("B4", "End-to-end resistance of each wire", [
          P("<b>Ignition OFF and battery negative disconnected</b> before unplugging the ECU connector. "
            "Measure each wire from the ESIM connector pin to its ECU connector pin (from the diagram)."),
          bullets(["<i>[practice]</i> Each wire should read a fraction of an ohm. Several ohms or more is "
                   "high resistance; open line is a break.",
                   "Also check each wire to chassis ground (should be open) and to battery positive "
                   "(should be open): a reading means a short.",
                   "Reconnect the ECU connector carefully and the battery last."])]),
      step("B5", "Jumper test: does the ECU see a closed switch?", [
          P("Battery reconnected, ignition RUN, ESIM unplugged, wiTECH data display open. With the fused "
            "jumper, connect the harness-side signal pin to the ground pin (this is what the closed switch "
            "does)."),
          bullets(["<b>wiTECH shows CLOSED:</b> wiring and ECU input are good. If Test A failed, the ESIM "
                   "switch or its connector contacts are at fault.",
                   "<b>wiTECH still shows OPEN:</b> the fault is in the wiring or the ECU input. Repeat the "
                   "jumper at the ECU end (from the diagram) to split wiring from ECU.",
                   "<i>[practice]</i> Wiggle the harness along its length while watching: a flicker "
                   "finds an intermittent fault."])])]

s += [P("Record sheet", h2),
      grid([["Test", "Result"],
            ["Date / odometer", " "],
            ["A3: wiTECH state with vacuum / released", " "],
            ["A3: wiggle test", " "],
            ["B1: connector condition", " "],
            ["B2: signal reference voltage", " "],
            ["B3: ground voltage / resistance", " "],
            ["B4: signal wire resistance, ends / to ground / to B+", " "],
            ["B4: ground wire resistance", " "],
            ["B5: wiTECH state with jumper", " "],
            ["Conclusion", " "]], [3.3 * inch, 3.7 * inch], row_h=0.34 * inch)]

s += [P("After the test", h2),
      bullets([
          "<b>Wiring fault found:</b> repair it (FCA-approved terminal and splice repair), clear codes, drive "
          "several days with fuel 15-85 percent and cold starts, then confirm with cuore's verify_repair: all "
          "three codes 'passed since clear'.",
          "<b>Signal path good (Test A passes):</b> the fault is in the ECU calibration or test logic. Flash "
          "check first; if already current, a dealer case with these three clean smoke tests and this sheet "
          "is the evidence.",
          "Enter the readings in cuore's evidence gate as manual measurements; a Test A pass is the "
          "disconfirming test that clears the wiring.",
      ])]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.8 * inch,
                        title="Stelvio ESIM Wiring Test", author="cuore / Claude")
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print(OUT)
