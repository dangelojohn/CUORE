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
