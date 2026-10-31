"""Install or remove the invented showcase cars (Maserati Grecale, Ferrari Purosangue).

    python -m cuore.tools.demo_cars install
    python -m cuore.tools.demo_cars remove
    python -m cuore.tools.demo_cars status

Run with PYTHONPATH=mes-log-mcp. The state directory is CUORE_STATE_DIR (else the usual ProgramData
one); tests use a temporary one. Content comes from data/demo_cars/<VIN>.json.

* Every record written is tagged "demo": true (a wrapper on mes.paths.append_jsonl and the service
  store), and the car card carries "demo": true.
* install is idempotent: it removes any earlier demo records first, so running it twice leaves one set.
* remove drops every demo-tagged line (and any line for a demo VIN, or a demo job or visit, made while
  demoing) from the top-level *.jsonl stores, leaving every other line byte for byte alone, deletes the
  demo car cards, and deletes files and folders that install created. audit.jsonl is never rewritten.
  Alfa data and the real Stelvio are never touched.

It never contacts the adapter or the car and imports nothing from the consent gate, safety, transport
or live session code.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .. import bootstrap  # noqa: F401  -- puts `mes` on sys.path
from mes import demo as mes_demo
from mes import jobs as jobs_mod
from mes import paths as mes_paths
from mes import service as service_mod
from mes import symptoms as symptoms_mod

from ..live.config import state_dir
from ..services import car_identify as ci
from ..services import demo_cars

MANIFEST = "demo_cars_manifest.json"
NEVER_REWRITE = {"audit.jsonl"}


def _snapshot(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")} if root.is_dir() else set()


@contextlib.contextmanager
def _tagging() -> Iterator[None]:
    """Every record appended inside the block carries demo: true."""
    real_append, real_service = mes_paths.append_jsonl, service_mod._append

    def tagged(p: Path, entry: dict[str, Any]) -> None:
        real_append(p, {**entry, "demo": True})

    def tagged_service(entry: dict[str, Any]) -> dict[str, Any]:
        return real_service({**entry, "demo": True})

    mes_paths.append_jsonl, service_mod._append = tagged, tagged_service
    try:
        yield
    finally:
        mes_paths.append_jsonl, service_mod._append = real_append, real_service


# --- remove ------------------------------------------------------------------------------------

def _demo_ids(lines: list[bytes]) -> set[str]:
    """Ids of demo jobs and visits, so a record made while demoing (no tag, no VIN) is still found."""
    ids: set[str] = set()
    for raw in lines:
        try:
            r = json.loads(raw)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("op") in ("open", "intake") and (
                r.get("demo") is True or mes_demo.is_demo_vin(r.get("vin"))):
            for k in ("id", "job_id"):
                if r.get(k):
                    ids.add(str(r[k]))
    return ids


def _is_demo_line(raw: bytes, ids: set[str]) -> bool:
    try:
        r = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(r, dict):
        return False
    if r.get("demo") is True or mes_demo.is_demo_vin(r.get("vin")):
        return True
    return any(str(r.get(k) or "") in ids for k in ("job_id", "visit_id"))


def _purge_jsonl(path: Path, ids: set[str]) -> int:
    lines = path.read_bytes().splitlines(keepends=True)
    keep = [ln for ln in lines if not _is_demo_line(ln.strip(), ids)]
    dropped = len(lines) - len(keep)
    if dropped:
        path.write_bytes(b"".join(keep))
    return dropped


def _purge_records(root: Path) -> int:
    files = [p for p in sorted(root.glob("*.jsonl")) if p.name not in NEVER_REWRITE]
    ids: set[str] = set()
    for p in files:
        ids |= _demo_ids(p.read_bytes().splitlines())
    return sum(_purge_jsonl(p, ids) for p in files)


def remove() -> dict[str, Any]:
    root = state_dir()
    dropped = _purge_records(root)
    deleted: list[str] = []
    for vin in demo_cars.vins():
        for p in sorted(root.rglob(f"*{vin}*"), key=lambda q: len(q.parts), reverse=True):
            if p.name in NEVER_REWRITE or not p.exists():
                continue
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            deleted.append(p.relative_to(root).as_posix())
    man_path = root / MANIFEST
    try:
        created = json.loads(man_path.read_text(encoding="utf-8")).get("created", [])
    except (OSError, ValueError):
        created = []
    for rel in sorted(created, key=lambda r: r.count("/"), reverse=True):
        p = root / rel
        if p.is_file() and not (p.suffix == ".jsonl" and p.stat().st_size > 0):
            p.unlink(missing_ok=True)
            deleted.append(rel)
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
            deleted.append(rel)
    man_path.unlink(missing_ok=True)
    return {"removed_records": dropped, "deleted_files": deleted}


# --- install -----------------------------------------------------------------------------------

def _stamp(days_ago: int) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _install_car(vin: str) -> dict[str, Any]:
    d = demo_cars.load(vin) or {}
    fields = {"vin": ci.make_field(vin, ci.SRC_TYPED), "make": ci.make_field(d["make"], ci.SRC_TYPED),
              "model": ci.make_field(d["model"], ci.SRC_TYPED),
              "model_year": ci.make_field(d["model_year"], ci.SRC_TYPED)}
    res = ci.create_service(fields, d["complaint"], d["odometer_km"], technician=d["technician"])
    card = ci.get_card(vin) or {}
    card["demo"] = True
    ci._save_card(card)
    job_id = res["job_id"]
    j = d["job"]
    for s in d.get("symptoms", []):
        symptoms_mod.add(vin, datetime.now().isoformat(timespec="seconds"), odometer_km=d["odometer_km"],
                         reporter="driver", tags=s["tags"], conditions=s.get("conditions"), text=s["text"])
    for h in j["hypotheses"]:
        hyp = jobs_mod.add_hypothesis(job_id, h["text"], system=h.get("system", ""), next_test=h.get("next_test", ""),
                                      codes=h.get("codes"), likelihood=h.get("likelihood"), by=d["technician"])
        for ref in h.get("for", []):
            jobs_mod.add_evidence(job_id, hyp["id"], "for", dict(ref), by=d["technician"])
        for ref in h.get("against", []):
            jobs_mod.add_evidence(job_id, hyp["id"], "against", dict(ref), by=d["technician"])
        if h["status"] != "open":
            jobs_mod.set_hypothesis(job_id, hyp["id"], status=h["status"], by=d["technician"])
    for a in j["actions"]:
        jobs_mod.add_action(job_id, a["kind"], a["text"], event_date=_stamp(a.get("days_ago", 0)))
    marked = ""
    if j.get("fault_to_mark_fixed"):
        from ..services import fault_board
        try:
            key = next(c["key"] for c in fault_board.board(vin, job_id)
                       if str(c.get("code", "")).startswith(j["fault_to_mark_fixed"]))
            fault_board.mark_fixed(vin, key, job_id, by=d["technician"])
            marked = key
        except Exception as exc:  # noqa: BLE001 -- the demo still installs without the mark
            marked = f"not marked: {exc}"
    sr = d.get("service_record")
    if sr:
        service_mod.record_service(vin, {"date": _stamp(sr["days_ago"]), "odometer_km": sr["odometer_km"],
                                         "category": sr["category"], "work_done": sr["work_done"],
                                         "discoveries": sr.get("discoveries"),
                                         "considerations_next": sr.get("considerations_next"),
                                         "technician": d["technician"]})
    return {"vin": vin, "job_id": job_id, "marked_fixed": marked}


def install() -> dict[str, Any]:
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True)
    man_path = root / MANIFEST
    try:
        created = set(json.loads(man_path.read_text(encoding="utf-8")).get("created", []))
    except (OSError, ValueError):
        created = set()
    replaced = remove()["removed_records"]          # idempotent: never two sets
    before = _snapshot(root) - created
    with _tagging():
        cars = [_install_car(v) for v in demo_cars.vins()]
    created |= _snapshot(root) - before
    created.discard(MANIFEST)
    man_path.write_text(json.dumps({"_about": "Files and folders demo_cars install created. remove deletes them.",
                                    "created": sorted(created)}, indent=1), encoding="utf-8")
    return {"installed": cars, "state_dir": str(root), "replaced_records": replaced}


def tree_hash(root: Path) -> dict[str, str]:
    """path -> sha256 for every file under root (the test: store identical after remove)."""
    out = {}
    for p in sorted(root.rglob("*")):
        out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<dir>"
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"
    if cmd == "install":
        print(json.dumps(install(), indent=1))
    elif cmd == "remove":
        print(json.dumps(remove(), indent=1))
    elif cmd == "status":
        print(json.dumps({"state_dir": str(state_dir()), "demo_vins": demo_cars.vins(),
                          "installed": [v for v in demo_cars.vins() if ci.get_card(v)]}, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
