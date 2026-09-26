"""One-page Gauges reference sheet for cuore (2018 Stelvio 2.0T)."""
import os

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "v_ZASFAKPN5J7B88115_gauges_autostart-demo_1300.png")
SHOT = os.path.join(HERE, "gauges_shot.png")
OUT = r"C:\Users\User\Desktop\Stelvio Gauges (1 page).pdf"

# toolbar + parameter table, then the graph, from the demo-mode screenshot
im = PILImage.open(SRC).convert("RGB")
a, g = im.crop((44, 312, 1256, 760)), im.crop((44, 958, 1256, 1268))
comb = PILImage.new("RGB", (1212, a.height + g.height + 6), "white")
comb.paste(a, (0, 0)); comb.paste(g, (0, a.height + 6)); comb.save(SHOT)

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.1, leading=8.7, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=8.6, leading=10.5, textColor=ACCENT)
sm = ParagraphStyle("sm", parent=b, fontSize=6.6, leading=8, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


GRID = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6)]


def table(rows, widths):
    t = Table([[P(c, bb if i == 0 else b) for c in r] for i, r in enumerate(rows)], colWidths=widths)
    t.setStyle(TableStyle(GRID + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]))
    return t


shot = Image(SHOT, width=4.45 * inch, height=4.45 * inch * comb.height / comb.width)
side = [P("Open it", h),
        P("cuore: <b>/v/ZASFAKPN5J7B88115/gauges</b> (the <b>Gauges</b> tab). Full-screen: <b>/gauges/hud</b>."),
        Spacer(1, 3), P("Data sources", h),
        P("<b>Live car</b>: starts a read-only poll session (OBD Mode 01 and UDS 0x22 reads, CAN-C only). "
          "While it runs, clears and actuator tests are refused."),
        P("<b>Replay</b>: plays a cuore or MES CSV recording at 0.25x to 16x, with seek. Marked as replay."),
        P("<b>Demo</b>: simulated values under a yellow <b>DEMO DATA - NOT FROM THE CAR</b> banner."),
        P("Replay, demo and snapshots are never used as evidence from the car.", sm),
        Spacer(1, 3), P("Keyboard", h),
        P("<b>Space</b> pause all &nbsp; <b>1-9</b> page tabs &nbsp; <b>R</b> record &nbsp; "
          "<b>S</b> snapshot &nbsp; <b>E</b> edit layout")]
top = Table([[shot, side]], colWidths=[4.6 * inch, 2.9 * inch])
top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

layouts = table([
    ["Built-in layout", "Shows", "Use it for"],
    ["MES Parameters + Graph", "Parameter table (value, min, max, avg, level, trend) and a multi-trace graph",
     "General live data, like the MES Parameters and Graph tabs"],
    ["Engine basics", "RPM, speed, coolant, intake air temp, load, throttle, battery", "Quick health check"],
    ["Boost", "MAP, barometric, computed boost (MAP minus baro)", "Turbo and boost faults"],
    ["EVAP job", "Purge duty, fuel level, EVAP vapour pressure, stacked graphs",
     "Watching wiTECH Test A; P0455, P0456, P0440"],
    ["Transmission", "TCM identifiers 04FE and 0518", "ZF 8HP fluid temperature (30-50 C fill window)"],
    ["TPMS", "Four tiles: pressure and temperature per wheel (RFHUB)", "Tyre pressures at a glance"],
], [1.35 * inch, 3.3 * inch, 2.85 * inch])

widgets = table([
    ["Widget", "What it is", "Widget", "What it is"],
    ["Digital", "Big number with min, max and average", "Stacked", "Mini graphs sharing one time axis and cursor"],
    ["Bar", "Linear gauge with zones and a peak marker", "Scope", "Fast 5 s sweep, trigger level, 3 faded sweeps"],
    ["Dial", "Analog gauge, green / yellow / red arcs, peak hold", "Scatter", "Y against X with a trail, e.g. MAP vs RPM"],
    ["Line", "Scrolling graph with warn and alarm bands", "Table", "MES-style parameter table with sparklines"],
    ["Multiline", "2-4 traces with their own scales, normalised mode", "Tiles", "Small coloured tiles, e.g. four tyres"],
    ["HUD", "Huge digits on black, mirror for a windshield", "", ""],
], [0.75 * inch, 2.95 * inch, 0.75 * inch, 3.05 * inch])

controls = table([
    ["Control", "What it does"],
    ["Layout picker, Save, Save as, Export, Import",
     "Built-ins are read-only: use Save as to make your own. Export and Import move a layout as JSON between laptop and tablet."],
    ["Edit layout",
     "Add widgets (type and channels), resize 1-4 x 1-3 cells, drag or use arrows to reorder, set min and max, warn and alarm "
     "bands, decimals, smoothing, time window, colours and refresh tier; add or rename pages."],
    ["Connect / Stop, Record, Snapshot",
     "Record writes an MES-format CSV that the existing log tools read. Snapshot saves every value on the page as one row, "
     "labelled with its source."],
    ["Pause all, time window, graph mouse",
     "Window 10 s to 10 min. On a paused graph: wheel to zoom, drag to pan, double-click to reset. Hover shows a cursor "
     "linked across graphs."],
    ["Sound, Alarms",
     "Warn and alarm colours per widget; with Sound on, a beep and a spoken warning. The Alarms drawer logs every event "
     "with time and value."],
    ["Triggers", "Rules such as boost crosses above a value, then start recording; or beep, speak, snapshot, mark. "
                 "Each rule has a cooldown."],
    ["Custom channels", "Torque-style formulas on a module identifier, e.g. (A*256+B)/10-40, or expressions over other "
                        "channels. Checked before saving."],
], [2.2 * inch, 5.3 * inch])

warn = Table([[P("<b>Bands and limits:</b> built-in layouts only show warn and alarm bands where a value is sourced. "
                 "Unknown limits are left blank rather than guessed. Check any band you add against the service "
                 "manual (TechAuthority).")]], colWidths=[7.5 * inch])
warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [P("Gauges - live data for the 2018 Alfa Romeo Stelvio 2.0T", title),
         P("VIN ZASFAKPN5J7B88115  |  cuore Gauges page  |  screenshot shows DEMO data  |  2026-09-26", sm),
         Spacer(1, 5), top, Spacer(1, 5), layouts, Spacer(1, 5), widgets, Spacer(1, 5), controls,
         Spacer(1, 5), warn]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "cuore Gauges: /v/ZASFAKPN5J7B88115/gauges  |  live sessions are read-only "
                 "and hold the adapter: stop the session before clearing codes or running actuator tests")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.45 * inch,
                  bottomMargin=0.55 * inch, title="Stelvio Gauges").build(story, onFirstPage=foot, onLaterPages=foot)
print(OUT)
