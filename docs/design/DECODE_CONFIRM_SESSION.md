# Decode-confirm session (sequential, static conditions)

One adapter: MES and CUORE never connect together. Each log is cut by tag number, so both runs must go through the same conditions in the same order. Read-only. Engine warm; battery maintainer on.

Tags: 1 = ignition on, engine off, pedal released. 2 = ignition on, engine off, pedal held fully down. 3 = engine idling, warm. 4 = steady 2000 rpm held (optional). Hold each condition 20 s or more (the first 3 s of each are dropped).

A. MES first
1. Connect MES to the ECM (Magneti Marelli IAW 10JA). Open the **Graph** tab.
2. Add: Engine speed; Boost pressure; Desired boost pressure; Boost pressure signal; Throttle position (Track 1); Throttle position (Track 2); Throttle angle; Throttle position; Atmospheric pressure; Vehicle speed; Battery voltage; Fuel level; Engine oil temperature; Engine temperature; Air temperature (Boost/Manifold). (Max 40.)
3. **CSV Start**.
4. Ignition on, engine off, pedal up. Press tag key **1**. 20 s.
5. Pedal fully down, held. Press tag key **2**. 20 s. Release.
6. Start the engine, idle warm. Press tag key **3**. 30 s.
7. Optional: hold 2000 rpm. Press tag key **4**. 20 s.
8. **CSV Stop**. Note the saved file name. Disconnect MES completely.

B. CUORE second
9. Start the session: `POST http://127.0.0.1:5000/live/session/start` body `{"channels":["engine_rpm","ecm_1000","ecm_1925","ecm_1926","ecm_195b","ecm_1959","ecm_195a","ecm_1956","barometric_pressure","ecm_1009","runtime_since_start","egr_temperature","throttle_position","vehicle_speed","ecm_1002","ecm_1955","fuel_level","ecm_1001","engine_oil_temp","ecm_1302"]}`
10. Record: `POST http://127.0.0.1:5000/live/record/start` -> `C:\ProgramData\cuore\recordings\live_<timestamp>.csv`.
11. Same conditions, same order, tag with `POST /live/record/tag` (key 1, 2, 3, optional 4), or the Live page tag buttons, each when the condition starts:
    ignition on/engine off/pedal up = **1**; pedal fully down = **2**; warm idle = **3**; 2000 rpm = **4**.
12. `POST /live/record/stop`, then `POST /live/session/stop`.

C. Analyse (no car contact)
13. MCP `decode_confirm_run(vin="ZASFAKPN5J7B88115", mes_log_path="<MES csv>", cuore_recording_path="C:\ProgramData\cuore\recordings\live_<timestamp>.csv")` (default `mode="static"`), or `POST /live/decode-confirm/run`.
14. Read `GET /live/decode-confirm/runs?run_id=<id>`: verdict, conditions compared, transform, reason per channel.
15. Accept per channel: `decode_confirm_accept(vin, run_id, channel)`; a `candidate` pairing also needs `confirm_pairing=true`. Result goes to `C:\ProgramData\cuore\did_overrides.json`; sensor health drops the suspect flag.

Rules: confirmed needs agreement in every condition with data, at least 2 conditions. Throttle candidates need tags 1 and 2 in both files. A MES text log (`FESLog_*.txt`) has no tags: every channel is `no_data` ("no tags"). A value that is the same in all conditions is `ambiguous`. `ecm_1009` and `egr_temperature` have no MES counterpart and stay `no_data`. Time-stamped graph CSVs can still be run with `mode="timestamp"`.
