"""One-page Oil Change sheet for the 2018 Stelvio 2.0T (cuore data, 2026-09-26)."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import service, service_specs as S  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = r"C:\Users\User\Desktop\Stelvio Oil Change (1 page).pdf"
ODO_KM = 142290
ODO_MI = round(ODO_KM / 1.60934)

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CONFIRMED": colors.HexColor("#dcefe1"), "CORROBORATED": colors.HexColor("#e6f0f8"),
           "SINGLE-SOURCE": colors.HexColor("#fbf1e4"), "UNKNOWN": colors.HexColor("#fbeaea")}
SHORT = {"CONFIRMED": "CONFIRM.", "CORROBORATED": "CORROB.", "SINGLE-SOURCE": "SINGLE", "UNKNOWN": "UNKNOWN"}

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.1, leading=8.6, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
sm = ParagraphStyle("sm", parent=b, fontSize=6.7, leading=8.2, textColor=MUTED)
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=8.6, leading=10.5, textColor=ACCENT)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


def esc(v):
    return ("" if v is None else str(v)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


GRIDSTYLE = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
             ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)]


def conf_cell(c):
    return Paragraph(SHORT.get(c, esc(c)), b)


# --- Oil / filter spec table -------------------------------------------------

oil = S.OIL_SPEC
drain = S.torque_by_key("drain_plug")
filtcap = S.torque_by_key("filter_cap")
filt = S.OIL_FILTER_PARTS[0]

rows = [[P(x, bb) for x in ("Item", "Spec", "Conf.")]]
st = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]


def add_row(item, val, conf):
    rows.append([P(item, bb), P(esc(val)), conf_cell(conf)])
    st.append(("BACKGROUND", (2, len(rows) - 1), (2, len(rows) - 1), CONF_BG.get(conf, SHADE)))


add_row("Viscosity", oil["viscosity"]["value"] + " full synthetic", oil["viscosity"]["confidence"])
add_row("Spec / approval", oil["spec_approval"]["value"], oil["spec_approval"]["confidence"])
add_row("Capacity (with filter)", f"{oil['capacity_with_filter_qt']['value']} qt / "
        f"{oil['capacity_with_filter_qt']['value_l']} L", oil["capacity_with_filter_qt"]["confidence"])
add_row("Filter", f"Mopar {filt['part_no']}", filt["confidence"])
add_row("Do NOT use", "Mopar 68191349AA / AC -- that is the 2.9L V6 (Quadrifoglio) filter, "
        "not this 2.0T", "CONFIRMED")
add_row("Drain plug torque", drain["display"], drain["confidence"])
add_row("Filter housing cap torque", filtcap["display"], filtcap["confidence"])

oil_table = Table(rows, colWidths=[1.5 * inch, 4.9 * inch, 0.9 * inch])
oil_table.setStyle(TableStyle(st))

drain_note = Table([[P(esc(drain["notes"]), sm)]], colWidths=[7.3 * inch])
drain_note.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))

# --- Interval table -----------------------------------------------------------

interval = S.SERVICE_INTERVAL
mx = interval["manufacturer_max"]
int_rows = [[P(x, bb) for x in ("Interval", "Value", "Conf.")],
            [P("Shop interval (conservative)"), P(f"{interval['miles']:,} mi / {interval['months']} mo"),
             conf_cell(interval["confidence"])],
            [P("FCA maximum"), P(f"{mx['miles']:,} mi / {mx['km']:,} km / {mx['months']} yr"),
             conf_cell(mx["confidence"])],
            [P("FCA severe duty maximum"), P(f"{mx['severe_duty_miles']:,} mi / {mx['severe_duty_km']:,} km"),
             conf_cell(mx["confidence"])]]
ist = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE),
                         ("BACKGROUND", (2, 1), (2, 1), CONF_BG[interval["confidence"]]),
                         ("BACKGROUND", (2, 2), (2, 2), CONF_BG[mx["confidence"]]),
                         ("BACKGROUND", (2, 3), (2, 3), CONF_BG[mx["confidence"]])]
int_table = Table(int_rows, colWidths=[2.1 * inch, 3.6 * inch, 1.6 * inch])
int_table.setStyle(TableStyle(ist))

ols = interval["oil_life_system"]
reset_methods = ols["reset_methods"]
reset_bits = "<br/>".join(f"&bull; {esc(m)}" for m in reset_methods)
reset_block = Table([[P("<b>Reset methods</b> (dash reminder + day/mile counter; "
                        f"{SHORT[ols['confidence']]}):<br/>" + reset_bits, b)]],
                    colWidths=[7.3 * inch])
reset_block.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))

# --- MES corroboration --------------------------------------------------------

noc = service.next_oil_change("ZASFAKPN5J7B88115")
mes_events = noc.get("mes_corroboration") or []
if mes_events:
    ev_txt = "; ".join(f"{e['operation']} {e['outcome']} at {e['timestamp']}" for e in mes_events)
else:
    ev_txt = "none found"
mes_note = Table([[P(f"<b>MES log:</b> Oil-change reset logged for this VIN -- {esc(ev_txt)}. No odometer was "
                     "recorded with this event; it corroborates that a reset was run, not a full service record. "
                     "Record the actual oil change (brand, amount, filter, torques, odometer) in cuore.", b)]],
                 colWidths=[7.3 * inch])
mes_note.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e6f0f8")),
                              ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#4a7fa8")),
                              ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

warn = Table([[P("<b>UNKNOWN values above must come from the service manual (TechAuthority)</b> -- never "
                 "substitute a guessed number. All figures here are graded CONFIRMED (manufacturer document), "
                 "CORROBORATED (two independent sources) or SINGLE (one source, not cross-checked).", b)]],
             colWidths=[7.3 * inch])
warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

# --- fill-in record block ------------------------------------------------------


def line_row(label, width_label=1.3):
    return [P(label, bb), ""]


form_rows = [
    ["Date", "", "Odometer (km / mi)", ""],
    ["Oil brand / product", "", "Amount added", ""],
    ["Filter brand", "", "Filter part no.", ""],
    ["Drain plug torque applied", "", "Initials", ""],
    ["Filter cap torque applied", "", "Initials", ""],
    ["Drain plug washer replaced?", "", "Sample taken?", ""],
]
form_data = [[P(r[0], bb), "", P(r[2], bb), ""] for r in form_rows]
form_t = Table(form_data, colWidths=[1.7 * inch, 1.95 * inch, 1.7 * inch, 1.95 * inch], rowHeights=15)
fst = [("LINEBELOW", (1, 0), (1, -1), 0.6, INK), ("LINEBELOW", (3, 0), (3, -1), 0.6, INK),
       ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
       ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 1),
       ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
form_t.setStyle(TableStyle(fst))

notes_rows = [[P("Discoveries (leaks, wear, anything found)", bb)], [""], [""],
              [P("Next time / considerations", bb)], [""], [""]]
notes_t = Table(notes_rows, colWidths=[7.3 * inch], rowHeights=[12] + [13, 13] + [12] + [13, 13])
notes_t.setStyle(TableStyle([("LINEBELOW", (0, 1), (0, 2), 0.6, RULE), ("LINEBELOW", (0, 4), (0, 5), 0.6, RULE),
                             ("LEFTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))

story = [P("Oil Change - 2018 Alfa Romeo Stelvio 2.0T", title),
         P(f"VIN ZASFAKPN5J7B88115  |  about {ODO_KM:,} km / {ODO_MI:,} mi  |  cuore, 2026-09-26", sm),
         Spacer(1, 4),
         P("Oil and filter", h), Spacer(1, 2), oil_table, drain_note, Spacer(1, 4),
         P("Interval", h), Spacer(1, 2), int_table, Spacer(1, 3), reset_block, Spacer(1, 4),
         mes_note, Spacer(1, 3), warn, Spacer(1, 6),
         P("Service record", h), Spacer(1, 2), form_t, Spacer(1, 4), notes_t]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "cuore Oil change: /v/ZASFAKPN5J7B88115/oil-change  |  record every "
                 "change in cuore so the next visit and next-due calculation see it")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.4 * inch,
                  bottomMargin=0.5 * inch, title="Stelvio Oil Change").build(story, onFirstPage=foot,
                                                                            onLaterPages=foot)
print(OUT)
