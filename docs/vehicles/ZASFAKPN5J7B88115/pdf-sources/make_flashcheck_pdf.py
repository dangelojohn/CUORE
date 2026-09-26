"""One-page wiTECH ECM flash check for the 2018 Stelvio (from CSN W05 / TSB 18-026-20)."""
from pathlib import Path

HERE = Path(__file__).parent
exec((HERE / "make_testa_pdf.py").read_text(encoding="utf-8").split("\ns = [", 1)[0])

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Spacer

OUT = r"C:\Users\User\Desktop\Stelvio wiTECH Flash Check (1 page).pdf"
t = ParagraphStyle("tt", parent=title, fontSize=17, leading=20)
hh = ParagraphStyle("hh", parent=h2, fontSize=11.5, leading=14, spaceBefore=8, spaceAfter=3)
b9 = ParagraphStyle("b9", parent=base, fontSize=9.2, leading=12.2)


def footer3(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(0.6 * inch, 0.4 * inch, "Steps from FCA CSN W05 (Mar 2020) and TSB 18-026-20 (Mar 25, 2020), 2018 GU Stelvio "
                 "2.0L EC2  |  VIN ZASFAKPN5J7B88115  |  2026-09-26")
    c.restoreState()


s = [P("wiTECH ECM Flash Check", t),
     P("2018 Stelvio 2.0T  |  VIN ZASFAKPN5J7B88115  |  Installed: ECU software <b>52170619</b>, supplier "
       "software <b>P235QB39</b> ver 0000, HW MM10JAHW232", small),
     Spacer(1, 6)]

s += [box([bullets([
    "<b>Charger on:</b> hold <b>13.2-13.5 V</b> (stand-alone voltmeter); timer to continuous. Too high: "
    "switch on lights or blower.",
    "<b>Only wiTECH on the OBD port</b> (MES and cuore disconnected). Laptop on mains, sleep off, stable "
    "internet.",
    "<b>Never interrupt a flash.</b> If it aborts, restart it.",
], b9)], WARN_BG, WARN_EDGE)]

s += [P("Check", hh), bullets([
    "Connect the wiTECH interface; ignition <b>RUN</b>, engine off.",
    "Sign in to wiTECH 2; select the vehicle; confirm the VIN.",
    "<b>Topology</b> > <b>ECM</b> > <b>Flash</b> tab.",
    "Compare <b>Current ECU Part Number</b> with <b>New ECU Part Number</b> and write both below.",
], b9)]

s += [grid([["If the numbers are...", "Then"],
            ["<b>The same</b>", "ECM is on the latest calibration. <b>Do not flash.</b> Software lead closed: go "
             "to wiTECH Test A (ESIM switch)."],
            ["<b>Different</b>", "A newer calibration exists: continue below."]],
           [1.7 * inch, 5.3 * inch])]

s += [P("Flash (only if different)", hh), bullets([
    "Tick the flash agreement, select <b>Flash ECU</b>, follow the screen (about 8 minutes). Watch the volts.",
    "<b>BCM</b> > <b>Misc. Functions</b> > <b>PROXI Alignment</b>.",
    "<b>View DTCs</b>; Topology > Action Items > <b>All DTCs</b> > <b>Clear All DTCs</b>.",
    "<b>ECM</b> > <b>Misc. Functions</b> > <b>Phonic Wheel Replacement</b>; follow prompts. "
    "(If skipped or done wrong, <b>P1300</b> stays active.)",
    "Clear All DTCs again. Re-open ECM Flash tab: Current now equals New.",
    "<b>BCM Flash tab:</b> compare and update the BCM too if different (TSB 18-026-20).",
    "Ignition OFF, disconnect, charger off.",
], b9)]

s += [P("Record", hh),
      grid([["Item", "Result"],
            ["Date / odometer", " "],
            ["ECM Current ECU Part Number", " "],
            ["ECM New ECU Part Number", " "],
            ["Flashed? / part number after", " "],
            ["PROXI + Phonic Wheel done / BCM current?", " "]],
           [2.8 * inch, 4.2 * inch], row_h=0.3 * inch),
      Spacer(1, 5),
      P("After a flash: drive several days (fuel 15-85 %, cold starts), then cuore <b>verify_repair</b> for "
        "P0455/P0456/P0440; 'passed since clear' on all three confirms it. The check-engine light cannot "
        "confirm it on this car. Enter the result on cuore's dealer-results page.", small)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                        topMargin=0.5 * inch, bottomMargin=0.6 * inch,
                        title="Stelvio wiTECH Flash Check", author="cuore / Claude")
doc.build(s, onFirstPage=footer3, onLaterPages=footer3)
print(OUT)
