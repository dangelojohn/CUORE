"""Warranty evidence pack: one bundle a technician attaches to a warranty claim.

``build(src, include_customer=False)`` is pure: it takes the gathered source data
(``gather`` collects it from the existing services) and returns the checklist, the
evidence sections in a fixed order and a manifest with a SHA-256 for every embedded
item. Nothing is invented: a missing source is reported as missing, never filled.
The claim itself is submitted through the manufacturer's warranty system.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

NOTE = "Evidence pack for a claim. The claim itself is submitted through the manufacturer's warranty system."
SCHEMA = "cuore.warranty_pack/1"
SECTIONS = ("complaint", "codes", "readings", "tests", "bulletins", "repair", "proof", "photos",
            "dealer", "technicians")
TITLES = {"complaint": "Complaint", "codes": "Codes and snapshots", "readings": "Readings",
          "tests": "Tests performed", "bulletins": "Bulletins and recalls checked",
          "repair": "Repair recorded", "proof": "Proof of repair", "photos": "Photos",
          "dealer": "Dealer results", "technicians": "Technician attribution"}
CUSTOMER_KEYS = ("customer", "customer_name", "customer_phone", "customer_email", "contact")
_READING_KINDS = {"live", "observation", "measurement", "mode06", "readiness", "pid", "voltage",
                  "freeze_frame", "dtc_detail", "evap_bundle"}


def canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


def sha(obj: Any) -> str:
    return hashlib.sha256(canon(obj)).hexdigest()


def _item(section: str, id_: str, at: str, source: str, text: str, *, label: str = "",
          values: Optional[dict] = None, who: str = "") -> dict[str, Any]:
    it: dict[str, Any] = {"id": id_, "section": section, "at": at or "", "source": source,
                          "label": label, "text": text, "by": who, "data": values or {}}
    return it


def _odo_keys(row: dict) -> dict[str, Any]:
    return {k: v for k, v in row.items() if "odo" in k.lower() and isinstance(v, (int, float, str)) and v != ""}


def _compose(src: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    job = src.get("job") or {}
    jid = job.get("id") or "nojob"
    sec: dict[str, list] = {k: [] for k in SECTIONS}
    tech = job.get("technician") or ""
    if (job.get("complaint") or "").strip():
        sec["complaint"].append(_item("complaint", f"job:{jid}:complaint", job.get("opened_at", ""),
                                      f"job {jid} intake", job["complaint"].strip(), who=tech))
    for s in src.get("symptoms") or []:
        owner = str(s.get("reporter") or "driver") in ("driver", "owner")
        sec["complaint"].append(_item(
            "complaint", f"symptom:{s.get('id', '')}", str(s.get("at") or s.get("created_at") or ""),
            "symptom log", str(s.get("text") or ""), label="owner's words" if owner else "",
            values=_odo_keys(s) or None, who="" if owner else str(s.get("reporter") or "")))
    ffs = {str(f.get("code")): f for f in src.get("freeze_frames") or []}
    for d in src.get("dtcs") or []:
        code = str(d.get("dtc") or d.get("code") or "")
        ff = ffs.get(code.split("-")[0]) or ffs.get(code)
        vals = {"first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"),
                "sessions": d.get("sessions"), "modules": d.get("modules"),
                "returned_after_clear": d.get("returned_after_clear")}
        vals.update(_odo_keys(d))
        if ff:
            vals["snapshot"] = ff.get("values")
            vals["snapshot_at"] = ff.get("at")
        sec["codes"].append(_item("codes", f"dtc:{code}", str(d.get("last_seen") or ""), "MES scan logs",
                                  f"{code} {(d.get('descriptions') or [''])[0]}".strip(),
                                  values={k: v for k, v in vals.items() if v not in (None, "", [])}))
    for o in src.get("observations") or []:
        sec["readings"].append(_item("readings", f"obs:{o.get('at')}:{o.get('kind')}", str(o.get("at") or ""),
                                     str(o.get("stream") or "live link"), str(o.get("kind") or ""),
                                     values=o.get("data") if isinstance(o.get("data"), dict) else None))
    for a in job.get("actions") or []:
        kind, ref = a.get("kind"), (a.get("ref") or {})
        at = str(a.get("event_date") or a.get("at") or "")
        who = str(a.get("by") or tech)
        res = ref.get("result")
        if kind == "observation" or (kind == "test" and ref.get("kind") in ("live", "observation", "measurement")):
            sec["readings"].append(_item("readings", f"action:{a.get('id')}", at, f"job {jid} action",
                                         str(a.get("text") or ""), who=who))
        elif kind in ("test", "inspection"):
            sec["tests"].append(_item("tests", f"action:{a.get('id')}", at, f"job {jid} {kind}",
                                      str(a.get("text") or ""), values={"result": res} if res else None, who=who))
        elif kind in ("repair", "part", "clear"):
            sec["repair"].append(_item("repair", f"action:{a.get('id')}", at, f"job {jid} {kind}",
                                       str(a.get("text") or ""), values={"kind": kind}, who=who))
    for h in job.get("hypotheses") or []:
        if h.get("deleted"):
            continue
        for side in ("evidence_for", "evidence_against"):
            for e in h.get(side) or []:
                src_label = "hypothesis '" + (h.get("text") or "")[:60] + "'"
                if e.get("kind") in ("test", "inspection", "actuator") or e.get("result"):
                    # the job store records a test's outcome as the side it was attached to (jobs.py "attach")
                    res = e.get("result") or ("supports the hypothesis" if side == "evidence_for"
                                              else "contradicts the hypothesis")
                    sec["tests"].append(_item(
                        "tests", f"hyp:{h.get('id')}:{e.get('id') or e.get('label')}", str(e.get("at") or ""),
                        src_label, str(e.get("label") or e.get("text") or ""),
                        values={"result": res, "side": side}, who=str(e.get("by") or tech)))
                elif e.get("kind") in ("live", "observation", "measurement"):
                    sec["readings"].append(_item("readings", f"hyp:{h.get('id')}:{e.get('id')}", str(e.get("at") or ""),
                                                 src_label, str(e.get("label") or e.get("text") or "")))
    x = src.get("xref")
    if x is not None:
        by_id = {b.get("id"): b for b in x.get("bulletins") or []}
        for code, rels in sorted((x.get("by_code") or {}).items()):
            for r in rels:
                b = by_id.get(r.get("bulletin")) or {}
                sec["bulletins"].append(_item(
                    "bulletins", f"tsb:{code}:{r.get('bulletin')}", "", "bulletin cross-reference",
                    f"{b.get('number') or r.get('bulletin')} {b.get('title') or ''} - {code}: {r.get('reason') or ''}".strip(),
                    label="outside fact"))
        for r in x.get("by_repair") or []:
            b = by_id.get(r.get("bulletin")) or {}
            sec["bulletins"].append(_item(
                "bulletins", f"tsb:repair:{r.get('bulletin')}:{r.get('at')}", str(r.get("at") or ""),
                "bulletin cross-reference",
                f"{b.get('number') or r.get('bulletin')} {b.get('title') or ''} - {r.get('reason') or ''}".strip(),
                label="outside fact"))
    v = job.get("verification") or {}
    if v.get("readiness_at") or v.get("codes_returned") or v.get("verdict") or job.get("outcome"):
        sec["proof"].append(_item("proof", f"job:{jid}:proof", str(job.get("closed_at") or v.get("readiness_at") or ""),
                                  f"job {jid} verification",
                                  f"outcome: {job.get('outcome') or 'not stated'}; verdict: {v.get('verdict') or 'not stated'}",
                                  values={"outcome": job.get("outcome"), "readiness_at": v.get("readiness_at"),
                                          "codes_returned": v.get("codes_returned") or []}, who=tech))
    for m in src.get("media") or []:
        sec["photos"].append(_item("photos", f"media:{m.get('id')}", str(m.get("captured_at") or ""),
                                   str(m.get("source") or "media library"), str(m.get("caption") or m.get("filename") or ""),
                                   values={"file": m.get("filename"), "kind": m.get("kind"), "sha256": m.get("sha256")},
                                   who=str(m.get("by") or "")))
    for d in src.get("dealer") or []:
        sec["dealer"].append(_item("dealer", f"dealer:{d.get('id') or d.get('at')}", str(d.get("at") or ""),
                                   "dealer result", f"{d.get('kind') or ''} {d.get('note') or ''}".strip(),
                                   values=d.get("data") if isinstance(d.get("data"), dict) else None))
    names: dict[str, str] = {}
    if tech:
        names[tech] = "job technician"
    for k, sect in sec.items():
        for it in sect:
            if it["by"] and it["by"] not in names:
                names[it["by"]] = f"author of {k} item"
    for n, role in sorted(names.items()):
        sec["technicians"].append(_item("technicians", f"who:{n}", "", "job record / accounts", n, who=role))
    for sect in sec.values():
        sect.sort(key=lambda i: i["at"] or "9999")
    return sec


def _checklist(sec: dict, src: dict) -> list[dict[str, Any]]:
    job = src.get("job") or {}
    has_snap = any((i.get("data") or {}).get("snapshot") for i in sec["codes"])
    proofs = sec["proof"]
    fixed = bool(proofs) and job.get("outcome") == "fixed"
    with_result = sum(1 for i in sec["tests"] if (i.get("data") or {}).get("result"))
    xr = src.get("xref") is not None
    rows = [
        ("complaint", "Complaint recorded", bool(sec["complaint"]), f"{len(sec['complaint'])} entry(ies)",
         "Record the customer complaint on the job."),
        ("codes", "Codes with snapshots", bool(sec["codes"]) and has_snap,
         f"{len(sec['codes'])} code(s), " + ("snapshot present" if has_snap else "no freeze-frame snapshot"),
         "Scan the car and save the codes with their freeze frames."),
        ("readings", "Readings with timestamps", bool(sec["readings"]) and all(i["at"] for i in sec["readings"]),
         f"{len(sec['readings'])} reading(s)", "Take and save live readings that show the fault."),
        ("tests", "Tests done with results", with_result > 0,
         f"{len(sec['tests'])} test(s), {with_result} with a result",
         "Run the diagnostic tests and record pass/fail for each."),
        ("bulletins", "Bulletin / recall checked", xr,
         f"{len(sec['bulletins'])} bulletin link(s)" if xr else "cross-reference unavailable",
         "Run the bulletin cross-reference for the codes."),
        ("repair", "Repair recorded", bool(sec["repair"]), f"{len(sec['repair'])} repair/part action(s)",
         "Record the repair and parts on the job."),
        ("proof", "Proof of repair", fixed,
         "job outcome fixed with verification" if fixed else
         ("verification recorded, outcome not 'fixed'" if proofs else "no verification recorded"),
         "Verify the fix (readiness, no codes returned) and close the job as fixed."),
        ("photos", "Photos", bool(sec["photos"]), f"{len(sec['photos'])} photo(s)/media",
         "Attach photos of the failed part and the repair."),
    ]
    return [{"key": k, "label": lab, "ok": bool(ok), "detail": d, "missing": "" if ok else m}
            for k, lab, ok, d, m in rows]


def build(src: dict[str, Any], include_customer: bool = False) -> dict[str, Any]:
    """The pack. ``src`` keys: vin, vehicle, job, symptoms, dtcs, freeze_frames, observations,
    xref, media, dealer, generated_at."""
    sec = _compose(src)
    check = _checklist(sec, src)
    ok = sum(1 for c in check if c["ok"])
    sections = [{"key": k, "title": TITLES[k], "items": sec[k]} for k in SECTIONS]
    if include_customer:
        job = src.get("job") or {}
        items = [_item("customer", f"customer:{k}", str(job.get("opened_at") or ""), "job record", f"{k}: {job[k]}")
                 for k in CUSTOMER_KEYS if job.get(k)]
        sections.append({"key": "customer", "title": "Customer details (as recorded on the job)", "items": items})
    manifest = [{"section": s["key"], "id": i["id"], "sha256": sha(i)} for s in sections for i in s["items"]]
    pack = {
        "schema": SCHEMA, "note": NOTE, "vin": src.get("vin"), "vehicle": src.get("vehicle") or "",
        "job_id": (src.get("job") or {}).get("id"), "generated_at": src.get("generated_at") or "",
        "include_customer": bool(include_customer),
        "score": {"done": ok, "total": len(check), "backed": ok == len(check)},
        "checklist": check,
        "missing": [c["label"] + ": " + c["missing"] for c in check if not c["ok"]],
        "sections": sections, "manifest": manifest,
    }
    pack["pack_sha256"] = sha({"manifest": manifest})
    return pack


def verify(pack: dict[str, Any]) -> list[str]:
    """Problems found re-hashing a downloaded pack (empty list = intact)."""
    bad = []
    flat = {(s["key"], i["id"]): i for s in pack.get("sections", []) for i in s["items"]}
    for m in pack.get("manifest", []):
        it = flat.get((m["section"], m["id"]))
        if it is None or sha(it) != m["sha256"]:
            bad.append(f"{m['section']}/{m['id']}")
    if len(flat) != len(pack.get("manifest", [])):
        bad.append("manifest count differs from items")
    if sha({"manifest": pack.get("manifest", [])}) != pack.get("pack_sha256"):
        bad.append("pack_sha256")
    return bad


def gather(vin: str, job_id: str = "") -> dict[str, Any]:
    """Collect source data from the existing services. Every source fails soft to empty."""
    from datetime import datetime
    out: dict[str, Any] = {"vin": vin, "generated_at": datetime.now().isoformat(timespec="seconds"),
                           "job": None, "symptoms": [], "dtcs": [], "freeze_frames": [], "observations": [],
                           "xref": None, "media": [], "dealer": [], "vehicle": ""}
    try:
        from mes import jobs as jobs_mod
        job = jobs_mod.get(job_id) if job_id else None
        if job is None or job.get("vin") != vin:
            job = jobs_mod.current(vin) or next(iter(reversed(jobs_mod.load(vin))), None)
        out["job"] = job
    except Exception:  # noqa: BLE001
        pass
    from . import jobs_bridge, mes_bridge
    out["symptoms"] = jobs_bridge._symptoms(vin)
    out["dealer"] = jobs_bridge._dealer_results(vin)
    try:
        out["vehicle"] = jobs_bridge._vehicle_name(vin)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["dtcs"] = list(mes_bridge.extract_dtcs(vin=vin).get("dtcs") or [])
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import path_diag
        for d in out["dtcs"][:20]:
            code = str(d.get("dtc") or "").split("-")[0]
            fr = path_diag.freeze_frames_for(vin, code)
            if fr:
                f = fr[-1]
                out["freeze_frames"].append({"code": code, "at": f.get("at") or f.get("timestamp"),
                                             "values": f.get("freeze_frame")})
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..live import store as live_store
        from . import cache
        since = str((out["job"] or {}).get("opened_at") or "")
        rows = [o for o in cache.recent_observations(n=2000, vin=vin)
                if live_store.is_from_car(o) and str(o.get("kind")) in _READING_KINDS
                and str(o.get("at") or "") >= since]
        out["observations"] = rows[-100:]
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import tsb_xref_bridge
        out["xref"] = tsb_xref_bridge.safe_xref(vin)
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import media_bridge
        out["media"] = media_bridge.list_media(vin)["items"]
    except Exception:  # noqa: BLE001
        pass
    return out
