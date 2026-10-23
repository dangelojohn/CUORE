# Ground voltage-drop test with a multimeter: 2018 Stelvio 2.0T

Written 2026-10-23. Procedure only: **no measurement from this car is in this
file.** Labels: **fact** = cited source or CUORE reading; **inference** = reasoned
from facts; **not found** = looked for, no source, no value offered.

Why: the failure-type wiring map (`GET /api/wiring`) shows no -11 / -14 / -16 code
on any module, but ABS `U1700-87` was logged at 10.6 V (2026-09-04) and BCM
`B101D-15` (battery voltage circuit, short to battery or open) is set as of
2026-10-23. A voltage-drop test is the direct way to find a resistive ground
or feed (**inference**: such a resistance can cause both). The load-step test
(`LOAD_STEP_VOLTAGE_TEST.md`) tells you which module to suspect; this test
measures the wiring itself.

## 1. How a voltage-drop test works

Current flowing through a resistance leaves a voltage across it. Put the
meter across a section of wiring that is carrying current: a good conductor
reads close to 0 V, a corroded or loose one reads more. A meter across a wire
with no current through it reads 0 V and proves nothing, so every
measurement below is made **under load**.

## 2. Equipment and safety

- Digital multimeter on the DC volts range with 0.001 V (mV) resolution; two
  alligator-clip probe leads so you do not have to hold probes near a running engine.
- A wire brush or abrasive pad to expose bare metal at the test points.
- Engine idling for the measurements. Keep hands, leads and the meter away
  from the serpentine belt, fan and exhaust. Ventilated area, handbrake on, in P.
- Do **not** disconnect the battery or any ground to "test" it: the car has
  many modules and disconnecting under load or then reconnecting can set codes and
  lose adaptations. This test needs no disconnection.
- Touch the probe to the bare metal of the **battery post itself** (the lead
  or lug clamped to it is part of what you are testing).

## 3. Load condition

Engine idling (or about 1500 rpm if the idle voltage is unstable), **headlights
on high beam + blower on maximum** (add rear defrost if you want a heavier load).
Same loads for all three measurements, and note them. Charger disconnected.
Let the voltage settle for 10 s before each reading.

## 4. The three measurements

Set the meter to DC volts. Polarity does not matter for this test; record the
magnitude.

| # | From | To | What a drop here means |
|---|---|---|---|
| 1 | Battery **negative post** | **Engine block** (bare metal on the block or a bolt threaded into it) | Resistance in the battery negative cable, its terminal, or the cable-to-block connection |
| 2 | **Engine block** | **Body / chassis** (bare metal, e.g. a body bolt or stud near the battery or in the engine bay) | Resistance in the engine-to-body ground strap(s) |
| 3 | **Body / chassis** | Battery **negative post** | Total body-side ground path. It should be about the sum of #1 and #2 if the body ground goes through the block, or small if the battery also has its own body ground lead |

Do #3 last as a cross-check: if #3 is much larger than #1 + #2, the extra
drop is in a part of the path not covered by #1 and #2 (for example the
battery's own body ground lead). If #3 is smaller than #2, the body is
grounded to the battery by a path that bypasses the block, which is fine.

Optional fourth and fifth (isolate the battery end): negative **post** to the
negative **clamp** (any reading above about 0.05 V means a loose or corroded
clamp), and the same on the positive side: positive post to the positive cable
lug.

For a **module** you suspect from the load-step result: with the same loads
on, measure from the module's ground pin (back-probe the connector, do not
pierce wires) to battery negative post. The pin allocation for the BCM, ABS and
IPC connectors is **not found** here; get it from the dealer or the service
information wiring diagrams.

## 5. Limits (general automotive practice, not Alfa-specific)

| Section | Limit | Source |
|---|---|---|
| Ground side, engine block / ground path to battery negative | about 0.2 V or less | [Fluke, starter-circuit voltage drop](https://www.fluke.com/en-us/learn/blog/digital-multimeters/how-to-check-starter-circuit-voltage-drop-with-a-multimeter) (read in full): ground-side test is starter housing / engine block to battery negative post |
| Positive side | about 0.3 V | same Fluke page |
| Total acceptable drop (positive + ground) | 0.2 to 0.5 V | same Fluke page |
| Any single connection | 0.1 V | [YouCanIC glossary](https://www.youcanic.com/glossary/voltage-drop-test/) (from the search summary; page not read in full) |
| Ground cable | 0.2 V | same YouCanIC entry |
| Per segment, power or ground side | 0.1 - 0.2 V | [Rick's Free Auto Repair Advice](https://ricksfreeautorepairadvice.com/the-professional-guide-to-conducting-a-voltage-drop-test/) (from the search summary; page not read in full) |

The published limits differ, so use this reading rule (**inference**, a
screening rule not a specification):

- 0.00 - 0.10 V per measurement: good.
- 0.10 - 0.20 V: acceptable but note it; clean and re-torque if it is a joint you can reach.
- above 0.20 V on any ground segment, or above 0.30 V on any one of the three
  measurements: a resistive connection; find and clean it, then repeat.
- The Fluke/YouCanIC figures are for high-current circuits (starter). Low-current electronics
  (modules, sensors) are more sensitive: a 0.3 V ground offset
  matters to a sensor reference. If the dealer gives an FCA figure, use theirs.

## 6. Stelvio-specific ground points

**Not found: no sourced diagram or forum post giving the engine-to-body ground
strap, battery negative cable routing or body ground-point locations for the
Stelvio was found** (searched 2026-10-23: Alfa forum threads returned were for
other models; a 2017 Giulia thread only describes a generic continuity method).
Ask the dealer for the **ground-point diagram and its G-codes** (the
wiring-diagram sheets list each ground as G-numbers with location and the
modules on it) for VIN ZASFAKPN5J7B88115.

What the repo does know, from FCA bulletin S2008000032 (scope there is
2020 Stelvio; check applicability to this VIN): the frame grounds are named
**G003A and G003B**, they are body/chassis grounds (not under-hood or in-cabin),
and that bulletin's fix for a multi-module warning cascade was securing connector
XY201 and cleaning both to bare metal. The exact body location is not given
(CUORE element ids `g003a`, `g003b`, `xy201`; `mes-log-mcp/mes/electrical.py`).
Test those as measurements once the dealer diagram shows where they are.

## 7. Known wiring weak point: recall 18V205 (BCM / A-pillar connector)

**Fact (cited):** NHTSA recall 18V-205 and Transport Canada recall 2018-151 cover
certain 2018 Stelvios. Water gets past the A-pillar sheet-metal joint and the
plenum / HVAC-box seam and corrodes the **BCM A-pillar connector and/or the BCM**;
effects named in the recall include warning lamps, loss of wipers, exterior
lighting and horn, and unintended turn signals. Remedy: dealers add sealing at the
A-pillar joint to the HVAC box.
Sources: [Transport Canada 2018151](https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018151),
[NHTSA 18V205 report](https://static.nhtsa.gov/odi/rcl/2018/RCLRPT-18V205-1808.pdf)
(PDF; I could not extract its text, the summary above is from the Transport
Canada page and press summaries),
[The Drive](https://www.thedrive.com/news/20091/alfa-romeo-stelvio-recalled-over-water-leaks.md).
Build-date windows quoted by different documents disagree (2017-03-20 to
2018-02-14 in the Part 573 summary; 2017-04-12 to 2018-03-19 in the dealer
document), so **check the VIN**, do not rely on the date.

**Status for this car: unknown.** The repo's recall row is unverified, and
whether ZASFAKPN5J7B88115 is in scope or was repaired is not known. Action:
VIN lookup on Transport Canada / NHTSA, and ask the dealer whether the sealing
was done.

**Inference (not stated by the recall):** BCM `B101D-15` is a battery-voltage
circuit open-or-short-to-battery code, and the BCM's `B1176-97` and the many
`U17xx` network codes are seen; corrosion at the BCM A-pillar connector is
a candidate for resistance on the BCM's feed or ground and should be inspected
(water marks, green/white corrosion, pin discolouration) before or together with
the ground test. A BCM whose own voltage reading (DID 1004) drops more than the
adapter's in the load-step test points the same way.

## 8. Recording the result in CUORE

Use the job's action and evidence fields; CUORE wants a descriptive entry (what,
when, values, meaning, next test), not a label. Fill this in for each
measurement and paste it as the text:

    WHAT: Voltage-drop test, <segment, e.g. battery negative post to engine block>,
      DC volts, <meter model>, probes on bare metal at <exact points>.
    WHEN: <YYYY-MM-DD HH:MM>, engine <idle / 1500 rpm>, loads <high beam + blower max>,
      adapter ATRV <x.x V> before, battery <y.y V> at the posts.
    VALUES: <0.xxx V>, with loads on; <0.xxx V> with loads off (optional baseline).
    MEANING: <within / over the 0.2 V ground limit (Fluke)>; supports / weakens /
      neutral for hypothesis "<text>" because <reason>.
    NEXT: <clean and re-torque X, then repeat / test the next segment / dealer
      ground diagram / inspect BCM A-pillar connector>.

How:
- Job action: `POST /api/jobs/{job_id}/actions` with
  `{"kind": "test", "text": "<the entry above>", "ref": {"kind": "measurement",
  "id": "gnd-neg-block-2026-10-23", "label": "Battery negative to engine block, loaded", "result": "0.xxx V"}}`.
  Use kind `repair` for a cleaning / re-torque, `inspection` for the connector look.
- Hypothesis evidence: `POST /api/jobs/{job_id}/hypotheses/{hyp_id}/evidence` with
  `{"action": "add", "side": "for" or "against", "ref": {same ref as above}}`. A
  failed measurement is evidence for a "resistive ground" hypothesis; three good
  ones are evidence against.
- Physical inspections (a corroded or loose G-point, water at a connector): electrical
  page (`/v/{vin}/electrical`), **Record inspection** on the matching element (`g003a`,
  `g003b`, `xy201`, `bcm`, `battery`), condition `ok / loose / corroded / water /
  chafed / not_found`, with a photo.
- Load-step recording: mention its file name
  (`live_load-step-voltage_<label>_<timestamp>.csv`) in the same entry.

After any cleaning or repair, **repeat the same measurement under the same loads**
and record it as a second entry; "prove the fix" means the before and after
numbers are both on the job.
