"""The owner's end-to-end flow for confirming live-value scales against MES.

Built on :mod:`decode_confirm` (pairing, verdict rules, acceptance -> ``did_overrides.json``);
this module only closes the gaps around it:

1. :func:`newest_mes_csv` finds the technician's newest MES graph CSV by itself (read-only).
2. :func:`record_start` / :func:`record_stop` record the same channels through the normal CUORE
   live session straight after (refuses while MES runs; contact only via CUORE sessions).
3. :func:`propose` picks the newest MES CSV and CUORE recording, pairs by tag (static) when both
   carry the same tags, else by engine speed (timestamp), and reports per channel the agreement,
   the sample count and a proposal: confirmed | candidate | rejected. Nothing is applied.
4. :func:`accept` / :func:`reject` are the person's decision. Only accept changes a value
   (via decode_confirm.accept); a channel is never confirmed without it.
5. :func:`status` -- "N of 133 confirmed", per module.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import decode_confirm as dc
from .config import state_dir
from .errors import BadCommand, Refused
from .ui_store import atomic_write_text

#: CUORE should record within this long after the MES CSV was written, else the engine state may differ.
MAX_GAP_S = 1800
PROPOSAL = {"confirmed": "confirmed", "wrong_scale": "rejected"}   # everything else: candidate
_RECORD_NAME = "decode-confirm"


def _decisions_path() -> Path:
    return state_dir() / "decode_flow.json"


def _decisions() -> dict[str, Any]:
    try:
        d = json.loads(_decisions_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


# --- 1. find the files ------------------------------------------------------------------

def newest_mes_csv() -> Optional[dict[str, Any]]:
    """Newest MES graph CSV in MES's CSV roots (read-only); CUORE's own live_* files are skipped."""
    from .. import bootstrap  # noqa: F401 -- side effect: mes on sys.path
    from mes import paths
    best = None
    for p in paths.iter_csv_files():
        if p.name.lower().startswith("live_"):
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if best is None or mt > best[0]:
            best = (mt, p)
    if best is None:
        return None
    return {"path": str(best[1]), "name": best[1].name, "mtime": best[0],
            "at": datetime.fromtimestamp(best[0]).isoformat(timespec="seconds")}


def newest_cuore_recording(not_before: float = 0.0) -> Optional[dict[str, Any]]:
    """Newest ``live_*.csv`` made by the CUORE live recorder, optionally newer than ``not_before``."""
    d = state_dir() / "recordings"
    files = []
    for p in d.glob("live_*.csv") if d.is_dir() else []:
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            pass
    files.sort(key=lambda x: x[0], reverse=True)
    if not files or files[0][0] < not_before:
        return None
    mt, p = files[0]
    return {"path": str(p), "name": p.name, "mtime": mt, "at": datetime.fromtimestamp(mt).isoformat(timespec="seconds")}


# --- 2. record the same channels --------------------------------------------------------

def wanted_channels(mes_csv: Optional[str] = None) -> list[str]:
    """CUORE channel ids whose aliased MES name is a column of the MES CSV (all aliased ones when
    no CSV is given); engine_rpm is always included because the pairing lag is searched on it."""
    names: Optional[set[str]] = None
    if mes_csv:
        from .. import bootstrap  # noqa: F401
        from mes import csvlog
        names = {c.name.strip().lower() for c in csvlog.load_csv(Path(mes_csv)).columns}
    out = ["engine_rpm"]
    for a in dc.load_aliases()["pairs"]:
        if (names is None or a["mes_name"].strip().lower() in names) and a["channel"] not in out:
            out.append(a["channel"])
    return out


def record_start(vin: str, mes_csv: str = "", confirm: bool = False, ops: Any = None, interlock: Any = None
                 ) -> dict[str, Any]:
    """Start a CUORE live session on the MES CSV's channels and a CSV recording. Refused while MES
    runs (one adapter). ``ops``/``interlock`` are injectable for tests."""
    if ops is None:
        from . import ops
    if interlock is None:
        from . import interlock
    if interlock.mes_status().get("running"):
        raise Refused("MES is still running: close MES first (one adapter), then record in CUORE")
    src = mes_csv or (newest_mes_csv() or {}).get("path", "")
    if not src:
        raise BadCommand("no MES graph CSV found: record one in MES first (Graph tab, CSV Start / Stop)")
    chans = wanted_channels(src)
    sess = ops.live_session_start(channels=chans, vin=vin)
    rec = ops.live_record_start(_RECORD_NAME) if _takes_name(ops) else ops.live_record_start()
    return {"mes_csv": src, "channels": chans, "session": sess, "recording": rec,
            "next": "Hold the same engine states as in MES (tags 1 key on/engine off, 3 warm idle ...), "
                    "then press stop and Compare."}


def _takes_name(ops: Any) -> bool:
    try:
        import inspect
        return bool(inspect.signature(ops.live_record_start).parameters)
    except (TypeError, ValueError):
        return False


def record_stop(ops: Any = None) -> dict[str, Any]:
    if ops is None:
        from . import ops
    rec = ops.live_record_stop()
    ses = ops.live_session_stop()
    return {"recording": rec, "session": ses}


# --- 3. propose -------------------------------------------------------------------------

def _tags(path: str) -> set[int]:
    try:
        return set(dc._load_csv_series(Path(path))[1].get("segments", {}))
    except Exception:  # noqa: BLE001 -- unreadable file: no tags
        return set()


def _proposal(c: dict[str, Any]) -> str:
    """confirmed | rejected | candidate. Rejected = a scale that is wrong (another transform fits) or a
    certain pairing that disagrees on at least half of its samples with no known transform fitting."""
    if c["verdict"] in PROPOSAL:
        return PROPOSAL[c["verdict"]]
    if (c["verdict"] == "ambiguous" and c.get("pairing") == "certain" and c.get("fit") is not None
            and c["fit"] <= 0.5 and (c.get("identity_fit") or 0) <= 0.5 and "no tested transform" in c.get("reason", "")):
        return "rejected"
    return "candidate"


def propose(vin: str, mes_path: str = "", cuore_path: str = "", tolerance: float = dc.DEFAULT_TOLERANCE
            ) -> dict[str, Any]:
    """Pair the newest MES CSV with the newest CUORE recording (or the given paths) and propose a
    status per channel. Saves a decode_confirm run; changes nothing."""
    notes: list[str] = []
    mes_info = {"path": mes_path} if mes_path else newest_mes_csv()
    if not mes_info:
        raise BadCommand("no MES graph CSV found: record one in MES first (Graph tab, CSV Start / Stop)")
    mes_path = mes_info["path"]
    cu_info = {"path": cuore_path} if cuore_path else newest_cuore_recording(
        not_before=Path(mes_path).stat().st_mtime if Path(mes_path).is_file() else 0.0)
    if not cu_info:
        raise BadCommand("no CUORE recording made after that MES CSV: close MES, record in CUORE, then compare")
    cuore_path = cu_info["path"]
    gap = Path(cuore_path).stat().st_mtime - Path(mes_path).stat().st_mtime
    if gap > MAX_GAP_S:
        notes.append(f"the CUORE recording is {gap / 60:.0f} min after the MES CSV: engine state may differ")
    common = _tags(mes_path) & _tags(cuore_path)
    mode = "static" if len(common) >= 2 else "timestamp"
    notes.append(f"paired by tag ({sorted(common)})" if mode == "static" else "paired by engine speed (no 2 common tags)")
    run = dc.run(vin, mes_path, cuore_path, tolerance=tolerance, mode=mode)
    rejected = _decisions().get("rejected", {})
    rows = []
    for c in run["channels"]:
        rows.append({"channel": c["channel"], "name": c["name"], "proposal": _proposal(c),
                     "verdict": c["verdict"], "agreement": c.get("fit"), "samples": c.get("samples", 0),
                     "reason": c.get("reason", ""), "mes_name": c.get("mes_name", ""), "pairing": c.get("pairing", ""),
                     "proposed_scale": (c.get("transform") or {}).get("name") if c["verdict"] == "wrong_scale" else "",
                     "owner_rejected": c["channel"] in rejected})
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["proposal"]] = counts.get(r["proposal"], 0) + 1
    return {"run_id": run["run_id"], "mode": mode, "mes_csv": mes_path, "cuore_recording": cuore_path,
            "notes": notes + run["timing"].get("notes", []), "counts": counts, "channels": rows,
            "applied": False, "next": "A person accepts or rejects each line; nothing is confirmed until then."}


# --- 4. the person decides --------------------------------------------------------------

def accept(vin: str, run_id: str, channel: str, confirm_pairing: bool = False) -> dict[str, Any]:
    """Acceptance -> decode_confirm.accept (the only writer of confirmed status)."""
    out = dc.accept(vin, run_id, channel, confirm_pairing=confirm_pairing)
    _set_decision("rejected", channel, None)
    return out


def reject(vin: str, run_id: str, channel: str, why: str = "") -> dict[str, Any]:
    """Record that the person rejected this channel's decoding. Changes no scale and no confidence."""
    row = next((c for c in dc.get_run(run_id)["channels"] if c["channel"] == channel), None)
    if row is None:
        raise BadCommand(f"channel {channel!r} is not in run {run_id}")
    entry = {"run_id": run_id, "vin": vin, "verdict": row["verdict"], "samples": row.get("samples", 0),
             "why": why, "at": datetime.now().isoformat(timespec="seconds")}
    _set_decision("rejected", channel, entry)
    return {"rejected": channel, **entry}


def _set_decision(kind: str, channel: str, entry: Optional[dict[str, Any]]) -> None:
    with dc._LOCK:
        d = _decisions()
        bucket = d.setdefault(kind, {})
        if entry is None:
            bucket.pop(channel, None)
        else:
            bucket[channel] = entry
        atomic_write_text(_decisions_path(), json.dumps(d, indent=1, ensure_ascii=False))


# --- 5. status --------------------------------------------------------------------------

def mes_ecm_total() -> int:
    """MES's ECM parameter count, from the parity table ("133 parameter names")."""
    try:
        p = Path(__file__).resolve().parents[1] / "data" / "parity_items.json"
        for it in json.loads(p.read_text(encoding="utf-8")).get("items", []):
            if it.get("id") == "live-ecm":
                m = re.search(r"(\d+)\s+parameter", (it.get("mes") or {}).get("note", ""))
                if m:
                    return int(m.group(1))
    except (OSError, ValueError, AttributeError):
        pass
    return 133


def status() -> dict[str, Any]:
    """Plain list: per module, how many decoded values are confirmed. ECM is counted against MES's
    133; other modules against the DID channels CUORE knows."""
    from . import channels as ch_mod
    rejected = _decisions().get("rejected", {})
    mods: dict[str, dict[str, Any]] = {}
    for c in ch_mod.registry().values():
        if c.kind != "did" or not c.module:
            continue
        m = mods.setdefault(c.module.upper(), {"module": c.module.upper(), "confirmed": 0, "known": 0,
                                               "rejected": 0, "unconfirmed": []})
        m["known"] += 1
        if c.confidence == "confirmed":
            m["confirmed"] += 1
        else:
            m["unconfirmed"].append(c.id)
            if c.id in rejected:
                m["rejected"] += 1
    total = mes_ecm_total()
    for name, m in mods.items():
        m["total"] = max(total, m["known"]) if name == "ECM" else m["known"]
        m["line"] = f"{name}: {m['confirmed']} of {m['total']} confirmed"
        if m["rejected"]:
            m["line"] += f", {m['rejected']} rejected"
    rows = sorted(mods.values(), key=lambda m: (m["module"] != "ECM", m["module"]))
    return {"modules": rows, "lines": [m["line"] for m in rows],
            "headline": next((m["line"] for m in rows if m["module"] == "ECM"), "ECM: 0 of 133 confirmed")}


__all__ = ["newest_mes_csv", "newest_cuore_recording", "record_start", "record_stop", "propose",
           "accept", "reject", "status", "wanted_channels"]
