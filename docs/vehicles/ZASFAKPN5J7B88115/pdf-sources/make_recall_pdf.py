"""Recall and campaign sheet for the 2018 Stelvio, from the NHTSA recalls API."""
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

OUT = r"C:\Users\User\Desktop\Stelvio Recalls and Campaigns.pdf"
SRC = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "nhtsa_recalls_2018_stelvio.json")
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6")
HOT = colors.HexColor("#fbeaea")

ss = getSampleStyleSheet()
base = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=INK)
small = ParagraphStyle("s", parent=base, fontSize=8.5, leading=11.5, textColor=MUTED)
title = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24)
sub = ParagraphStyle("st", parent=base, fontSize=11, leading=15, textColor=MUTED)
h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                    textColor=ACCENT, spaceBefore=14, spaceAfter=6)
cell = ParagraphStyle("c", parent=base, fontSize=8.5, leading=11)
cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")


def P(t, s=base):
    return Paragraph(t, s)


def bullets(items):
    return ListFlowable([ListItem(P(t), leftIndent=14) for t in items], bulletType="bullet",
                        start="-", leftIndent=14, bulletFontSize=10)


def table(rows, widths, hot_rows=()):
    data = [[P(c, cellb if r == 0 else cell) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("BACKGROUND", (0, 0), (-1, 0), SHADE),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for r in hot_rows:
        st.append(("BACKGROUND", (0, r), (-1, r), HOT))
    t.setStyle(TableStyle(st))
    return t


def footer(c, doc):
    c.saveState()
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawString(0.75 * inch, 0.5 * inch,
                 "2018 Stelvio 2.0T  |  VIN ZASFAKPN5J7B88115  |  NHTSA recalls API, retrieved 2026-09-26")
    c.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    c.restoreState()


recs = json.load(open(SRC, encoding="utf-8"))["results"]

# Applicability to THIS car (2018 GU Stelvio, 2.0L, not Quadrifoglio), judged from each
# summary's own scope. VIN-level inclusion and completion are NOT public.
APPLIES = {
    "25V586000": ("Yes: 2018-2019 Stelvio", "HIGH - loss of drive power risk; also replaces the "
                  "fuel delivery module, where the EVAP internal vapour line connects (TSB 9100471)"),
    "18V636000": ("Yes: 2018 Stelvio with 2.0L", "HIGH for this diagnosis - remedy is an ECM "
                  "software update; do with the ECM flash check"),
    "19V551000": ("Yes: 2018-2019 Stelvio", "Relevant to EVAP: BCM fuel-level reading; EVAP "
                  "tests depend on fuel level"),
    "18V205000": ("Yes: 2018 Stelvio", "Relevant to network codes: water into BCM connectors"),
    "18V203000": ("Yes: 2018 Stelvio", "Liftgate connector water protection"),
    "24V510000": ("Yes: 2018-2025 Stelvio", "Seat belt buckle sensor connection (airbag)"),
    "19V148000": ("If fitted with adaptive cruise", "BSM software, ACC disable"),
    "18V147000": ("Yes: 2018 Stelvio (certain)", "Wiper motor replacement"),
    "17V823000": ("Only early-build 2018 cars", "Brake fluid contamination inspection"),
    "23V382000": ("Only with carbon ceramic brakes", "Almost certainly not this car"),
    "18V635000": ("No: Quadrifoglio only", "Not applicable to the 2.0T"),
}
ORDER = ["25V586000", "18V636000", "19V551000", "18V205000", "18V203000", "24V510000",
         "19V148000", "18V147000", "17V823000", "23V382000", "18V635000"]
by = {r["NHTSACampaignNumber"]: r for r in recs}

s = [P("Recalls and Campaigns", title),
     P("2018 Alfa Romeo Stelvio 2.0T (GU)  |  VIN ZASFAKPN5J7B88115", sub), Spacer(1, 10)]

s += [P("Read this first", h2),
      bullets([
          "This list is every NHTSA recall for the <b>2018 Stelvio model year</b> (11 recalls), "
          "with each one's scope judged for a 2.0T that is not a Quadrifoglio. Whether each "
          "recall includes <b>this VIN</b>, and whether it has already been done, is not public "
          "data.",
          "<b>Check open status by VIN</b> at nhtsa.gov/recalls or alfaromeousa.com (owners, "
          "recalls), or in wiTECH/DealerCONNECT VIP. Recall work is free at any Alfa Romeo dealer. "
          "FCA US customer service: 1-800-853-1403.",
          "Two items matter for the EVAP fault now: <b>25V586000</b> (fuel pump) and "
          "<b>18V636000</b> (ECM software). Book them together with the ECM flash check.",
      ])]

rows = [["Campaign", "Year / component", "Issue (NHTSA summary, shortened)", "Remedy",
         "Applies to this car?", "Priority / relevance"]]
hot = []
for i, n in enumerate(ORDER, start=1):
    r = by.get(n)
    if not r:
        continue
    summary = (r.get("Summary") or "").replace("\n", " ")
    remedy = (r.get("Remedy") or "").replace("\n", " ")
    rows.append([f"<b>{n}</b>", f"{r.get('ReportReceivedDate', '')[-4:]}<br/>{r.get('Component', '').title()}",
                 summary[:260] + ("..." if len(summary) > 260 else ""),
                 remedy[:170] + ("..." if len(remedy) > 170 else ""),
                 APPLIES[n][0], APPLIES[n][1]])
    if n in ("25V586000", "18V636000"):
        hot.append(len(rows) - 1)

s += [P("NHTSA recalls, 2018 Stelvio", h2),
      table(rows, [0.8 * inch, 0.95 * inch, 1.9 * inch, 1.35 * inch, 0.95 * inch, 1.05 * inch], hot)]

s += [P("Service campaigns and bulletins (not recalls)", h2),
      table([["Item", "What it is", "Applies", "Relevance"],
             ["<b>CSN W05</b> (Mar 2020)", "Customer Satisfaction Notification: reprogram PCM, PROXI "
              "Alignment, Phonic Wheel Replacement. PCM software may not allow enough turbo oil-feed "
              "cooling time.", "2018-2019 Stelvio 2.0L GME-T4 (EC2)",
              "An ECM reflash; may already be done. Check in wiTECH."],
             ["<b>TSB 18-026-20</b> (Mar 2020)", "Flash: PCM updates. Fix list includes P1CEA "
              "(boost-side EVAP purge) and P24D6 (EVAP pressure switch circuit).",
              "2018 Stelvio 2.0L EC2, North America", "EVAP-related ECM calibration"],
             ["<b>TSB 18-030-17 REV. B</b> and the 18-0xx flash family",
              "PCM flash family whose fixed-DTC lists include P0440 / P0441 / P0455 / P0456.",
              "Giulia / Stelvio", "Why the ECM flash check is on the EVAP fault tree (step E8)"],
             ["<b>TSB 18-048-23</b>", "wiTECH Small Leak Verification Test (SLVT); a road test "
              "cannot confirm a small-leak repair.", "All FCA gasoline", "Verifies an EVAP fix"]],
            [1.35 * inch, 2.9 * inch, 1.35 * inch, 1.4 * inch])]

s += [P("Suggested dealer visit", h2),
      bullets([
          "Ask for a VIN recall check and complete every open item.",
          "Priority: <b>25V586000</b> fuel delivery module and <b>18V636000</b> ECM software.",
          "While it is connected: ECM Flash tab, compare Current vs New ECU Part Number "
          "(see the 'Stelvio ECM Flash Procedure (wiTECH)' PDF), and confirm CSN W05 status.",
          "After a fuel delivery module replacement, have the technician confirm the internal "
          "vapour line is connected at the FDM port (TSB 9100471).",
      ])]

s += [Spacer(1, 8),
      P("Source: NHTSA recalls API, api.nhtsa.gov/recalls/recallsByVehicle?make=ALFA ROMEO&model="
        "STELVIO&modelYear=2018, retrieved 2026-09-26. CSN W05 and TSB 18-026-20 from "
        "static.nhtsa.gov. Applicability column is judged from each recall's stated scope; VIN "
        "inclusion must be confirmed by VIN lookup.", small)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.8 * inch,
                        title="Stelvio Recalls and Campaigns", author="cuore / Claude")
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print(OUT)
