"""Scale review queue: recorded MES log values beside recorded CUORE raw DID bytes. Offline, read-only.

Nothing here talks to the car or the adapter, and nothing here is ever applied. Inputs are files that
already exist:

* MES ``FESLog_*.txt`` sessions: every ``READING PARAMETERS:`` block is a live sample. The session has
  no per-sample clock, so the whole log is ONE condition spanning ``[session start, file saved]``.
* CUORE's audit log: every positive ``22 xx xx`` reply, with the raw bytes and the time it was read.

A CUORE channel is compared with a MES name only when ``cuore/data/mes_param_aliases.json`` pairs them
(same module, unless the alias says ``mes_module``) AND a CUORE read of that DID lies within
``max_gap_s`` of the MES condition. Each such pair is one condition (x = decoded CUORE value, y = MES
value); the transforms and the verdict rules are decode_confirm's own, with a minimum of two
conditions that differ. One condition is reported as a single point and is never acceptable.

Output is a decode_confirm-shaped run (``mode`` = ``recorded``), so the person's accept/reject goes
through the existing ``decode_flow.accept`` / ``reject``. A scale is only ever confirmed by that tap.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from . import decode_confirm as dc

MAX_GAP_S = 1800
#: reads this much later than the nearest one still count for the same condition
CLUSTER_S = 300
MODULES = ("ECM", "TCM", "BCM")
#: MES ``ecu_description`` fragment -> module. Only what the logs on file show; anything else is unknown.
_MES_MODULE = (("magneti marelli iaw", "ECM"), ("instrument panel", "IPC"))


def _payload(raw: str) -> list[int]:
    """Reassemble the UDS payload from the adapter's CAN frame lines (single, first and consecutive frames)."""
    out: list[int] = []
    for line in (x.strip() for x in (raw or "").splitlines()):
        if len(line) < 12:
            continue
        h = bytes.fromhex(line[8:])
        kind = h[0] >> 4
        if kind == 0:
            out += list(h[1:1 + (h[0] & 15)])
        elif kind == 1:
            out += list(h[2:])
        elif kind == 2:
            out += list(h[1:])
    return out


def cuore_did_reads(audit_path: Optional[Path] = None, modules: Iterable[str] = MODULES
                    ) -> list[dict[str, Any]]:
    """Positive ``22 xx xx`` replies from the audit log: {at (naive local), ecu, did, data (bytes after DID)}."""
    if audit_path is None:
        from . import audit
        audit_path = audit.log_path()
    want = {m.upper() for m in modules}
    out: list[dict[str, Any]] = []
    try:
        fh = open(audit_path, encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            if '"22' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            req = str(d.get("req") or "")
            if d.get("event") != "uds" or d.get("error") or not req.startswith("22") or len(req) != 6:
                continue
            if str(d.get("ecu") or "").upper() not in want:
                continue
            try:
                pl = _payload(str(d.get("raw") or ""))
                at = datetime.fromisoformat(str(d["iso"])).replace(tzinfo=None)
            except (ValueError, KeyError):
                continue
            if len(pl) >= 3 and pl[0] == 0x62 and f"{pl[1]:02X}{pl[2]:02X}" == req[2:].upper():
                out.append({"at": at, "ecu": str(d["ecu"]).upper(), "did": req[2:].upper(), "data": pl[3:]})
    return out


def mes_conditions(paths: Optional[Iterable[Path]] = None, vin: str = "") -> list[dict[str, Any]]:
    """One condition per MES log that has live samples: {log, module, start, end, values{name: (unit, [n..])}}."""
    from .. import bootstrap  # noqa: F401
    from mes import fes, paths as mes_paths
    files = list(paths) if paths is not None else sorted(
        p for p in mes_paths.iter_log_files() if p.name.upper().startswith("FESLOG_"))
    out: list[dict[str, Any]] = []
    for p in files:
        try:
            log = fes.load_fes(Path(p))
        except Exception:  # noqa: BLE001 -- an unreadable log is skipped, not guessed
            continue
        if not log.samples or log.simulation:
            continue
        if vin and log.vin and log.vin.upper() != vin.upper():
            continue
        try:
            start = datetime.fromisoformat(log.session_time.replace("/", "-"))
            end = datetime.fromtimestamp(os.path.getmtime(p))
        except (ValueError, OSError):
            continue
        desc = (log.ecu_description or "").lower()
        module = next((m for frag, m in _MES_MODULE if frag in desc), "")
        values: dict[str, tuple[str, list[float]]] = {}
        for s in log.samples:
            for v in s.values:
                if v.number is not None:
                    values.setdefault(v.name, (v.unit, []))[1].append(v.number)
        out.append({"log": Path(p).name, "module": module, "ecu": log.ecu_description, "start": start,
                    "end": max(end, start), "values": values})
    return out


def _gap(read_at: datetime, cond: dict[str, Any]) -> float:
    if cond["start"] <= read_at <= cond["end"]:
        return 0.0
    return min(abs((read_at - cond["start"]).total_seconds()), abs((read_at - cond["end"]).total_seconds()))


def _span(seconds: float) -> str:
    m = int(seconds) // 60
    return f"{m} min" if m < 180 else f"{m / 60:.0f} h" if m < 2880 else f"{m / 1440:.0f} days"


def _decode(formula: str, data: list[int]) -> Optional[float]:
    from .readall import eval_formula
    try:
        v = eval_formula(formula, data)
    except Exception:  # noqa: BLE001
        return None
    return float(v) if isinstance(v, (int, float)) else None


def build(vin: str, max_gap_s: float = MAX_GAP_S, tolerance: float = dc.DEFAULT_TOLERANCE,
          audit_path: Optional[Path] = None, mes_paths: Optional[Iterable[Path]] = None) -> dict[str, Any]:
    """The review queue (not saved, nothing applied). See :func:`decode_flow.review_queue`."""
    from . import channels as ch_mod
    reg = ch_mod.registry()
    aliases = dc.load_aliases()["pairs"]
    reads = cuore_did_reads(audit_path)
    conds = mes_conditions(mes_paths, vin)
    by_mod_conds = {m: [c for c in conds if c["module"] == m] for m in {c["module"] for c in conds}}
    by_ch: dict[str, list[dict[str, Any]]] = {}
    for a in aliases:
        by_ch.setdefault(a["channel"], []).append(a)

    rows: list[dict[str, Any]] = []
    for cid, entries in by_ch.items():
        ch = reg.get(cid)
        if ch is None or ch.kind != "did" or ch.module.upper() not in MODULES or not ch.formula or ch.field \
                or ch.untrusted:
            continue
        mod = ch.module.upper()
        did = f"{ch.did:04X}"
        mine = [r for r in reads if r["ecu"] == mod and r["did"] == did]
        best: Optional[dict[str, Any]] = None
        for a in entries:
            src_mod = a.get("mes_module", mod)
            cands = [c for c in by_mod_conds.get(src_mod, []) if a["mes_name"] in c["values"]]
            pairs: list[tuple[float, float, float]] = []
            evidence: list[dict[str, Any]] = []
            nearest: Optional[float] = None
            for i, c in enumerate(cands):
                unit, ys = c["values"][a["mes_name"]]
                gaps = [(_gap(r["at"], c), r) for r in mine]
                if gaps:
                    nearest = min(nearest if nearest is not None else 9e18, min(g for g, _ in gaps))
                used = [(g, r) for g, r in gaps if g <= max_gap_s]
                if not used:
                    continue
                # only the reads closest in time speak for this condition (a read half an hour away does not)
                near = min(g for g, _ in used)
                used = [(g, r) for g, r in used if g <= near + CLUSTER_S]
                xs = [x for x in (_decode(ch.formula, r["data"]) for _, r in used) if x is not None]
                if not xs:
                    continue
                x, y = statistics.median(xs), statistics.median(ys)
                pairs.append((x, y, float(i)))
                nearest_read = min(used, key=lambda t: t[0])[1]
                evidence.append({"mes_log": c["log"], "mes_window": [c["start"].isoformat(timespec="seconds"),
                                                                       c["end"].isoformat(timespec="seconds")],
                                 "mes_value": y, "mes_unit": unit, "mes_samples": len(ys),
                                 "cuore_reads": len(used), "cuore_raw": "".join(f"{b:02X}" for b in nearest_read["data"]),
                                 "cuore_decoded": x, "cuore_at": nearest_read["at"].isoformat(timespec="seconds"),
                                 "gap_s": int(min(g for g, _ in used))})
            T = dc._transforms(ch.unit, a.get("mes_unit", ""), ch.formula, a.get("also_try", []))
            if pairs:
                r = dc._verdict(pairs, T, tolerance, min_pairs=2, min_distinct=2, fit_frac=1.0,
                                unit_word="conditions with data")
                if r["verdict"] == "no_data" and len(pairs) == 1:
                    ident = dc._fit(pairs, T[0], tolerance)
                    r["single_point"] = {"identity_agrees": bool(ident["fit"] >= 1.0),
                                         "note": "one condition is a single point, not a scale; it cannot be accepted"}
            elif not mine:
                r = {"verdict": "no_data", "samples": 0, "reason": "CUORE never read this DID in the audit log"}
            elif not cands:
                r = {"verdict": "no_data", "samples": 0,
                     "reason": f"no MES live log of {src_mod} with '{a['mes_name']}' on file"}
            else:
                r = {"verdict": "no_data", "samples": 0,
                     "reason": f"nearest CUORE read is {_span(nearest or 0)} from a MES log "
                               f"(limit {int(max_gap_s) // 60} min): engine state may differ"}
            row = {**r, "mes_name": a["mes_name"], "mes_unit": a.get("mes_unit", ""), "pairing": a["certainty"],
                   "evidence": evidence, "cross_module": src_mod != mod}
            rank = (row["verdict"] == "no_data", row["pairing"] != "certain", -(row.get("fit") or 0))
            if best is None or rank < best["_rank"]:
                best = {**row, "_rank": rank}
        if best is None:
            continue
        best.pop("_rank")
        rows.append({"channel": cid, "module": mod, "did": did, "name": ch.name, "unit": ch.unit,
                     "current_confidence": ch.confidence, "alternatives": [], **best})
    rows.sort(key=lambda r: ({"confirmed": 0, "wrong_scale": 0}.get(r["verdict"], 1 if r.get("single_point") else 2),
                             r["module"], r["channel"]))
    ecm_names = {n for c in by_mod_conds.get("ECM", []) for n in c["values"]}
    aliased = {a["mes_name"] for a in aliases}
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1
    per_module = {m: {"mes_live_logs": len(by_mod_conds.get(m, [])),
                      "channels_with_alias": sum(1 for r in rows if r["module"] == m),
                      "evidence_conditions": sum(len(r["evidence"]) for r in rows if r["module"] == m)}
                  for m in MODULES}
    return {"vin": vin, "max_gap_s": max_gap_s, "tolerance": tolerance, "summary": summary, "channels": rows,
            "per_module": per_module, "cuore_did_reads": len(reads), "mes_live_logs": len(conds),
            "mes_ecm_names_seen": len(ecm_names),
            "mes_ecm_names_without_channel": sorted(ecm_names - aliased)}


def save_run(vin: str, q: dict[str, Any]) -> dict[str, Any]:
    """Save the queue as a decode_confirm run (same file shape) so the existing accept/reject apply to it."""
    from datetime import datetime as _dt
    from .ui_store import atomic_write_text
    with dc._LOCK:
        d = dc._dir()
        d.mkdir(parents=True, exist_ok=True)
        run_id = _dt.now().strftime("%Y%m%d-%H%M%S")
        n = 1
        while (d / f"{run_id}.json").exists():
            n += 1
            run_id = f"{_dt.now().strftime('%Y%m%d-%H%M%S')}-{n}"
        rec = {"run_id": run_id, "vin": vin, "at": _dt.now().isoformat(timespec="seconds"),
               "mes_log": "recorded MES logs", "cuore_recording": "audit log (raw DID bytes)",
               "tolerance": q["tolerance"], "mode": "recorded", "tags": {"mes": [], "cuore": []},
               "timing": {"max_gap_s": q["max_gap_s"], "notes": ["paired by recorded time, no live tags"]},
               "summary": q["summary"], "channels": q["channels"], "accepted": []}
        atomic_write_text(d / f"{run_id}.json", json.dumps(rec, indent=1, ensure_ascii=False, default=str))
    return rec


__all__ = ["build", "save_run", "cuore_did_reads", "mes_conditions", "MAX_GAP_S"]
