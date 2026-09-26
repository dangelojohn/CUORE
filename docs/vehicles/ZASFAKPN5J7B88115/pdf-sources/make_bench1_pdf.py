"""One-page ESIM bench test for the 2018 Stelvio."""
from pathlib import Path

HERE = Path(__file__).parent
exec((HERE / "make_testa_pdf.py").read_text(encoding="utf-8").split("\ns = [", 1)[0])

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Spacer

OUT = r"C:\Users\User\Desktop\Stelvio ESIM Bench Test (1 page).pdf"
t = ParagraphStyle("tt", parent=title, fontSize=17, leading=20)
hh = ParagraphStyle("hh", parent=h2, fontSize=11.5, leading=14, spaceBefore=7, spaceAfter=3)
b9 = ParagraphStyle("b9", parent=base, fontSize=9.2, leading=12.1)
c8 = ParagraphStyle("c8", parent=cell, fontSize=8.6, leading=11)


def g(rows, widths, row_h=None):
    data = [[P(c, cellb if r == 0 else c8) for c in row] for r, row in enumerate(rows)]
    heights = None if row_h is None else [None] + [row_h] * (len(rows) - 1)
    tb = Table(data, colWidths=widths, rowHeights=heights)
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return tb


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(0.6 * inch, 0.4 * inch, "General bench practice; no FCA spec or pinout for this ESIM was obtainable  |  "
                 "VIN ZASFAKPN5J7B88115  |  2026-09-26")
    c.restoreState()


s = [P("ESIM Bench Test", t),
     P("2018 Stelvio 2.0T  |  ESIM Mopar 04861961AD, fitted new 2026-09-02  |  EVAP smoke-tested sealed 3 times",
       small), Spacer(1, 5),
     box([P("<b>Purpose:</b> confirm the new ESIM's switch closes under a small vacuum, its seal holds, and it "
            "vents under light pressure. Do <b>wiTECH Test A first</b> if you can: it tests the ESIM in place "
            "plus its wiring. Bench-test only if Test A fails or no ESIM parameter exists in wiTECH. "
            "Compare against a new ESIM where a number matters.", c8)], KEY_BG, KEY_EDGE),
     Spacer(1, 4),
     box([P("<b>Safety:</b> fuel vapour, no sparks or flames; ignition OFF before unplugging; apply vacuum and "
            "pressure <b>gently</b>; never shop air.  <b>Tools:</b> multimeter (ohms), hand vacuum pump, "
            "low-range gauge or water manometer, rubber caps.", c8)], WARN_BG, WARN_EDGE)]

s += [P("Steps", hh), bullets([
    "<b>Access:</b> remove the driver-side rear wheel liner; unplug the ESIM (ignition off). Inspect the "
    "connector: corrosion, water, bent or pushed-back pins.",
    "<b>Remove</b> the ESIM or free both hoses. Mark the <b>canister-side</b> and <b>fresh-air</b> ports.",
    "<b>At rest:</b> meter across the switch pins: expect <b>open</b>. (More than 2 pins: find the pair "
    "that changes in the next step.)",
    "<b>Vacuum</b> on the canister-side port, fresh-air side open: pump slowly. Switch should snap "
    "<b>closed</b> (near 0 ohms) at a small vacuum. Note the gauge reading.",
    "<b>Hold</b> 1 minute: vacuum steady, switch stays closed (seal test).",
    "<b>Release:</b> switch opens again.",
    "<b>Pressure:</b> gentle puff into the canister-side port: it should vent through, not hold.",
    "<b>Tap and wiggle</b> while held closed: no flicker.",
], b9)]

s += [P("Result", hh),
      g([["You see", "Means", "Next"],
         ["Never closes", "Failed switch: ECU sees a leak on a sealed system", "Replace ESIM only (TSB 9100469)"],
         ["Closes, vacuum bleeds away", "Internal seal leak", "Replace ESIM only"],
         ["Closes only at much higher vacuum than new", "Sluggish switch", "Replace ESIM"],
         ["Flickers when tapped", "Failing contacts", "Replace ESIM; check harness connector"],
         ["Passes every step", "ESIM good", "Wiring (Test B) or ECU calibration (flash check)"]],
        [2.2 * inch, 2.6 * inch, 2.4 * inch])]

s += [P("Record", hh),
      g([["Item", "Result"],
         ["Date / connector condition", " "],
         ["At rest (open?)", " "],
         ["Vacuum where it closed", " "],
         ["Held 1 min? / reopened on release?", " "],
         ["Vents under light pressure? / flicker?", " "],
         ["New-unit comparison / conclusion", " "]],
        [2.8 * inch, 4.4 * inch], row_h=0.29 * inch)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                        topMargin=0.5 * inch, bottomMargin=0.6 * inch,
                        title="Stelvio ESIM Bench Test (1 page)", author="cuore / Claude")
doc.build(s, onFirstPage=foot, onLaterPages=foot)
print(OUT)
