"""Failure-type wiring map: which modules show wiring / ground-type faults.

Every DTC ever seen for one VIN -- the MES log corpus (SCAN and FES logs,
parsed by the existing :mod:`mes` parsers, plus the copies kept under
``data/captures/<car>/mes_logs``) and CUORE's own observation store
(``module_dtcs`` and ``dtc_detail`` reads from the adapter) -- is grouped by
the FCA / ISO 14229 failure-type byte (FTB, the ``-15`` in ``B101D-15``).

Why the FTB: the base code names a circuit; the FTB says *how* it failed.
``-11`` short to ground, ``-12`` short to battery, ``-13`` open circuit,
``-14`` short to ground or open, ``-15`` short to battery or open, ``-16`` /
``-17`` voltage low / high are wiring-type faults. ``-8x`` are communication
(a message was missing or invalid, not a wire measured bad). ``-9x`` are
component / performance. Byte meanings come from :func:`mes.dtc.failure_type`
(corpus-printed or ISO-corroborated); nothing is invented here.

What is a fact and what is inference:

* FACT: a code with this FTB was reported by that module on that date.
* INFERENCE (labelled as such in the output): the **ground-suspect score**.
  Per module it is the share of that module's distinct DTC reads that were
  ``-11`` / ``-14`` / ``-16`` failures or whose freeze frame logged a low
  supply voltage. A high score points at a shared ground or feed as one
  candidate; it does not prove one. The score is meaningless on a handful of
  reads, so a module with fewer than ``MIN_READS_FOR_SCORE`` reads is flagged
  ``low_confidence``.

Counting rule: a "read" is one session. Sightings of the same module + code
within ``SESSION_GAP_MIN`` minutes (several MES files from one sitting, or a
MES log and a CUORE scan of the same hour) merge into one read, so a code is
never counted twice for one visit.

CUORE-store DTCs are counted only when the UDS status byte says the DTC is
actually set (test failed / pending / confirmed / failed since clear --
``status & 0x2F``). A status of ``0x40`` ("test not completed this cycle")
is a supported-but-never-failed entry and is ignored.

Every public function degrades to an empty result rather than raising.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path
from . import cache

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Classes, in display order.
CLASS_WIRING = "wiring"
CLASS_COMM = "communication"
CLASS_PERF = "performance"
CLASS_SIGNAL = "signal_range"
CLASS_OTHER = "other"
CLASSES = (CLASS_WIRING, CLASS_COMM, CLASS_PERF, CLASS_SIGNAL, CLASS_OTHER)

WIRING_FTBS = frozenset({"11", "12", "13", "14", "15", "16", "17"})
#: The three that feed the ground-suspect score.
GROUND_FTBS = frozenset({"11", "14", "16"})
COMM_FTBS = frozenset({"81", "82", "83", "84", "85", "86", "87", "88", "89"})
PERF_FTBS = frozenset({"92", "93", "94", "95", "96", "97", "98", "99"})
SIGNAL_FTBS = frozenset({"18", "19", "1A", "1B", "1C", "1D", "1E", "1F",
                         "21", "22", "23", "24", "25", "26", "27", "28", "29",
                         "2A", "2B", "2C", "2D", "2F"})

#: A freeze frame counts as "low supply voltage" below LOW_V_ANY, or below
#: LOW_V_RUNNING while the engine is turning. 12.0-12.1 V with the engine off
#: is a normal rested battery and is NOT flagged (several such frames exist).
LOW_V_ANY = 11.5
LOW_V_RUNNING = 12.8
RUNNING_RPM = 400.0

SESSION_GAP_MIN = 10
MIN_READS_FOR_SCORE = 3

#: UDS status bits that mean the DTC is really set (see module docstring).
_STATUS_ACTIVE_MASK = 0x2F

#: obd_dtcs reply header -> module
_HEADER_MODULE = {"18DAF110": "ECM", "18DAF118": "TCM"}

_FTB_LEGEND = [
    ("11", "short to ground"), ("12", "short to battery"), ("13", "open circuit"),
    ("14", "short to ground or open"), ("15", "short to battery or open"),
    ("16", "voltage low"), ("17", "voltage high"),
    ("1C", "out of range"), ("29", "signal invalid"), ("2F", "erratic"),
    ("86", "invalid message"), ("87", "missing message"),
    ("92", "performance"), ("96", "component internal"), ("97", "component obstructed"),
]


def classify_ftb(ftb: Optional[str]) -> str:
    f = (ftb or "").upper()
    if f in WIRING_FTBS:
        return CLASS_WIRING
    if f in COMM_FTBS:
        return CLASS_COMM
    if f in PERF_FTBS:
        return CLASS_PERF
    if f in SIGNAL_FTBS:
        return CLASS_SIGNAL
    return CLASS_OTHER


def _mod():
    """The ``mes`` pieces this module needs, or ``None`` if the package is unusable."""
    try:
        from mes import catalog, dtc, dtc_descriptions, fes, modules, paths, scan
        return {"catalog": catalog, "dtc": dtc, "desc": dtc_descriptions, "fes": fes,
                "modules": modules, "paths": paths, "scan": scan}
    except Exception:  # noqa: BLE001 -- must never be why a page 500s
        return None


# --- module naming ---------------------------------------------------------

_FES_KEYWORDS = (
    ("abs", "ABS"), ("body computer", "BCM"), ("iaw", "ECM"), ("injection", "ECM"),
    ("transfer case", "DTCM"), ("instrument", "IPC"), ("cluster", "IPC"),
    ("gearbox", "TCM"), ("transmission", "TCM"), ("airbag", "ORC"),
    ("steering", "EPS"),
)


def _module_from_fes(ecu_description: str) -> str:
    low = (ecu_description or "").lower()
    for kw, name in _FES_KEYWORDS:
        if kw in low:
            return name
    return ecu_description or "unknown"


def _module_from_abbrev(abbrev: str, mods: Any) -> str:
    try:
        norm = mods.normalize_abbrev(abbrev)
    except Exception:  # noqa: BLE001
        norm = None
    return norm or abbrev or "unknown"


# --- time helpers -------------------------------------------------------------

def _parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).strip().replace(" ", "T")
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


# --- sighting collection -----------------------------------------------------------

def _split_full(full: str) -> tuple[str, str]:
    code, _, ftb = (full or "").strip().upper().partition("-")
    return code, ftb


def _sighting(module: str, full: str, ts: Optional[datetime], source: str, *,
              description: str = "", voltage: Optional[float] = None,
              rpm: Optional[float] = None, status: str = "") -> Optional[dict[str, Any]]:
    code, ftb = _split_full(full)
    if len(code) != 5 or ts is None:
        return None
    return {"module": module, "code": code, "ftb": ftb, "ts": ts, "source": source,
            "description": description, "voltage": voltage, "rpm": rpm, "status": status}


def _low_voltage(voltage: Optional[float], rpm: Optional[float]) -> bool:
    if voltage is None:
        return False
    if voltage < LOW_V_ANY:
        return True
    return rpm is not None and rpm > RUNNING_RPM and voltage < LOW_V_RUNNING


def _mes_sightings(vin: str, m: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Sightings from every real (non-simulated) MES log of this VIN."""
    catalog, fes_mod, scan_mod, paths = m["catalog"], m["fes"], m["scan"], m["paths"]
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    files = 0

    def handle(path: Path, kind: str, ts: Optional[datetime], name: str) -> None:
        nonlocal files
        try:
            if kind == "scan":
                log = scan_mod.load_scan(path, timestamp=str(ts or ""))
                if vin and vin not in (log.vin or "").upper():
                    return
                files += 1
                rows = []
                for entry in list(log.modules) + list(log.post_clear_modules):
                    mod = _module_from_abbrev(entry.abbrev, m["modules"])
                    for d in entry.dtcs:
                        rows.append((mod, d, None, None))
            else:
                log = fes_mod.load_fes(path, timestamp=str(ts or ""))
                if log.simulation or (vin and vin not in (log.vin or "").upper()):
                    return
                files += 1
                mod = _module_from_fes(log.ecu_description)
                rows = []
                for d in log.dtcs:
                    v = d.freeze("Battery voltage")
                    r = d.freeze("Engine speed")
                    rows.append((mod, d, v.number if v else None, r.number if r else None))
        except Exception:  # noqa: BLE001 -- one corrupt log must not sink the map
            return
        for mod, d, volt, rpm in rows:
            s = _sighting(mod, d.full, ts, f"mes:{name}", description=d.description or "",
                          voltage=volt, rpm=rpm, status=d.status.value)
            if s:
                out.append(s)

    for e in catalog.CATALOG.select(vin=vin):          # configured roots + CUORE exports
        seen_names.add(e.name.lower())
        if e.parse_error:
            continue
        handle(e.path, e.kind, e.stamp, e.name)

    # Repo copies of the car's logs (the MES install can be wiped or moved).
    for d in sorted((REPO_ROOT / "data" / "captures").glob("*/mes_logs")):
        for p in sorted(d.glob("*.txt")):
            if p.name.lower() in seen_names:
                continue
            kind, raw, _veh = paths.classify_name(p.name)
            if kind not in ("scan", "fes"):
                continue
            seen_names.add(p.name.lower())
            handle(p, kind, catalog.parse_stamp(raw), p.name)
    return out, files


def _store_sightings(vin: str) -> tuple[list[dict[str, Any]], int]:
    """Sightings from CUORE's observation store (real serial reads only)."""
    try:
        from ..live import store
        rows = store.recent_observations(10 ** 9, vin=vin)
        from_car = store.is_from_car
    except Exception:  # noqa: BLE001
        return [], 0
    out: list[dict[str, Any]] = []
    n = 0

    def active(status: Any) -> bool:
        return isinstance(status, int) and bool(status & _STATUS_ACTIVE_MASK)

    for o in rows:
        if not from_car(o):
            continue
        ts = _parse_ts(o.get("at"))
        data = o.get("data") or {}
        kind = o.get("kind")
        found: list[tuple[str, str]] = []
        if kind == "module_dtcs":
            for d in data.get("dtcs") or []:
                if active(d.get("status")):
                    found.append((data.get("ecu") or "unknown", d.get("code") or ""))
        elif kind == "dtc_detail":
            if active(data.get("status")):
                found.append((data.get("ecu") or "unknown", data.get("dtc") or ""))
        elif kind == "obd_dtcs":
            for hdr, codes in (data.get("by_ecu") or {}).items():
                for c in codes or []:
                    found.append((_HEADER_MODULE.get(hdr, hdr), f"{c}-00" if "-" not in c else c))
        else:
            continue
        n += 1
        for mod, full in found:
            s = _sighting(mod, full, ts, "cuore")
            if s:
                out.append(s)
    return out, n


# --- aggregation ------------------------------------------------------------------

def _reads(sightings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge sightings of one module+code into sessions (see module docstring).

    Each read keeps the date, the lowest freeze-frame voltage seen in it (with
    the rpm at that moment) and whether any sighting in it was a low-voltage frame.
    """
    reads: list[dict[str, Any]] = []
    gap = timedelta(minutes=SESSION_GAP_MIN)
    for s in sorted(sightings, key=lambda x: x["ts"]):
        if reads and s["ts"] - reads[-1]["last_ts"] <= gap:
            r = reads[-1]
            r["last_ts"] = s["ts"]
            r["sources"].add(s["source"].split(":")[0])
        else:
            r = {"first_ts": s["ts"], "last_ts": s["ts"], "sources": {s["source"].split(":")[0]},
                 "low_v": None, "frame_v": None}
            reads.append(r)
        if s["voltage"] is not None:
            if r["frame_v"] is None or s["voltage"] < r["frame_v"]:
                r["frame_v"] = s["voltage"]
            if _low_voltage(s["voltage"], s["rpm"]):
                r["low_v"] = s["voltage"] if r["low_v"] is None else min(r["low_v"], s["voltage"])
    return reads


def _describe(m: Optional[dict[str, Any]], code: str, sights: list[dict[str, Any]]) -> str:
    for s in sights:
        if s["description"]:
            return s["description"]
    if m is not None:
        try:
            d = m["desc"].code_description(code)
            if d.get("confidence", "UNKNOWN") != "UNKNOWN":
                return d.get("text", "")
        except Exception:  # noqa: BLE001
            pass
    return ""


def _ftb_text(m: Optional[dict[str, Any]], ftb: str) -> str:
    if m is None or not ftb:
        return ""
    try:
        ft = m["dtc"].failure_type(ftb)
        return ft.text if ft else ""
    except Exception:  # noqa: BLE001
        return ""


def _build(vin: str) -> dict[str, Any]:
    m = _mod()
    mes_s, mes_files = _mes_sightings(vin, m) if m else ([], 0)
    store_s, store_obs = _store_sightings(vin)
    sightings = mes_s + store_s

    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for s in sightings:
        by_key.setdefault((s["module"], s["code"], s["ftb"]), []).append(s)

    modules: dict[str, dict[str, Any]] = {}
    for (mod, code, ftb), sights in by_key.items():
        reads = _reads(sights)
        cls = classify_ftb(ftb)
        dates = sorted({r["first_ts"].date().isoformat() for r in reads})
        low = [r["low_v"] for r in reads if r["low_v"] is not None]
        row = {
            "code": f"{code}-{ftb}" if ftb else code, "circuit": code, "ftb": ftb,
            "ftb_text": _ftb_text(m, ftb), "class": cls, "reads": len(reads),
            "dates": dates, "first_seen": dates[0], "last_seen": dates[-1],
            "description": _describe(m, code, sights),
            "ground_type": ftb in GROUND_FTBS,
            "low_voltage_reads": len(low),
            "min_frame_voltage": min((r["frame_v"] for r in reads if r["frame_v"] is not None),
                                     default=None),
            "sources": sorted({src for r in reads for src in r["sources"]}),
        }
        g = modules.setdefault(mod, {"module": mod, "circuits": [], "_ground_reads": 0,
                                     "_low_v_only": 0, "_reads": 0})
        g["circuits"].append(row)
        g["_reads"] += len(reads)
        for r in reads:
            if ftb in GROUND_FTBS:
                g["_ground_reads"] += 1
            elif r["low_v"] is not None:
                g["_low_v_only"] += 1

    out_modules: list[dict[str, Any]] = []
    for mod, g in modules.items():
        circuits = sorted(g["circuits"], key=lambda r: (CLASSES.index(r["class"]), -r["reads"], r["code"]))
        counts = {c: {"circuits": 0, "reads": 0} for c in CLASSES}
        for r in circuits:
            counts[r["class"]]["circuits"] += 1
            counts[r["class"]]["reads"] += r["reads"]
        total = g["_reads"]
        events = g["_ground_reads"] + g["_low_v_only"]
        low_conf = total < MIN_READS_FOR_SCORE
        out_modules.append({
            "module": mod,
            "reads": total,
            "classes": counts,
            "ground_suspect": {
                "score": round(events / total, 2) if total else 0.0,
                "ground_type_reads": g["_ground_reads"],
                "low_voltage_frame_reads": g["_low_v_only"],
                "of_reads": total,
                "low_confidence": low_conf,
                "label": "inference",
            },
            "circuits": circuits,
        })
    # Highest score first; a low-confidence score is still shown (it can be the only lead
    # a car has) but carries its flag. Ties: more wiring-class reads, then more reads.
    out_modules.sort(key=lambda x: (-x["ground_suspect"]["score"],
                                    -x["classes"][CLASS_WIRING]["reads"], -x["reads"], x["module"]))

    low_frames = sorted(
        ({"module": mod, "code": f"{code}-{ftb}" if ftb else code,
          "voltage": r["low_v"], "date": r["first_ts"].date().isoformat()}
         for (mod, code, ftb), sights in by_key.items()
         for r in _reads(sights) if r["low_v"] is not None),
        key=lambda x: (x["date"], x["module"]))

    return {
        "vin": vin,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "sources": {"mes_logs_parsed": mes_files, "cuore_observations_read": store_obs,
                    "dtc_sightings": len(sightings)},
        "rules": {
            "read": f"sightings of one module+code within {SESSION_GAP_MIN} min merge into one read",
            "ground_suspect": ("INFERENCE: (reads that were -11/-14/-16, plus other reads whose freeze "
                               f"frame logged supply < {LOW_V_ANY} V, or < {LOW_V_RUNNING} V with the "
                               f"engine above {int(RUNNING_RPM)} rpm) / all reads of that module; "
                               f"flagged low_confidence under {MIN_READS_FOR_SCORE} reads"),
            "cuore_store": "only DTCs whose UDS status & 0x2F is non-zero (really set) are counted",
        },
        "ftb_legend": [{"ftb": b, "meaning": t} for b, t in _FTB_LEGEND],
        "low_voltage_frames": low_frames,
        "modules": out_modules,
    }


def _cache_key(vin: str) -> tuple:
    mt = 0.0
    try:
        from . import mes_bridge
        mt = mes_bridge.newest_mtime(vin)
    except Exception:  # noqa: BLE001
        pass
    obs = 0.0
    try:
        from ..live import store
        obs = store.observations_path().stat().st_mtime
    except Exception:  # noqa: BLE001
        pass
    return ("wiring", vin, mt, obs)


def wiring_map(vin: str) -> dict[str, Any]:
    """The failure-type wiring map for ``vin`` (cached on corpus + store mtime)."""
    vin = (vin or "").strip().upper()
    try:
        return cache.get_or_build(_cache_key(vin), lambda: _build(vin))
    except Exception as exc:  # noqa: BLE001 -- a page must still render
        return {"vin": vin, "modules": [], "error": f"{type(exc).__name__}: {exc}",
                "sources": {}, "rules": {}, "ftb_legend": []}


def flat_table(vin: str) -> list[dict[str, Any]]:
    """One row per module: reads, per-class read counts, score. For the dossier table / reports."""
    rows = []
    for mod in wiring_map(vin).get("modules", []):
        c = mod["classes"]
        wiring = [r for r in mod["circuits"] if r["class"] == CLASS_WIRING]
        rows.append({
            "module": mod["module"], "reads": mod["reads"],
            "wiring": c[CLASS_WIRING]["reads"], "communication": c[CLASS_COMM]["reads"],
            "performance": c[CLASS_PERF]["reads"], "signal_range": c[CLASS_SIGNAL]["reads"],
            "other": c[CLASS_OTHER]["reads"],
            "ground_score": mod["ground_suspect"]["score"],
            "low_confidence": mod["ground_suspect"]["low_confidence"],
            "wiring_codes": ", ".join(f"{r['code']} x{r['reads']}" for r in wiring),
        })
    return rows


__all__ = ["wiring_map", "flat_table", "classify_ftb", "WIRING_FTBS", "GROUND_FTBS",
           "COMM_FTBS", "PERF_FTBS"]
