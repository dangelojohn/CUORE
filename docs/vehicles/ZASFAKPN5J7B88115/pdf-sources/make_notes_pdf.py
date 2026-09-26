"""One-page Mechanic Notes sheet for the 2018 Stelvio 2.0T (cuore data, 2026-09-26)."""
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import notes as notes_mod  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VIN = "ZASFAKPN5J7B88115"
OUT = r"C:\Users\User\Desktop\Stelvio Mechanic Notes (1 page).pdf"

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")

ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.4, leading=9.2, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
sm = ParagraphStyle("sm", parent=b, fontSize=6.9, leading=8.4, textColor=MUTED)
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=ACCENT)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


def esc(v):
    return ("" if v is None else str(v)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


GRIDSTYLE = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 3.5), ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]

# --- what notes are for --------------------------------------------------------

purpose = Table([[P(
    "The corpus (MES/wiTECH logs) and the dealer store answer <b>what happened</b>. Notes answer "
    "<b>what the technician knows about it that nothing else captured</b> -- e.g. \"purge valve replaced by "
    "me 2026-09-10\", \"this scan was taken right after a battery disconnect\", \"smoke test done at 0.5 psi, "
    "no leak\". If it is not written down here, Claude, the gate, and the fault tree cannot see it -- it stays "
    "invisible context that only lives in one person's head.", b)]], colWidths=[7.3 * inch])
purpose.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))

# --- how to add ------------------------------------------------------------------

howto = Table([[P(
    "<b>In cuore:</b> open <b>/v/&lt;VIN&gt;/notes</b> for the full list and add-note form, or use the "
    "\"Add a note\" panel embedded on the vehicle page, a code page, or a fault-tree step page (the target is "
    "pre-filled and locked there so a note cannot be mis-filed). Pick a <b>target</b>, write the note "
    "(up to 4,000 characters), and submit. Notes are append-only: <b>Edit</b> adds a new version and keeps the "
    "old text as history; <b>Hide</b> soft-deletes (never actually erased). Default author is "
    "\"technician\" unless you set one.", b)]], colWidths=[7.3 * inch])
howto.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))

# --- target kinds table -----------------------------------------------------------

TARGETS = [
    ("vehicle", "The car as a whole"),
    ("code", "One DTC, matched on its base code (a note on P0456 also attaches to P0456-00)"),
    ("log", "One MES log file, by name"),
    ("observation", "One live-link observation, by its timestamp"),
    ("dealer", "One dealer (wiTECH) result, by its timestamp"),
    ("tree_step", "One fault-tree step, e.g. evap-leak:E7"),
    ("component", "A free-text part name, e.g. ESIM"),
]
rows = [[P("Target kind", bb), P("Matches against", bb)]]
for k, desc in TARGETS:
    rows.append([P(f"<font face='Courier-Bold'>{k}</font>"), P(esc(desc))])
targets_table = Table(rows, colWidths=[1.3 * inch, 6.0 * inch])
targets_table.setStyle(TableStyle(GRIDSTYLE + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]))

# --- notes currently stored for this VIN ------------------------------------------

stored = notes_mod.load(VIN)
if stored:
    srows = [[P("When", bb), P("Note", bb), P("Target", bb), P("By", bb)]]
    for n in stored:
        target = n.get("target_kind", "")
        if n.get("target_id"):
            target += f":{n['target_id']}"
        srows.append([P(esc(n.get("at", ""))), P(esc(n.get("text", ""))), P(esc(target)),
                     P(esc(n.get("author", "")))])
    stored_table = Table(srows, colWidths=[1.2 * inch, 4.2 * inch, 1.2 * inch, 0.7 * inch])
    stored_table.setStyle(TableStyle(GRIDSTYLE + [("BACKGROUND", (0, 0), (-1, 0), SHADE)]))
    stored_block = stored_table
    stored_count_line = f"{len(stored)} note(s) on record for this VIN, read from the live cuore notes store."
else:
    stored_block = Table([[P("No notes are currently stored for this VIN in cuore (checked "
                            "2026-09-26, read-only, against the live notes store).", b)]],
                         colWidths=[7.3 * inch])
    stored_block.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SHADE), ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    stored_count_line = None

# --- blank ruled note lines --------------------------------------------------------

n_lines = 14
line_rows = [[""] for _ in range(n_lines)]
lines_table = Table(line_rows, colWidths=[7.3 * inch], rowHeights=[16] * n_lines)
lines_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (0, -1), 0.5, RULE),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))

story = [P("Mechanic Notes - 2018 Alfa Romeo Stelvio 2.0T", title),
         P(f"VIN {VIN}  |  cuore, 2026-09-26", sm),
         Spacer(1, 5),
         P("What notes are for", h), Spacer(1, 2), purpose, Spacer(1, 6),
         P("How to add a note in cuore", h), Spacer(1, 2), howto, Spacer(1, 4),
         P("Target kinds", h), Spacer(1, 2), targets_table, Spacer(1, 6),
         P("Notes on record for this VIN", h), Spacer(1, 2), stored_block]
if stored_count_line:
    story += [Spacer(1, 2), P(stored_count_line, sm)]
story += [Spacer(1, 8), P("Blank note lines (transcribe into cuore afterward)", h), Spacer(1, 3), lines_table]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, f"cuore Notes: /v/{VIN}/notes  |  write it down or it stays invisible "
                 "to the fault tree and to Claude")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.45 * inch,
                  bottomMargin=0.55 * inch, title="Stelvio Mechanic Notes").build(story, onFirstPage=foot,
                                                                                 onLaterPages=foot)
print(OUT)
