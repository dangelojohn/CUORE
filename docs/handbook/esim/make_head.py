import sys, math
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors

OUT = sys.argv[1]
W, H = letter
c = canvas.Canvas(OUT, pagesize=letter)
c.setTitle("ESIM bench test - 2018 Alfa Romeo Stelvio")


def st(size=9, lead=None, color="#111111", align=0):
    return ParagraphStyle("s", fontName="Helvetica", fontSize=size, leading=lead or size * 1.22,
                          textColor=colors.HexColor(color), alignment=align)


BODY = st(9.5, 11.6)
NAVY = colors.HexColor("#1f3a5f")
GREEN_F, GREEN_S = colors.HexColor("#d9f2dc"), colors.HexColor("#2e8b3d")
RED_F, RED_S = colors.HexColor("#fbdada"), colors.HexColor("#c0282d")
GREY_F, GREY_S = colors.HexColor("#e9e9ec"), colors.HexColor("#8a8a93")
STEP_F, STEP_S = colors.HexColor("#eaf1fb"), colors.HexColor("#3d6cb3")
DEC_F, DEC_S = colors.HexColor("#fff3d1"), colors.HexColor("#c58a00")
ARROW = colors.HexColor("#333333")


def para(text, w, style=BODY):
    p = Paragraph(text, style)
    _, h = p.wrap(w, 10000)
    return p, h


def box(x, ytop, w, text, fill=STEP_F, stroke=STEP_S, diamond=False, pad=6, style=BODY, lw=1.2):
    inner = w - 2 * pad - (12 if diamond else 0)
    p, h = para(text, inner, style)
    bh = h + 2 * pad
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(lw)
    c.roundRect(x, ytop - bh, w, bh, 7, fill=1, stroke=1)
    p.drawOn(c, x + pad + (12 if diamond else 0), ytop - pad - h)
    if diamond:
        cx, cy, r = x + pad + 5, ytop - pad - 6, 5.5
        c.setFillColor(stroke)
        pth = c.beginPath(); pth.moveTo(cx, cy + r); pth.lineTo(cx + r, cy); pth.lineTo(cx, cy - r); pth.lineTo(cx - r, cy); pth.close()
        c.drawPath(pth, fill=1, stroke=0)
    return ytop, ytop - bh


def head(x1, y1, x2, y2, color):
    a = math.atan2(y2 - y1, x2 - x1); s = 6.5
    p = c.beginPath(); p.moveTo(x2, y2)
    p.lineTo(x2 - s * math.cos(a - 0.4), y2 - s * math.sin(a - 0.4))
    p.lineTo(x2 - s * math.cos(a + 0.4), y2 - s * math.sin(a + 0.4)); p.close()
    c.setFillColor(color); c.drawPath(p, fill=1, stroke=0)


def line(pts, arrow=True, color=ARROW):
    c.setStrokeColor(color); c.setLineWidth(1.4)
    p = c.beginPath(); p.moveTo(*pts[0])
    for q in pts[1:-1]:
        p.lineTo(*q)
    x2, y2 = pts[-1]
    if arrow:
        x1, y1 = pts[-2]
        d = math.hypot(x2 - x1, y2 - y1); ux, uy = (x2 - x1) / d, (y2 - y1) / d
        p.lineTo(x2 - ux * 5, y2 - uy * 5)
    else:
        p.lineTo(x2, y2)
    c.drawPath(p, stroke=1, fill=0)
    if arrow:
        head(pts[-2][0], pts[-2][1], x2, y2, color)


def label(cx, cy, text, color="#111111", w=80, bold=True, anchor="c"):
    s = ParagraphStyle("l", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=9, leading=10.5,
                       textColor=colors.HexColor(color), alignment=1)
    p = Paragraph(text, s)
    tw = max(c.stringWidth(t, s.fontName, 9) for t in text.split("<br/>")) + 4
    ww = min(w, tw)
    _, h = p.wrap(ww, 1000)
    if anchor == "b": cy = cy + h / 2
    elif anchor == "t": cy = cy - h / 2
    c.setFillColor(colors.white)
    c.rect(cx - ww / 2 - 1.5, cy - h / 2 - 1, ww + 3, h + 2, fill=1, stroke=0)
    p.drawOn(c, cx - ww / 2, cy - h / 2)
    return h


def footer(n):
    c.setFont("Helvetica", 9); c.setFillColor(colors.HexColor("#555555"))
    c.drawString(30, 18, "Prepared with CUORE · 2026-10-20")
    c.drawRightString(W - 30, 18, "Page %d of 2" % n)


# ---------------- PAGE 1 ----------------
y = H - 30
c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 17)
c.drawString(30, y - 14, "ESIM bench test — new, untested part, out of the car")
sub, sh = para("2018 Alfa Romeo Stelvio 2.0T · Evaporative System Integrity Module · find the correct orientation "
               "(small white cap UP or DOWN) and prove the part works", W - 60, st(10, 12, "#333333"))
sub.drawOn(c, 30, y - 22 - sh)
y = y - 22 - sh - 8

_, yb = box(30, y, W - 60,
            "<b>RULES</b> &nbsp; <b>Blow gently</b> through a short clean hose — <b>never suck</b> (fuel vapour). Gentle = enough to make a candle flicker, "
            "not go out. &nbsp;<b>No battery, no 12 V</b> — the ESIM has no solenoid. Multimeter on the two switch pins, set to <b>ohms</b>. "
            "<b>Hold the ESIM perfectly still</b>; after every change of position <b>wait 5 seconds</b> before blowing.",
            fill=DEC_F, stroke=DEC_S)
y = yb - 8

ly = y - 9


def leg(x, fill, stroke, txt, dia=False):
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(1)
    c.roundRect(x, ly - 5, 22, 11, 3, fill=1, stroke=1)
    if dia:
        cx, cy, r = x + 11, ly + 0.5, 4.5
        c.setFillColor(stroke); p = c.beginPath(); p.moveTo(cx, cy + r); p.lineTo(cx + r, cy); p.lineTo(cx, cy - r); p.lineTo(cx - r, cy); p.close()
        c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#111111")); c.setFont("Helvetica", 9)
    c.drawString(x + 27, ly - 3, txt)
    return x + 27 + c.stringWidth(txt, "Helvetica", 9) + 14


lx = 30
lx = leg(lx, STEP_F, STEP_S, "Step")
lx = leg(lx, DEC_F, DEC_S, "Decision (diamond)", True)
lx = leg(lx, GREEN_F, GREEN_S, "PASS")
lx = leg(lx, RED_F, RED_S, "FAULTY")
lx = leg(lx, GREY_F, GREY_S, "Note")
y = ly - 16

