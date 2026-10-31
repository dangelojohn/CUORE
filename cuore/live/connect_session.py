"""Guided connection session: one sitting at the car, steps in a fixed order, results per module.

Orchestration only. Every step calls an EXISTING read path (module_dtcs, module_identity,
module_code_round, verify_bus, set_cable, abs_connect_test, discover, the live channel reads);
this module adds no address, bit rate, service or bus traffic of its own, and never clears,
writes or runs an actuator. It does not touch the consent gate, transport or barriers.

Rules kept (docs/project/RULES.md 4, 5, 10, 12): one owner of the adapter (MES open, a running
five-minute test or a second step refuses); CAN-CH only at 500 kbit/s and only after the person
confirmed the grey A6 cable on the page; the optional discover needs the person's confirm on the
page and runs after ABS answered; every long step needs 13.2 V or more (engine running).

Automatic stops: low voltage, a silent bus, CAN ERROR twice on a bus, another owner of the
adapter. A stop says what to check and blocks further Runs until the person presses Resume.

A result is ANSWERED or NOT READ with the reason. Nothing here claims a match with MES; the one
comparison made is live values against a real same-session MES CSV (the five-minute test's rule),
and every other comparison is reported as not made.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import five_minute
from .config import state_dir

MIN_VOLTS = five_minute.MIN_VOLTS
ROUND_MODULES = ("ECM", "TCM", "BCM", "IPC", "RFHUB", "DTCM", "DASM", "ESM")
DISCOVER_DEADLINE_S = 60.0
CAN_ERROR_LIMIT = 2
ANSWERED, NOT_READ = "ANSWERED", "NOT READ"

#: Same order as showcase STATUS section 5. ``mes`` = take turns with MES after this step;
#: ``cable`` = cable the person must confirm; ``optional`` steps may be skipped.
STEPS: list[dict[str, Any]] = [
    dict(id="voltage_bus", n=1, title="Voltage and bus", bus="can_c", cable="none", engine="on", mes=False,
         hands="Plain adapter in the OBD port, no cable. Start the engine and keep it running. Ignition on.",
         does="Reads battery voltage, then a passive listen on CAN-C (the existing verify_bus)."),
    dict(id="code_round", n=2, title="CAN-C code round", bus="can_c", cable="none", engine="on", mes=True,
         hands="Same plain adapter, engine running. Do not touch the car while it reads.",
         does="Stored codes (19 02) from ECM, TCM, BCM, IPC, RFHUB, DTCM, DASM, ESM, one at a time."),
    dict(id="ecm_live", n=3, title="ECM live values at idle", bus="can_c", cable="none", engine="on", mes=True,
         hands="Engine at steady warm idle, nothing switched on. Run MES live values first if you want a comparison.",
         does="Reads each confirmed ECM channel once (the existing live channel read)."),
    dict(id="snapshot", n=4, title="ECM stored-code snapshot", bus="can_c", cable="none", engine="on", mes=True,
         hands="Engine running, plain adapter.",
         does="Code round with snapshots on ECM (the existing module_code_round)."),
    dict(id="identity", n=5, title="Identity remainder", bus="can_c", cable="none", engine="on", mes=True,
         hands="Engine running, plain adapter.",
         does="Identity (22 F1xx) from the eight CAN-C modules, one at a time."),
    dict(id="abs", n=6, title="Grey A6 cable, CAN-CH, ABS test", bus="can_ch", cable="grey_a6", engine="on", mes=True,
         hands="Engine running. Swap the plain adapter lead for the grey A6 cable, then press 'Grey A6 is fitted' below.",
         does="Declares grey_a6, passive listen on CAN-CH at 500 kbit/s, then the ABS connect test (at most 5 requests); "
              "if ABS answers, its identity and codes."),
    dict(id="discover_ch", n=7, title="Bounded CAN-CH discover (optional)", bus="can_ch", cable="grey_a6",
         engine="on", mes=False, optional=True, needs_abs=True, needs_confirm=True,
         hands="Grey cable still fitted, engine running. Tick the confirm box first.",
         does=f"The existing discover on CAN-CH with a {int(DISCOVER_DEADLINE_S)} s deadline, for EPS, ORC, AFLS, PAM, HALF."),
    dict(id="blue_a5", n=8, title="Blue A5 cable, CAN-IHS (optional)", bus="can_ihs", cable="blue_a5", engine="on",
         mes=False, optional=True, needs_confirm=True,
         hands="Swap to the blue A5 cable, press 'Blue A5 is fitted', tick the confirm box. Naming responders is done on the Modules page.",
         does=f"Declares blue_a5, passive listen on CAN-IHS, then the existing discover with a {int(DISCOVER_DEADLINE_S)} s deadline."),
]
STEP_BY_ID = {s["id"]: s for s in STEPS}
_RUN_LOCK = threading.Lock()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- the car, behind one small interface so tests can fake it ------------------------------

class ConnectProbe(five_minute.LiveProbe):
    """Default probe: the five-minute reads plus the cable, listen, round and discover calls."""

    def set_cable(self, cable: str) -> dict[str, Any]:
        from . import ops
        return ops.set_cable(cable)

    def read_vin(self) -> dict[str, Any]:
        from . import ops
        return ops.obd_vin()

    def verify(self, bus: str) -> dict[str, Any]:
        from . import ops
        return ops.verify_bus(bus)

    def code_round(self, bus: str, modules: list[str], vin: str, confirm: bool) -> dict[str, Any]:
        from . import ops
        return ops.module_code_round(bus=bus, modules=modules, vin=vin, confirm=confirm)

    def discover(self, bus: str, vin: str, confirm: bool) -> dict[str, Any]:
        from . import ops
        return ops.discover(bus=bus, vin=vin, confirm=confirm, deadline_s=DISCOVER_DEADLINE_S)

    def other_owner(self) -> str:
        """Why someone else holds the adapter, or an empty string."""
        if self.mes_running():
            return "MultiEcuScan is open"
        if five_minute._RUN_LOCK.locked():
            return "a five-minute test is running"
        return ""


class _Halt(Exception):
    def __init__(self, reason: str, check: str, kind: str):
        super().__init__(reason)
        self.reason, self.check, self.kind = reason, check, kind


# --- state ----------------------------------------------------------------------------------

def _dir() -> Path:
    d = state_dir() / "connect_session"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_session(vin: str) -> dict[str, Any]:
    stamp = now()
    base = datetime.now().strftime("%Y%m%dT%H%M%S%f")      # sortable and unique to the microsecond
    return {"version": 1, "id": base + "_" + vin, "vin": vin,
            "started": stamp, "updated": stamp, "finished": None, "read_only": True,
            "cable_confirmed": {}, "steps": {s["id"]: {"status": "pending", "runs": []} for s in STEPS},
            "items": {}, "history": [], "can_errors": {}, "stop": None, "events": [], "baseline": {}}


def save(st: dict[str, Any]) -> Path:
    st["updated"] = now()
    p = _dir() / f"{st['id']}.json"
    p.write_text(json.dumps(st, indent=2), encoding="utf-8")
    return p


def _files(vin: str) -> list[Path]:
    return sorted(_dir().glob(f"*_{vin}.json"), reverse=True)


def _load(p: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _baseline(vin: str, skip_id: str = "") -> dict[str, str]:
    """Item key -> status from the newest earlier session of this car: what 'moved' is judged against."""
    for p in _files(vin):
        s = _load(p)
        if s and s.get("id") != skip_id and s.get("items"):
            return {k: v["status"] for k, v in s["items"].items()}
    return {}


def current(vin: str, create: bool = True) -> Optional[dict[str, Any]]:
    for p in _files(vin):
        s = _load(p)
        if s and not s.get("finished"):
            return s
    if not create:
        return None
    s = new_session(vin)
    s["baseline"] = _baseline(vin, s["id"])
    save(s)
    return s


def latest(vin: str) -> Optional[dict[str, Any]]:
    for p in _files(vin):
        s = _load(p)
        if s:
            return s
    return None


def _event(st: dict[str, Any], what: str) -> None:
    st["events"].append({"at": now(), "what": what})


def start_new(vin: str) -> dict[str, Any]:
    old = current(vin, create=False)
    if old:
        old["finished"] = now()
        _event(old, "closed because a new session was started")
        save(old)
    return current(vin)  # type: ignore[return-value]


def confirm_cable(vin: str, cable: str) -> dict[str, Any]:
    st = current(vin)
    if cable not in ("grey_a6", "blue_a5"):
        raise ValueError("cable must be grey_a6 or blue_a5")
    st["cable_confirmed"][cable] = now()
    _event(st, f"person confirmed the {cable} cable is fitted")
    save(st)
    return st


def skip(vin: str, step_id: str) -> dict[str, Any]:
    st = current(vin)
    spec = STEP_BY_ID[step_id]
    if st["steps"][step_id]["status"] not in ("done",):
        st["steps"][step_id]["status"] = "skipped"
        _event(st, f"person skipped step {spec['n']} ({spec['title']})")
        save(st)
    return st


def resume(vin: str) -> dict[str, Any]:
    st = current(vin)
    if st["stop"]:
        _event(st, f"person pressed Resume after stop at step {st['stop']['step']}: {st['stop']['reason']}")
        if st["stop"].get("bus"):
            st["can_errors"][st["stop"]["bus"]] = 0
        st["stop"] = None
        save(st)
    return st


def finish(vin: str) -> dict[str, Any]:
    st = current(vin)
    st["finished"] = now()
    _event(st, "session finished by the person")
    save(st)
    return st


# --- gating ---------------------------------------------------------------------------------

def blocked_reason(st: dict[str, Any], step_id: str, confirm: bool = False) -> str:
    """Why this step cannot run yet ('' = it may). Pure state check: no car contact."""
    spec = STEP_BY_ID[step_id]
    if st.get("finished"):
        return "this session is finished; start a new one"
    if st["stop"]:
        return f"stopped at step {st['stop']['step']}: {st['stop']['reason']}. {st['stop']['check']} Then press Resume."
    for s in STEPS:
        if s["id"] == step_id:
            break
        if not s.get("optional") and st["steps"][s["id"]]["status"] not in ("done", "skipped"):
            return f"step {s['n']} ({s['title']}) comes first"
    if spec["cable"] in ("grey_a6", "blue_a5") and spec["cable"] not in st["cable_confirmed"]:
        return f"confirm the {spec['cable'].replace('_', ' ').upper()} cable is fitted first (button on the page)"
    if spec.get("needs_abs") and not _abs_answered(st):
        return "the optional discover runs only after ABS has answered"
    if spec.get("needs_confirm") and not confirm:
        return "tick the confirm box: this sends a bounded read-only sweep on that bus"
    return ""


def _abs_answered(st: dict[str, Any]) -> bool:
    return any(i["status"] == ANSWERED for k, i in st["items"].items() if k.startswith("abs:ABS"))


def next_step(st: dict[str, Any]) -> Optional[str]:
    for s in STEPS:
        if st["steps"][s["id"]]["status"] not in ("done", "skipped") and not s.get("optional"):
            return s["id"]
    return None


# --- running a step -------------------------------------------------------------------------

class _Ctx:
    def __init__(self, st: dict[str, Any], probe: Any, vin: str, spec: dict[str, Any], confirm: bool):
        self.st, self.probe, self.vin, self.spec, self.confirm = st, probe, vin, spec, confirm
        self.items: list[dict[str, Any]] = []
        self.retries: list[dict[str, Any]] = []
        self.mes_pairs: list[dict[str, Any]] = []
        self.volts: Optional[float] = None
        self.mes_csv: Optional[str] = None

    def add(self, key: str, label: str, ok: bool, reason: str = "", **detail: Any) -> None:
        self.items.append({"key": f"{self.spec['id']}:{key}", "label": label,
                           "status": ANSWERED if ok else NOT_READ,
                           "reason": "" if ok else reason, "at": now(),
                           **detail})

    def read(self, fn: Any, label: str) -> tuple[dict[str, Any], str]:
        """One read with the five-minute retry rule; counts CAN ERROR per bus and halts at two."""
        before = len(self.retries)
        r, err = five_minute._read_once(fn, label, self.retries)
        bus = self.spec["bus"]
        n = 0
        for rt in self.retries[before:]:
            n += int(five_minute._is_can_error(rt["first_error"])) + int(five_minute._is_can_error(rt["retry_error"] or ""))
        if n:
            self.st["can_errors"][bus] = self.st["can_errors"].get(bus, 0) + n
            if self.st["can_errors"][bus] >= CAN_ERROR_LIMIT:
                raise _Halt(f"CAN ERROR {self.st['can_errors'][bus]} times on {bus} (last: {label})",
                            "Check the adapter seating and cable, ignition on, battery voltage, and that no other "
                            "program holds the adapter.", "can_error")
        return r, err


def _step_voltage_bus(c: _Ctx) -> None:
    c.add("voltage", "Battery voltage", True, volts=c.volts, unit="V")
    v = c.probe.verify("can_c")
    heard = bool(v.get("verified"))
    if not heard:
        if five_minute._is_can_error(str(v.get("error") or "")):
            c.st["can_errors"]["can_c"] = c.st["can_errors"].get("can_c", 0) + 1
        raise _Halt("CAN-C is silent: " + str(v.get("reason") or v.get("note") or "no traffic and no reply"),
                    "Check the adapter is firmly in the OBD port, ignition on, engine running.", "bus_silent")
    c.add("bus", "CAN-C bus", True, via=v.get("verified_by"), frames=v.get("frames"))
    # Every later read is filed under this page's VIN, so the car must say it is this car.
    read = str(c.probe.read_vin().get("vin") or "").strip().upper()
    if read != c.vin.upper():
        raise _Halt(f"the car reported VIN {read or 'nothing'}, not {c.vin}: nothing was filed",
                    "Check this is the right car and page, ignition on, then Resume.", "wrong_car")
    c.add("vin", "Car VIN", True, value=read)


def _step_code_round(c: _Ctx) -> None:
    table = {m["code"]: m for m in c.probe.modules("can_c", c.vin)}
    for code in ROUND_MODULES:
        m = table.get(code)
        if m is None or not m.get("usable"):
            c.add(code, code, False, "NOT READ: " + ((m or {}).get("why") or "not in the module table for this car"))
            continue
        r, err = c.read(lambda k=code: c.probe.dtcs(k, c.vin, True), f"{code} codes")
        if not err and "codes" in r:
            c.add(code, code, True, codes=r.get("codes"))
        else:
            c.add(code, code, False, "NOT READ: " + five_minute._why_silent(r, err))


def _step_ecm_live(c: _Ctx) -> None:
    chans = [ch for ch in c.probe.channels("can_c") if ch.get("kind") != "battery" and ch.get("module") in (None, "", "ECM")]
    if not chans:
        c.add("channels", "ECM live channels", False, "NOT READ: no confirmed ECM channel is listed")
        return
    csv = None
    try:
        csv = c.probe.mes_csv(datetime.now().timestamp())
    except Exception:  # noqa: BLE001 -- no CSV means no comparison, not a failure
        csv = None
    c.mes_csv = csv["name"] if csv else None
    for ch in chans:
        r, err = c.read(lambda k=ch: c.probe.read_channel(k, c.vin, True), f"channel {ch['id']}")
        v = r.get("value")
        if err or v is None:
            c.add(ch["id"], ch["name"], False, "NOT READ: " + (err or r.get("error") or "no value"))
            continue
        cmp_ = "not compared (no same-session MES CSV)"
        rng = (csv or {}).get("ranges", {}).get(ch["name"].strip().lower()) if csv else None
        if csv and rng is None:
            cmp_ = "not compared (column not in the MES CSV)"
        elif rng:
            inside = rng["min"] <= v <= rng["max"]
            cmp_ = ("inside" if inside else "outside") + f" the MES CSV range {rng['min']}..{rng['max']}"
            c.mes_pairs.append({"channel": ch["name"], "value": v, "inside": inside})
        c.add(ch["id"], ch["name"], True, value=v, unit=r.get("unit"), mes=cmp_)


def _step_snapshot(c: _Ctx) -> None:
    out, err = c.read(lambda: c.probe.code_round("can_c", ["ECM"], c.vin, True), "ECM snapshot round")
    row = next((m for m in (out.get("modules") or []) if m.get("module") == "ECM"), None)
    if err or row is None or row.get("skipped") or not row.get("read"):
        why = err or (row or {}).get("skipped") or (row or {}).get("warning") or "no answer"
        c.add("ECM", "ECM snapshot", False, f"NOT READ: {why}")
    else:
        c.add("ECM", "ECM snapshot", True, codes=row.get("codes"), snapshots_decoded=row.get("snapshots_decoded"),
              snapshots_raw=row.get("snapshots_raw"))


def _step_identity(c: _Ctx) -> None:
    table = {m["code"]: m for m in c.probe.modules("can_c", c.vin)}
    for code in ROUND_MODULES:
        m = table.get(code)
        if m is None or not m.get("usable"):
            c.add(code, code, False, "NOT READ: " + ((m or {}).get("why") or "not in the module table for this car"))
            continue
        r, err = c.read(lambda k=code: c.probe.identity(k, c.vin, True), f"{code} identity")
        fields = five_minute._identity_ok(r) if not err else []
        if fields:
            c.add(code, code, True, fields=fields)
        else:
            c.add(code, code, False, "NOT READ: " + five_minute._why_silent(r, err))


def _listen(c: _Ctx, bus: str, cable: str) -> None:
    c.probe.set_cable(cable)
    v = c.probe.verify(bus)
    if five_minute._is_can_error(str(v.get("error") or "")):
        c.st["can_errors"][bus] = c.st["can_errors"].get(bus, 0) + 1
    if not v.get("verified"):
        n = c.st["can_errors"].get(bus, 0)
        kind = "can_error" if n >= CAN_ERROR_LIMIT else "bus_silent"
        raise _Halt(f"{bus} is silent under the {cable} cable: " + str(v.get("reason") or v.get("note") or "no traffic"),
                    "Check the cable is fully seated at both ends and is the right one, ignition on, engine running.", kind)
    c.add("bus", f"{bus} bus", True, via=v.get("verified_by"), frames=v.get("frames"))


def _step_abs(c: _Ctx) -> None:
    _listen(c, "can_ch", "grey_a6")
    ct = c.probe.abs_connect(c.vin)
    answered = bool(ct.get("answered_by"))
    c.add("ABS", "ABS connect test", answered,
          "NOT READ: no route answered (" + str(ct.get("conclusion") or "silent") + ")",
          answered_by=ct.get("answered_by"), conclusion=ct.get("conclusion"), requests_sent=ct.get("requests_sent"))
    if not answered:
        return
    r, err = c.read(lambda: c.probe.identity("ABS", c.vin, True), "ABS identity")
    fields = five_minute._identity_ok(r) if not err else []
    c.add("ABS-identity", "ABS identity", bool(fields), "NOT READ: " + five_minute._why_silent(r, err), fields=fields)
    r, err = c.read(lambda: c.probe.dtcs("ABS", c.vin, True), "ABS codes")
    ok = not err and "codes" in r
    c.add("ABS-codes", "ABS codes", ok, "NOT READ: " + five_minute._why_silent(r, err), codes=r.get("codes") if ok else None)


def _discover(c: _Ctx, bus: str) -> None:
    r, err = c.read(lambda: c.probe.discover(bus, c.vin, True), f"discover {bus}")
    if err:
        c.add("discover", f"{bus} discover", False, "NOT READ: " + err)
        return
    hits = r.get("found") or r.get("responders") or []
    c.add("discover", f"{bus} discover", True, found=len(hits) if hasattr(hits, "__len__") else None,
          note="Naming a responder is a person's step on the Modules page; nothing was named here.")


def _step_discover_ch(c: _Ctx) -> None:
    _discover(c, "can_ch")


def _step_blue(c: _Ctx) -> None:
    _listen(c, "can_ihs", "blue_a5")
    _discover(c, "can_ihs")


_RUNNERS = {"voltage_bus": _step_voltage_bus, "code_round": _step_code_round, "ecm_live": _step_ecm_live,
            "snapshot": _step_snapshot, "identity": _step_identity, "abs": _step_abs,
            "discover_ch": _step_discover_ch, "blue_a5": _step_blue}


def _stop(st: dict[str, Any], spec: dict[str, Any], h: _Halt) -> None:
    st["stop"] = {"step": spec["n"], "step_id": spec["id"], "at": now(), "kind": h.kind, "reason": h.reason,
                  "check": h.check, "bus": spec["bus"] if h.kind in ("can_error", "bus_silent") else None}
    _event(st, f"STOPPED at step {spec['n']}: {h.reason}")


def run_step(vin: str, step_id: str, *, confirm: bool = False, probe: Any = None,
             persist: bool = True) -> dict[str, Any]:
    """Run one step. Returns ``{"ok", "refused", "reason", "session"}``; a stop is recorded in the session."""
    st = current(vin)
    probe = probe or ConnectProbe()
    spec = STEP_BY_ID[step_id]

    def out(refused: bool, reason: str = "") -> dict[str, Any]:
        if persist:
            save(st)
        return {"ok": not refused and not st["stop"], "refused": refused, "reason": reason, "session": st}

    why = blocked_reason(st, step_id, confirm)
    if why:
        return out(True, why)
    if not _RUN_LOCK.acquire(blocking=False):
        return out(True, "another step of this session is running; reads go strictly one at a time")
    try:
        owner = probe.other_owner() if hasattr(probe, "other_owner") else ("MultiEcuScan is open" if probe.mes_running() else "")
        if owner:
            _stop(st, spec, _Halt(f"another owner holds the adapter: {owner}",
                                  "Close MES (or wait for the other test), then come back: CUORE and MES take turns, never together.",
                                  "other_owner"))
            return out(False)
        volts = probe.voltage()
        if volts is None:
            _stop(st, spec, _Halt("no battery voltage reading", "Check the adapter is in the OBD port and the ignition is on.", "voltage"))
            return out(False)
        if volts < MIN_VOLTS:
            _stop(st, spec, _Halt(f"battery is {volts:.1f} V, below {MIN_VOLTS} V",
                                  "Start the engine and keep it running (or put a charger on), then Resume. A weak battery can also be why a module is silent.",
                                  "voltage"))
            return out(False)
        c = _Ctx(st, probe, vin, spec, confirm)
        c.volts = volts
        halt: Optional[_Halt] = None
        try:
            _RUNNERS[step_id](c)
        except _Halt as h:
            halt = h
        except Exception as e:  # noqa: BLE001 -- a refused or failed read is a finding, never a crash
            c.add("error", spec["title"], False, f"NOT READ: {type(e).__name__}: {e}")
        _record(st, spec, c, volts, halt)
        if halt:
            _stop(st, spec, halt)
        return out(False)
    finally:
        _RUN_LOCK.release()


def _record(st: dict[str, Any], spec: dict[str, Any], c: _Ctx, volts: float, halt: Optional[_Halt]) -> None:
    at = now()
    for it in c.items:
        prev = st["items"].get(it["key"])
        was = (prev or {}).get("status") or st["baseline"].get(it["key"])
        it["previously"] = was
        if it["status"] == ANSWERED and was == NOT_READ:
            it["moved_at"] = at
        elif prev and prev.get("moved_at") and it["status"] == ANSWERED:
            it["moved_at"] = prev["moved_at"]
        st["items"][it["key"]] = it
        st["history"].append({"at": it["at"], "key": it["key"], "status": it["status"], "reason": it["reason"]})
    run = {"at": at, "voltage": volts, "items": [i["key"] for i in c.items], "retries": c.retries,
           "mes_csv": c.mes_csv, "mes_pairs": c.mes_pairs, "stopped": halt.reason if halt else None}
    s = st["steps"][spec["id"]]
    s["runs"].append(run)
    s["status"] = "stopped" if halt else "done"
    _event(st, f"step {spec['n']} ({spec['title']}) " + ("stopped" if halt else "ran") + f" at {volts:.1f} V")


# --- result summary -------------------------------------------------------------------------

def summary(st: dict[str, Any]) -> dict[str, Any]:
    items = list(st["items"].values())
    ans = [i for i in items if i["status"] == ANSWERED]
    nr = [i for i in items if i["status"] == NOT_READ]
    moved = sorted(({"key": i["key"], "label": i["label"], "moved_at": i["moved_at"]}
                    for i in items if i.get("moved_at") and i["status"] == ANSWERED), key=lambda m: m["moved_at"])
    pairs = [p for s in st["steps"].values() for r in s["runs"] for p in r.get("mes_pairs", [])]
    csv = next((r["mes_csv"] for s in st["steps"].values() for r in s["runs"] if r.get("mes_csv")), None)
    inside = sum(1 for p in pairs if p["inside"])
    if pairs:
        mes = (f"Live values compared with MES CSV {csv}: {inside} of {len(pairs)} inside the CSV's min..max range. "
               "Codes, identity and snapshots were not compared with MES.")
    else:
        mes = "No comparison with MES was made in this session, so nothing here is claimed to match MES."
    by_step = []
    for s in STEPS:
        ss = st["steps"][s["id"]]
        keys = [i for i in items if i["key"].startswith(s["id"] + ":")]
        by_step.append({"n": s["n"], "title": s["title"], "status": ss["status"], "runs": len(ss["runs"]),
                        "answered": sum(1 for i in keys if i["status"] == ANSWERED),
                        "not_read": sum(1 for i in keys if i["status"] == NOT_READ)})
    return {"session": st["id"], "vin": st["vin"], "started": st["started"], "updated": st["updated"],
            "finished": st["finished"], "answered": len(ans), "not_read": len(nr), "total": len(items),
            "not_read_items": [{"key": i["key"], "label": i["label"], "reason": i["reason"], "at": i["at"]} for i in nr],
            "moved": moved, "by_step": by_step, "stop": st["stop"], "mes_statement": mes,
            "baseline_note": ("compared with the previous connection session of this car" if st["baseline"]
                              else "no earlier connection session of this car to compare with"),
            "events": st["events"]}
