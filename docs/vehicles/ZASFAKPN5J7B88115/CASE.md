# Case file: 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115

Recurring EVAP codes **P0455** (large leak), **P0456** (small leak), **P0440** (EVAP system).
Case file as of 2026-09-26, about 142,290 km. Everything cuore produced for this car lives in
this folder; the live-read evidence lives in cuore's state directory (`C:\ProgramData\cuore`).

## Vehicle and ECU

| Field | Value |
|---|---|
| Engine | 2.0L GME-T4 MultiAir turbo, sales code EC2, Q4 AWD, ZF 8HP |
| ECU | Magneti Marelli IAW 10JA (MM10JA), hardware MM10JAHW232, drawing 52055320 |
| ECU spare part | 50544870 (same hardware reflashed across 2017-2021; never superseded) |
| ECU software | 52170619, supplier software P235QB39 ver 0000 |

No public source names a newer calibration. This car's software number is higher than every
MM10JA software number found publicly (highest indexed: 52145143 / P141VA0E, 2023 files), so it
has probably already been reflashed (CSN W05 and TSB 18-026-20 both cover this car). Only the
wiTECH Flash tab can confirm.

## Repair and test history

| When | What | Codes afterwards |
|---|---|---|
| 2025-09-24 | P0456 first logged, 114,117 km | chronic |
| 08/2025 | Gas cap new; EVAP canister replaced; smoke test clean | returned |
| 2026-09-02 | Canister filter new; fuel cap and seal new; valve at canister new; ESIM 04861961AD new | returned |
| 2026-09-15 | Codes cleared (only P0440 stored at the time) | all three back |
| 2026-09-16 | Second smoke test clean; E5 purge routing and E1 quick-connect OK | returned |
| 09-02 to 09-25 | Engine-side purge valve 68337662AC replaced | returned |
| 2026-09-25 20:02 | Freeze frames: P0455 at 141,930 km (fuel 93.7 %), P0440 at 142,227 km (91.8 %), P0456 at 142,290 km (cold-start idle, 80 %) | |
| 2026-09-25 20:12 | Live UDS read: all three status 0x4D (failed, pending, confirmed); MIL request bit clear | |
| 2026-09-25 20:27 | Codes cleared in MES (ECM, BCM, RFHUB, DASM) | re-running |
| 2026-09-26 | Owner: filter clear; no fuel in canister; quick-connect latched; no topping off; no hiss, smell or slow fill; no water ingress | |
| 2026-09-26 | Third smoke test: all sealed | |

The check-engine light has not been on: the ECM stores and confirms these codes without
requesting the MIL, so the light cannot show the fault or its repair on this car.

## Diagnosis

The EVAP system is **physically sealed** (three smoke tests) and every EVAP part is new, yet the
codes return. The ECM declares a leak when it does not see the **ESIM switch** report the system
sealed during its tests. On a sealed system with a new, correct ESIM the fault is one of:

1. **The ESIM signal path to the ECM**: switch contacts, connector behind the driver-side rear
   wheel liner, wiring, or ECM input. The only part never changed. No ESIM circuit code has set,
   so an intermittent or high-resistance fault is likelier than a clean break.
2. **The ECM calibration / test logic.** Probably already recent (see above), but unconfirmed.

Ruled out: purge valve (replaced; actuates), canister (replaced), ESIM part number (04861961AD is
listed as the production Stelvio/Giulia part), fuel cap, filter, quick-connect, overfilling,
flooding, water ingress, a physical leak.

## Next steps, in order

1. **wiTECH flash check**: ECM Flash tab, Current vs New ECU Part Number
   (`pdf/Stelvio wiTECH Flash Check (1 page).pdf`). Flash if different.
2. **wiTECH Test A**: vacuum on the ESIM while watching the ECU's switch reading
   (`pdf/Stelvio wiTECH Test A - ESIM Switch.pdf`). Follows the vacuum = wiring good, software;
   never changes = signal path.
3. If Test A fails: **wiring test** (`pdf/Stelvio ESIM Wiring Test (1 page).pdf`) with pins from
   the FCA diagram (`pdf/Stelvio ESIM Wiring Diagram Lookup.pdf`); **bench test** the ESIM if the
   wiring is good (`pdf/Stelvio ESIM Bench Test (1 page).pdf`).
4. Open recalls, especially **25V586000** (fuel pump; replaces the fuel delivery module) and
   **18V636000** (2.0L ECM software update): `pdf/Stelvio Recalls and Campaigns.pdf`.
5. After any fix: clear, drive several days (fuel 15-85 %, cold starts), then cuore
   `verify_repair` for P0455, P0456, P0440: all "passed since clear" confirms it.

Record every dealer-tool result on cuore's dealer page (`/v/ZASFAKPN5J7B88115/dealer`) so the
evidence gate and dossier use it.

## Other open codes on this car

BCM U1711/U1712/U1713-2F (erratic messages from brake and engine modules) and DASM C141C-86
(private CAN camera-radar): chronic since 2026-06-07; fault tree `network-cascade` /
`dasm-half-private-can`. BCM B1176-97 rear-left window riser. DASM C141B-97 camera blinded.
RFHUB B1040-64 appeared 2026-09-25 during ignition cycling: likely a bystander.

## Folder contents

- `pdf/`: every procedure and report given to the owner (copies of the Desktop PDFs).
- `pdf-sources/`: the scripts that generate them (reportlab; run with any Python that has
  reportlab installed; outputs go to the Desktop).
- `data/nhtsa_recalls_2018_stelvio.json`: NHTSA recalls API response, 2026-09-26.
- `bulletins/`: CSN W05 and TSB 18-026-20 (this car), plus two checked and found not applicable.
- Related repo docs: `docs/research/EVAP_STELVIO.md`, `docs/research/EVAP_SMOKE_TEST.md`,
  `docs/research/WITECH_PASSIVE_LEARNING.md`, `docs/reference/TSB_CATALOGUE.md`,
  `docs/reference/GIORGIO_MODULE_MAP.md`.
