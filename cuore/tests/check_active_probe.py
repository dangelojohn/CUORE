"""Regression checks for the CAN-C active-probe verification fallback.

2018+ Giorgio cars (Security Gateway Module) put the OBD diagnostic pair
(pins 6/14, CAN-C) behind a gateway that emits no broadcast traffic at all --
a passive listen there is 0 frames on a perfectly healthy car. verify_bus()
now falls back to one legislated Mode 01 PID 00 request on CAN-C (never
can_ihs/can_ch) before reporting the bus silent. See cuore/live/ops.py
(_active_probe_0100, verify_bus) and cuore/live/transport.py
(AdapterLink.mark_verified, AdapterLink.session's _bypass_silence_guard).

Same posture as cuore/tests/check_live.py: plain script, ``check(label,
cond, detail)``, exit 1 on failure, no pytest -- a hand-written fake
``Stream`` that answers exactly the bytes a real ELM327/STN adapter would.
This never opens COM3 and never talks to the real adapter.

Run:
    .venv/Scripts/python.exe cuore/tests/check_active_probe.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-active-probe-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
os.environ["CUORE_AUTOSTART"] = "0"   # never let send_raw's cuore_client spawn a real cuore

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from cuore.live import ops  # noqa: E402
from cuore.live.buses import CAN_C, CAN_IHS  # noqa: E402
from cuore.live.errors import Refused  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


class ScriptedStream(Stream):
    """Same fake as check_live.py's: answers from a fixed script, keyed by
    the exact command sent. A command with no entry gets ``"?"`` -- the
    adapter's own "unrecognized" reply, which is benign (not an error, not a
    frame), exactly like a real STN that was asked something it has no
    answer for.
    """

    def __init__(self, script: dict[str, str]):
        self.script = script
        self._buf = bytearray()
        self._opened = False
        self.sent: list[str] = []

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
        self.sent.append(cmd)
        reply = self.script.get(cmd, "?")
        self._buf.extend(reply.encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        if not self._buf:
            return b""
        n = max(n, 1)
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    def in_waiting(self) -> int:
        return len(self._buf)

    @property
    def describe(self) -> str:
        return "scripted"


class RouteStream(ScriptedStream):
    """ScriptedStream that tracks the selected ``STP n`` and answers every
    hex (OBD request) command with ``NO DATA`` while on a protocol listed in
    ``silent_on`` -- the way this ECM is silent to legislated requests on
    one addressing flavour and answers on the other, depending on the day."""

    def __init__(self, script: dict[str, str], silent_on=()):
        super().__init__(script)
        self.proto = ""
        self.silent_on = set(silent_on)
        self.requests: list[tuple[str, str]] = []   # (stn protocol, hex request)

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
        if cmd.startswith("STP "):
            self.proto = cmd[4:].strip()
        if re.fullmatch(r"[0-9A-F]{2,}", cmd):
            self.requests.append((self.proto, cmd))
            if self.proto in self.silent_on:
                self.sent.append(cmd)
                self._buf.extend(b"NO DATA\r>")
                return
        super().write(data)


#: Common adapter-init replies every session needs, STN1170-flavoured.
_BASE = {
    "ATE0": "OK", "ATL0": "OK", "ATS0": "OK", "ATH1": "OK", "ATAT1": "OK",
    "ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2",
    "STP 34": "OK", "STP 33": "OK", "STP 54": "OK",
    "STCMM 0": "OK", "STCMM 1": "OK",
    "STFAC": "OK", "STPO": "OK",
    "ATCAF1": "OK", "ATSH7DF": "OK",
}


def _link(script: dict[str, str], port: str = "COM99", stream: "ScriptedStream | None" = None
          ) -> tuple[AdapterLink, ScriptedStream]:
    scripted = stream or ScriptedStream(script)
    lk = AdapterLink(stream_factory=lambda p, b: scripted, process="check_active_probe")
    lk.auto_verify_seconds = 0.05
    set_link(lk)
    return lk, scripted


_saved_port_env = {k: os.environ.get(k) for k in ("CUORE_OBD_PORT", "OBD_PORT")}
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)

try:
    # =======================================================================
    # (a) passive listen hears nothing, active probe gets 41 00 -> verified.
    # =======================================================================
    script_ok = dict(_BASE)
    script_ok["0100"] = "7E8 06 41 00 BE 3F A8 13"
    # deliberately no "STM" entry: the passive listen hears nothing on
    # either route (STP 34, then STP 33), same as the car on the bench.
    lk, scripted = _link(script_ok)

    result = ops.verify_bus("can_c", seconds=0.05)
    check("active probe: verified True", result.get("verified") is True, str(result))
    check_eq("active probe: verified_by", result.get("verified_by"), "active_probe_0100")
    check_eq("active probe: responders", result.get("responders"), ["7E8"])
    check("active probe: 0100 was actually sent", "0100" in scripted.sent, str(scripted.sent))
    check("active probe: link.verified records verified_by",
          lk.verified.get("can_c", {}).get("verified_by") == "active_probe_0100",
          str(lk.verified.get("can_c")))

    buses_out = lk.cable_state()
    can_c_row = next(b for b in buses_out["buses"] if b["bus"] == "can_c")
    check_eq("buses(): can_c verified", can_c_row["verified"], True)
    check_eq("buses(): can_c verified_by surfaced", can_c_row["verified_by"], "active_probe_0100")

    # A now-verified can_c also satisfies a normal (non-passive) session.
    try:
        with lk.session("after_probe", bus=CAN_C) as _sess:
            pass
        opened = True
    except Refused:
        opened = False
    check("a transmit session opens once the active probe has verified can_c", opened)

    # =======================================================================
    # (b) passive listen AND the active probe both hear nothing -> still
    #     refused, with the active-probe detail folded into the message.
    # =======================================================================
    script_silent = dict(_BASE)  # no "0100" entry either -> "?"
    lk2, scripted2 = _link(script_silent)

    result2 = ops.verify_bus("can_c", seconds=0.05)
    check_eq("silent: verified False", result2.get("verified"), False)
    check("silent: note mentions the active probe got no reply",
          "active probe 0100 got no reply" in (result2.get("note") or ""),
          repr(result2.get("note")))
    check("silent: 0100 was still tried", "0100" in scripted2.sent, str(scripted2.sent))

    try:
        with lk2.session("write_probe", bus=CAN_C) as _sess:
            pass
        refused = False
        msg = ""
    except Refused as e:
        refused = True
        msg = str(e)
    check("silent: a transmit session on can_c is refused", refused)
    check("silent: refusal message carries the active-probe detail",
          "active probe 0100 got no reply" in msg, msg)

    # =======================================================================
    # (c) can_ihs never gets an active probe: no "0100" is ever sent, and
    #     the result carries no active-probe verification.
    # =======================================================================
    script_ihs = dict(_BASE)  # also no "0100" entry -- it must never be asked for
    lk3, scripted3 = _link(script_ihs)

    result3 = ops.verify_bus("can_ihs", seconds=0.05)
    check_eq("can_ihs: verified False", result3.get("verified"), False)
    check_eq("can_ihs: verified_by is not active_probe_0100",
             result3.get("verified_by"), None)
    check("can_ihs: 0100 was never sent", "0100" not in scripted3.sent, str(scripted3.sent))
    check("can_ihs: no attempt is tagged active_probe",
          not any(a.get("active_probe") for a in (result3.get("attempts") or [])),
          str(result3.get("attempts")))

    # =======================================================================
    # (c2) can_ihs under blue_a5: silent listen -> one functional 3E 00.
    # =======================================================================
    script_3e = dict(_BASE)
    script_3e["3E00"] = "18DAF1A0 02 7E 00"
    lk5, scripted5 = _link(script_3e)
    lk5.set_cable("blue_a5")
    result5 = ops.verify_bus("can_ihs", seconds=0.05)
    check("ihs probe: verified True", result5.get("verified") is True, str(result5))
    check_eq("ihs probe: verified_by", result5.get("verified_by"), "active_probe_3e00")
    check_eq("ihs probe: responders", result5.get("responders"), ["18DAF1A0"])
    check("ihs probe: 3E00 sent on 18DB33F1 after the listen",
          "3E00" in scripted5.sent and "ATCP18" in scripted5.sent
          and "ATSHDB33F1" in scripted5.sent, str(scripted5.sent))
    check("ihs probe: link.verified records verified_by",
          lk5.verified.get("can_ihs", {}).get("verified_by") == "active_probe_3e00",
          str(lk5.verified.get("can_ihs")))

    script_3e_silent = dict(_BASE)
    lk6, scripted6 = _link(script_3e_silent)
    lk6.set_cable("blue_a5")
    result6 = ops.verify_bus("can_ihs", seconds=0.05)
    check_eq("ihs silent: verified False", result6.get("verified"), False)
    check("ihs silent: note mentions the probe",
          "active probe 3E00 got no reply" in (result6.get("note") or ""),
          repr(result6.get("note")))
    check("ihs silent: 3E00 was tried", "3E00" in scripted6.sent, str(scripted6.sent))
    check("ihs silent: attempt tagged active_probe",
          any(a.get("active_probe") for a in (result6.get("attempts") or [])))

    script_ch = dict(_BASE)
    script_ch["3E00"] = "18DAF1A0 02 7E 00"
    script_ch["0100"] = "7E8 06 41 00 BE 3F A8 13"
    for cable in ("blue_a5", "grey_a6"):
        lk7, scripted7 = _link(script_ch)
        lk7.set_cable(cable)
        try:
            result7 = ops.verify_bus("can_ch", seconds=0.05)
        except Exception as e:  # noqa: BLE001 -- unreachable under this cable is fine too
            result7 = {"verified": False, "exc": str(e)}
        check(f"can_ch/{cable}: never verified by a probe", not result7.get("verified"),
              str(result7))
        check(f"can_ch/{cable}: no 3E00/0100 ever sent",
              "3E00" not in scripted7.sent and "0100" not in scripted7.sent,
              str(scripted7.sent))

    lk7.set_cable("none")   # the declared cable persists in the state dir

    # =======================================================================
    # (d) send_raw: ATRV (adapter-only) never triggers the silence guard,
    #     even on a totally unverified link.
    # =======================================================================
    import json as _json

    script_atrv = dict(_BASE)
    script_atrv["ATRV"] = "14.1V"
    lk4, scripted4 = _link(script_atrv)
    check("ATRV precondition: can_c starts unverified",
          not lk4.is_verified(CAN_C), str(lk4.verified))

    import server as obd2_server  # noqa: E402  -- obd2-mcp/server.py

    out = _json.loads(obd2_server.send_raw("ATRV"))
    check("send_raw ATRV: not refused", "refused" not in out, str(out))
    check("send_raw ATRV: not an error", "error" not in out, str(out))
    check_eq("send_raw ATRV: raw reply", out.get("raw"), "14.1V")
    check("send_raw ATRV: never ran the passive listen (no STM/STMA monitor sent)",
          not any(c.strip().upper() in ("STM", "STMA") for c in scripted4.sent),
          str(scripted4.sent))
    check("send_raw ATRV: can_c still unverified afterwards (never auto-verified)",
          not lk4.is_verified(CAN_C), str(lk4.verified))

    # =======================================================================
    # (e) 2026-10-19 regression: STMA hears CAN-C keep-alive frames, so the
    #     passive listen verifies the bus -- the 0100 probe must STILL run so
    #     legislated reads know which route (29-bit / 11-bit) the ECM answers.
    # =======================================================================
    frames = "1E36000100112233\r1E36000B00112233"
    script_pl = dict(_BASE)
    script_pl["STMA"] = frames
    script_pl["0100"] = "7E8 06 41 00 BE 3F A8 13"
    rs_pl = RouteStream(script_pl, silent_on={"34"})     # only the 11-bit pair answers
    lk8, scripted8 = _link(script_pl, stream=rs_pl)
    lk8.set_cable("none")
    result8 = ops.verify_bus("can_c", seconds=0.05)
    check_eq("passive+probe: verified_by stays passive_listen",
             result8.get("verified_by"), "passive_listen")
    check("passive+probe: verified True", result8.get("verified") is True, str(result8))
    check("passive+probe: 0100 probe still ran after the listen",
          ("34", "0100") in rs_pl.requests and ("33", "0100") in rs_pl.requests,
          str(rs_pl.requests))
    check_eq("passive+probe: probe_ok", result8.get("probe_ok"), True)
    check_eq("passive+probe: probe_stn_protocol in the result",
             result8.get("probe_stn_protocol"), "33")
    check_eq("passive+probe: responders in the result", result8.get("responders"), ["7E8"])
    check_eq("passive+probe: probe_stn_protocol recorded on the link",
             lk8.verified.get("can_c", {}).get("probe_stn_protocol"), "33")
    check_eq("passive+probe: responders recorded on the link",
             lk8.verified.get("can_c", {}).get("responders"), ["7E8"])
    check_eq("passive+probe: link still says passive_listen",
             lk8.verified.get("can_c", {}).get("verified_by"), "passive_listen")

    # Probe silent on both routes: the passive verification stands, the note
    # says the legislated route is unknown, and no route is recorded.
    script_pl2 = dict(_BASE)
    script_pl2["STMA"] = frames
    lk8b, _s8b = _link(script_pl2)
    lk8b.set_cable("none")
    result8b = ops.verify_bus("can_c", seconds=0.05)
    check("probe silent: still verified by the passive listen",
          result8b.get("verified") is True and result8b.get("verified_by") == "passive_listen",
          str(result8b))
    check_eq("probe silent: probe_ok False", result8b.get("probe_ok"), False)
    check("probe silent: note says the legislated route is unknown",
          "legislated route unknown" in (result8b.get("note") or ""), repr(result8b.get("note")))
    check_eq("probe silent: no route recorded",
             lk8b.verified.get("can_c", {}).get("probe_stn_protocol"), None)

    # =======================================================================
    # (f) _obd_route() follows the probe's protocol whatever verified_by says;
    #     with no probe result: 29-bit first, then 11-bit.
    # =======================================================================
    lk9, _s9 = _link(dict(_BASE))
    lk9.set_cable("none")
    lk9.mark_verified(CAN_C, 24, verified_by="passive_listen", probe_stn_protocol="33")
    check_eq("route: probe's 11-bit protocol wins under passive_listen",
             ops._obd_route().stn_protocol, "33")
    check_eq("route: order puts the probe's protocol first",
             [r.stn_protocol for r in ops._legislated_routes_in_order()], ["33", "34"])
    lk9.mark_verified(CAN_C, 24, verified_by="passive_listen", probe_stn_protocol="34")
    check_eq("route: probe's 29-bit protocol wins under passive_listen",
             ops._obd_route().stn_protocol, "34")
    lk9.mark_verified(CAN_C, 24, verified_by="passive_listen")
    check_eq("route: no probe result -> 29-bit route first",
             [r.stn_protocol for r in ops._legislated_routes_in_order()], ["34", "33"])

    # =======================================================================
    # (g) NO DATA on the preferred route retries ONCE on the other route.
    # =======================================================================
    script_fb = dict(_BASE)
    script_fb["03"] = "7E8 02 43 00"
    rs_fb = RouteStream(script_fb, silent_on={"34"})
    lk10, _s10 = _link(script_fb, stream=rs_fb)
    lk10.set_cable("none")
    lk10.mark_verified(CAN_C, 24, verified_by="passive_listen")     # no probe route known
    res_fb = ops.obd_dtcs("stored")
    check_eq("fallback: mode 03 asked on 29-bit then once on 11-bit",
             [r for r in rs_fb.requests if r[1] == "03"], [("34", "03"), ("33", "03")])
    check("fallback: the 11-bit answer is returned, no warning",
          "warning" not in res_fb and res_fb.get("dtcs") == [], str(res_fb))
    check_eq("fallback: reported as answered on 33",
             (res_fb.get("route_fallback") or {}).get("answered_on"), "33")
    check_eq("fallback: working route remembered on the link",
             lk10.verified.get("can_c", {}).get("probe_stn_protocol"), "33")
    rs_fb.requests.clear()
    ops.obd_dtcs("stored")
    check_eq("fallback: the next read goes straight to the remembered route",
             [r for r in rs_fb.requests if r[1] == "03"], [("33", "03")])

    rs_dead = RouteStream(script_fb, silent_on={"34", "33"})
    lk11, _s11 = _link(script_fb, stream=rs_dead)
    lk11.set_cable("none")
    lk11.mark_verified(CAN_C, 24, verified_by="passive_listen")
    res_dead = ops.obd_dtcs("stored")
    check_eq("fallback: both routes silent -> exactly one retry",
             [r for r in rs_dead.requests if r[1] == "03"], [("34", "03"), ("33", "03")])
    check("fallback: both silent -> the usual no-ECU warning, route_fallback answered_on None",
          "no ECU answered" in (res_dead.get("warning") or "")
          and (res_dead.get("route_fallback") or {}).get("answered_on", "x") is None,
          str(res_dead))

finally:
    for k, v in _saved_port_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
