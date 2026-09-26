"""One-page General Service Record (fill-in sheet) for the 2018 Stelvio 2.0T, matching cuore's service form."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import service_specs as S  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

OUT = r"C:\Users\User\Desktop\Stelvio General Service Record (1 page).pdf"
INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CONFIRMED": colors.HexColor("#dcefe1"), "CORROBORATED": colors.HexColor("#e6f0f8"),
           "SINGLE-SOURCE": colors.HexColor("#fbf1e4"), "UNKNOWN": colors.HexColor("#fbeaea")}
SHORT = {"CONFIRMED": "CONFIRM.", "CORROBORATED": "CORROB.", "SINGLE-SOURCE": "SINGLE", "UNKNOWN": "UNKNOWN"}

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.2, leading=8.8, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=8.6, leading=10.5, textColor=ACCENT)
sm = ParagraphStyle("sm", parent=b, fontSize=6.6, leading=8, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


BOX = [("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
       ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
       ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]


def boxed(rows, widths, heights=None, head=True, extra=()):
    t = Table(rows, colWidths=widths, rowHeights=heights)
    st = list(BOX) + list(extra)
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), SHADE))
    t.setStyle(TableStyle(st))
    return t


# --- header fields -------------------------------------------------------------
header = boxed([[P("<b>Date</b>"), P("<b>Odometer (km)</b>"), P("<b>Technician</b>"), P("<b>Entered in cuore</b>")],
                ["", "", "", P("[ ] yes, on ____ / ____")]],
               [1.6 * inch, 1.9 * inch, 2.2 * inch, 1.8 * inch], [None, 0.3 * inch])

# --- category tick boxes (cuore's categories, in its order) -------------------
labels = [S.CATEGORY_LABELS[c] for c in S.CATEGORIES]
cells = [P("[ ] " + lab) for lab in labels]
while len(cells) % 5:
    cells.append("")
cat_rows = [cells[i:i + 5] for i in range(0, len(cells), 5)]
cats = boxed(cat_rows, [1.5 * inch] * 5, head=False)

# --- work done ------------------------------------------------------------------
work = boxed([[P("<b>Work done</b> (what was done and why)")], [""], [""], [""]], [7.5 * inch],
             [None, 0.22 * inch, 0.22 * inch, 0.22 * inch])

# --- parts + fluids -------------------------------------------------------------
parts = boxed([[P("<b>Part</b>"), P("<b>Part number</b>"), P("<b>Qty</b>"), P("<b>Brand / notes</b>")]]
              + [["", "", "", ""] for _ in range(5)],
              [2.1 * inch, 1.8 * inch, 0.5 * inch, 3.1 * inch], [None] + [0.21 * inch] * 5)
fluids = boxed([[P("<b>Fluid</b>"), P("<b>Spec</b>"), P("<b>Amount</b>"), P("<b>Brand</b>")]]
               + [["", "", "", ""] for _ in range(2)],
               [2.1 * inch, 1.8 * inch, 1.0 * inch, 2.6 * inch], [None] + [0.21 * inch] * 2)

# --- torque checklist: sourced values from cuore, plus blank rows --------------
rows = [[P(x, bb) for x in ("Fastener", "Spec", "Conf.", "Applied", "Initials")]]
extra = []
for r in S.TORQUES:
    r = r if isinstance(r, dict) else r.__dict__
    if r.get("value") is None:
        continue
    spec = f"{r['value']:g} Nm ({r['value_lbft']:g} lb-ft)" if r.get("value_lbft") else f"{r['value']:g} Nm"
    if r.get("angle"):
        spec += f" + {r['angle']}"
    if r.get("single_use"):
        spec += ", single-use"
    rows.append([P(r["component"]), P(spec), P(SHORT.get(r["confidence"], r["confidence"])), "", ""])
    extra.append(("BACKGROUND", (2, len(rows) - 1), (2, len(rows) - 1), CONF_BG.get(r["confidence"], SHADE)))
for _ in range(3):
    rows.append([P("<font color='#5b6770'>other:</font>"), "", "", "", ""])
torque = boxed(rows, [2.9 * inch, 1.75 * inch, 0.7 * inch, 1.2 * inch, 0.95 * inch], extra=extra)

# --- discoveries + next time ------------------------------------------------------
notes = boxed([[P("<b>Discoveries</b> (wear, leaks, damage, codes seen)"), P("<b>Consider next time</b>")],
               ["", ""], ["", ""], ["", ""]],
              [3.75 * inch, 3.75 * inch], [None, 0.22 * inch, 0.22 * inch, 0.22 * inch])

history = Table([[P("<b>On record for this car:</b> no general service entries in cuore yet. Logged in MES: oil-change "
                    "reset 2026-09-15 (no odometer); turbocharger replaced and overboost counter reset 2025-10-14. "
                    "Open: transfer case oil and drive belt are past their schedule unless done (see the Routine "
                    "Maintenance sheet).")]], colWidths=[7.5 * inch])
history.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                             ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [P("General Service Record - 2018 Alfa Romeo Stelvio 2.0T", title),
         P("VIN ZASFAKPN5J7B88115  |  about 142,290 km  |  same fields as the cuore Service page  |  oil changes, "
           "brakes/tyres and routine maintenance have their own sheets", sm),
         Spacer(1, 4), history, Spacer(1, 5),
         header, Spacer(1, 4), P("Category (tick one)", h), cats, Spacer(1, 4), work, Spacer(1, 4),
         P("Parts and fluids", h), parts, Spacer(1, 2), fluids, Spacer(1, 4),
         P("Torque checklist (sourced values from cuore; UNKNOWN fasteners: use the service manual, TechAuthority)", h),
         torque, Spacer(1, 4), notes]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "Enter this record in cuore: /v/ZASFAKPN5J7B88115/service  |  "
                 "calibrated torque wrench; replace single-use fasteners")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.45 * inch,
                  bottomMargin=0.55 * inch, title="Stelvio General Service Record").build(
    story, onFirstPage=foot, onLaterPages=foot)
print(OUT)
