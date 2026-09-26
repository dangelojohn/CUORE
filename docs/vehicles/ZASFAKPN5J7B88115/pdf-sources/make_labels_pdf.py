"""One-page Service Labels reference sheet for cuore (2018 Stelvio 2.0T)."""
import os
import sys

sys.path.insert(0, r"C:\Users\User\mcp-servers")
from cuore.labels import templates as T  # noqa: E402  (stdlib-only module)

import pypdfium2 as pdfium  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = r"C:\Users\User\mcp-servers\docs\vehicles\ZASFAKPN5J7B88115\pdf\Stelvio Sample Service Labels.pdf"
OUT = r"C:\Users\User\Desktop\Stelvio Service Labels (1 page).pdf"
SCALE = 4.0  # render scale: 72 dpi * 4 = 288 dpi previews
PT_PER_MM = 72 / 25.4

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE, WARN = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6"), colors.HexColor("#fbf1e4")
CONF_BG = {"CORROBORATED": colors.HexColor("#e6f0f8"), "SINGLE-SOURCE": colors.HexColor("#fbf1e4"),
           "UNVERIFIED": colors.HexColor("#fbeaea")}
ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=7.1, leading=8.7, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=8.6, leading=10.5, textColor=ACCENT)
sm = ParagraphStyle("sm", parent=b, fontSize=6.6, leading=8, textColor=MUTED)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


def crop_cell(page_index, template_id, name):
    """Crop cell 0 of one sample-sheet page to a PNG, using the template's own geometry."""
    t = T.TEMPLATES[template_id]
    page = pdfium.PdfDocument(SAMPLE)[page_index]
    img = page.render(scale=SCALE).to_pil()
    x_mm, y_mm = t.cell_origin_mm(0)
    k = PT_PER_MM * SCALE
    box = (int(x_mm * k), int(y_mm * k), int((x_mm + t.label_w_mm) * k), int((y_mm + t.label_h_mm) * k))
    path = os.path.join(HERE, name)
    img.crop(box).save(path)
    return path, t.label_w_mm / 25.4, t.label_h_mm / 25.4


PREVIEW = 0.7  # previews at 70% of actual size so four fit across the page


def framed(path, w_in, h_in, caption):
    w_in, h_in = w_in * PREVIEW, h_in * PREVIEW
    im = Image(path, width=w_in * inch, height=h_in * inch)
    t = Table([[im], [P(caption, sm)]], colWidths=[w_in * inch + 6])
    t.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.6, colors.HexColor("#8a949b")),
                           ("ALIGN", (0, 0), (-1, -1), "LEFT"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


# sample sheet pages: 0 oil_change 5520, 1 reminder 5520, 2 torque_tag 5520, 3 oil_change 6576
prev = [crop_cell(0, "avery_5520", "lbl_oil.png"), crop_cell(1, "avery_5520", "lbl_rem.png"),
        crop_cell(2, "avery_5520", "lbl_torque.png"), crop_cell(3, "avery_6576", "lbl_6576.png")]
caps = ["Oil change (5520)", "Next service reminder (5520)", "Torque tag (5520)",
        "Oil change on 6576 durable ID"]
previews = Table([[framed(p, w, hh, c) for (p, w, hh), c in zip(prev, caps)]],
                 colWidths=[2.0 * inch, 2.0 * inch, 2.0 * inch, 1.5 * inch], hAlign="LEFT")
previews.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

rows = [[P(x, bb) for x in ("Template", "Size", "Per sheet", "Printer", "Geometry")]]
st = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
      ("BACKGROUND", (0, 0), (-1, 0), SHADE),
      ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
      ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
for t in T.TEMPLATES.values():
    name = t.name.split("\u2014")[0].split(" \ufffd")[0].strip()
    conf = t.confidence
    rows.append([P(name), P(f'{t.label_w_in} x {t.label_h_in}'), P(f"{t.count} ({t.cols} x {t.rows})"),
                 P(t.printer if hasattr(t, "printer") else getattr(t, "media", "")),
                 P(conf + ("" if t.geometry_confirmed else ": margins not found, test grid first"))])
    st.append(("BACKGROUND", (4, len(rows) - 1), (4, len(rows) - 1), CONF_BG.get(conf, SHADE)))
tmpl = Table(rows, colWidths=[2.2 * inch, 1.1 * inch, 0.9 * inch, 0.7 * inch, 2.6 * inch])
tmpl.setStyle(TableStyle(st))

kinds = Table([[P(x, bb) for x in ("Label kind", "What it prints", "Filled from")],
               [P("Oil change"), P("Shop, date, NEXT due km / mi or date, odometer, oil grade / spec / litres, "
                                   "filter part, technician, short VIN"),
                P("An oil-change record in cuore (or typed values)")],
               [P("Service"), P("Section, date, work done, odometer, next due"), P("A general service record")],
               [P("Torque tag"), P("Fastener, torque in Nm and lb-ft, angle, SINGLE-USE flag, date, technician"),
                P("cuore's sourced torque table")],
               [P("Reminder"), P("NEXT SERVICE DUE, km / mi and date, vehicle and job"),
                P("Next-due calculation (oil interval)")]],
              colWidths=[1.0 * inch, 4.0 * inch, 2.5 * inch])
kinds.setStyle(TableStyle(st[:6]))

steps = [P("How to print", h),
         P("1. Open <b>/v/ZASFAKPN5J7B88115/labels</b>, pick the label kind, the Avery template and the record (or type "
           "values). Set <b>start position</b> to reuse a part-used sheet and the number of copies."),
         P("2. Click <b>Print test grid</b> and print it on plain paper. Hold it over a label sheet against a light: "
           "every outline should sit on a label. If it is off, set the X / Y offset in mm and print the grid again."),
         P("3. Print the labels at <b>Actual size / 100%</b>, never Fit to page. Use the laser template for laser "
           "WeatherProof film and the 95xxx template for inkjet."),
         P("4. Text shrinks to fit (down to 4 pt), then is cut with an ellipsis: it never runs off a label.")]

warn = Table([[P("<b>Awaiting your print check:</b> the sample sheet (Desktop: Stelvio Sample Service Labels.pdf) uses "
                 "a stand-in odometer of 142,290 km, because MES logged the 2026-09-15 oil-change reset without one. "
                 "Avery 6576 and 6578 durable ID margins are not published anywhere found, so cuore spreads the labels "
                 "evenly: print the test grid first and tell cuore the offsets if they miss.")]], colWidths=[7.5 * inch])
warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN),
                          ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#c07a1c")),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

story = [P("Service Labels - 2018 Alfa Romeo Stelvio 2.0T", title),
         P("VIN ZASFAKPN5J7B88115  |  cuore Labels page: printable Avery reminder tags  |  2026-09-26", sm),
         Spacer(1, 6), P("Label previews from the sample sheet, shown at 70% of actual size", h), previews, Spacer(1, 6),
         P("Label kinds", h), kinds, Spacer(1, 6),
         P("Avery templates", h), tmpl,
         P("CORROBORATED: size and count from Avery, margins from two other sources and checked to add up to 8.5 x 11 in. "
           "SINGLE-SOURCE: derived from Avery's size and count only. UNVERIFIED: size and count known, margins not.", sm),
         Spacer(1, 6)] + steps + [Spacer(1, 6), warn]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, "cuore Labels: /v/ZASFAKPN5J7B88115/labels  |  PDF: /v/<VIN>/labels.pdf  |  "
                 "print at 100%, test grid first on new stock")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.45 * inch,
                  bottomMargin=0.55 * inch, title="Stelvio Service Labels").build(story, onFirstPage=foot,
                                                                                onLaterPages=foot)
print(OUT)
