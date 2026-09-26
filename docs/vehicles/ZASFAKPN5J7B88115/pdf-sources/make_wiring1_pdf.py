"""One-page ESIM wiring test for the 2018 Stelvio."""
from pathlib import Path

HERE = Path(__file__).parent
exec((HERE / "make_testa_pdf.py").read_text(encoding="utf-8").split("\ns = [", 1)[0])

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Spacer

OUT = r"C:\Users\User\Desktop\Stelvio ESIM Wiring Test (1 page).pdf"
t = ParagraphStyle("tt", parent=title, fontSize=17, leading=20)
hh = ParagraphStyle("hh", parent=h2, fontSize=11.2, leading=13.5, spaceBefore=6, spaceAfter=2)
b9 = ParagraphStyle("b9", parent=base, fontSize=8.9, leading=11.6)
c8 = ParagraphStyle("c8", parent=cell, fontSize=8.4, leading=10.6)


def g(rows, widths, row_h=None):
    data = [[P(c, cellb if r == 0 else c8) for c in row] for r, row in enumerate(rows)]
    heights = None if row_h is None else [None] + [row_h] * (len(rows) - 1)
    tb = Table(data, colWidths=widths, rowHeights=heights)
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    return tb


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(0.6 * inch, 0.4 * inch, "Pins, colours and reference voltage come from the FCA diagram for this VIN "
                 "(see the Wiring Diagram Lookup PDF)  |  VIN ZASFAKPN5J7B88115  |  2026-09-26")
    c.restoreState()


s = [P("ESIM Wiring Test", t),
     P("2018 Stelvio 2.0T  |  Does the ESIM switch signal reach the ECU intact?", small), Spacer(1, 4),
     box([P("<b>Do first:</b> wiTECH <b>flash check</b>, then <b>Test A</b> (vacuum on the ESIM while watching the "
            "ECU's switch reading). If Test A passes, the wiring is good. Run this sheet only if Test A never "
            "changes or flickers. No ESIM circuit code (e.g. P24D6) has set, so look for <b>intermittent / "
            "high-resistance</b> faults rather than a clean break.", c8)], KEY_BG, KEY_EDGE),
     Spacer(1, 3),
     box([P("<b>Safety:</b> back-probe only (never spread terminals); battery negative OFF before unplugging the "
            "ECU; fused jumper; fuel vapour at the canister, no sparks.", c8)], WARN_BG, WARN_EDGE)]

s += [P("From the diagram (fill in first)", hh),
      g([["ESIM connector / signal pin, colour", "Ground pin, colour / ground point", "ECU connector + pin / reference V"],
         [" ", " ", " "]], [2.43 * inch, 2.43 * inch, 2.43 * inch], row_h=0.32 * inch)]

s += [P("Steps", hh), bullets([
    "<b>B1 Connector:</b> ignition OFF, unplug the ESIM (driver-side rear wheel well). Look for corrosion, water, "
    "bent or pushed-back pins, loose terminal grip. Check the harness for chafe on the wheel-well edge.",
    "<b>B2 Signal reference:</b> connector unplugged, ignition RUN. Harness-side signal pin to chassis ground: "
    "expect the diagram's reference voltage. 0 V = open or ECU not driving it. Battery voltage where a low "
    "reference is expected = short to power.",
    "<b>B3 Ground:</b> harness-side ground pin to battery negative: near 0 V (ignition RUN) and a few ohms or "
    "less (ignition OFF).",
    "<b>B4 End to end:</b> battery negative disconnected, ECU connector unplugged. Each wire ESIM pin to ECU pin: "
    "a fraction of an ohm. Several ohms = high resistance; OL = break. Each wire to ground and to B+: open. "
    "Reconnect ECU, battery last.",
    "<b>B5 Jumper:</b> battery on, ignition RUN, ESIM unplugged, wiTECH ECM data display open. Fused jumper "
    "from signal pin to ground pin (= closed switch). wiTECH should show <b>closed</b>. Wiggle the harness "
    "along its route while watching.",
], b9)]

s += [P("Result", hh),
      g([["Finding", "Meaning", "Next"],
         ["B5 shows closed, Test A failed", "Wiring and ECU input good", "ESIM switch/contacts: bench test or replace"],
         ["B5 stays open", "Wiring or ECU input", "Jumper at the ECU end to split wire from ECU"],
         ["B2/B3/B4 out of range", "Open, short or high resistance", "Repair that circuit (FCA terminal/splice)"],
         ["Flicker on wiggle", "Intermittent connection", "Repair connector or chafe point"]],
        [2.1 * inch, 2.3 * inch, 2.9 * inch])]

s += [P("Record", hh),
      g([["Test", "Result", "Test", "Result"],
         ["B1 connector", " ", "B4 signal wire ohms / to gnd / to B+", " "],
         ["B2 signal reference V", " ", "B4 ground wire ohms", " "],
         ["B3 ground V / ohms", " ", "B5 wiTECH state / wiggle", " "]],
        [1.55 * inch, 2.0 * inch, 1.75 * inch, 2.0 * inch], row_h=0.3 * inch),
      Spacer(1, 3),
      P("After a repair: clear codes, drive several days (fuel 15-85 %, cold starts), then cuore verify_repair "
        "for P0455/P0456/P0440 ('passed since clear' on all three). The check-engine light cannot confirm it.", small)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                        topMargin=0.5 * inch, bottomMargin=0.6 * inch,
                        title="Stelvio ESIM Wiring Test (1 page)", author="cuore / Claude")
doc.build(s, onFirstPage=foot, onLaterPages=foot)
print(OUT)
