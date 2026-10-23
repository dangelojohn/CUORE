"""CUORE export bundle: one scan or one job as a ``*.cuore.zip`` a person carries.

Owner decision (docs/integration/ALFACORE_INTEGRATION_SPEC.md, sections 2-4):
CUORE runs car-side with no network link to AlfaCore and no tokens. Data moves
as a file (USB stick, shared folder, browser upload). This module builds that
file; ``cuore/services/bundle_schema.py`` and
``docs/integration/cuore_bundle.schema.json`` define and check it.

Read-only by construction (invariants I2, I5, I10): it reads the stores and
writes only ``<state_dir>/exports/`` (plus ``station.json`` once). It imports
nothing from the adapter layer, never opens a serial port, and a failed write
leaves every store untouched (the zip is built beside its final name and
renamed into place).

Identity and idempotency: ``station_id`` is minted once and kept in
``<state_dir>/station.json``. ``bundle_uuid`` is a uuid5 over ``station_id``,
kind, source id and a hash of the part files, so exporting unchanged data
again gives the same id (the importer treats it as "already imported").

Timestamps: the stores hold naive local time. Every stamp is converted with
``CUORE_TZ`` (IANA zone) or the PC's local zone and flagged
``tz_assumed: true``; stored values are never rewritten.

Evidence classes (spec 5.3, contracts 1.13) are assigned at the source and
travel with each reference. A conclusion carries the WEAKEST class among its
supports, ranked reading > inference > owner_attested > outside_literature;
a hypothesis is itself an inference, so it is never better than that.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import __version__
from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import store as live_store
from ..live.config import state_dir
from ..live.obd import decode_dtc_status
from . import scan_requirements_bridge as req_bridge
from .errors import BadRequest, NotFound

SCHEMA = "cuore.bundle/1.0"
_NAMESPACE = uuid.UUID("5f3c2b1e-7a64-4d0e-9c1f-0c0a5e1d2b3a")
_STATION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

EVIDENCE_RANK = {"reading": 3, "inference": 2, "owner_attested": 1, "outside_literature": 0}
EVIDENCE_CLASS_RULES = {
    "reading": "what this car said on a real serial adapter (from_car true)",
    "inference": "a conclusion drawn from readings or hypothesis text; a DTC alone is not a measurement",
    "outside_literature": "bulletins, forums, other cars or years; never a reading of this car",
    "owner_attested": "a person said it (owner event, mechanic-typed fact, test result recorded by hand)",
    "ranking": "a conclusion carries the weakest class among its supports: "
               "reading > inference > owner_attested > outside_literature",
}
#: Evidence-ref kind -> class. A car read is a reading; what a person typed or
#: judged is attested; a bulletin is outside literature. Unknown kinds are
#: inference (never promoted).
REF_CLASS = {
    "code": "reading", "freeze_frame": "reading", "actuator": "reading",
    "live": "reading", "observation": "reading",
    "test": "owner_attested", "measurement": "owner_attested",
    "inspection": "owner_attested", "symptom": "owner_attested",
    "note": "owner_attested", "media": "owner_attested", "dealer": "owner_attested",
    "feedback": "owner_attested", "bulletin": "outside_literature",
}
_STAMP_KEYS = {"at", "opened_at", "closed_at", "updated_at", "confirmed_at",
               "event_date", "effective_date", "readiness_at"}
_VOLATILE_KEYS = {"generated_at"}


# --- station, zone, time ---------------------------------------------------------

def exports_dir() -> Path:
    d = state_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def station_id() -> str:
    """The one id of this PC, minted on first use and then never changed."""
    env = (os.environ.get("CUORE_STATION_ID") or "").strip().lower()
    if _STATION_RE.match(env):
        return env
    p = state_dir() / "station.json"
    try:
        sid = str(json.loads(p.read_text(encoding="utf-8")).get("station_id") or "")
        if _STATION_RE.match(sid):
            return sid
    except (OSError, ValueError, AttributeError):
        pass
    sid = "cuore-" + uuid.uuid4().hex[:8]
    _atomic_write(p, json.dumps({"station_id": sid,
                                 "created_at": _now().isoformat(timespec="seconds")},
                                indent=2).encode("utf-8"))
    return sid


def _zone() -> Any:
    name = (os.environ.get("CUORE_TZ") or "").strip()
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 -- unknown zone or no tzdata: fall back to local
            pass
    return None


def _tz_name() -> str:
    return (os.environ.get("CUORE_TZ") or "").strip() or _now().tzname() or "local"


def _now() -> datetime:
    return datetime.now().astimezone()


def _aware(value: Any) -> tuple[Optional[str], bool]:
    """``(offset-aware ISO string, tz_assumed)`` for a stored stamp, or
    ``(None, False)`` for anything that is not a date-time (a bare date stays
    a bare date)."""
    s = str(value or "")
    if "T" not in s and " " not in s.strip():
        return None, False
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None, False
    if dt.tzinfo is not None:
        return dt.isoformat(timespec="seconds"), False
    zone = _zone()
    dt = dt.replace(tzinfo=zone) if zone is not None else dt.astimezone()
    return dt.isoformat(timespec="seconds"), True


def _stamp_tree(node: Any) -> None:
    """Add ``<key>_iso`` (and ``tz_assumed``) beside every naive stamp, in place."""
    if isinstance(node, dict):
        assumed = False
        for k in list(node):
            v = node[k]
            if k in _STAMP_KEYS and isinstance(v, str):
                iso, was = _aware(v)
                if iso:
                    node[f"{k}_iso"] = iso
                    assumed = assumed or was
            else:
                _stamp_tree(v)
        if assumed:
            node["tz_assumed"] = True
    elif isinstance(node, list):
        for v in node:
            _stamp_tree(v)


def _strip_volatile(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_volatile(v) for k, v in node.items() if k not in _VOLATILE_KEYS}
    if isinstance(node, list):
        return [_strip_volatile(v) for v in node]
    return node


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str,
                      separators=(",", ":")).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _git_commit() -> str:
    try:
        root = Path(__file__).resolve().parents[2]
        head = (root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = root / ".git" / head.split(None, 1)[1]
            if ref.exists():
                return ref.read_text(encoding="utf-8").strip()[:40]
            return ""
        return head[:40]
    except OSError:
        return ""


# --- observations ----------------------------------------------------------------

def _envelope(o: dict[str, Any], sid: str) -> dict[str, Any]:
    iso, assumed = _aware(o.get("at"))
    data = o.get("data") if isinstance(o.get("data"), dict) else {}
    return {
        "obs_id": hashlib.sha256(
            f"{sid}{o.get('at')}{o.get('kind')}".encode() + _canon(data)).hexdigest()[:16],
        "at": str(o.get("at") or ""), "at_iso": iso or "", "tz_assumed": assumed,
        "kind": str(o.get("kind") or ""), "vin": str(o.get("vin") or ""),
        "bus": str(o.get("bus") or ""), "cable": str(o.get("cable") or ""),
        "stream": str(o.get("stream") or ""), "from_car": live_store.is_from_car(o),
        "data": data,
    }


def _of(obs: list[dict[str, Any]], *kinds: str) -> list[dict[str, Any]]:
    return [o for o in obs if o.get("kind") in kinds]


def _carry(d: dict[str, Any]) -> dict[str, Any]:
    """Failure fields are data, never dropped (contracts 1.3)."""
    return {k: d[k] for k in ("error", "nrc", "warning", "note") if d.get(k)}


def _dtc_state(status: Any) -> str:
    try:
        st = int(status)
    except (TypeError, ValueError):
        return "unknown"
    if st & 0x0D:
        return "active"
    if st & 0x20:
        return "history"
    if st & 0x40 and not st & ~0x40:
        return "readiness_only"
    return "tracked"


def _dtc_parts(obs: list[dict[str, Any]], sid: str) -> dict[str, Any]:
    module, obd = [], []
    for o in _of(obs, "module_dtcs"):
        env = _envelope(o, sid)
        d = env["data"]
        recs = []
        for r in d.get("dtcs") or []:
            if not isinstance(r, dict):
                continue
            code = str(r.get("code") or "")
            base, _, ftb = code.partition("-")
            st = r.get("status")
            try:
                flags = decode_dtc_status(int(st))  # all 8 named bits, always
            except (TypeError, ValueError):
                flags = r.get("flags") if isinstance(r.get("flags"), dict) else {}
            recs.append({"code": code, "base_code": base, "failure_type_byte": ftb or None,
                         "status": st, "flags": flags, "state": _dtc_state(st),
                         "raw": r.get("raw")})
        module.append({"ecu": d.get("ecu") or "", "bus": env["bus"] or d.get("bus") or "",
                       "at_iso": env["at_iso"], "tz_assumed": env["tz_assumed"],
                       "stream": env["stream"], "from_car": env["from_car"],
                       "mask": d.get("mask"), "availability_mask": d.get("availability_mask"),
                       "counts": {s: sum(1 for x in recs if x["state"] == s)
                                  for s in ("active", "history", "tracked", "readiness_only")},
                       "dtcs": recs, **_carry(d)})
    for o in _of(obs, "obd_dtcs"):
        env = _envelope(o, sid)
        d = env["data"]
        obd.append({"dtc_kind": d.get("dtc_kind") or d.get("kind") or "", "at_iso": env["at_iso"],
                    "tz_assumed": env["tz_assumed"], "stream": env["stream"],
                    "from_car": env["from_car"], "bus": env["bus"],
                    "dtcs": d.get("dtcs") or [], "by_ecu": d.get("by_ecu") or {}, **_carry(d)})
    return {"module_dtcs": module, "obd_dtcs": obd}


def _present_codes(dtcs: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for m in dtcs["module_dtcs"]:
        for r in m["dtcs"]:
            if r["state"] in ("active", "history") and r["base_code"] not in out:
                out.append(r["base_code"])
    for m in dtcs["obd_dtcs"]:
        for c in m["dtcs"]:
            b = str(c).partition("-")[0]
            if b and b not in out:
                out.append(b)
    return out


def _identities(obs: list[dict[str, Any]], sid: str) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for o in _of(obs, "module_identity"):
        env = _envelope(o, sid)
        d = env["data"]
        latest[(str(d.get("ecu") or ""), env["bus"] or str(d.get("bus") or ""))] = {
            "ecu": d.get("ecu") or "", "bus": env["bus"] or d.get("bus") or "",
            "at": env["at"], "at_iso": env["at_iso"], "tz_assumed": env["tz_assumed"],
            "from_car": env["from_car"], "fields": d.get("fields") or {}, **_carry(d)}
    return [latest[k] for k in sorted(latest)]


# --- scan ------------------------------------------------------------------------

def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _guided_for(scan_id: str) -> dict[str, Any]:
    g = _read_json(state_dir() / "fullscan_guided.json")
    return g if isinstance(g, dict) and g.get("scan_id") == scan_id else {}


def _scan_status(cov: dict[str, Any]) -> str:
    """Same honesty rule as the scan log: complete = CAN-C attempted and a
    CAN-C module answered; attempt = nothing answered anywhere."""
    rows = [r for r in cov.get("coverage") or [] if isinstance(r, dict)]
    if not cov:
        return "partial"
    answered = [r for r in rows if r.get("category") == "answered"]
    if not answered:
        return "attempt"
    if "can_c" in (cov.get("buses_attempted") or ["can_c"]) \
            and any(r.get("bus") == "can_c" for r in answered):
        return "complete"
    return "partial"


def _code_findings(codes: list[str]) -> dict[str, Any]:
    try:
        from mes import code_findings
    except Exception:  # noqa: BLE001
        return {"codes": codes, "findings": [], "available": False}
    out = []
    for code in codes:
        for f in code_findings.lookup(code):
            out.append({
                "code": f.get("code"), "module": f.get("module"), "meaning": f.get("meaning"),
                "meaning_source": f.get("meaning_source"),
                "classification": f.get("classification"),
                "classification_label": f.get("classification_label"),
                "safety": bool(f.get("safety")), "safety_note": f.get("safety_note") or "",
                "ladder": f.get("ladder") or [], "proof": f.get("proof") or "",
                "evidence": {
                    "readings": list(f.get("readings") or []),
                    "inference": [x for x in (f.get("classification_note"),
                                              f.get("implications")) if x],
                    "outside_literature": list(f.get("literature") or []),
                    "owner_attested": list(f.get("owner") or []),
                }})
    return {"codes": codes, "findings": out, "available": True}


def _tsb_xref(vin: str, warnings: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    from . import tsb_xref_bridge
    try:
        view = tsb_xref_bridge.xref(vin)
    except Exception as exc:  # noqa: BLE001 -- the xref is context; the bundle still exports
        warnings.append(f"tsb cross-reference unavailable: {type(exc).__name__}: {exc}")
        return {"vin": vin, "available": False, "bulletins": [], "analogues": []}, {}
    rows = []
    for b in view.get("bulletins") or []:
        # every catalogue row carries an `applicability` relation; only rows
        # tied to this car's codes, systems, jobs or repairs are worth shipping
        if not any(r.get("type") != "applicability" for r in b.get("relations") or []):
            continue
        rows.append({
            "id": b.get("id"), "number": b.get("number"), "kind": b.get("kind"),
            "title": b.get("title"), "applies": b.get("applies"),
            "verified": b.get("verified"), "vehicle_scope": b.get("vehicle_scope"),
            "relations": b["relations"], "flags": b.get("flags") or [],
            "score": b.get("score"), "score_parts": b.get("score_parts") or [],
            "evidence_class": ("outside_literature" if b.get("vehicle_scope") == "sibling_engine"
                               else "inference")})
    return {"vin": vin, "available": True, "job_id": view.get("job_id"), "weights": view.get("weights"),
            "bulletins": rows, "analogues": view.get("analogues") or []}, view


# --- job -------------------------------------------------------------------------

def _weakest(classes: list[str]) -> str:
    return min(classes, key=lambda c: EVIDENCE_RANK.get(c, 2)) if classes else "inference"


def _label_job(job: dict[str, Any]) -> dict[str, Any]:
    j = copy.deepcopy(job)
    for h in j.get("hypotheses") or []:
        supports = []
        for side in ("evidence_for", "evidence_against"):
            for ref in h.get(side) or []:
                cls = REF_CLASS.get(str(ref.get("kind")), "inference")
                ref["evidence_class"] = cls
                if side == "evidence_for":
                    supports.append(cls)
        if h.get("attested_resolved"):
            supports.append("owner_attested")
        h["evidence_class"] = _weakest(["inference"] + supports)
        h["evidence_class_basis"] = ("weakest of the hypothesis text (inference) and its "
                                     "supporting references")
    for a in j.get("actions") or []:
        a["evidence_class"] = "owner_attested"
        a.setdefault("event_date", None)
        a.setdefault("effective_date", a.get("event_date") or a.get("at"))
    _stamp_tree(j)
    return j


def _plans(vin: str, job: dict[str, Any], view: dict[str, Any],
           warnings: list[str]) -> dict[str, Any]:
    from . import mechanic_plan_bridge
    plans = []
    for h in job.get("hypotheses") or []:
        if h.get("deleted"):
            continue
        try:
            p = mechanic_plan_bridge.plan(vin, job["id"], h["id"], xref_view=view or None, job=job)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"mechanic plan for hypothesis {h.get('id')} unavailable: {exc}")
            plans.append({"hypothesis_id": h.get("id"), "steps": [], "error": str(exc)})
            continue
        p = _strip_volatile(copy.deepcopy(p))
        p["hypothesis_id"] = p.get("hypothesis_id") or h["id"]
        for s in p.get("steps") or []:
            s["evidence_class"] = ("outside_literature"
                                   if str(s.get("source") or "").startswith("OUTSIDE LITERATURE")
                                   else "inference")
        plans.append(p)
    return {"plans": plans}


def _proof(job: dict[str, Any], vin: str, obs_all: list[dict[str, Any]], sid: str) -> dict[str, Any]:
    ver = job.get("verification") or {}
    codes = sorted({str(c).partition("-")[0] for h in job.get("hypotheses") or []
                    if not h.get("deleted") for c in h.get("codes") or []})
    criteria = [{"code": f["code"], "module": f["module"], "proof": f["proof"],
                 "evidence_class": "inference"}
                for f in _code_findings(codes)["findings"] if f["proof"]]
    clears = [{"at_iso": e["at_iso"], "tz_assumed": e["tz_assumed"], "ecu": e["data"].get("ecu"),
               "active": e["data"].get("active") or [],
               "file": os.path.basename(str(e["data"].get("file") or ""))}
              for e in (_envelope(o, sid) for o in _of(obs_all, "clear_evidence"))
              if e["at"] >= str(job.get("opened_at") or "")]
    present = bool(ver.get("readiness_at") or ver.get("codes_returned") or ver.get("verdict")
                   or job.get("outcome"))
    out = {"present": present, "job_id": job.get("id"), "criteria": criteria,
           "verification": ver, "outcome": job.get("outcome"), "closed_at": job.get("closed_at"),
           "clear_evidence": clears}
    _stamp_tree(out)
    return out


# --- packaging -------------------------------------------------------------------

def _package(kind: str, source_id: str, vin: str, parts: dict[str, bytes],
             identities: list[dict[str, Any]], warnings: list[str], finalized: bool) -> Path:
    sid = station_id()
    files = [{"path": n, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
             for n, b in sorted(parts.items())]
    content = hashlib.sha256("".join(f"{f['path']}:{f['sha256']};" for f in files)
                             .encode()).hexdigest()
    bundle_uuid = str(uuid.uuid5(_NAMESPACE, f"{sid}|{kind}|{source_id}|{content}"))
    now = _now()
    manifest: dict[str, Any] = {
        "schema": SCHEMA, "bundle_uuid": bundle_uuid, "kind": kind, "source_id": source_id,
        "station_id": sid, "created_at": now.isoformat(timespec="seconds"), "tz": _tz_name(),
        "cuore_version": __version__, "content_sha256": content,
        "vehicle": {"vin": vin, "identities": identities},
        "files": files, "contains": [f["path"] for f in files],
        "warnings": warnings, "finalized": finalized,
    }
    commit = _git_commit()
    if commit:
        manifest["git_commit"] = commit
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in [("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))] \
                + sorted(parts.items()):
            zi = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", source_id)
    name = f"{now.strftime('%Y%m%d-%H%M%S')}_{vin[-6:]}_{kind}_{safe_id}.cuore.zip"
    out = exports_dir() / name
    _atomic_write(out, buf.getvalue())
    return out


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def _check_vin(vin: str) -> str:
    v = (vin or "").strip().upper()
    if not re.match(r"^[A-HJ-NPR-Z0-9]{17}$", v):
        raise BadRequest("a valid 17-character VIN is required to export "
                         "(an item with an unresolved VIN is not exported)")
    return v


def export_scan(scan_id: str, vin: str) -> Path:
    """Bundle one scan (full or guided) of ``vin``: the scan state, DTCs with
    status bytes, freeze frames, Mode 06, readiness, EVAP bundle, the
    scan-requirements result, TSB cross-reference and code findings."""
    vin = _check_vin(vin)
    scan_id = (scan_id or "").strip()
    sid = station_id()
    ctx = req_bridge._build_ctx(scan_id, vin, "")
    if ctx is None:
        raise BadRequest(f"scan id {scan_id!r} not recognised "
                         "(expected SCAN_YYMMDDHHMM or an ISO timestamp)")
    guided = _guided_for(scan_id)
    obs = ctx.in_window
    if not obs and not guided:
        raise NotFound(f"no observations or guided session for scan {scan_id!r} on {vin}")
    warnings: list[str] = []
    untagged = sum(1 for o in obs if not (o.get("vin") or ""))
    if untagged:
        warnings.append(f"{untagged} observation(s) carry no VIN and were assigned to {vin} "
                        "(single-car store assumption)")
    non_car = sum(1 for o in obs if not live_store.is_from_car(o))
    if non_car:
        warnings.append(f"{non_car} observation(s) are not from a real serial link "
                        "(test, replay or scripted) and are not readings")
    cov_obs = [o for o in _of(obs, "scan_coverage")
               if (o.get("data") or {}).get("scan_id") == scan_id]
    cov = (cov_obs[-1].get("data") or {}) if cov_obs else {}
    status = _scan_status(cov)
    if status != "complete":
        warnings.append(f"scan status is {status!r}: it does not count as a completed scan")
    finalized = (guided.get("status") in ("done", "abandoned")) if guided else bool(cov_obs)
    if guided and not finalized:
        warnings.append("guided scan is paused: this bundle is not final")

    dtcs = _dtc_parts(obs, sid)
    codes = _present_codes(dtcs)
    streams = sorted({str(o.get("stream") or "") for o in obs})
    scan = {"scan_id": scan_id, "vin": vin, "status": status,
            "from_car": bool(obs) and non_car == 0, "streams": streams,
            "non_car_observations": non_car,
            "window": {"start": ctx.start.isoformat(timespec="seconds"),
                       "end": ctx.end.isoformat(timespec="seconds"),
                       "start_iso": _aware(ctx.start.isoformat())[0],
                       "end_iso": _aware(ctx.end.isoformat())[0], "tz_assumed": True},
            "cable": cov.get("cable") or guided.get("cable") or "",
            "buses_attempted": cov.get("buses_attempted") or [],
            "guided": {k: guided[k] for k in ("status", "segments", "pending_index", "started",
                                              "stream", "cable", "session_opens") if k in guided}
            if guided else {},
            "steps": cov.get("steps") or guided.get("steps") or [],
            "coverage": cov.get("coverage") or guided.get("coverage") or [],
            "counts": cov.get("counts") or {}}
    _stamp_tree(scan["guided"])
    xref, _view = _tsb_xref(vin, warnings)
    envs = [_envelope(o, sid) for o in obs]
    ff = {"mode02": [e for e in envs if e["kind"] in ("freeze_frame", "freeze_frame_set")],
          "dtc_detail": [e for e in envs if e["kind"] == "dtc_detail"]}
    evap = [e for e in envs if e["kind"] == "evap_bundle"]
    parts = {
        "scan.json": _dump(scan),
        "dtcs.json": _dump(dtcs),
        "freeze_frames.json": _dump(ff),
        "mode06.json": _dump({"records": [e for e in envs if e["kind"] == "mode06"]}),
        "readiness.json": _dump({"records": [e for e in envs if e["kind"] == "readiness"]}),
        "evap_bundle.json": _dump({"present": bool(evap), "records": evap}),
        "scan_requirements.json": _dump(req_bridge.check(scan_id, vin)),
        "tsb_xref.json": _dump(xref),
        "code_findings.json": _dump(_code_findings(codes)),
        "observations.jsonl": ("\n".join(json.dumps(e, sort_keys=True, default=str)
                                         for e in envs) + "\n").encode("utf-8"),
    }
    return _package("scan", scan_id, vin, parts, _identities(obs, sid), warnings, finalized)


def export_job(job_id: str, vin: str) -> Path:
    """Bundle one job: the folded ledger with an evidence class on every
    reference, hypothesis and action, the mechanic plan per hypothesis,
    proof-of-fix material, the TSB cross-reference and code findings."""
    from mes import jobs as jobs_mod
    vin = _check_vin(vin)
    sid = station_id()
    job = jobs_mod.get(job_id)
    if job is None:
        raise NotFound(f"no job {job_id!r}")
    if str(job.get("vin") or "").upper() != vin:
        raise BadRequest(f"job {job_id!r} belongs to a different vehicle than {vin}")
    warnings: list[str] = []
    obs_all = req_bridge._all_observations(vin)
    xref, view = _tsb_xref(vin, warnings)
    codes = sorted({str(c).partition("-")[0] for h in job.get("hypotheses") or []
                    if not h.get("deleted") for c in h.get("codes") or []}
                   | {str(r.get("id")).partition("-")[0]
                      for h in job.get("hypotheses") or [] for r in h.get("evidence_for") or []
                      if r.get("kind") == "code" and r.get("id")})
    open_ = job.get("status") != "closed"
    if open_:
        warnings.append("job is open: a later bundle may supersede this one")
    parts = {
        "job.json": _dump({"job": _label_job(job), "evidence_class_rules": EVIDENCE_CLASS_RULES}),
        "mechanic_steps.json": _dump(_plans(vin, job, view, warnings)),
        "proof_of_fix.json": _dump(_proof(job, vin, obs_all, sid)),
        "tsb_xref.json": _dump(xref),
        "code_findings.json": _dump(_code_findings(codes)),
    }
    return _package("job", job_id, vin, parts, _identities(obs_all, sid), warnings, not open_)


def read_manifest(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def resolve_export_path(raw: str) -> Path:
    """``raw`` as a file under ``<state_dir>/exports`` or ``BadRequest``/``NotFound``.
    Anything outside that folder (``..``, absolute elsewhere, symlinks out) is refused."""
    base = exports_dir().resolve()
    try:
        p = Path(raw).resolve()
        p.relative_to(base)
    except (ValueError, OSError):
        raise BadRequest("only files under the exports folder can be downloaded") from None
    if not p.name.endswith(".cuore.zip"):
        raise BadRequest("only *.cuore.zip bundles can be downloaded")
    if not p.is_file():
        raise NotFound("no such bundle")
    return p


__all__ = ["export_scan", "export_job", "read_manifest", "resolve_export_path", "station_id",
           "exports_dir", "SCHEMA", "EVIDENCE_RANK", "REF_CLASS"]
