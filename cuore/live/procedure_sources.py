"""DOCUMENTED procedures: the second, labelled source for CUORE's write path.

A documented procedure comes from published tool documentation, open-source code or a published
trace (never from guesswork) and is stored as JSON with its citation and confidence. It goes through
the SAME gate as a procedure CUORE captured from MES (``procedure_capture.review`` / ``gate``), may be
dry-run freely, and a real run additionally needs an explicit owner acceptance record naming the
procedure, its source citation and a hash of its steps. Change the steps and the acceptance is void.

Offline and pure: nothing here opens an adapter. Definitions ship in ``cuore/data/procedures/*.json``;
the owner/research overrides them in ``CUORE_STATE_DIR/procedures/<name>.json`` (shallow merge: dicts are
merged key by key, everything else, notably ``steps``, is replaced). Acceptances are append-only in
``CUORE_STATE_DIR/procedure_acceptances.jsonl``.

Definition fields: name, module, intent, status ("awaiting source" while steps is empty), session
{bus, bitrate, diagnostic_session}, max_seconds, steps [ "22F190" | {"request": "..."} ], read_back
{status, label, module, checks[{quantity, did, expect}]}, preconditions / postconditions
{engine_state, voltage_v, label}, verification_rule, mes_function, source {kind: documented|captured,
citation, confidence}, accepted_by_owner (always derived from the acceptance log, never trusted from a file).

``ready(name)`` is the single truth other code asks before a real run.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import procedure_capture
from .config import state_dir

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "procedures"
ALLOWLIST_PATH = Path(__file__).resolve().parents[1] / "data" / "write_allowlist.json"
_LIST = list  # the builtin; this module also exports list()
AWAITING = "awaiting source"

#: Services a documented procedure may never contain, unless (2E only) an explicit per-DID allowlist entry exists.
#: 0x27 is never allowable. Even an allowlisted 0x2E is still refused by the gate (outside the actuation allowlist).
FORBIDDEN_SERVICES = {
    "27": "SecurityAccess", "2E": "WriteDataByIdentifier", "34": "RequestDownload",
    "35": "RequestUpload", "36": "TransferData", "37": "RequestTransferExit",
    "11": "ECUReset", "85": "ControlDTCSetting", "28": "CommunicationControl",
    "14": "ClearDiagnosticInformation", "3D": "WriteMemoryByAddress",
}
SOURCE_KINDS = ("documented", "captured")
REQUIRED = ("name", "module", "intent", "session", "steps", "read_back", "preconditions",
            "postconditions", "verification_rule", "source")


def _state() -> Path:
    return state_dir()


def _override_path(name: str) -> Path:
    return _state() / "procedures" / f"{name}.json"


def acceptances_path() -> Path:
    return _state() / "procedure_acceptances.jsonl"


def _read_json(p: Path) -> Optional[dict[str, Any]]:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def list() -> list[dict[str, Any]]:  # noqa: A001 -- the requested public name
    """Every known definition (shipped + owner-only overrides) with its status."""
    names = {p.stem for p in DATA_DIR.glob("*.json")}
    ov = _state() / "procedures"
    if ov.is_dir():
        names |= {p.stem for p in ov.glob("*.json")}
    out = []
    for n in sorted(names):
        try:
            d = load(n)
        except KeyError:
            continue
        out.append({"name": n, "module": d.get("module"), "status": d["status"],
                    "steps": len(d.get("steps") or []), "source_kind": (d.get("source") or {}).get("kind"),
                    "accepted": is_accepted(n)["accepted"]})
    return out


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(name: str) -> dict[str, Any]:
    """Repo default merged with the state-dir override. ``status`` and ``accepted_by_owner`` are derived."""
    base = _read_json(DATA_DIR / f"{name}.json")
    over = _read_json(_override_path(name))
    if base is None and over is None:
        raise KeyError(f"no procedure definition named {name!r}")
    d = _merge(base or {}, over or {})
    d["name"] = d.get("name") or name
    d["status"] = AWAITING if not d.get("steps") else (
        d.get("status") if d.get("status") not in (None, AWAITING) else "filled, not yet accepted")
    d["has_override"] = over is not None
    d["accepted_by_owner"] = bool(is_accepted(name, _d=d)["accepted"]) if d.get("steps") else False
    return d


# ---------------------------------------------------------------------------------------------
# steps, hashing
# ---------------------------------------------------------------------------------------------

def normalized_steps(d: dict[str, Any]) -> list[str]:
    return ["".join(procedure_capture._norm_request(s)) for s in d.get("steps") or []]


def steps_hash(d: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(normalized_steps(d)).encode()).hexdigest()


def _write_allowlist() -> list[dict[str, Any]]:
    """Per-DID write allowlist, if another component has written one. Default deny."""
    try:
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("entries") or data.get("allowed") or data.get("dids") or []
    return [e for e in data if isinstance(e, dict)] if isinstance(data, _LIST) else []


def _allowlisted_write(module: str, req: list[str]) -> bool:
    if len(req) < 3:
        return False
    did = (req[1] + req[2]).upper()
    for e in _write_allowlist():
        if str(e.get("module", "")).upper() == module.upper() and \
                str(e.get("did", "")).upper().replace("0X", "").zfill(4) == did:
            svc = str(e.get("service", "2E")).upper().replace("0X", "")
            if svc == "2E":
                return True
    return False


# ---------------------------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------------------------

def validate(defn: dict[str, Any], *, pre: Optional[dict] = None, post: Optional[dict] = None) -> dict[str, Any]:
    """Schema check plus the gate's own rules. ``ok`` = no errors; with empty steps that is true and
    ``status`` is "awaiting source" (``gate`` is None: nothing to gate yet)."""
    errors: list[str] = []
    for k in REQUIRED:
        if k not in defn:
            errors.append(f"missing field: {k}")
    src = defn.get("source") or {}
    if src.get("kind") not in SOURCE_KINDS:
        errors.append(f"source.kind must be one of {SOURCE_KINDS}")
    for k in ("citation", "confidence"):
        if k not in src:
            errors.append(f"source.{k} missing")
    steps = defn.get("steps")
    if not isinstance(steps, _LIST):
        errors.append("steps must be a list")
        steps = []
    if steps and not src.get("citation"):
        errors.append("steps present but source.citation is empty: a documented procedure must cite its source")
    if defn.get("accepted_by_owner") not in (False, None, True):
        errors.append("accepted_by_owner must be a boolean")
    rb = defn.get("read_back")
    if not isinstance(rb, dict) or not isinstance(rb.get("checks"), _LIST) or not rb["checks"]:
        errors.append("read_back.checks must list what proves the change")
    reqs: list[list[str]] = []
    for i, st in enumerate(steps, 1):
        try:
            req = procedure_capture._norm_request(st)
        except ValueError as e:
            errors.append(f"step {i}: {e}")
            continue
        if not req:
            errors.append(f"step {i}: empty request")
            continue
        reqs.append(req)
        svc = req[0]
        if svc in FORBIDDEN_SERVICES:
            if svc == "2E" and _allowlisted_write(str(defn.get("module", "")), req):
                continue
            errors.append(f"step {i}: service 0x{svc} {FORBIDDEN_SERVICES[svc]} refused "
                          "(no per-DID allowlist entry; default deny)" if svc == "2E" else
                          f"step {i}: service 0x{svc} {FORBIDDEN_SERVICES[svc]} is never allowed in a procedure")
    gate = None
    if steps and not errors:
        proc = procedure_capture.documented_procedure(defn)
        gate = procedure_capture.gate(
            proc, listen_bitrate=proc.get("bitrate"),
            pre={**(proc.get("pre") or {}), **(pre or {})}, post={**(proc.get("post") or {}), **(post or {})},
            max_seconds=proc.get("max_seconds"), name=defn.get("name", ""),
            mes_function=defn.get("mes_function") or "")
    return {"ok": not errors, "errors": errors, "gate": gate,
            "status": AWAITING if not steps else ("invalid" if errors else "filled")}


# ---------------------------------------------------------------------------------------------
# acceptance (append-only)
# ---------------------------------------------------------------------------------------------

def accept(name: str, by: str, note: str) -> dict[str, Any]:
    """Record the owner's acceptance of THIS procedure from THIS source with THESE steps.
    Refused while the steps are empty or the definition is invalid."""
    d = load(name)
    if not (by or "").strip():
        raise ValueError("accept() needs 'by' (who accepts)")
    if not d.get("steps"):
        raise ValueError(f"{name}: status is '{AWAITING}'; there is nothing to accept")
    v = validate(d)
    if not v["ok"]:
        raise ValueError(f"{name}: definition invalid: {'; '.join(v['errors'])}")
    src = d.get("source") or {}
    rec = {"at": datetime.now().isoformat(timespec="seconds"), "procedure": name, "by": by.strip(),
           "note": note, "source_kind": src.get("kind"), "citation": src.get("citation"),
           "confidence": src.get("confidence"), "steps_sha256": steps_hash(d),
           "n_steps": len(d["steps"])}
    p = acceptances_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def is_accepted(name: str, *, _d: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """``{"accepted": bool, "reason", "record"}``. The latest record for ``name`` counts, and only while
    the current steps hash and source citation still equal the recorded ones."""
    try:
        d = _d or load(name)
    except KeyError:
        return {"accepted": False, "reason": "unknown procedure", "record": None}
    last = None
    try:
        for line in acceptances_path().read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("procedure") == name:
                last = r
    except OSError:
        pass
    if last is None:
        return {"accepted": False, "reason": "no owner acceptance recorded", "record": None}
    if not d.get("steps"):
        return {"accepted": False, "reason": "steps are empty", "record": last}
    if last.get("steps_sha256") != steps_hash(d):
        return {"accepted": False, "reason": "acceptance void: the steps changed since it was recorded",
                "record": last}
    if last.get("citation") != (d.get("source") or {}).get("citation"):
        return {"accepted": False, "reason": "acceptance void: the source citation changed", "record": last}
    return {"accepted": True, "reason": "accepted", "record": last}


# ---------------------------------------------------------------------------------------------
# ready
# ---------------------------------------------------------------------------------------------

def ready(name: str, *, pre: Optional[dict] = None, post: Optional[dict] = None) -> dict[str, Any]:
    """The single truth before a real run:
    ``{"dry_run_ok", "gate", "accepted", "read_back_known", "blockers": [...]}``.
    ``pre``/``post`` are the conditions recorded for this run (voltage etc.)."""
    d = load(name)
    blockers: list[str] = []
    steps = d.get("steps") or []
    v = validate(d, pre=pre, post=post)
    gate = v["gate"]
    dry_ok = False
    if not steps:
        blockers.append(f"status '{AWAITING}': no source steps yet (none invented)")
    if v["errors"]:
        blockers.extend(f"schema: {e}" for e in v["errors"])
    if gate is not None:
        if not gate["passed"]:
            blockers.extend(f"gate: {r}" for r in gate["reasons"])
        else:
            from . import procedure_dry_run
            proc = procedure_capture.documented_procedure(d)
            rep = procedure_dry_run.dry_run(
                proc, pre={**(proc.get("pre") or {}), **(pre or {})},
                post={**(proc.get("post") or {}), **(post or {})})
            dry_ok = rep["verdict"] == procedure_dry_run.WORKED
            if not dry_ok:
                blockers.append(f"dry run: {rep['verdict']} - {rep['verdict_line']}")
    acc = is_accepted(name, _d=d)
    if not acc["accepted"]:
        blockers.append(f"owner acceptance: {acc['reason']}")
    rb = d.get("read_back") or {}
    rb_known = rb.get("status") == "confirmed" and bool(rb.get("checks")) and \
        all(c.get("did") for c in rb["checks"])
    if not rb_known:
        blockers.append("read-back DIDs not confirmed (still service_dids discovery candidates)")
    return {"name": name, "module": d.get("module"), "source": (d.get("source") or {}).get("kind"),
            "status": d["status"], "dry_run_ok": dry_ok, "gate": gate, "accepted": acc["accepted"],
            "read_back_known": rb_known, "blockers": blockers}


__all__ = ["list", "load", "validate", "accept", "is_accepted", "ready", "steps_hash"]
