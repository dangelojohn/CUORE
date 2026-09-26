"""Live observations recorded by the cuore live link, read by the evidence gate.

The live layer appends one JSON line per read to an observations file; this
module is the only place the ``mes`` library learns about it. The path is
``MES_LIVE_OBSERVATIONS`` if set, else ``%PROGRAMDATA%\\cuore\\observations.jsonl``,
matching where cuore keeps its state. ``mes`` never writes here.

Each line: ``{"at": iso, "kind": ..., "vin": ..., "bus": ..., "cable": ..., "data": {...}}``.
Kinds the gate understands: ``obd_dtcs`` (data.kind stored|pending|permanent,
data.dtcs), ``readiness`` (data.since_clear.monitors), ``module_dtcs``
(data.ecu, data.codes), ``did`` (data.ecu, data.did, data.bytes/ascii/value).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional


def observations_path() -> Path:
    """Mirror ``cuore.live.config.state_dir()``: same override, same candidates.

    The writer picks the first *writable* candidate; this reader picks the
    first candidate that already holds a file, so both sides land on the same
    path without ``mes`` importing ``cuore``.
    """
    env = os.environ.get("MES_LIVE_OBSERVATIONS")
    if env:
        return Path(env)
    candidates: list[Path] = []
    if os.environ.get("CUORE_STATE_DIR"):
        candidates.append(Path(os.environ["CUORE_STATE_DIR"]))
    if os.environ.get("PROGRAMDATA"):
        candidates.append(Path(os.environ["PROGRAMDATA"], "cuore"))
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"], "cuore"))
    candidates.append(Path.home() / ".cuore")
    for d in candidates:
        if (d / "observations.jsonl").exists():
            return d / "observations.jsonl"
    return candidates[0] / "observations.jsonl"


#: UDS status bits that mean "failing now": testFailed, pendingDTC,
#: confirmedDTC. A module lists every code it tracks (the ECM listed 278 on
#: 2026-09-25, 275 of them at 0x40 "not run this cycle"); presence in the
#: list is not a fault.
ACTIVE_MASK = 0x01 | 0x04 | 0x08


def from_car(entry: dict[str, Any]) -> bool:
    """Only reads from a real serial link are evidence about a vehicle.

    Mirrors ``cuore.live.store.is_from_car``. Test suites and replays wrote
    scripted reads into the real store until 2026-09-26; those carry a
    ``scripted`` / ``playback`` stream or none at all, and never count.
    """
    s = str(entry.get("stream") or "")
    return s.startswith("serial") or s.startswith("recording(serial")


def load(vin: Optional[str] = None, kind: Optional[str] = None,
         limit: int = 5000, from_car_only: bool = True) -> list[dict[str, Any]]:
    """Observations newest-last, filtered by VIN and kind when given.

    Only real-link reads unless ``from_car_only`` is False."""
    p = observations_path()
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if vin and (obj.get("vin") or "") != vin:  # untagged reads never match a named car
            continue
        if kind and obj.get("kind") != kind:
            continue
        if from_car_only and not from_car(obj):
            continue
        out.append(obj)
    return out


def newest(observations: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    obs = list(observations)
    return obs[-1] if obs else None


def verify_live(m: dict[str, Any], vin: str) -> dict[str, Any]:
    """Verify a ``type: live`` citation against recorded observations.

    Citation fields: ``kind`` (dtc | permanent | readiness | module_dtc | did),
    plus ``code`` for dtc/permanent/module_dtc, ``monitor`` for readiness,
    ``ecu`` and ``did`` for did. Returns status verified / unverified with the
    observation it matched.
    """
    kind = str(m.get("kind", "")).strip().lower()
    code = str(m.get("code", "")).strip().upper()

    if kind in ("dtc", "permanent"):
        want = "permanent" if kind == "permanent" else "stored"
        for obs in reversed(load(vin, "obd_dtcs")):
            data = obs.get("data", {})
            if data.get("kind") != want:
                continue
            if code and code in (data.get("dtcs") or []):
                return {"status": "verified", "observation_at": obs.get("at"),
                        "note": f"{want} code {code} read live from the vehicle"}
            if not code:
                return {"status": "verified", "observation_at": obs.get("at"),
                        "note": f"{want} codes read live: {data.get('dtcs')}"}
        return {"status": "unverified",
                "note": f"no live {want} read shows {code or 'any code'} for this VIN"}

    if kind == "module_dtc":
        ecu = str(m.get("ecu", "")).strip().upper()
        st = active_status(vin, code, ecu)
        if st is None:
            return {"status": "unverified", "note": f"no live UDS read shows {code}"}
        if not st["active"]:
            return {"status": "unverified", "observation_at": st["at"],
                    "note": (f"{code} is only tracked by {st['ecu']} (status {st['status']}), "
                             f"not failing: a listed code is not a fault")}
        return {"status": "verified", "observation_at": st["at"],
                "note": f"{code} failing live on {st['ecu']} (status {st['status']})"}

    if kind == "readiness":
        monitor = str(m.get("monitor", "Evaporative system"))
        obs = newest(load(vin, "readiness"))
        if not obs:
            return {"status": "unverified", "note": "no live readiness read for this VIN"}
        mons = (obs.get("data", {}).get("since_clear") or {}).get("monitors") or []
        hit = next((x for x in mons if x.get("monitor") == monitor), None)
        if hit is None:
            return {"status": "unverified",
                    "note": f"monitor {monitor!r} not reported in the live readiness read"}
        return {"status": "verified", "observation_at": obs.get("at"),
                "note": f"{monitor} monitor {'complete' if hit.get('complete') else 'NOT complete'} "
                        f"in the live read", "complete": hit.get("complete")}

    if kind == "did":
        ecu = str(m.get("ecu", "")).upper()
        did = str(m.get("did", "")).upper()
        for obs in reversed(load(vin, "did")):
            data = obs.get("data", {})
            if (not ecu or data.get("ecu") == ecu) and (not did or data.get("did") == did):
                return {"status": "verified", "observation_at": obs.get("at"),
                        "note": f"DID {data.get('did')} on {data.get('ecu')} read live",
                        "value": data.get("value", data.get("ascii", data.get("bytes")))}
        return {"status": "unverified", "note": f"no live DID read {did} on {ecu}"}

    return {"status": "unverified",
            "note": "live citation needs kind: dtc | permanent | readiness | module_dtc | did"}


def active_status(vin: str, code: str, ecu: str = "") -> Optional[dict[str, Any]]:
    """The newest real UDS read of ``code`` for this VIN: status and whether active."""
    base = code.upper().split("-")[0]
    for obs in reversed(load(vin, "module_dtcs")):
        data = obs.get("data", {})
        if ecu and str(data.get("ecu", "")).upper() != ecu:
            continue
        if data.get("error") or data.get("codes") is None:
            continue
        for rec in data.get("dtcs") or []:
            if str(rec.get("code", "")).upper().split("-")[0] == base:
                s = int(rec.get("status") or 0)
                return {"at": obs.get("at"), "ecu": data.get("ecu"), "code": rec.get("code"),
                        "status": f"0x{s:02X}", "active": bool(s & ACTIVE_MASK)}
    return None


__all__ = ["observations_path", "load", "newest", "verify_live", "from_car",
           "active_status", "ACTIVE_MASK"]
