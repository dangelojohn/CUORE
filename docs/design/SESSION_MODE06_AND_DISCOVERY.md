# Session plan: Mode 06 layout proof and responder naming

Car: 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115. All COM3 contact goes through CUORE
(never a raw adapter script). MES must not be connected to the adapter while CUORE reads.

## A. Mode 06 layout check (one live read, read-only)

1. Engine state: key on, engine running at idle, warm (EVAP and catalyst monitors only report
   after they have run; a cold or just-cleared car returns fewer test ids, which is fine for the
   layout proof). Park, handbrake on.
2. Bus and cable: CAN-C, the OBD port directly (no blue A5 / grey A6 bypass cable). Legislated
   Mode 06 is answered on the OBD route (STP 33), which CUORE tries first and then the other route.
3. Run in CUORE: `GET /live/obd/mode06` (MCP `read_mode06`), no `mids` argument so the supported
   bitmaps (06 00, 06 20, ...) are read too. A call with `mids=3C,3B` also writes the file but has
   no bitmap to check against.
4. CUORE re-parses the raw reply by itself (`cuore/live/mode06_layout.py`) and writes
   `C:\ProgramData\cuore\mode06_layout_check\<timestamp>.json` (raw reply + verdict). The response
   carries `layout_check` with `ok`, `anomalies` and `saved_to`.
5. Done looks like: `layout_check.ok` is true, no anomalies, and the saved file lists the records.
   That proves the 9-byte big-endian layout once; keep the file. If `ok` is false, read the
   anomalies and `alternative_layouts_tried` in the file: a better-fitting alternative means the
   layout, not the car, is wrong. Do not edit `mode06.py` from one guess; compare the saved raw.
6. Scaling stays unknown for any UASID not in `mode06._UASID_TABLE`; this check does not change
   that. The ranges tested are listed in `mode06_layout.RULES` (TID 00 and UASID 00/FF are treated
   as reserved: an assumption, not a verified table).

## B. Discovery responder naming (sweep needs the car; naming and accept do not)

1. Engine state: key on, engine off is enough (modules awake); engine running is also fine.
   Battery charger or a healthy battery; doors closed so modules do not sleep mid-sweep.
2. Bus and cable, one sweep per bus: CAN-C with no cable; CAN-IHS with the blue A5; CAN-CH with the
   grey A6. `POST /live/discover` is the 29-bit sweep; the 11-bit sweep (discover11) also stores its
   hits as responders, without the extra identity reads. Fit the cable CUORE asks for, verify the
   bus, then sweep.
3. Run in CUORE: `POST /live/discover` with `bus` and `vin`. After the
   sweep, every responder's Annex C identity set (F190 F187 F188 F189 F18C F191 F192 F194 F195,
   read-only `22`) is read and stored with its address in `C:\ProgramData\cuore\responders.json`
   (`responders` in the response says what was stored).
4. Back at the desk, no car: `GET /live/responders?vin=...` or MCP `name_responders`. Each
   responder gets a status:
   - `proposed by MES log match`: the module name plus the reason, with the log file and line of
     every matching string (hardware / software number, spare part, drawing number, serial, ISO
     code) from `C:\Program Files (x86)\MultiEcuScan\SCAN_*.txt` and `FESLog_*.txt`. Only logs
     printing this VIN are used.
   - `ambiguous` or `no MES log match`: nothing proposed.
5. Owner decision: read the reason, then `POST /live/responders/accept` with `vin`, `address`
   (`29` or `18DA29F1`) and `module` (e.g. `DTCM`), or MCP `accept_responder`. This writes
   `confirmed (owner)` into `addresses.json`, which `resolve_module` reads; nothing is promoted
   without this call. Only 29-bit responders can be promoted. A warning is returned if the same
   target byte is already confirmed for another module.
6. Done looks like: every responder you care about is either `confirmed (owner)` or has a stated
   reason it is not. DTCM at 18DA29F1, ESM, DASM, AFLS, PAM and HALF should each show a proposal
   with log lines before you accept. If an identity DID that MES prints is absent from the
   responder (module did not answer it), the match falls to the strings it did answer.
