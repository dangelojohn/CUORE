"""One-page Vehicle Dashboard sheet for the 2018 Stelvio 2.0T (cuore data, mes.dashboard, 2026-09-26)."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import dashboard  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VIN = "ZASFAKPN5J7B88115"
OUT = r"C:\Users\User\Desktop\Stelvio Vehicle Dashboard (1 page).pdf"

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
SEV_BG = {"returned": colors.HexColor("#f6d5d5"), "chronic": colors.HexColor("#fbeaea"),
          "recurring": colors.HexColor("#fbf1e4"), "cleared": colors.HexColor("#dcefe1"),
          "seen-once": colors.HexColor("#f1f4f6")}
SEV_LABEL = {"returned": "RETURNED", "chronic": "CHRONIC", "recurring": "RECURRING",
            "cleared": "CLEARED", "seen-once": "SEEN-ONCE"}

ss = getSampleStyleSheet()
cell = ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica", fontSize=6.2, leading=7.2, textColor=INK)
cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.4, leading=9, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
sm = ParagraphStyle("sm", parent=b, fontSize=6.8, leading=8.2, textColor=MUTED)
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=8.8, leading=10.6, textColor=ACCENT)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=cell):
    return Paragraph(t, s)


def esc(v):
    return ("" if v is None else str(v)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def short(t, n):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "..."


def date_only(ts):
    return str(ts or "")[:10] or "-"


GRIDSTYLE = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
             ("TOPPADDING", (0, 0), (-1, -1), 1.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4)]

d = dashboard.build(VIN)
summary = d["summary"]
timeline = d["code_timeline"]
modules = d["modules"]
odo_series = d["odometer_series"]

# --- summary strip -----------------------------------------------------------

odo_first_km = summary.get("odometer_first_km")
odo_last_km = summary.get("odometer_last_km")


def km_mi(km):
    if km is None:
        return "-"
    return f"{km:,.0f} km / {km / 1.60934:,.0f} mi"


sum_rows = [
    ["Vehicle", esc(summary.get("vehicle") or "-")],
    ["Odometer span", f"{km_mi(odo_first_km)}  to  {km_mi(odo_last_km)}"],
    ["Logs on file", str(summary.get("log_count") or 0)],
    ["Last scan", esc(summary.get("last_scan_date") or "-")],
    ["Open codes now", str(summary.get("open_codes_count"))],
    ["Chronic codes", str(summary.get("chronic_count"))],
]
sum_table = Table([[P(k, cellb), P(v)] for k, v in sum_rows], colWidths=[1.3 * inch, 2.55 * inch])
sum_table.setStyle(TableStyle(GRIDSTYLE + [("BACKGROUND", (0, 0), (0, -1), SHADE)]))

ecu_seen = summary.get("ecu_seen") or []
after_clear = summary.get("newest_session_after_clear")
notes_lines = []
if ecu_seen:
    notes_lines.append(f"<b>ECUs seen:</b> {esc(', '.join(ecu_seen))}")
if after_clear:
    findings = ", ".join(after_clear.get("findings_before") or [])
    notes_lines.append(f"<b>Newest session is right after a clear</b> (cleared {esc(after_clear.get('cleared_at'))} "
                       f"via {esc(after_clear.get('source'))}) -- 0 standing codes is silence, not a clean bill; "
                       f"pre-clear findings were: {esc(findings) or 'none recorded'}.")
side_note = Table([[P("<br/><br/>".join(notes_lines) or "-", cell)]], colWidths=[3.75 * inch])
side_note.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
summary_row = Table([[sum_table, side_note]], colWidths=[3.9 * inch, 3.85 * inch])
summary_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

# --- code timeline summary table -----------------------------------------------

class_counts = {}
for row in timeline:
    class_counts[row["class"]] = class_counts.get(row["class"], 0) + 1
counts_line = "  |  ".join(f"{SEV_LABEL.get(k, k.upper())}: {v}" for k, v in
                           sorted(class_counts.items(), key=lambda kv: -kv[1]))

tl_rows = [[P(x, cellb) for x in ("Code", "Description", "Module", "Class", "Sess.", "First seen", "Last seen",
                                  "Odo span (km)")]]
tst = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]
for row in timeline:
    span = row.get("distance_span_km")
    span_txt = f"{span:,.0f}" if span else "-"
    tl_rows.append([P(esc(row["code"]), cellb), P(esc(short(row["description"], 60))),
                    P(esc(row["module"].split(",")[0].split("/")[-1].strip()[:14])),
                    P(SEV_LABEL.get(row["class"], row["class"])),
                    P(str(row["sessions"])), P(date_only(row["first_seen"])), P(date_only(row["last_seen"])),
                    P(span_txt)])
    r = len(tl_rows) - 1
    tst.append(("BACKGROUND", (3, r), (3, r), SEV_BG.get(row["class"], SHADE)))
timeline_table = Table(tl_rows, colWidths=[0.55 * inch, 2.55 * inch, 1.0 * inch, 0.75 * inch, 0.4 * inch,
                                           0.7 * inch, 0.7 * inch, 0.75 * inch], repeatRows=1)
timeline_table.setStyle(TableStyle(tst))

# --- module table ------------------------------------------------------------

mod_rows = [[P(x, cellb) for x in ("Module", "DTC count", "Last read", "Source", "Active now")]]
mst = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]
for m in modules:
    active = m.get("active_now")
    active_txt = "yes" if active else ("no" if active is False else "-")
    mod_rows.append([P(esc(m["module"]), cellb), P(str(m["dtc_count"])), P(esc(m.get("last_read") or "-")),
                     P(esc(m.get("last_read_source") or "-")), P(active_txt)])
    if active:
        mst.append(("BACKGROUND", (4, len(mod_rows) - 1), (4, len(mod_rows) - 1), colors.HexColor("#fbeaea")))
module_table = Table(mod_rows, colWidths=[0.55 * inch, 0.55 * inch, 1.1 * inch, 0.6 * inch, 0.6 * inch])
module_table.setStyle(TableStyle(mst))

# --- odometer span table -------------------------------------------------------

odo_rows = [[P(x, cellb) for x in ("Date", "Odometer (km)", "Odometer (mi)")]]
ost = list(GRIDSTYLE) + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]
for pt in odo_series:
    odo_rows.append([P(date_only(pt["at"])), P(f"{pt['odometer_km']:,.1f}"),
                     P(f"{pt['odometer_km'] / 1.60934:,.0f}")])
odo_table = Table(odo_rows, colWidths=[1.3 * inch, 1.1 * inch, 1.1 * inch])
odo_table.setStyle(TableStyle(ost))

story = [P("Vehicle Dashboard - 2018 Alfa Romeo Stelvio 2.0T", title),
         P(f"VIN {VIN}  |  from mes.dashboard  |  cuore, 2026-09-26", sm),
         Spacer(1, 4), summary_row, Spacer(1, 6),
         P(f"Code timeline summary ({len(timeline)} codes ever seen -- {counts_line})", h), Spacer(1, 2),
         timeline_table, Spacer(1, 6)]

bottom_row = Table([[module_table, odo_table]], colWidths=[3.65 * inch, 3.65 * inch])
bottom_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 1), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 10)]))

story += [Table([[P("Modules", h), P("Odometer span (log-derived points)", h)]],
                colWidths=[3.65 * inch, 3.65 * inch],
                style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)])),
         Spacer(1, 2), bottom_row]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, f"cuore Dashboard: /v/{VIN}/dashboard  |  charts omitted from this "
                 "printable sheet -- see the live page for the SVG timeline and mileage graph")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.4 * inch,
                  bottomMargin=0.5 * inch, title="Stelvio Vehicle Dashboard").build(story, onFirstPage=foot,
                                                                                   onLaterPages=foot)
print(OUT)
