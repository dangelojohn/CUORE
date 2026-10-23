#!/usr/bin/env python
"""Read-only CUORE scan runner for the 2018 Stelvio, 2026-10-22.

Plan: scan_plan_2026-10-22.md (same folder). HTTP only, against a running
CUORE (default http://127.0.0.1:5000). This script never imports cuore and
never opens COM3: every adapter contact is a CUORE session on the server.

Refuses to run unless CUORE_ADAPTER_IN=1 is set in the environment.

Order is fixed: preflight (no adapter) -> adapter voltage -> legislated OBD
(modes 01/02/03/06/07/09/0A) -> read-only UDS (0x19 / 0x22) -> adapter voltage
-> CUORE-state reads. Legislated reads come FIRST because on 2026-10-19 they
returned NO DATA after UDS sessions. Nothing legislated is repeated after UDS.

Every request goes through guard(): an allowlist of read-only paths plus a
deny-substring list. Anything else raises before a byte is sent.

Every raw response is saved to scan_2026-10-22/NN_<step>.json next to this
file (override with CUORE_SCAN_OUT). manifest.json is written at the end and
also on Ctrl-C / abort.

Env knobs
  CUORE_ADAPTER_IN=1          required
  CUORE_URL                   default http://127.0.0.1:5000
  CUORE_TOKEN                 sent as X-Cuore-Token when set
  CUORE_PLAN_FULL_SWEEP=1     also run the full CAN-C 22 F190 address sweep
                              (optional step B8; off by default)
  CUORE_SCAN_OUT              output directory override
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

VIN = "ZASFAKPN5J7B88115"
BASE = os.environ.get("CUORE_URL", "http://127.0.0.1:5000").rstrip("/")
OUT = Path(os.environ.get("CUORE_SCAN_OUT") or (Path(__file__).resolve().parent / "scan_2026-10-22"))

# CAN-C modules that have a usable address in cuore/live/addressing.py.
UDS_MODULES = ("ECM", "BCM", "TCM", "IPC", "RFHUB")

# ---------------------------------------------------------------- guard -----

#: Only these (method, path-regex) pairs may ever be sent.
ALLOW = [
    ("GET", r"^/api/live/(status|session|buses|modules|observations|audit)$"),
    ("GET", r"^/api/live/obd/(voltage|vin|supported|readiness|dtcs|mode06|freeze)$"),
    ("GET", r"^/api/live/obd/pid/[0-9A-Fa-f]{2}$"),
    ("GET", r"^/api/live/scan$"),
    ("GET", r"^/api/live/module/(ECM|BCM|TCM|IPC|RFHUB)/(identity|dtcs)$"),
    ("GET", r"^/api/live/module/(ECM|BCM|TCM|IPC|RFHUB)/did/(F132|19BD|1955|1001|1956|1004)$"),
    ("GET", r"^/api/live/module/ECM/dtc/P[0-9A-F]{4}(-[0-9A-F]{2})?$"),
    ("GET", r"^/api/scans/" + VIN + r"(/SCAN_\d{10}/export)?$"),
    ("POST", r"^/api/live/verify$"),
    ("POST", r"^/api/live/discover$"),
]

#: Belt and braces: a path containing any of these is refused even if it
#: somehow matched ALLOW.
DENY_SUBSTR = (
    "clear", "actuat", "cable", "probe", "coverage", "fullscan", "connect",
    "learn", "capture", "session/", "record", "alarms", "stream", "discover-dids",
    "repair", "liveboard", "buscapture", "export/", "/jobs", "send_raw", "reset",
)


class Refusal(Exception):
    pass


def guard(method: str, path: str, query: dict | None = None, body: dict | None = None) -> None:
    p = path.split("?", 1)[0]
    low = p.lower()
    # "/export" on the scans route is the one allowed use of that word.
    if low.endswith("/export") and low.startswith("/api/scans/"):
        low = low[: -len("/export")]
    for bad in DENY_SUBSTR:
        if bad in low:
            raise Refusal(f"{method} {p}: contains forbidden fragment {bad!r}")
    if not any(m == method and re.match(rx, p) for m, rx in ALLOW):
        raise Refusal(f"{method} {p}: not on the read-only allowlist")
    if p == "/api/live/verify" and (body or {}).get("bus") != "can_c":
        raise Refusal("verify is allowed on can_c only")
    if p == "/api/live/discover":
        b = body or {}
        if b.get("bus") != "can_c":
            raise Refusal("discover is allowed on can_c only")
        if b.get("confirm"):
            raise Refusal("discover must not pass confirm=true")
    if p == "/api/live/obd/dtcs" and (query or {}).get("kind") not in ("all", "stored", "pending", "permanent"):
        raise Refusal("bad dtcs kind")


# ------------------------------------------------------------ plumbing ------

STEPS: list[dict] = []
ISSUES: list[dict] = []
_seq = [0]
_last_http_at = [0.0]
NODATA_RX = re.compile(r"NO DATA|no ECU answered|no answer|no reply|TIMEOUT|did not complete", re.I)


def _http(method: str, path: str, query: dict | None, body: dict | None, timeout: float):
    guard(method, path, query, body)
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    tok = os.environ.get("CUORE_TOKEN", "").strip()
    if tok:
        headers["X-Cuore-Token"] = tok
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:  # connection refused, timeout ...
        return url, 0, {"transport_error": str(e)}, time.monotonic() - t0
    try:
        resp = json.loads(raw)
    except ValueError:
        resp = {"non_json_body": raw[:4000]}
    return url, status, resp, time.monotonic() - t0


def problems(obj, path="") -> list[str]:
    """Every 'warning'/'error' string anywhere in a response (silence, NRC text, bus errors)."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("warning", "error") and isinstance(v, str) and v:
                found.append(f"{path}/{k}: {v[:160]}")
            else:
                found.extend(problems(v, f"{path}/{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(problems(v, f"{path}[{i}]"))
    return found


def step(name: str, method: str, path: str, *, query: dict | None = None, body: dict | None = None,
         phase: str, timeout: float = 120.0, retry_once_if_silent: bool = False,
         pause: float = 0.6, note: str = ""):
    """Run one request, save the raw response, record issues. Returns (status, response)."""
    _seq[0] += 1
    n = _seq[0]
    wait = pause - (time.monotonic() - _last_http_at[0])
    if wait > 0:
        time.sleep(wait)
    attempts = []
    for attempt in (1, 2):
        started = datetime.now().isoformat(timespec="seconds")
        url, status, resp, dt = _http(method, path, query, body, timeout)
        _last_http_at[0] = time.monotonic()
        probs = problems(resp)
        silent = status != 200 or any(NODATA_RX.search(p) for p in probs)
        attempts.append({"attempt": attempt, "started": started, "http_status": status,
                         "elapsed_s": round(dt, 2), "problems": probs})
        if silent and retry_once_if_silent and attempt == 1:
            # ONE retry, UDS steps only. No adapter reset, no route change.
            time.sleep(3.0)
            continue
        break
    fname = f"{n:02d}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', name)}.json"
    record = {"step": name, "phase": phase, "method": method, "url": url, "body": body,
              "attempts": attempts, "http_status": status, "response": resp, "note": note}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / fname).write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    ok = status == 200 and not attempts[-1]["problems"]
    STEPS.append({"n": n, "step": name, "phase": phase, "file": fname, "http_status": status,
                  "clean": ok, "attempts": len(attempts)})
    if not ok:
        ISSUES.append({"n": n, "step": name, "http_status": status, "problems": attempts[-1]["problems"][:6]})
    flag = "ok " if ok else "ISSUE"
    print(f"[{n:02d}] {flag} {method} {path} {query or ''} -> {status} ({attempts[-1]['elapsed_s']}s)  {name}")
    return status, resp


class Abort(Exception):
    pass


def write_manifest(started: datetime, extra: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"plan": "scan_plan_2026-10-22.md", "vin": VIN, "base_url": BASE,
                "run_started": started.isoformat(timespec="seconds"),
                "run_finished": datetime.now().isoformat(timespec="seconds"),
                "order": "preflight -> legislated -> uds -> voltage -> state reads",
                "steps": STEPS, "issues": ISSUES, **extra}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


# ----------------------------------------------------------------- plan -----

NO_PATH = {
    "uds_19_0A_reportSupportedDTC": "No CUORE function sends 19 0A. 19 02 with mask FF (step B1) already lists "
                                   "every DTC the module tracks with its status byte; 19 0A is not needed for the codes.",
    "radio_ETM": "Radio/nav (ETM 0x6F) is registered on CAN-IHS; with cable 'none' CUORE has no route to CAN-IHS.",
    "parkview_camera_PAM": "PAM (parking control) is registered on CAN-CH and its address is unknown; "
                           "with cable 'none' CUORE has no route to CAN-CH. The only chance of seeing a "
                           "camera/PAM node on CAN-C is the optional full address sweep (B8); a silent result "
                           "is expected and is NOT evidence the module is absent.",
    "DTCM_DASM_ESM_addresses": "DTCM (0x29, unverified), DASM and ESM (address unknown) have no confirmed address "
                               "for this VIN (addresses.json holds only ABS), so /module/{code}/dtcs|identity "
                               "return 400. Only POST /api/live/discover (B7/B8) can find them; HTTP discover "
                               "probes 22 F190 only (ops.discover(probe_dids=...) exists in Python but is not on HTTP).",
    "mode09_beyond_VIN": "Only Mode 09 PID 02 (VIN) has an ops/HTTP reader. Cal IDs/CVN/IUPR exist only inside "
                         "fullscan (in-process mode09.read_mode09), which is on the forbidden list.",
    "module_identity_store_kind": "HTTP /identity records kind 'identity'; kind 'module_identity' is written "
                                  "only by ops.sweep_bus_full (fullscan), not reachable read-only over HTTP.",
}


def main() -> int:
    if os.environ.get("CUORE_ADAPTER_IN") != "1":
        print("REFUSED: set CUORE_ADAPTER_IN=1 to confirm the adapter is plugged in, ignition on / engine off, "
              "charger connected, MultiEcuScan closed.", file=sys.stderr)
        return 2
    if os.environ.get("CUORE_RESET_BEFORE_LEGISLATED") == "1":
        print("NOTE: CUORE_RESET_BEFORE_LEGISLATED is set in THIS shell. It only matters in the CUORE server's "
              "environment; this runner never resets the adapter.")

    started = datetime.now()
    extra: dict = {"no_read_only_path": NO_PATH}
    print(f"CUORE scan runner -> {BASE}   out: {OUT}")
    try:
        # ---------------- Phase 0: preflight (no adapter contact) ----------------
        _, st = step("status", "GET", "/api/live/status", phase="preflight")
        if st.get("transport_error"):
            raise Abort(f"CUORE not reachable at {BASE}: {st['transport_error']}")
        cable = (st.get("cable") or {}).get("cable")
        mes = (st.get("mes") or {}).get("state")
        if cable != "none":
            raise Abort(f"declared cable is {cable!r}, expected 'none' (CAN-C only). This runner never declares cables.")
        if mes == "connected":
            raise Abort("MultiEcuScan is connected to the vehicle; disconnect it first.")
        _, ses = step("poller_session", "GET", "/api/live/session", phase="preflight")
        if ses.get("active"):
            raise Abort("a live-data poll session holds the adapter; stop it from the CUORE UI first.")
        step("buses", "GET", "/api/live/buses", phase="preflight")
        step("modules_can_c", "GET", "/api/live/modules", query={"bus": "can_c"}, phase="preflight")
        _, obs0 = step("state_paths_observations", "GET", "/api/live/observations", query={"n": 1}, phase="preflight")
        _, aud0 = step("state_paths_audit", "GET", "/api/live/audit", query={"n": 1}, phase="preflight")
        extra["observations_path"] = obs0.get("path")
        extra["audit_path"] = aud0.get("path")
        extra["state_dir"] = str(Path(obs0["path"]).parent) if obs0.get("path") else None

        # ---------------- Phase A: adapter + legislated OBD (NO UDS yet) ----------------
        A = "legislated"
        step("A1_adapter_voltage_ATRV_before", "GET", "/api/live/obd/voltage", phase=A,
             note="adapter ATRV; passive session; no bus traffic")
        _, ver = step("A2_verify_can_c", "POST", "/api/live/verify", body={"bus": "can_c", "seconds": 2.0}, phase=A,
                      note="passive listen + one legislated 0100 probe; records which legislated route answers")
        if not ver.get("verified"):
            raise Abort("CAN-C did not verify (ignition on? plug seated? HS/MS switch?). Nothing else was sent.")
        extra["legislated_route"] = {k: ver.get(k) for k in ("verified_by", "probe_ok", "probe_stn_protocol", "responders", "awake")}
        _, vin = step("A3_mode09_vin", "GET", "/api/live/obd/vin", phase=A)
        if vin.get("vin") and vin["vin"] != VIN:
            raise Abort(f"car on the cable reports VIN {vin['vin']}, expected {VIN}.")
        _, sup = step("A4_mode01_supported_pids", "GET", "/api/live/obd/supported", phase=A)
        supported: set[str] = set()
        for ecu in (sup.get("by_ecu") or {}).values():
            supported.update(p.upper() for p in ecu.get("pids", []))
        step("A5_readiness_pid01_41_30_31_MIL", "GET", "/api/live/obd/readiness", phase=A,
             note="records store kind 'readiness' (PID 01, 41, 30, 31, MIL, EVAP verdict)")
        step("A5b_pid01_raw", "GET", "/api/live/obd/pid/01", phase=A)
        step("A5c_pid41_raw", "GET", "/api/live/obd/pid/41", phase=A)
        step("A6_dtcs_mode03_07_0A", "GET", "/api/live/obd/dtcs", query={"kind": "all"}, phase=A,
             note="stored (03), pending (07), permanent (0A); store kind 'obd_dtcs' x3")
        step("A7_mode06_3A_3C_3D", "GET", "/api/live/obd/mode06", query={"mids": "3A,3C,3D"}, phase=A,
             note="store kind 'mode06'; explicit MIDs skip discovery")
        # Mode 02 freeze frame (frame 0): the frozen DTC, then the EVAP-input PIDs.
        step("A8_freeze_dtc_pid02", "GET", "/api/live/obd/freeze", query={"pid": ""}, phase=A)
        for pid in ("05", "0F", "46", "2F"):
            step(f"A8_freeze_pid{pid}", "GET", "/api/live/obd/freeze", query={"pid": pid}, phase=A)
        # Mode 01 live values. Only PIDs the ECU says it supports (A4); if A4 gave nothing, try the required ones.
        want = ["21", "4D", "4E", "42", "46", "0F", "2F", "0C", "0D", "05", "33", "32", "2E"]
        required = {"21", "4D", "4E", "42", "46", "0F", "2F"}
        for pid in want:
            if supported and pid not in supported and pid not in required:
                continue
            if supported and pid not in supported:
                ISSUES.append({"step": f"A9_pid{pid}", "problems": [f"PID {pid} not in A4 supported list; read anyway once"]})
            step(f"A9_pid{pid}", "GET", f"/api/live/obd/pid/{pid}", phase=A)
        extra["legislated_done_at"] = datetime.now().isoformat(timespec="seconds")

        # ---------------- Phase B: read-only UDS (0x19 / 0x22 / 22 F190 discovery) ----------------
        B = "uds"
        print("--- legislated block finished; UDS block starts. No legislated read will be repeated. ---")
        sst, scan = step("B1_uds_19_02_all_modules", "GET", "/api/live/scan",
                         query={"bus": "can_c", "vin": VIN, "mask": 255, "detail": "true"}, phase=B,
                         retry_once_if_silent=True,
                         note="19 02 FF on every addressed CAN-C module, raw status byte per code; kinds 'scan' + 'module_dtcs'")
        rows = {m.get("ecu"): m for m in (scan.get("modules") or []) if isinstance(m, dict)}
        # A module "answered" if its 19 02 row has no adapter/bus error and no "no answer" warning
        # (a negative response still proves a live node).
        answered = [c for c in UDS_MODULES if rows.get(c) and not rows[c].get("error")
                    and not rows[c].get("warning") and not rows[c].get("skipped")]
        extra["uds_answered_in_B1"] = answered
        for code in UDS_MODULES:
            if code in answered:
                step(f"B2_identity_{code}", "GET", f"/api/live/module/{code}/identity", query={"vin": VIN},
                     phase=B, retry_once_if_silent=True, note="DIDs F190 F187 F188 F189 F18C F191 F192 F194 F195; kind 'identity'")
            else:
                ISSUES.append({"step": f"B2_identity_{code}", "problems": ["skipped: no 19 02 answer in B1"]})
        for code in answered:
            step(f"B3_did_F132_{code}", "GET", f"/api/live/module/{code}/did/F132", query={"vin": VIN},
                 phase=B, note="optional identity DID; NRC 31 is a normal answer; kind 'did'")
        # ECM EVAP codes: status + 19 04 snapshot + 19 06 extended data.
        ecm = rows.get("ECM") or {}
        # EVAP + EVAP-input range: P0440-P0457, P0496/98/99, P0460-P0464 (fuel level), P2400-P242F.
        evap_rx = re.compile(r"^P(04(4[0-9A-F]|5[0-7]|96|98|99|6[0-4])|24[0-2][0-9A-F])")
        always = ("P0440", "P0455", "P0456")
        picks: list[str] = []
        for rec in ecm.get("dtcs") or []:
            code = rec.get("code") or ""
            st_byte = rec.get("status") if isinstance(rec.get("status"), int) else 0
            # status 0x40 alone = "test not completed since clear": never failed, so no snapshot exists to read.
            if evap_rx.match(code) and (code[:5] in always or (st_byte & 0xBF)):
                picks.append(code)
        picks = list(dict.fromkeys(picks))[:8]
        extra["ecm_evap_codes_detailed"] = picks
        for code in picks:
            step(f"B4_dtc_detail_ECM_{code}", "GET", f"/api/live/module/ECM/dtc/{code}", query={"vin": VIN},
                 phase=B, retry_once_if_silent=True, note="status + 19 04 snapshot + 19 06 extended; kind 'dtc_detail'")
        # Battery / charge / EVAP-input DIDs.
        dids = [("ECM", "19BD", "IBS state of charge"), ("ECM", "1955", "ECM battery voltage"),
                ("ECM", "1001", "Fuel tank level"), ("ECM", "1956", "Ambient/barometric pressure"),
                ("BCM", "1004", "BCM battery voltage")]
        for mod, did, label in dids:
            if mod in answered:
                step(f"B5_did_{mod}_{did}", "GET", f"/api/live/module/{mod}/did/{did}", query={"vin": VIN},
                     phase=B, retry_once_if_silent=True, note=label)
        # DTCM at its registry address 0x29 (unverified): read-only 22 F190 + identity DIDs.
        step("B7_discover_DTCM_0x29", "POST", "/api/live/discover", phase=B, timeout=180,
             body={"bus": "can_c", "vin": VIN, "confirm": False, "candidates": ["29"], "per_target_timeout": 0.6},
             note="22 F190 at 18DA29F1 then identity DIDs. May persist a confirmed target to addresses.json (CUORE state, not the car)")
        if os.environ.get("CUORE_PLAN_FULL_SWEEP") == "1":
            step("B8_discover_full_can_c_sweep", "POST", "/api/live/discover", phase=B, timeout=1500,
                 body={"bus": "can_c", "vin": VIN, "confirm": False, "per_target_timeout": 0.3},
                 note="22 F190 at every address 00..FF except F1/33/BA; finds DASM/ESM/radio/camera if they answer on CAN-C")
        else:
            extra["full_sweep"] = "skipped (set CUORE_PLAN_FULL_SWEEP=1 to run step B8)"

        # ---------------- Phase C: voltage again, then CUORE-state reads ----------------
        step("C1_adapter_voltage_ATRV_after", "GET", "/api/live/obd/voltage", phase="end",
             note="UDS finished; compare with A1 for charger/battery sag")
        step("C2_observations_tail", "GET", "/api/live/observations", query={"n": 400, "vin": VIN}, phase="state")
        step("C3_audit_tail", "GET", "/api/live/audit", query={"n": 300}, phase="state")
        _, scans = step("C4_scanlog_list", "GET", f"/api/scans/{VIN}", phase="state")
        ids: list[str] = []
        try:
            items = scans.get("scans") if isinstance(scans, dict) else scans
            floor = started.strftime("%Y-%m-%dT%H:%M")
            ids = [s_["id"] for s_ in (items or []) if str(s_.get("started") or "") >= floor and s_.get("id")]
        except Exception:
            ids = []
        extra["scan_ids"] = ids
        for sid in ids[:3]:
            if re.fullmatch(r"SCAN_\d{10}", sid):
                step(f"C5_scan_export_json_{sid}", "GET", f"/api/scans/{VIN}/{sid}/export", query={"fmt": "json"}, phase="state")
        if not ids:
            extra["scan_id_note"] = ("could not pick a scan id from C4_scanlog_list; open that file and match by time. "
                                     "Convention: SCAN_<yymmddHHMM> of the first from-car observation of each 15-minute cluster.")
    except Abort as a:
        print(f"ABORT: {a}", file=sys.stderr)
        extra["aborted"] = str(a)
    except Refusal as r:
        print(f"GUARD REFUSED: {r}", file=sys.stderr)
        extra["guard_refusal"] = str(r)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        extra["interrupted"] = True
    finally:
        write_manifest(started, extra)
        print(f"manifest: {OUT / 'manifest.json'}   issues: {len(ISSUES)}")
    return 1 if extra.get("aborted") or extra.get("guard_refusal") else 0


if __name__ == "__main__":
    sys.exit(main())
