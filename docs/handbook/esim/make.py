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


def label(cx, cy, text, color="#111111", w=80, bold=True):
    s = ParagraphStyle("l", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=9, leading=10.5,
                       textColor=colors.HexColor(color), alignment=1)
    p = Paragraph(text, s)
    tw = max(c.stringWidth(t.replace("&amp;", "&"), s.fontName, 9) for t in text.split("<br/>")) + 4
    ww = min(w, tw)
    _, h = p.wrap(ww, 1000)
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

LX, LW = 132, 222
RX, RW = 396, 186
RAIL = 44
cxL = LX + LW / 2
GAP = 22
RED = "#c0282d"

# A
a_t, a_b = box(LX, y, LW, "<b>A. PREPARE</b><br/>Tape-label the two holes “1” and “2”. Mark the small white cap end “W”. Meter should read <b>OPEN</b>.")
line([(cxL, a_b), (cxL, a_b - GAP)])
# B
b_t, b_b = box(LX, a_b - GAP, LW, "<b>B. POSITION 1: upright, W UP.</b><br/>Hold still 5 s. Blow gently into hole 1, then hole 2.", fill=DEC_F, stroke=DEC_S, diamond=True)
# D
d_t, d_b = box(RX, b_t, RW, "<b>D. POSITION 2: upright, W DOWN.</b><br/>Hold still 5 s. Repeat B.", fill=DEC_F, stroke=DEC_S, diamond=True)
yb_mid = b_t - 14
line([(LX + LW, yb_mid), (RX, yb_mid)])
label((LX + LW + RX) / 2, yb_mid + 15, "BOTH pass<br/>easily", w=60)

# B -> C
c_top = b_b - 40
line([(cxL, b_b), (cxL, c_top)])
label(cxL, (b_b + c_top) / 2, "ONE hole passes easily,<br/>the OTHER is BLOCKED", w=200)
c_t, c_b = box(LX, c_top, LW, "<b>C. SWITCH TEST</b>, same position, held still.<br/>Blow gently into the <b>BLOCKED</b> hole.", fill=DEC_F, stroke=DEC_S, diamond=True)

# C -> PASS
p_top = c_b - 46
line([(cxL, c_b), (cxL, p_top)])
label(cxL, (c_b + p_top) / 2, "Meter CLOSES (about 0.5–2 ohm)<br/>while you blow, OPENS when you stop", w=215)
p_t, p_b = box(LX, p_top, LW, "<b>PASS in this position</b><br/>Blowing a little harder makes air suddenly pass (vacuum relief valve opening).", fill=GREEN_F, stroke=GREEN_S, lw=1.8)
line([(cxL, p_b), (cxL, p_b - GAP)])
# E
e_t, e_b = box(LX, p_b - GAP, LW, "<b>E. RECORD THE CORRECT ORIENTATION</b><br/>Write down: W up or W down (or the flat position), and which hole is the tank side.")
line([(cxL, e_b), (cxL, e_b - GAP)])
# F
f_t, f_b = box(LX, e_b - GAP, LW,
               "<b>F. FIT AND PROVE</b><br/>Mount on the car in the recorded orientation, vertical, tank-side hole to the canister. Ignition on, back-probe the ESIM signal wire: "
               "about 5 V at rest, about 0 V when gentle vacuum closes the switch. <b>Do NOT clear codes.</b> Drive until the EVAP monitor completes, then read in CUORE.")
fx_top = f_b - 32
line([(cxL, f_b), (cxL, fx_top)])
label(cxL, (f_b + fx_top) / 2, "Monitor complete", w=200)
x_t, x_b = box(LX, fx_top, LW, "<b>FIXED</b> — P0440, P0455, P0456 with no fail bits.", fill=GREEN_F, stroke=GREEN_S, lw=1.8)

# Right column: D -> D2
d2_top = d_b - 40
D2W = RW - 26
line([(RX + 50, d_b), (RX + 50, d2_top)])
label(RX + 50, (d_b + d2_top) / 2, "Both STILL pass easily", w=120)
d2_t, d2_b = box(RX, d2_top, D2W, "<b>Try lying flat</b>, connector at 12, 3, 6 and 9 o'clock, 5 s each.", fill=DEC_F, stroke=DEC_S, diamond=True)

gx = (LX + LW + RX) / 2
# D -> C
y_dc = c_t - 12
yd_out = d_b - 14
line([(RX, yd_out), (gx, yd_out), (gx, y_dc), (LX + LW, y_dc)])
label(gx, (yd_out + y_dc) / 2 + 10, "Pattern<br/>appears<br/>(W DOWN<br/>works)", w=44)
# D2 -> C
y_d2c = c_t - 44
yd2 = d2_b + 14
line([(RX, yd2), (gx + 0, yd2)], arrow=False)
line([(gx, yd2), (gx, y_d2c), (LX + LW, y_d2c)])
label(gx + 0, yd2 + 0, "Pattern<br/>in one<br/>(note<br/>position)", w=44)

# notes
n1_top = d2_b - 120
n1_t, n1_b = box(RX, n1_top, D2W,
                 "<b>Note</b> The EASY hole is the tank/canister side; the BLOCKED hole is the fresh-air side (inferred from the design).",
                 fill=GREY_F, stroke=GREY_S)
n2_t, n2_b = box(RX, e_t, D2W,
                 "<b>Note: check the other upright position once.</b> If it ALSO seals, orientation is not critical for this part. If it leaks, orientation IS critical — mount exactly as found.",
                 fill=GREY_F, stroke=GREY_S)

# G faulty
g_top = x_b - 70
gh_t, g_b = box(30, g_top, W - 60,
                "<b>G. FAULTY</b> — Do not fit. Return it / replace with the VIN-correct ESIM and run this same test on the replacement before fitting.",
                fill=RED_F, stroke=RED_S, lw=1.8)
yb_r = b_t - 24
line([(LX, yb_r), (RAIL, yb_r), (RAIL, g_top)], color=colors.HexColor(RED))
label((LX + RAIL) / 2, yb_r + 21, "BOTH blocked even<br/>when blown harder<br/>= FAULTY<br/>(valves stuck shut)", color=RED, w=100)
yc_r = c_t - 24
line([(LX, yc_r), (RAIL, yc_r)], arrow=False, color=colors.HexColor(RED))
label((LX + RAIL) / 2, yc_r + 15, "Meter stays OPEN<br/>= FAULTY (switch)", color=RED, w=100)
rxg = RX + RW - 12
line([(RX + D2W, d2_t - 14), (rxg, d2_t - 14), (rxg, g_top)], color=colors.HexColor(RED))
label(rxg, g_top + 50, "None<br/>= FAULTY<br/>(weights<br/>not sealing)", color=RED, w=60)
print("G bottom", g_b, "fixed bottom", x_b, "n1", n1_b, "n2", n2_b, "d2", d2_b, "e_t", e_t)
footer(1)
c.showPage()

# ---------------- PAGE 2 ----------------
y = H - 36
c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 17)
c.drawString(30, y - 14, "ESIM bench test — extra checks and sources")
y -= 34
_, y = box(30, y, W - 60,
           "<b>WHITE CAP CHECK</b> (optional, if the white cap is visible)<br/><br/>"
           "Hold still in the working position and blow gently into the <b>EASY</b> hole. The cap should lift and drop back freely the moment you stop. "
           "<b>Stays up or sticks = FAULTY.</b><br/><br/>"
           "<b>Note:</b> the white cap's identity is not documented — most likely the large weighted pressure valve; rely on the blow and switch results, "
           "not on the cap alone. A rattle or click when shaken is NOT a valid test.",
           fill=STEP_F, stroke=STEP_S, style=st(11, 14.5), pad=10)
y -= 16
_, y = box(30, y, W - 60,
           "<b>WHAT THIS TEST CANNOT PROVE</b><br/><br/>"
           "Breath is not measured, so it cannot confirm the exact switch point (about 1 inch of water vacuum). For that, use a hand vacuum pump with a "
           "gauge in inches of water and stay between 1 and 2 inH<sub>2</sub>O (above about 2.2 inH<sub>2</sub>O the vacuum relief valve opens by design and mimics a leak).",
           fill=GREY_F, stroke=GREY_S, style=st(11, 14.5), pad=10)
y -= 16
_, y = box(30, y, W - 60,
           "<b>SOURCES</b> (outside literature — none is a reading from this car)<br/><br/>"
           "• <b>Chrysler ESIM design and thresholds</b> (pressure valve ~0.5 inH<sub>2</sub>O, vacuum valve ~2.2 inH<sub>2</sub>O, switch ~1 inH<sub>2</sub>O, ~0.5–2 ohm closed): "
           "vehicleservicepros.com article 53084355 “Chrysler ESIM”.<br/><br/>"
           "• <b>Vertical mounting, no solenoid, 5 V reference:</b> B&amp;W/BWD tech tip bw10235esim.<br/><br/>"
           "• <b>Wrong orientation causing P0440/P0441/P0456, fixed by re-orienting (Ram):</b> ALLDATA tech tip “incorrect-eism-install-ram-evaporative-issues”.<br/><br/>"
           "Flow directions in the mouth test are inferred from the design.",
           fill=colors.white, stroke=GREY_S, style=st(10.5, 13.8), pad=10)
footer(2)
c.showPage()
c.save()
