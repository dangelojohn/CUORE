"""One-page Service Hub sheet for the 2018 Stelvio 2.0T (cuore data, refreshed 2026-10-07)."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio Service Hub (1 page).pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6")
OPEN_BG, OK_BG = colors.HexColor("#fbeaea"), colors.HexColor("#e8f2ec")

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.0, leading=8.6, textColor=INK)
bh = ParagraphStyle("bh", parent=b, fontName="Helvetica-Bold", fontSize=8.6, leading=10.4, textColor=ACCENT)
sm = ParagraphStyle("sm", parent=b, fontSize=6.4, leading=7.6, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)

# (section, key specs, last known service, open items / flags, cuore page)
CARDS = [
    ("Engine oil & service",
     "0W-30 full synthetic, FCA MS-13340 (CORROB.). 5.5 qt / 5.2 L with filter (SINGLE). Filter Mopar "
     "4892339 (not 68191349 = V6). Drain plug 20 Nm, filter cap 25 Nm (SINGLE). Shop interval 8,000 mi / 12 mo (CORROB.); FCA max 10,000 mi / 1 yr, severe duty 4,000 mi (CONFIRM.).",
     "Oil change reset logged in MES 2026-09-15 (no odometer). Turbo replaced 2025-10-14 (overboost counter reset).",
     "Record the oil change details in cuore (brand, filter, torques applied, condition).",
     "/oil-change"),
    ("Routine maintenance",
     "Owner's manual (CONFIRM.): air filter and spark plugs due every 30k mi; car is near 88,400 mi (142,290 km), "
     "approaching the 90k mi mark for both. Spark plug NGK 90219 / Mopar 68292346AA (CORROB.), 19.5 Nm. Cabin "
     "filter 20k mi / 2 yr. Coolant OAT MS.90032, 8.8 L engine circuit + separate intercooler circuit, 150k mi / "
     "15 yr. Brake fluid DOT 4 MS.90039 every 2 yr (CONFIRM.). Drive belt 36k mi / 4 yr (18k mi / 2 yr severe "
     "duty). A/C R-1234yf, annual. PCV, throttle body, boost hoses: UNKNOWN.",
     "Oil-change reset only (MES 2026-09-15). No maintenance items recorded yet.",
     "Record a baseline visit (what is known, with odometer) so due dates can be calculated, unless records show "
     "these were already done. Air filter, spark plugs and drive belt are likely due soon.",
     "/maintenance"),
    ("Brakes, wheels & tyres",
     "Front rotor 330 x 28 mm new, 25.5 mm min (SINGLE); rear min UNKNOWN (read cast MIN TH). DOT 4, MS.90039, change every 2 yr (CONFIRM.). "
     "235/60R18 or 235/55R19 (CORROB.). Lugs 121 Nm / 89 lb-ft (CORROB.). Pressures: read the door placard.",
     "No brake/tyre record yet.",
     "Rear pads: put the electric park brake in service mode first (MES or wiTECH).",
     "/brakes-tires"),
    ("Transmission (ZF 8HP)",
     "ZF LifeguardFluid 8 / Mopar 68218925AA, NOT ATF+4. Level check only at 30-50 C (CONFIRM.). Pan/filter "
     "bolts 10 Nm (CONFIRM.). Drain/fill plug torques UNKNOWN. Relearn adaptations after service.",
     "No transmission service on record.",
     "TSB 21-035-20 TCM flash applies to this VIN: check on wiTECH.",
     "/drivetrain/transmission"),
    ("Transfer case (Q4)",
     "Tutela, FIAT 9.55550-DA11 (CORROB.). Capacity ~0.7 L, sources conflict. Plug torques UNKNOWN. "
     "Replace oil at 80k mi / 128k km / 8 yr (CONFIRM., owner's manual).",
     "No record.", "DUE: car is past 128,000 km. Replace transfer case oil unless records show it was done.",
     "/drivetrain/transfer_case"),
    ("Differentials",
     "Front 75W-80 GL-5 DA10, 0.5 L; rear 75W-85 DA9, 0.9-1.1 L by unit (SINGLE). Rear plugs 26 Nm (SINGLE); "
     "front plugs UNKNOWN. Which rear unit (open/LSD/eLSD) this VIN has: UNKNOWN.",
     "No record.", "", "/drivetrain/differentials"),
    ("Driveline",
     "Hub nut 52 lb-ft + 47 deg, SINGLE-USE (SINGLE). Hub mount bolts 74 lb-ft (SINGLE). Propshaft flange "
     "UNKNOWN (online 72-101 lb-ft figure is from a 1970s Alfa: do not use).",
     "No record.", "", "/drivetrain/driveline"),
    ("Mounts",
     "Engine mount bolts 22-27 Nm; dogbone 25-31 Nm, single-use (SINGLE). Strut-to-lower-arm and upper-arm "
     "torques UNKNOWN (fabricated values withdrawn in fact-check).",
     "No record.", "", "/drivetrain/mounts"),
    ("EVAP & emissions",
     "P0455, P0456, P0440 chronic since 2025-09. System sealed (3 smoke tests); canister, ESIM, cap, filter, "
     "purge valve all new. ECM software 52170619 / P235QB39. P0455 / P0440 freeze frames: fuel 94% / 92% (EVAP "
     "monitor needs 15-85%).",
     "P0440 recurred in the 2026-09-28 and 09-29 scans after earlier clears; cleared again 2026-09-29 10:46 "
     "(SCAN_2609291046). The 2026-10-04 clean session/scan came after that clear, before any monitor could "
     "re-run: repair is UNVERIFIED, not confirmed.",
     "wiTECH flash check (TSB 18-030-17), then Test A (ESIM switch). Check recalls 25V586000 (fuel pump) and "
     "18V636000 (ECM software). Do not clear codes again; verify with a readiness read after drives with fuel "
     "15-85%.",
     "/tree, /dashboard"),
    ("Network / body / ADAS",
     "Network: U0100 (ECM comms), U1713 (BCM), B1040 (RFHUB), C141B (DASM camera) -- chronic since 2026-06/"
     "08-27. Separate: B1176 (rear left window riser, BCM), chronic since 2026-08-27.",
     "Network codes present in the 2026-09-28 scan, gone by 2026-09-29: one power/bus event, not per-module "
     "faults. B1176 persisted through 2026-09-29 -- a separate, unresolved body fault.",
     "Confirm network codes stay clear next scan. B1176: grey-cable read of ABS/HALF, then the window-riser "
     "fault tree (separate from the network-cascade steps).",
     "/tree"),
]

rows = [[Paragraph(h, ParagraphStyle("hh", parent=b, fontName="Helvetica-Bold")) for h in
         ("Section", "Key specs (confidence)", "Last known service", "Open items", "cuore page")]]
st = [("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
      ("BACKGROUND", (0, 0), (-1, 0), SHADE),
      ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
      ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
for i, (name, specs, last, opens, page) in enumerate(CARDS, start=1):
    rows.append([Paragraph(name, bh), Paragraph(specs, b), Paragraph(last, b),
                 Paragraph(opens or "-", b), Paragraph(f"/v/&lt;VIN&gt;{page}" if page.startswith("/") and "," not in page
                                                       else page, sm)])
    if opens:
        st.append(("BACKGROUND", (3, i), (3, i), OPEN_BG))

t = Table(rows, colWidths=[1.05 * inch, 2.85 * inch, 1.35 * inch, 1.55 * inch, 0.75 * inch], repeatRows=1)
t.setStyle(TableStyle(st))

story = [Paragraph("Service Hub - 2018 Alfa Romeo Stelvio 2.0T", title),
         Paragraph("VIN ZASFAKPN5J7B88115  |  about 142,290 km  |  Q4 AWD, ZF 8HP  |  cuore, 2026-10-07", sm),
         Spacer(1, 6), t, Spacer(1, 6),
         Paragraph("Confidence: CONFIRM. = manufacturer document; CORROB. = two independent sources; SINGLE = one "
                   "source; UNKNOWN = use the FCA service manual (TechAuthority). Torque data fact-checked "
                   "2026-09-26. Full torque tables: 'Stelvio Torque Settings' and 'Stelvio Drivetrain Torque "
                   "Settings' PDFs, and the cuore torque page.", sm)]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "cuore Service hub: /v/ZASFAKPN5J7B88115/service-hub  |  record every job "
                 "in cuore so the next visit sees it")
    c.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                        topMargin=0.5 * inch, bottomMargin=0.55 * inch, title="Stelvio Service Hub")
doc.build(story, onFirstPage=foot, onLaterPages=foot)
print(OUT)
