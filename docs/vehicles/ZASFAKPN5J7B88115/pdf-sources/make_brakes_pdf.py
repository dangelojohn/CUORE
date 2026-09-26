"""One-page Brakes, Wheels & Tyres sheet for the 2018 Stelvio 2.0T (cuore data, 2026-09-26)."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import service_specs as S, maintenance_specs as M  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio Brakes Wheels Tyres (1 page).pdf"

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CONFIRMED": colors.HexColor("#dcefe1"), "CORROBORATED": colors.HexColor("#e6f0f8"),
           "SINGLE-SOURCE": colors.HexColor("#fbf1e4"), "UNKNOWN": colors.HexColor("#fbeaea")}
SHORT = {"CONFIRMED": "CONFIRM.", "CORROBORATED": "CORROB.", "SINGLE-SOURCE": "SINGLE", "UNKNOWN": "UNKNOWN"}

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=6.9, leading=8.3, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
sm = ParagraphStyle("sm", parent=b, fontSize=6.6, leading=8, textColor=MUTED)
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=8.6, leading=10.5, textColor=ACCENT)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


def esc(v):
    return ("" if v is None else str(v)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


GRIDSTYLE = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
             ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6)]


def conf_cell(c):
    return Paragraph(SHORT.get(c, esc(c)), b)


brake = S.BRAKE_SPEC

# --- rotor / pad table ---------------------------------------------------------

rows = [[P(x, bb) for x in ("", "Front", "Rear", "Conf.")]]
rn, rm = brake["rotor_new_mm"], brake["rotor_min_mm"]
rows.append([P("Rotor, new"), P(f"{rn['front']['value']} mm ({rn['front']['diameter_mm']} mm dia.)"),
             P(f"{rn['rear']['value']} mm ({rn['rear']['diameter_mm']} mm dia.)"),
             conf_cell(rn["front"]["confidence"])])
rows.append([P("Rotor, minimum (discard)"), P(f"{rm['front']['value']} mm"),
             P("UNKNOWN -- read cast MIN TH marking"), conf_cell(rm["front"]["confidence"])])
rows.append([P("Pad minimum thickness"), P("UNKNOWN -- electronic pad-wear sensor on inner pad"),
             P("UNKNOWN"), conf_cell("UNKNOWN")])
rst = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE),
                         ("BACKGROUND", (3, 1), (3, 1), CONF_BG[rn["front"]["confidence"]]),
                         ("BACKGROUND", (3, 2), (3, 2), CONF_BG[rm["front"]["confidence"]]),
                         ("BACKGROUND", (3, 3), (3, 3), CONF_BG["UNKNOWN"])]
rotor_table = Table(rows, colWidths=[1.7 * inch, 2.35 * inch, 2.35 * inch, 0.85 * inch])
rotor_table.setStyle(TableStyle(rst))

epb = brake["epb_service_mode"]
epb_box = Table([[P(f"<b>EPB service mode required before rear pad service:</b> {esc(epb['note'])}", b)]],
                colWidths=[7.25 * inch])
epb_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                             ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

# --- fluid / tyres table --------------------------------------------------------

bf = M.ITEMS["brake_fluid"]
oe = brake["oe_tire_size"]
tp = brake["tire_pressure_kpa"]

fluid_rows = [[P(x, bb) for x in ("Item", "Value", "Conf.")],
              [P("Brake fluid"), P(esc(bf["fluid"]["spec"]) + f" -- capacity {bf['fluid']['capacity']} "
                 f"{bf['fluid']['unit']} (reservoir + lines)"), conf_cell(bf["fluid"]["confidence"])],
              [P("Change interval"), P(f"Every {bf['interval_months'] // 12} years, regardless of mileage"),
               conf_cell(bf["interval_confidence"])],
              [P("Tyre size, base 18in"), P(esc(oe["base_18in"]["value"])), conf_cell(oe["base_18in"]["confidence"])],
              [P("Tyre size, Ti 19in"), P(esc(oe["ti_19in"]["value"])), conf_cell(oe["ti_19in"]["confidence"])],
              [P("Pressure (19in fitment)"), P(f"Front {tp['front']['value']} kPa / {tp['front']['psi']} psi; "
                 f"rear {tp['rear']['value']} kPa / {tp['rear']['psi']} psi -- READ THE DOOR-JAMB PLACARD"),
               conf_cell(tp["front"]["confidence"])],
              [P("Rotation"), P("Square (non-staggered) fitments: standard front-to-rear. Staggered "
                 "(Quadrifoglio or any mismatched fitment): DO NOT ROTATE."),
               conf_cell(brake["rotation_pattern"]["confidence"])]]
fst = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]
for i, conf in enumerate([bf["fluid"]["confidence"], bf["interval_confidence"], oe["base_18in"]["confidence"],
                          oe["ti_19in"]["confidence"], tp["front"]["confidence"],
                          brake["rotation_pattern"]["confidence"]], start=1):
    fst.append(("BACKGROUND", (2, i), (2, i), CONF_BG.get(conf, SHADE)))
fluid_table = Table(fluid_rows, colWidths=[1.5 * inch, 5.05 * inch, 0.7 * inch])
fluid_table.setStyle(TableStyle(fst))

# --- torques ---------------------------------------------------------------

t_rows = [[P(x, bb) for x in ("Fastener", "Torque", "Conf.", "Note")]]
tst = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]
for key in ("wheel_lug", "caliper_slider_front", "caliper_bracket_front", "caliper_slider_rear",
            "caliper_bracket_rear", "rotor_retaining_screw", "wheel_bearing_hub_nut"):
    row = S.torque_by_key(key)
    note = row["notes"]
    if row.get("single_use"):
        note = "SINGLE-USE. " + note
    note = " ".join(note.split())
    if len(note) > 95:
        note = note[:94].rsplit(" ", 1)[0] + "..."
    t_rows.append([P(esc(row["component"])), P("<b>" + esc(row["display"]) + "</b>"),
                  conf_cell(row["confidence"]), P(esc(note), sm)])
    tst.append(("BACKGROUND", (2, len(t_rows) - 1), (2, len(t_rows) - 1), CONF_BG.get(row["confidence"], SHADE)))
torque_table = Table(t_rows, colWidths=[2.05 * inch, 0.85 * inch, 0.6 * inch, 3.75 * inch])
torque_table.setStyle(TableStyle(tst))

# --- four-corner fill-in grid ------------------------------------------------

corners = ["FL", "FR", "RL", "RR"]
grid_rows = [[P("", bb)] + [P(c, bb) for c in corners]]
grid_labels = ["Pad thickness (mm) inner/outer", "Rotor thickness (mm)",
               "Tread depth (32nds / mm)", "Pressure (psi/kPa)", "Tyre DOT date code"]
for lbl in grid_labels:
    grid_rows.append([P(lbl, bb)] + ["" for _ in corners])
gst = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
       ("BACKGROUND", (0, 0), (-1, 0), SHADE), ("LEFTPADDING", (0, 0), (-1, -1), 3),
       ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 5),
       ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
grid_table = Table(grid_rows, colWidths=[1.85 * inch] + [1.35 * inch] * 4, rowHeights=[16] + [18] * len(grid_labels))
grid_table.setStyle(TableStyle(gst))

warn = Table([[P("<b>UNKNOWN values above must come from the service manual (TechAuthority)</b> -- never "
                 "substitute a guessed number. Wheel lug bolts thread into the hub (not nuts on studs); torque "
                 "in a star pattern, snug then final torque. This is a safety-critical fastener.", b)]],
             colWidths=[7.25 * inch])
warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [P("Brakes, Wheels &amp; Tyres - 2018 Alfa Romeo Stelvio 2.0T", title),
         P("VIN ZASFAKPN5J7B88115  |  about 142,290 km / 88,415 mi  |  cuore, 2026-09-26", sm),
         Spacer(1, 4),
         P("Rotors &amp; pads", h), Spacer(1, 2), rotor_table, Spacer(1, 4), epb_box, Spacer(1, 5),
         P("Fluid &amp; tyres", h), Spacer(1, 2), fluid_table, Spacer(1, 5),
         P("Torques", h), Spacer(1, 2), torque_table, Spacer(1, 5), warn, Spacer(1, 6),
         P("Four-corner record", h), Spacer(1, 2), grid_table]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "cuore Brakes/wheels/tyres: /v/ZASFAKPN5J7B88115/brakes-tires  |  put the "
                 "EPB in service mode before touching a rear caliper")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.4 * inch,
                  bottomMargin=0.5 * inch, title="Stelvio Brakes Wheels Tyres").build(story, onFirstPage=foot,
                                                                                     onLaterPages=foot)
print(OUT)
