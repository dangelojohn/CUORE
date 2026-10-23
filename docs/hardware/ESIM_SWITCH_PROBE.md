# ESIM switch probe

A small, read-only meter that watches the ESIM switch circuit while the car runs, so CUORE can record whether the ECM's EVAP test ever closes the switch. It taps the circuit; it never drives it.

Status: design plus the CUORE software side (serial channel source, simulator, recording preset). **No hardware has been built.** Everything below the firmware sketch is untested on the car; the host software is checked only against the simulator (`cuore/tests/check_esim_probe.py`).

Provenance labels used here: **[car]** = a reading or document from this car; **[lit]** = outside literature about FCA ESIMs in general (`mes-log-mcp/mes/parts.py`, `ESIM_DESIGN`, "outside literature, not a reading from this car"); **[design]** = this document's own engineering choice.

## 1. Why this exists

The ESIM switch has no readable DID, MES lists no ESIM parameter, and CUORE refuses the 0x31 routine (`docs/research/CEL_2026-10-19_DIAGNOSIS.md`, Test A). So the switch state can only come from wiTECH or from a meter on the circuit. wiTECH needs a parked car and a hand pump; a drive cycle cannot be watched that way. The probe is the meter, logged at 20 Hz next to the PIDs, so one drive answers: did the switch close when the ECM ran its test?

What the probe sees is the voltage at the ESIM connector. It is **not** what the ECM concluded. Whether the ECM read the same closure is a separate question (hypothesis C7 in the diagnosis).

## 2. What is known about the circuit

| Fact | Provenance |
|---|---|
| Passive module, no solenoid; weighted gravity valves, about 0.5 inH2O pressure and 2.2 inH2O vacuum | [lit] |
| Internal switch closes at about 1 inH2O vacuum; 0.5 to 2 ohm closed | [lit] |
| ECM supplies a 5 V reference and a ground; the signal reads about 5 V at rest and about 0 V while the switch is closed | [lit] |
| Mounted vertically (white cylinder up); wrong orientation = switch never closes | [lit] |
| No ESIM circuit DTC exists on this ECM (an open or short will not set a code by itself) | [car] status-bit map 2026-10-19 |
| ESIM connector is behind the driver-side rear wheel liner, in the splash area | [car] `ESIM Wiring Test` PDF |
| **Pin numbers, wire colours, ECM pin, ground point, reference voltage: not in the repo** | [car] the `ESIM Wiring Diagram Lookup` form is still blank |

### Pinout: confirm at the connector with a meter

Nothing in the repo names the ESIM connector pins or wire colours, and this document does not guess them. Before fitting the probe, identify the three roles on the **car-side (harness) connector**, ESIM unplugged, with a digital meter (10 Mohm input) and back-probe leads, never probes pushed into the front of the terminals:

1. **Ignition OFF, ohms.** Find the pin with under about 2 ohm to battery negative / a clean chassis ground. That is the **ground pin**. (This is wiring test B3.)
2. **Ignition ON, engine off, volts to chassis ground.** A pin that reads about 5 V is the **5 V reference** or, on a two-wire switch, the signal line pulled up to 5 V (wiring test B2: "the ECU's pull-up on the switch line"). Record the exact value; the thresholds in section 4 assume 5 V.
3. **Which one is the switch signal?** Plug the ESIM back in, back-probe each non-ground pin, and apply gentle hand vacuum at the ESIM port (wiTECH Test A procedure). The pin that falls from about 5 V to about 0 V and returns on release is the **switch signal**. A pin that stays near 5 V throughout is the **reference**.

Outcomes:

- **Three pins (reference, signal, ground):** tap SIG on the signal pin and REF on the reference pin.
- **Two pins (signal pulled up, ground):** there is no separate reference to tap. Set `CUORE_ESIM_PROBE_NO_REF=1` on the host and build the firmware with `NO_REF` true. The state rule then ignores the reference, and a missing pull-up can no longer be told apart from a wiring fault, which is the price of having one tap fewer.
- **Anything else (a pin at 12 V, a pin at mid-voltage):** stop. Do not fit the probe. Write down what you measured and ask for the wiring diagram page for this VIN.

Write the result into the table on page 2 of the `ESIM Wiring Test` PDF; the same table serves this probe.

## 3. Safety

1. **Tap only. Never feed voltage into an ECM line.** The probe is a high-impedance voltmeter. Its ESIM-side pins are inputs; nothing on the board may drive them. The firmware has no output on those pins and the host software never writes a byte to the probe port.
2. **No splice and no cut without the owner's OK.** Use back-probing at the connector. A splice into the harness is a modification of the car's wiring and needs the owner's explicit permission, recorded on the job.
3. **Back-probe at the connector.** Fine back-probe pins or a breakout lead slid in behind the seal, insulated, with the ESIM connector fully re-seated afterward. Check the terminals still grip.
4. **Route the leads away from the exhaust and the moving parts.** Keep them clear of the exhaust, heat shields, the rear subframe edge, the wheel and driveshaft, and sharp wheel-well edges. Strain-relieve and tie them to existing loom with soft ties. Twisted pair, kept short (about 1.5 m or less, [design]).
5. **Fuel vapour.** The ESIM sits in the EVAP system. No sparks, no soldering, no work near the canister with the system open. Hand vacuum only for tests; never shop air.
6. **Power the probe from the laptop's USB, not from the car.** No 12 V wire is needed anywhere. If the probe leads ever find 12 V (a short in the harness), the 2.6 Mohm input path limits the current to about 5 microamp and the clamp diodes hold the buffer inputs inside its supply.
7. **Ground loops.** The probe ground goes to the ground pin you identified (or a known-good chassis ground); the laptop then shares a ground path through USB. Run the laptop on battery, or put a USB isolator in line (section 5, optional).
8. **Never on COM3.** COM3 is the OBD adapter. The probe uses a different USB port; CUORE refuses `COM3` and the OBD adapter's resolved port as the probe port.
9. **Do not clear codes** before, during or after a probe drive; the monitor must be left to run.
10. **No ESIM wiring tests with 12 V.** Applying 12 V across the switch can damage it [lit]. This probe needs none.

## 4. Electrical design

Two identical channels, SIG and REF.

```
 ESIM connector (back-probe)                                  to MCU ADC pin
 SIG ----[ Rs 100k ]----[ R1 1.5M ]----+----------[ buffer ]----[ 10k ]----+---- ADC
                                       |                                    |
                                    [ R2 1.0M ]                          [100 nF]
                                       |                                    |
 GND (ESIM ground pin) ----------------+------------------------------------+---- probe GND
```

- **Series protection 100 kohm** at the tap end, so a fault on the probe side can never load the circuit meaningfully.
- **Divider R1 + R2** brings 0 to about 5.5 V into 0 to about 2.1 V. Total input resistance seen by the car: 100k + 1.5M + 1.0M = **2.6 Mohm**, above the 1 Mohm requirement. Divider ratio 1.0 / 2.6, so firmware multiplies the ADC millivolts by **2.6** (calibrate this against a meter, section 7).
- **Buffer.** A divider this stiff (source impedance about 600 kohm) cannot drive a microcontroller ADC directly. A single-supply rail-to-rail CMOS op-amp as a unity-gain follower (pA input bias) presents the divider with an effectively infinite load. Power it from the probe's own 3.3 V or 5 V; its input never exceeds about 2.1 V in normal use.
- **Input clamp** at the buffer input: two small-signal Schottky diodes, one to the supply rail and one to ground, so a transient cannot reach the op-amp.
- **Output filter** 10 kohm + 100 nF (corner about 160 Hz) at the ADC, with 16 readings averaged per sample in firmware.
- **Optional digital isolation:** a USB isolator between the probe and the laptop (galvanic isolation of the data and power lines). This isolates the whole probe from the laptop and is the simple way to remove a ground loop. An optocoupler on the analog signal is not recommended: it would give only an OPEN/CLOSED bit, losing the millivolts the FAULT state and the sag check need.
- **Resolution:** a 10-bit 5 V ADC (Nano class) gives about 5 mV at the pin, about 13 mV at the car side after the 2.6 factor. A 12-bit ESP32-C3 ADC is finer. Both are far inside the 800 mV / 4000 mV / 4500 mV thresholds.

### State rule

```
CLOSED   sig < 800 mV  and  ref > 4500 mV
OPEN     sig > 4000 mV
FAULT    everything else (open or sagging reference, wiring, voltage in between)
```

CLOSED is checked first, then OPEN. FAULT includes: reference lost (ref low, sig low), a mid-voltage signal (a high-resistance contact or a failing pull-up), and both lines dead. The host (`cuore/live/esim_probe.py`, `classify_state`) re-derives the state from the millivolts and counts any disagreement with the firmware's state word in `state_mismatches`.

### Line protocol

ASCII over USB serial, 115200 baud, 8N1, 20 Hz, one line per sample:

```
ESIM,<ms>,<sig_mV>,<ref_mV>,<state>
ESIM,184250,4962,5010,OPEN
ESIM,184300,141,5004,CLOSED
```

`ms` = the probe's millisecond counter. Lines not beginning `ESIM,` (boot banner, lines starting `#`) are ignored by CUORE. The probe only transmits.

## 5. Parts list (generic)

| Qty | Part | Note |
|---|---|---|
| 1 | Microcontroller board with USB serial: ESP32-C3 development board (3.3 V) or Nano-class 5 V board | either works; ADC pins differ, see the sketch |
| 1 | USB data cable, short | to the laptop |
| 1 | Dual rail-to-rail CMOS op-amp, single supply, picoamp-class input bias | unity-gain buffers, one per channel |
| 2 | Resistor 100 kohm, 1 % metal film | series protection |
| 2 | Resistor 1.5 Mohm, 1 % | divider top |
| 2 | Resistor 1.0 Mohm, 1 % | divider bottom |
| 2 | Resistor 10 kohm, 1 % | output filter |
| 2 | Capacitor 100 nF | output filter |
| 1 | Capacitor 100 nF | op-amp supply decoupling |
| 4 | Small-signal Schottky diode (or 2 dual-diode packages) | input clamps |
| 1 | Small plastic enclosure, strain relief for the leads | non-conductive |
| 3 | Insulated back-probe pins (SIG, REF, GND) with fine leads, 1.5 m twisted | no piercing of insulation |
| 1 | Pull-up resistor 10 kohm and two jumper leads | bench rig only (section 7) |
| 1 | Soft cable ties, split loom | routing |
| optional | USB isolator (galvanic isolation of data and power) | ground-loop removal |
| optional | USB power bank | to power the probe separately from the laptop, see section 8 |
| for building | Multimeter, 10 Mohm input | calibration and pin identification |

## 6. Firmware sketch (reference, untested)

Read-only. It has no code path that drives the ESIM pins.

```cpp
// ESIM switch probe -- transmit only. ESP32-C3 or Nano-class (Arduino framework).
#include <Arduino.h>

const float  DIV     = 2.6f;    // (Rs + R1 + R2) / R2 = 2.6M / 1.0M; calibrate against a meter
const bool   NO_REF  = false;   // true for a two-wire switch (see section 2)
#if defined(ARDUINO_ARCH_ESP32)
  const int PIN_SIG = 0, PIN_REF = 1;                       // ADC1 inputs on a C3 board
  static uint32_t pin_mV(int p) { return analogReadMilliVolts(p); }
#else
  const int PIN_SIG = A0, PIN_REF = A1;
  static uint32_t pin_mV(int p) { return (uint32_t)analogRead(p) * 5000UL / 1023UL; }
#endif

static long car_mV(int pin) {            // 16-sample average, scaled back up past the divider
  uint32_t s = 0;
  for (int i = 0; i < 16; i++) s += pin_mV(pin);
  return (long)((s / 16.0f) * DIV + 0.5f);
}

static const char* classify(long sig, long ref) {
  if (sig < 800 && (NO_REF || ref > 4500)) return "CLOSED";
  if (sig > 4000) return "OPEN";
  return "FAULT";
}

void setup() {
  Serial.begin(115200);
  Serial.println("# ESIM probe v1, 20 Hz, transmit only");
}

void loop() {
  static uint32_t next = 0;
  if ((int32_t)(millis() - next) < 0) return;
  next = millis() + 50;                   // 20 Hz
  long sig = car_mV(PIN_SIG);
  long ref = NO_REF ? 5000 : car_mV(PIN_REF);
  Serial.print("ESIM,"); Serial.print(millis()); Serial.print(',');
  Serial.print(sig);     Serial.print(',');
  Serial.print(ref);     Serial.print(',');
  Serial.println(classify(sig, ref));
}
```

Opening the serial port resets many Nano-class boards (DTR); the banner line is ignored and the first samples arrive about a second later. On an ESP32-C3 using the native USB port, enable "USB CDC on boot" in the board options.

## 7. Bench procedure: validate the probe before it goes near the car

Everything here is on a bench, with the probe on USB only. No car, no 12 V, no hand pump.

**A. Meter calibration (probe alone).**
1. Probe powered, SIG and REF inputs connected to a bench source you can measure with the meter: the probe's own 3.3 V or 5 V pin through a resistor chain is enough, or a battery pack in series with a resistor. Common ground.
2. At about 0.5 V, 2.5 V and 4.9 V, compare the reported `sig_mV` / `ref_mV` against the meter. Adjust `DIV` until they agree within about 2 %.
3. Record the three pairs on the job.

**B. State rules.**
1. Tie SIG to ground through a 1 kohm resistor (stand-in for a closed switch) with REF at about 5 V: expect `CLOSED`.
2. Float SIG with REF at about 5 V through the pull-up: expect `OPEN`.
3. Remove REF (leave it open): expect `FAULT`, with `ref_mV` near 0.
4. Hold SIG at about 2.5 V: expect `FAULT`.

**C. Real ESIM, on the bench, using the existing ESIM bench test** (`docs/handbook/esim/ESIM_Bench_Test_Stelvio.pdf`, wiki page ESIM Bench Test). Blow gently through a short clean hose, never suck, exactly as that sheet says. No hand pump and no 12 V are needed.
1. Wire the ESIM's two switch pins to the probe like the car would see them: one pin to probe GND; the other pin to the SIG input, pulled up to the probe's 5 V through the 10 kohm resistor; REF tapped on the 5 V side of that pull-up. (The 10 kohm is a stand-in; the ECM's real pull-up value is not known.)
2. Hold the ESIM still in the orientation the bench sheet says, and follow its step C. While the sheet's meter reads open, the probe should read `OPEN` (about 5 V). While gentle blowing closes the switch (the sheet's 0.5 to 2 ohm), the probe should read `CLOSED` (a few hundred millivolts at most) and return to `OPEN` when you stop. Repeat three times.
3. Wiggle the leads and press on the connector while closed: any `FAULT` or flicker in the probe is a probe or lead problem, not the car.

**D. Host chain with the simulator.**
1. Set `CUORE_ESIM_PROBE_PORT=sim` for the CUORE process, start a live session with the **esim-switch-watch** preset (probe channels only if no car is connected), and watch `esim_switch_state` toggle on the live board; start a recording and confirm the CSV carries the three probe columns and `ESIM CLOSED` / `ESIM OPEN` tags on the transitions.
2. Set the variable to the probe's real port (any COM port **other than COM3**) and repeat with the bench rig from step C. The channels must match the step C results.

Only after A to D agree is the probe ready to go to the car.

## 8. Fitting and the drive-cycle use case

**Fitting (needs the owner present and in agreement):** identify the pins (section 2), back-probe SIG, REF (if there is one) and GND at the car-side connector with the ESIM plugged in, route the leads per section 3, and close the enclosure inside the cabin or boot, away from heat.

**What to record:** the recording preset **esim-switch-watch** (`cuore/live/channels.py`, `RECORDING_PRESETS`):

| Channel | Source | Rate |
|---|---|---|
| `esim_switch_state` (1 CLOSED, 0 OPEN, -1 FAULT), `esim_signal_mV`, `esim_ref_mV` | probe | 20 Hz |
| `commanded_evap_purge` (PID 2E) | ECM | requested 2 Hz |
| `short_fuel_trim_b1` (PID 06) | ECM | requested 1 Hz |
| `engine_rpm` (PID 0C), `vehicle_speed` (PID 0D) | ECM | requested 2 Hz |
| `fuel_level` (PID 2F) | ECM | requested 0.2 Hz |

The recording gets one row per probe sample, and a TAG on every state change (`ESIM CLOSED`, `ESIM OPEN`, `ESIM FAULT`), the same way DTC changes are tagged.

**The drive:** the EVAP monitor wants the conditions the diagnosis already lists (cold start, fuel level in the 15 to 85 percent window the wiring-test sheet uses, a steady 20 minute or longer cruise, then a long soak). Start the session before the engine, with the probe port set. Do not clear codes. Afterwards read the CSV together with the EVAP monitor results in CUORE (Mode 06, readiness, status bytes).

**How to read it** (inference rules, to be filled in with the readings, not with this document's guesses):

- `esim_switch_state` never reaches CLOSED while `commanded_evap_purge` is above zero during the monitor window: no closure was seen at the connector. That fits vacuum never reaching the ESIM or a switch that does not close (hypotheses C1 to C5), and says nothing about the ECM's side. Compare the mV: a stuck 5 V is a clean OPEN; a mid-voltage is a wiring or contact problem (FAULT).
- CLOSED is seen, holds, and releases cleanly, yet the EVAP code sets: the circuit presented a closed switch at the connector. The question moves to what the ECM did with it (C7), subject to the probe being the only reading and the ECM's own view still unobserved.
- `FAULT` with the reference low or dropping out: a reference or ground problem on the harness side (C6), to be proven with the wiring test B2 and B3 before any repair.
- Flicker (CLOSED/OPEN/FAULT toggling in under a second) while the car is moving: contact or connector trouble, to be reproduced with the wiggle test.

**Limits, stated plainly:**
- The probe sees the connector, not the ECM's input stage.
- The ECM's engine-off leak test, if it runs after key-off, needs the probe powered with the ignition off. Power the probe from a power bank rather than from the laptop's port if the laptop sleeps; CUORE only records while it is running and the session is active, and the OBD side of the session ends when the ECM stops answering.
- Setting `CUORE_ESIM_PROBE_PORT` only takes effect for a CUORE process started after it is set.

## 9. Host software

`cuore/live/esim_probe.py`:

- opens the port named in `CUORE_ESIM_PROBE_PORT` (115200 baud, **read only**); `sim` replays a scripted open / closed / bounce / fault trace and opens no port; unset means the probe channels report "not set" and nothing else changes;
- refuses `COM3` and the OBD adapter's resolved port;
- registers `esim_switch_state`, `esim_signal_mV` and `esim_ref_mV` (kind `probe`) in the channel registry, shown on the live board in an "ESIM probe (external, serial)" group;
- a session of only probe channels needs no OBD adapter, so `sim` works with no car and no cable;
- `CUORE_ESIM_PROBE_NO_REF=1` selects the two-wire state rule.

Check script: `.venv/Scripts/python.exe cuore/tests/check_esim_probe.py`.

## 10. Open items for the owner

1. Confirm the three roles (reference, signal, ground) at the connector with a meter, section 2, and write the pin numbers and wire colours on the wiring-test sheet.
2. Decide whether the circuit has a separate reference pin (three-wire) or not (two-wire), which sets `NO_REF`.
3. Give an explicit OK before any splice. The plan above needs none (back-probe only).
4. Say whether the probe should be powered from a power bank for the key-off phase.
