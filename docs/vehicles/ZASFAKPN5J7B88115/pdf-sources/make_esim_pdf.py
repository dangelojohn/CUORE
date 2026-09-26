"""Build the ESIM bench-test procedure PDF for the Stelvio."""
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

OUT = r"C:\Users\User\Desktop\Stelvio ESIM Bench Test.pdf"

INK = colors.HexColor("#1b2227")
MUTED = colors.HexColor("#5b6770")
ACCENT = colors.HexColor("#9e1b21")
RULE = colors.HexColor("#c9d1d6")
SHADE = colors.HexColor("#f1f4f6")
WARN_BG = colors.HexColor("#fbf1e4")
WARN_EDGE = colors.HexColor("#c07a1c")

ss = getSampleStyleSheet()
base = ParagraphStyle("base", parent=ss["Normal"], fontName="Helvetica", fontSize=10,
                      leading=14, textColor=INK, alignment=TA_LEFT)
small = ParagraphStyle("small", parent=base, fontSize=8.5, leading=11.5, textColor=MUTED)
title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=20,
                       leading=24, textColor=INK, spaceAfter=2)
subtitle = ParagraphStyle("subtitle", parent=base, fontSize=11, leading=15, textColor=MUTED)
h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                    textColor=ACCENT, spaceBefore=14, spaceAfter=6)
h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                    spaceBefore=6, spaceAfter=2)
cell = ParagraphStyle("cell", parent=base, fontSize=9, leading=12)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")


def P(text, style=base):
    return Paragraph(text, style)


def bullets(items, style=base):
    return ListFlowable([ListItem(P(t, style), leftIndent=14) for t in items],
                        bulletType="bullet", start="-", leftIndent=14, bulletFontSize=10)


def boxed(flowables, bg, edge):
    t = Table([[flowables]], colWidths=[7.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def grid(rows, widths, header=True, row_h=None):
    data = [[P(c, cellb if (header and r == 0) else cell) for c in row]
            for r, row in enumerate(rows)]
    heights = None if row_h is None else [None] + [row_h] * (len(rows) - 1)
    t = Table(data, colWidths=widths, rowHeights=heights, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), SHADE))
    t.setStyle(TableStyle(style))
    return t


def step(n, head, body):
    return KeepTogether([P(f"Step {n}. {head}", h3)] + body)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.5 * inch,
                      "Stelvio 2.0T ESIM bench test  |  VIN ZASFAKPN5J7B88115  |  2026-09-26")
    canvas.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


story = []
story += [
    P("ESIM Bench Test", title),
    P("Evaporative System Integrity Module: vacuum switch, seal and relief check", subtitle),
    Spacer(1, 4),
    P("2018 Alfa Romeo Stelvio 2.0T  |  VIN ZASFAKPN5J7B88115  |  about 142,290 km", small),
    Spacer(1, 10),
]

story += [P("Why this test", h2),
          P("The ECU has stored <b>P0455</b> (large leak), <b>P0456</b> (small leak) and "
            "<b>P0440</b> (EVAP system) repeatedly. Every inexpensive cause has already been "
            "ruled out. The ESIM is the part that tells the ECU whether the EVAP system is "
            "sealed. If its switch never closes, or its internal seal leaks, the ECU records a "
            "leak even when every hose is tight, and all three codes can come from that one "
            "fault. This test decides whether the ESIM is at fault before any part is bought."),
          Spacer(1, 6)]

story += [P("Already checked on this car", h3),
          grid([["Check", "Result"],
                ["EVAP air filter", "Clear and clean"],
                ["Recirculation-line mid-point quick-connect", "Seated and latched"],
                ["Liquid fuel at the canister", "None"],
                ["Refuelling habit", "Stops at first click; no topping off"],
                ["Filling symptoms, last 2 fills", "No hiss, no smell, no slow filling"],
                ["Water ingress at the canister", "None found"],
                ["Purge valve (engine bay)", "Replaced with a new unit; clicks"],
                ["Fuel cap", "New"],
                ["Check-engine light", "Off. The ECU stored and confirmed the codes without "
                 "requesting it (status 0x4D, light bit clear), so the light is not a guide "
                 "for this fault."]],
               [2.8 * inch, 4.2 * inch]),
          Spacer(1, 8)]

story += [boxed([P("<b>Source note.</b> FCA bulletin 9100469 confirms the ESIM is a separate "
                   "part from the vapour canister and says to replace only the ESIM when the "
                   "fault is in the ESIM. No factory bench-test procedure, switch threshold or "
                   "connector pinout for this car was obtainable. The steps below are general "
                   "bench practice for this type of vacuum switch. <b>Compare against a new "
                   "ESIM</b> wherever a number matters.", cell)], SHADE, RULE)]

story += [P("Safety", h2),
          boxed([bullets([
              "The ESIM and canister hold fuel vapour. Work outdoors or in a ventilated bay, "
              "away from sparks, flames and running engines.",
              "Ignition OFF before unplugging the connector.",
              "Apply vacuum and pressure <b>gently</b>. The switch acts at a very small vacuum; "
              "a hard pump stroke can damage the diaphragm.",
              "Never use shop air or any regulated air line on the ESIM.",
          ], cell)], WARN_BG, WARN_EDGE)]

story += [P("Tools", h2),
          bullets([
              "Multimeter set to ohms or continuity.",
              "Hand vacuum pump with a short length of rubber hose.",
              "A low-range vacuum gauge or a simple water manometer (a clear U-tube of water). "
              "A hand pump's inHg dial is too coarse to see where this switch closes.",
              "Rubber vacuum caps, a flat trim tool, and a torch.",
              "Optional but best: a new ESIM to test side by side.",
          ])]

story += [P("Procedure", h2)]
story += [step(1, "Access and inspect the connector", [bullets([
    "Remove the driver-side rear wheel liner. The ESIM sits on the vent side of the canister.",
    "With the ignition off, unplug the ESIM connector.",
    "Look for green corrosion, water, pushed-back or bent pins, and a loose lock. The ESIM "
    "sits in road spray; a poor connection alone makes the ECU read the switch as open.",
])])]
story += [step(2, "Remove the ESIM or free its ports", [bullets([
    "Remove it, or disconnect both hoses. Before disconnecting, <b>mark which port faces the "
    "canister</b> and which faces the fresh-air filter.",
])])]
story += [step(3, "Switch at rest", [bullets([
    "Put the meter across the switch terminals with the ESIM at atmospheric pressure.",
    "<b>Expected: open</b> (OL or no continuity).",
    "If the connector has more than two pins, find the pair whose reading changes in Step 4.",
])])]
story += [step(4, "Vacuum test on the canister-side port", [
    P("Fresh-air side left open to air. Pump vacuum into the canister-side port slowly.", base),
    bullets([
        "<b>Switch closes:</b> the meter snaps to near 0 ohms at a small vacuum. This is the "
        "ECU's 'system sealed' signal.",
        "<b>Hold:</b> stop pumping. The vacuum should hold steady and the switch stay closed. "
        "This tests the internal seal.",
        "<b>Release:</b> let the vacuum go. The switch should open again.",
        "Note the gauge reading at which it closes, and whether the vacuum falls while holding.",
    ])])]
story += [step(5, "Pressure relief check", [bullets([
    "Apply gentle low pressure to the canister-side port.",
    "<b>Expected:</b> it vents through to the fresh-air side and does not hold. This confirms "
    "the ESIM is not stuck shut, which matches the normal fill-ups on this car.",
])])]
story += [step(6, "Tap and wiggle", [bullets([
    "With the meter connected and the switch held closed by vacuum, tap the body lightly and "
    "wiggle the terminals. Watch for the reading flickering or dropping out.",
])])]

story += [P("Reading the result", h2),
          grid([["What you see", "What it means", "Next step"],
                ["Switch never closes", "Failed switch. The ECU sees a leak on a tight system, "
                 "which fits all three codes.", "Replace the ESIM only (TSB 9100469)."],
                ["Closes, but the vacuum bleeds away", "Internal seal leaking: a real leak "
                 "inside the ESIM.", "Replace the ESIM only."],
                ["Closes only at a much higher vacuum than a new unit", "Sluggish switch; can "
                 "fail the engine-off test intermittently.", "Replace the ESIM."],
                ["Reading flickers when tapped", "Failing contacts.", "Replace the ESIM; "
                 "check the harness connector too."],
                ["Behaves like a new unit on every step", "ESIM exonerated. The leak is "
                 "elsewhere.", "Run the smoke test by section: canister first."]],
               [2.1 * inch, 2.7 * inch, 2.2 * inch])]

story += [P("Record sheet", h2),
          P("Fill this in during the test. These values go into the cuore evidence gate: the "
            "readings are the measurement, and a clean pass on every step is the disconfirming "
            "test that clears the ESIM.", small),
          Spacer(1, 6),
          grid([["Item", "Result"],
                ["Date / odometer", " "],
                ["Connector condition", " "],
                ["Step 3: resting reading (should be open)", " "],
                ["Step 4: vacuum at which the switch closed", " "],
                ["Step 4: vacuum held? (drop over 1 minute)", " "],
                ["Step 4: switch reopened on release?", " "],
                ["Step 5: vents under light pressure?", " "],
                ["Step 6: any flicker when tapped?", " "],
                ["New-unit comparison (if available)", " "],
                ["Conclusion", " "]],
               [3.3 * inch, 3.7 * inch], row_h=0.36 * inch)]

story += [P("After the test", h2),
          bullets([
              "<b>If the ESIM failed:</b> replace only the ESIM, clear the codes, then drive "
              "several times with fuel between about 15 and 85 percent, including cold starts. "
              "Confirm with cuore's verify_repair, which reads whether each leak test has re-run "
              "and passed. The check-engine light cannot confirm it on this car.",
              "<b>If the ESIM passed:</b> it is exonerated. Run the smoke test by section "
              "(docs/research/EVAP_SMOKE_TEST.md), introducing smoke at the canister purge port "
              "rather than the fuel filler, so the new cap is tested where it sits.",
              "A road test alone cannot confirm a small-leak repair (TSB 18-048-23).",
          ])]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.75 * inch,
                        rightMargin=0.75 * inch, topMargin=0.7 * inch,
                        bottomMargin=0.8 * inch, title="Stelvio ESIM Bench Test",
                        author="cuore / Claude", subject="ESIM vacuum switch bench test")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
