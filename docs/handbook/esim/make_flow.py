LX, LW = 122, 232
RX, RW = 420, 162
D2W = 130
RAIL = 40
cxL = LX + LW / 2
GAP = 22
RED = "#c0282d"
REDC = colors.HexColor(RED)

# A
a_t, a_b = box(LX, y, LW, "<b>A. PREPARE</b><br/>Tape-label the two holes “1” and “2”. Mark the small white cap end “W”. Meter should read <b>OPEN</b>.")
line([(cxL, a_b), (cxL, a_b - GAP)])
# B
b_t, b_b = box(LX, a_b - GAP, LW, "<b>B. POSITION 1: upright, W UP.</b><br/>Hold still 5 s. Blow gently into hole 1, then hole 2.", fill=DEC_F, stroke=DEC_S, diamond=True)
# D
d_t, d_b = box(RX, b_t, RW, "<b>D. POSITION 2</b><br/>upright, <b>W DOWN</b>. Hold still 5 s. Repeat B.", fill=DEC_F, stroke=DEC_S, diamond=True)
yb_mid = b_t - 12
line([(LX + LW, yb_mid), (RX, yb_mid)])
label((LX + LW + RX) / 2, yb_mid + 2, "BOTH pass<br/>easily", w=60, anchor="b")

# B -> C
c_top = b_b - 40
line([(cxL, b_b), (cxL, c_top)])
label(cxL, (b_b + c_top) / 2, "ONE hole passes easily, the OTHER is BLOCKED", w=230)
c_t, c_b = box(LX, c_top, LW, "<b>C. SWITCH TEST</b>, same position, held still.<br/>Blow gently into the <b>BLOCKED</b> hole.", fill=DEC_F, stroke=DEC_S, diamond=True)

# C -> PASS
p_top = c_b - 42
line([(cxL, c_b), (cxL, p_top)])
label(cxL, (c_b + p_top) / 2, "Meter CLOSES (about 0.5–2 ohm)<br/>while you blow, OPENS when you stop", w=230)
p_t, p_b = box(LX, p_top, LW, "<b>PASS in this position</b><br/>Blowing a little harder makes air suddenly pass (vacuum relief valve opening).", fill=GREEN_F, stroke=GREEN_S, lw=1.8)
line([(cxL, p_b), (cxL, p_b - GAP)])
# E
e_t, e_b = box(LX, p_b - GAP, LW, "<b>E. RECORD THE CORRECT ORIENTATION</b><br/>Write down: W up or W down (or the flat position), and which hole is the tank side.")
line([(cxL, e_b), (cxL, e_b - GAP)])
# F
f_t, f_b = box(LX, e_b - GAP, LW,
               "<b>F. FIT AND PROVE</b><br/>Mount on the car in the recorded orientation, vertical, tank-side hole to the canister. Ignition on, back-probe the ESIM signal wire: "
               "about 5 V at rest, about 0 V when gentle vacuum closes the switch. <b>Do NOT clear codes.</b> Drive until the EVAP monitor completes, then read in CUORE.")
fx_top = f_b - 30
line([(cxL, f_b), (cxL, fx_top)])
label(cxL, (f_b + fx_top) / 2, "Monitor complete", w=200)
x_t, x_b = box(LX, fx_top, LW, "<b>FIXED</b> — P0440, P0455, P0456 with no fail bits.", fill=GREEN_F, stroke=GREEN_S, lw=1.8)

# Right column: D -> D2
d2_top = d_b - 34
line([(RX + D2W / 2, d_b), (RX + D2W / 2, d2_top)])
label(RX + D2W / 2, (d_b + d2_top) / 2, "Both STILL pass easily", w=150)
d2_t, d2_b = box(RX, d2_top, D2W, "<b>Try lying flat</b>, connector at 12, 3, 6 and 9 o'clock, 5 s each.", fill=DEC_F, stroke=DEC_S, diamond=True)

gx = LX + LW + 10
y_dc = c_t - 12
yd_out = d_b + 11
# bus from D exit down to C
line([(RX, yd_out), (gx, yd_out), (gx, y_dc), (LX + LW, y_dc)])
label((gx + RX) / 2 + 1, yd_out - 3, "Pattern<br/>appears<br/>(W DOWN<br/>works)", w=48, anchor="t")
yd2 = d2_b + 12
line([(RX, yd2), (gx, yd2), (gx, y_dc)], arrow=False)
label((gx + RX) / 2 + 1, yd2 - 3, "Pattern in<br/>one of<br/>them: note<br/>position", w=48, anchor="t")

# notes
n1_t, n1_b = box(RX, d2_b - 56, D2W,
                 "<b>Note</b> The EASY hole is the tank/canister side; the BLOCKED hole is the fresh-air side (inferred from the design).",
                 fill=GREY_F, stroke=GREY_S)
n2_t, n2_b = box(RX, min(e_t, n1_b - 12), D2W,
                 "<b>Note: check the other upright position once.</b> If it ALSO seals, orientation is not critical for this part. If it leaks, orientation IS critical — mount exactly as found.",
                 fill=GREY_F, stroke=GREY_S)

# G faulty
g_top = x_b - 34
gh_t, g_b = box(30, g_top, W - 60,
                "<b>G. FAULTY</b> — Do not fit. Return it / replace with the VIN-correct ESIM and run this same test on the replacement before fitting.",
                fill=RED_F, stroke=RED_S, lw=1.8)
yb_r = b_t - 28
line([(LX, yb_r), (RAIL, yb_r), (RAIL, g_top)], color=REDC)
label((LX + RAIL) / 2, yb_r + 2, "BOTH blocked<br/>even when<br/>blown harder<br/>= FAULTY<br/>(valves<br/>stuck shut)", color=RED, w=80, anchor="b")
yc_r = c_t - 24
line([(LX, yc_r), (RAIL, yc_r)], arrow=False, color=REDC)
label((LX + RAIL) / 2, yc_r + 2, "Meter stays<br/>OPEN = FAULTY<br/>(switch)", color=RED, w=80, anchor="b")
rxg = RX + RW - 10
line([(RX + D2W, d2_t - 14), (rxg, d2_t - 14), (rxg, g_top)], color=REDC)
label(rxg, g_top + 60, "None<br/>FAULTY<br/>(weights<br/>not<br/>sealing)", color=RED, w=44)
print("G bottom", g_b, "fixed bottom", x_b, "n1", n1_b, "n2", n2_b, "d2", d2_b, "e_t", e_t, "rules/leg y", y)
