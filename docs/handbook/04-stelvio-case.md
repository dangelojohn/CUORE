# The 2018 Stelvio case (VIN ZASFAKPN5J7B88115)

Full per-session detail lives in `docs/vehicles/ZASFAKPN5J7B88115/sessions/`; this is the standing summary. As of 2026-10-07, about 142,290 km.

## State

- Chronic EVAP codes P0455, P0440, P0456. The system is sealed (three smoke tests); canister, ESIM, cap, filter and purge valve are new. The ECM declares a fault when it does not see the ESIM switch report sealed, so the fault is the ESIM signal path (wiring or connector) or the ECM calibration.
- Clears on 2026-09-28 and 2026-09-29 (P0440 and B1176 returned between them). The 2026-10-04 engine session and scan read clean, after the clear and before any monitor re-ran: not proof of repair. Computed verdict: UNVERIFIED REPAIR.
- Freeze frames: P0455 at 93.7 % fuel and P0440 at 91.8 % (monitor window 15-85 %), P0456 at 80 %.
- No driver symptom reported across 12 EVAP sessions, which is the expected pattern for EVAP. Network and EVAP codes co-occurred in 6 of 18 sessions. The 28 Sep network and ADAS codes were gone by 29 Sep: one power or bus event. B1176 (rear left window riser) is a separate body fault.
- ECM software P235QB39 / 52170619. Recalls to check: 25V586000 (fuel pump), 18V636000 (2.0L ECM software). Bulletins: 18-030-17 REV. B, S2125000002, 18-048-23, TSB 21-035-20 (TCM).

## Next decisive steps

1. wiTECH Flash tab comparison of the ECM calibration.
2. Test A: vacuum on the ESIM while watching the switch parameter in wiTECH (one-page sheet in the case folder).
3. Do not clear codes until Test A is done; verify afterwards with a readiness read after drives at 15-85 % fuel.

## Pending maintenance (owner's manual schedule, no ledger records yet)

Transfer case oil (80k mi / 128k km / 8 yr) and drive belt (36k mi / 4 yr) overdue unless done; air filter and spark plugs due at 90k mi; brake fluid every 2 yr; cabin filter 20k mi / 2 yr; coolant 150k mi / 15 yr; oil max 10k mi / 1 yr (shop 8k mi / 12 mo). Enter a baseline visit and the 2026-09-15 oil change in CUORE.

## Open checks

Avery 6576/6578 label margins unverified (print the test grid); window riser B1176; grey-cable read of the chassis bus; unsourced values (EVAP purge and vapour-pressure limits, peak boost, tyre pressures from the door placard, P052E/P04DB, several torques marked UNKNOWN).
