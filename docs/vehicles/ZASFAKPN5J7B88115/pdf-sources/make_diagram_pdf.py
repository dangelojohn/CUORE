"""How to find and read the ESIM wiring diagram for the 2018 Stelvio."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("sty", HERE / "make_testa_pdf.py")
src = (HERE / "make_testa_pdf.py").read_text(encoding="utf-8")
# Reuse the styling helpers only (everything above the first 's = [' line).
exec(src.split("\ns = [", 1)[0])

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Spacer

OUT = r"C:\Users\User\Desktop\Stelvio ESIM Wiring Diagram Lookup.pdf"


def footer2(c, doc):
    c.saveState()
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawString(0.75 * inch, 0.5 * inch, "Stelvio 2.0T ESIM wiring diagram lookup  |  VIN ZASFAKPN5J7B88115  |  2026-09-26")
    c.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    c.restoreState()


s = [P("ESIM Wiring Diagram Lookup", title),
     P("Find the ESIM circuit for this VIN and copy what the tests need", sub), Spacer(1, 4),
     P("2018 Alfa Romeo Stelvio 2.0T (GU)  |  VIN ZASFAKPN5J7B88115", small), Spacer(1, 10)]

s += [box([P("<b>Why.</b> The ESIM wiring test and wiTECH Test A need this car's exact ESIM connector, "
             "pin numbers, wire colours, ECU pin and ground point. Those are only in FCA service "
             "information for the VIN. This sheet is how to find them and what to write down.", cell)],
          KEY_BG, KEY_EDGE),
      Spacer(1, 6),
      box([P("<b>Menu names vary.</b> FCA's service information and wiTECH change between releases, and "
             "Alfa Romeo content may be organised differently from Chrysler/Jeep content. Treat the paths "
             "below as where to look, not exact clicks. No pin numbers are given here on purpose: copy them "
             "from the diagram for this VIN.", cell)], WARN_BG, WARN_EDGE)]

s += [P("Where to find it", h2)]
s += [step(1, "Route 1: from the fault code in wiTECH (quickest)", [bullets([
    "Connect wiTECH, select the car, open the <b>ECM</b>, then its DTC list.",
    "Select <b>P0456</b> (or P0455 / P0440) and open its <b>diagnostic procedure</b>.",
    "FCA diagnostic procedures for EVAP codes usually include a <b>schematic</b> of the circuits the "
    "test uses, with connector views. Look for the ESIM (Evaporative System Integrity Module) and the "
    "ECU pins it connects to.",
])])]
s += [step(2, "Route 2: FCA service information (full wiring diagrams)", [bullets([
    "FCA's service information for independent shops is <b>TechAuthority</b> (techauthority.com); "
    "dealers use DealerCONNECT Service Library. Your wiTECH account may or may not include service "
    "information; if not, TechAuthority sells short subscriptions.",
    "Select the vehicle by <b>VIN</b> (ZASFAKPN5J7B88115), so the diagram matches this build.",
    "Open the <b>wiring diagrams</b> and search for: <b>ESIM</b>, <b>Evaporative System Integrity "
    "Module</b>, <b>EVAP</b>, <b>leak detection</b>, <b>canister</b>.",
    "Also open the <b>connector pin-out / connector views</b> for the ESIM connector and the ECU "
    "connector, and the <b>ground locations</b> page for the ground the ESIM uses.",
])])]
s += [step(3, "Route 3: if neither is available", [bullets([
    "Ask a dealer service advisor to print the ESIM circuit page and the ESIM and ECU connector views "
    "for the VIN. It is a two-minute lookup for them.",
])])]

s += [P("How to read it", h2),
      bullets([
          "Follow each wire from the ESIM connector to where it ends: one should go to an <b>ECU pin</b> "
          "(the switch <b>signal</b>), and one to a <b>ground</b> (a ground point or an ECU sensor-ground "
          "pin). Some designs use more pins; note every one.",
          "Write down, for each ESIM pin: pin number, wire colour code, circuit name, and the far end "
          "(ECU connector and pin, or ground point ID).",
          "Note any <b>inline connector</b> the wires pass through on the way (a common corrosion point "
          "near the wheel well).",
          "If the diagram or its circuit description gives the switch's <b>reference voltage</b> or state "
          "logic (closed = sealed), note it: Test B step B2 compares against it.",
          "Take a photo or print of the page for the job file.",
      ])]

s += [P("Fill-in sheet (copy into the wiring test PDF)", h2),
      grid([["Item", "From the diagram for this VIN"],
            ["Source (wiTECH procedure / TechAuthority page / dealer print)", " "],
            ["ESIM connector ID and location", " "],
            ["ESIM pin 1: colour / circuit / far end", " "],
            ["ESIM pin 2: colour / circuit / far end", " "],
            ["Other ESIM pins (if any)", " "],
            ["ECU connector and signal pin", " "],
            ["Ground: ground point ID or ECU sensor-ground pin", " "],
            ["Inline connectors on the route", " "],
            ["Switch reference voltage / logic (if stated)", " "],
            ["wiTECH parameter name for the switch (Test A)", " "]],
           [3.2 * inch, 3.8 * inch], row_h=0.36 * inch)]

s += [P("Then", h2),
      bullets(["Run <b>wiTECH Test A</b> (vacuum on the ESIM while watching the ECU's switch reading).",
               "If Test A fails, run the <b>ESIM Wiring Test</b> PDF's Test B with the pins above.",
               "Record results in cuore so the evidence gate and history keep them."])]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.8 * inch,
                        title="Stelvio ESIM Wiring Diagram Lookup", author="cuore / Claude")
doc.build(s, onFirstPage=footer2, onLaterPages=footer2)
print(OUT)
