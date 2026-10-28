"""Decoding confirmation: pair a MultiEcuScan (MES) recording with a CUORE live-session
recording by time and value, and say per CUORE channel whether its decoding is right.

Read-only and offline: both inputs are files, nothing here talks to the car or an adapter.

Inputs
  * MES: a graph CSV recording (``Time`` in seconds, per-sample timing) or the ``FESLog_*.txt``
    session log (no per-sample timestamps in the format, so ``mes_interval_s`` is required and the
    spacing is an assumption, reported as such).
  * CUORE: a ``live_*.csv`` made by the live-session recorder (same MES graph-CSV shape; its
    file name carries the start time).

Pairing: ``cuore/data/mes_param_aliases.json`` names which MES parameter is which CUORE channel
(``certain`` = same quantity and unit by name, ``candidate`` = ranked by value agreement only).
Clocks: each recording starts at its own instant; the start times are taken from the file names
or mtimes, and a lag is then searched on engine speed (the one certain pair every session has)
so a few seconds of clock difference do not matter. Samples pair when within ``PAIR_WINDOW_S``.

Verdict per channel (rules in :func:`_verdict`):
  confirmed    best transform is the identity (units converted where the unit differs) and agrees
  wrong_scale  a different transform agrees and the identity does not; it is proposed, not applied
  no_data      fewer than ``MIN_PAIRS`` paired numeric samples, or a column is missing
  ambiguous    nothing agrees, MES never moved, or two transforms/MES names fit equally

Nothing is changed by a run. :func:`accept` writes the owner's decision to the state override
file ``did_overrides.json`` which ``did_catalog`` reads at load time.
"""

from __future__ import annotations

import bisect
import json
import re
import statistics
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir
from .errors import BadCommand
from .ui_store import atomic_write_text

ALIASES_PATH = Path(__file__).resolve().parents[1] / "data" / "mes_param_aliases.json"
PAIR_WINDOW_S = 2.0
MIN_PAIRS = 5
FIT_FRACTION = 0.9          # share of pairs that must agree for a transform to "fit"
TIE_MARGIN = 0.05
DEFAULT_TOLERANCE = 0.05
MAX_LAG_S = 60.0
STATIC_SKIP_S = 3.0
_LOCK = threading.Lock()

#: (CUORE unit, MES unit) -> multiplier. Only exact, standard conversions.
_UNIT_FACTORS = {("bar", "mbar"): 1000.0, ("mbar", "bar"): 0.001, ("kpa", "mbar"): 10.0,
                 ("mbar", "kpa"): 0.1, ("kpa", "bar"): 0.01, ("bar", "kpa"): 100.0,
                 ("pa", "kpa"): 0.001, ("g/s", "kg/h"): 3.6, ("kg/h", "g/s"): 1 / 3.6}


def _unorm(u: str) -> str:
    t = (u or "").strip().lower().replace("°", "").replace("deg.", "deg")
    return {"degc": "c", "": ""}.get(t, t)


# --- data files -------------------------------------------------------------------

def _dir() -> Path:
    return state_dir() / "decode_confirm"


def load_aliases() -> dict[str, Any]:
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


def _num(text: Any) -> Optional[float]:
    t = str(text).strip().strip('"').strip()
    if not t:
        return None
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


# --- loading the two recordings into {(name_lower, unit): [(t, value)]} ---------------

def _stamp_from_name(path: Path) -> Optional[datetime]:
    m = re.search(r"(\d{8})-(\d{6})", path.stem)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            return None
    m = re.search(r"FESLog_(\d{10})", path.stem)
    if m:
        try:
            return datetime.strptime(m.group(1), "%y%m%d%H%M")
        except ValueError:
            return None
    return None


_TAG_NO = re.compile(r"^\s*(?:tag\s*)?(\d)\b", re.IGNORECASE)


def _segments(rec: Any) -> dict[int, list[tuple[float, float]]]:
    """{tag number: [(start_s, end_s)]}: a segment runs from the row where the TAG cell first shows
    that number until the next row showing a different number (CUORE writes "TAG n: label", MES's
    TAG column holds the tag it inserted; a cell without a leading number is ignored)."""
    out: dict[int, list[tuple[float, float]]] = {}
    cur, start = None, 0.0
    for t, row in zip(rec.times, rec.rows):
        m = _TAG_NO.match(row[-1].strip().strip('"')) if row else None
        if m and int(m.group(1)) != cur:
            if cur is not None:
                out.setdefault(cur, []).append((start, t))
            cur, start = int(m.group(1)), t
    if cur is not None:
        out.setdefault(cur, []).append((start, float("inf")))
    return out


def _load_csv_series(path: Path, lower: bool = True) -> tuple[dict[tuple[str, str], list[tuple[float, float]]], dict[str, Any]]:
    from .. import bootstrap  # noqa: F401 -- side effect: mes on sys.path
    from mes import csvlog
    rec = csvlog.load_csv(path)
    if not rec.columns or not rec.times:
        raise BadCommand(f"{path.name}: no samples")
    out: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for col in rec.columns:
        pts = []
        for t, row in zip(rec.times, rec.rows):
            v = _num(row[col.index]) if col.index < len(row) else None
            if v is not None:
                pts.append((t, v))
        out[(col.name.strip().lower() if lower else col.name.strip(), _unorm(col.unit))] = pts
    return out, {"kind": "csv", "duration_s": rec.times[-1] - rec.times[0], "samples": len(rec.times),
                 "segments": _segments(rec)}


def _load_fes_series(path: Path, interval_s: float) -> tuple[dict[tuple[str, str], list[tuple[float, float]]], dict[str, Any]]:
    from .. import bootstrap  # noqa: F401
    from mes import fes
    log = fes.load_fes(path)
    if not log.samples:
        raise BadCommand(f"{path.name}: this MES session logged no live parameters")
    out: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for i, s in enumerate(log.samples):
        for v in s.values:
            if v.number is not None:
                k = (v.name.strip().lower(), _unorm(v.unit))
                out.setdefault(k, []).append((i * interval_s, v.number))
    return out, {"kind": "fes_text", "duration_s": (len(log.samples) - 1) * interval_s,
                 "samples": len(log.samples),
                 "timing_note": f"assumed uniform spacing of {interval_s:g} s: the text log has no per-sample times"}


def _is_csv(path: Path) -> bool:
    head = path.read_bytes()[:400]
    text = head.decode("utf-16", "ignore") if head[:2] in (b"\xff\xfe", b"\xfe\xff") else head.decode("utf-8", "ignore")
    return text.lstrip("\ufeff \t\"").lower().startswith("time")


def _load_mes(path: Path, interval_s: Optional[float]):
    head = path.read_bytes()[:400]
    text = head.decode("utf-16", "ignore") if head[:2] in (b"\xff\xfe", b"\xfe\xff") else head.decode("utf-8", "ignore")
    if text.lstrip("﻿ \t\"").lower().startswith("time"):
        return _load_csv_series(path)
    if not interval_s or interval_s <= 0:
        raise BadCommand("this MES file is a text session log with no per-sample timestamps: pass "
                         "mes_interval_s (seconds between 'READING PARAMETERS' blocks), or record "
                         "MES's graph CSV instead")
    return _load_fes_series(path, float(interval_s))


# --- pairing -------------------------------------------------------------------------

def _pair(cu: list[tuple[float, float]], me: list[tuple[float, float]], shift: float
          ) -> list[tuple[float, float, float]]:
    """[(cuore value, mes value, mes time)]: each MES sample (time + shift, on the CUORE clock) with
    the nearest CUORE sample inside PAIR_WINDOW_S."""
    ct = [t for t, _ in cu]
    out = []
    for tm, y in me:
        tc = tm + shift
        i = bisect.bisect_left(ct, tc)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(ct) and abs(ct[j] - tc) <= PAIR_WINDOW_S and (best is None or abs(ct[j] - tc) < abs(ct[best] - tc)):
                best = j
        if best is not None:
            out.append((cu[best][1], y, tm))
    return out


def _best_lag(cu: list[tuple[float, float]], me: list[tuple[float, float]], base: float, max_lag: float
              ) -> tuple[float, Optional[float]]:
    """Lag (added to ``base``) that makes engine speed agree best; (0.0, None) when it cannot be judged."""
    ys = [y for _, y in me]
    xs = [x for _, x in cu]
    if not ys or not xs or max(ys) - min(ys) < 300 or max(xs) - min(xs) < 300:
        return 0.0, None
    best = (None, 0.0)
    steps = int(max_lag / 0.5)
    for k in range(-steps, steps + 1):
        lag = k * 0.5
        pr = _pair(cu, me, base + lag)
        if len(pr) < MIN_PAIRS:
            continue
        err = sum(abs(x - y) for x, y, _ in pr) / len(pr)
        if best[0] is None or err < best[0] - 1e-9 or (abs(err - best[0]) <= 1e-9 and abs(lag) < abs(best[1])):
            best = (err, lag)
    return (best[1], best[0]) if best[0] is not None else (0.0, None)


def _static_pairs(cu, me, cseg, mseg, skip_s: float = STATIC_SKIP_S) -> list[tuple[float, float, float]]:
    """[(CUORE median, MES median, tag)] per tag present in both files; each tag's rows start
    ``skip_s`` after the tag and end at the next tag."""
    def med(pts, segs):
        v = [x for t, x in pts if any(a + skip_s <= t < b for a, b in segs)]
        return statistics.median(v) if v else None
    out = []
    for n in sorted(set(cseg) & set(mseg)):
        x, y = med(cu, cseg[n]), med(me, mseg[n])
        if x is not None and y is not None:
            out.append((x, y, float(n)))
    return out


# --- transforms ---------------------------------------------------------------------

def _linear(formula: str) -> Optional[tuple[float, float]]:
    """(m, c) with decoded = raw*m + c for a one/two-byte catalogue formula, else None."""
    if not formula or re.search(r"[C-P]", re.sub(r"SIGNED", "", formula)):
        return None
    try:
        from .readall import eval_formula
        two = "B" in formula
        f = lambda raw: eval_formula(formula, [raw // 256, raw % 256] if two else [raw, 0])  # noqa: E731
        c, m = f(0), f(1) - f(0)
        if not isinstance(c, float) and not isinstance(c, int):
            return None
        if abs(f(2) - c - 2 * m) > 1e-9 * max(1.0, abs(m)) or m == 0:
            return None
        return float(m), float(c)
    except Exception:  # noqa: BLE001 - not a plain linear formula: no raw-based variants
        return None


def _transforms(ch_unit: str, mes_unit: str, formula: str, also: list[str]) -> list[dict[str, Any]]:
    """Candidate y = a*x + b maps from the CUORE decoded value x to MES units. Only these exist:
    identity (with a standard unit conversion when units differ), /10, /100, the catalogue's own
    offset dropped / raw counts (only when its formula names an offset), and raw/100 degrees (only
    when the alias lists "degrees")."""
    cu, me = _unorm(ch_unit), _unorm(mes_unit)
    uf = 1.0 if cu == me else _UNIT_FACTORS.get((cu, me))
    note = "" if uf is not None else f"units differ ({ch_unit or '-'} vs {mes_unit or '-'}), no conversion applied"
    uf = uf if uf is not None else 1.0
    T = [{"name": "identity", "a": uf, "b": 0.0, "unit": mes_unit, "note": note},
         {"name": "divide_by_10", "a": uf / 10, "b": 0.0, "unit": mes_unit, "note": note},
         {"name": "divide_by_100", "a": uf / 100, "b": 0.0, "unit": mes_unit, "note": note}]
    lin = _linear(formula)
    if lin:
        m, c = lin
        if abs(c) > 1e-12:
            T.append({"name": "offset_dropped", "a": uf, "b": -c * uf, "unit": mes_unit,
                      "note": f"the catalogue offset ({c:g}) removed"})
            T.append({"name": "raw_counts", "a": 1 / m, "b": -c / m, "unit": mes_unit,
                      "note": "unscaled unsigned raw integer, no offset (as the 195A fix)"})
        if "degrees" in also:
            T.append({"name": "raw_over_100_degrees", "a": 1 / (m * 100), "b": -c / (m * 100), "unit": "deg",
                      "note": "raw/100, read as degrees"})
    out: list[dict[str, Any]] = []
    for t in T:      # two names for the same map (e.g. offset dropped + bar->mbar == raw counts) must not tie
        if not any(abs(t["a"] - o["a"]) <= 1e-9 * abs(o["a"]) and abs(t["b"] - o["b"]) <= 1e-9 * (abs(o["b"]) + 1)
                   and t["unit"] == o["unit"] for o in out):
            out.append(t)
    return out


def _fit(pairs: list[tuple[float, float, float]], T: dict[str, Any], tol: float) -> dict[str, Any]:
    ys = [y for _, y, _ in pairs]
    span = max(ys) - min(ys)
    ref = max(span, statistics.median(abs(y) for y in ys))
    err = [abs(T["a"] * x + T["b"] - y) for x, y, _ in pairs]
    allowed = tol * ref
    return {"transform": T, "fit": sum(e <= allowed for e in err) / len(err),
            "residual": (statistics.median(err) / ref) if ref else None}


def _verdict(pairs: list[tuple[float, float, float]], T: list[dict[str, Any]], tol: float,
             min_pairs: int = MIN_PAIRS, min_distinct: int = 3, fit_frac: float = FIT_FRACTION,
             unit_word: str = "paired samples") -> dict[str, Any]:
    """The rules, in order: no_data (< MIN_PAIRS) / ambiguous (MES never moved) / ambiguous (nothing
    reaches FIT_FRACTION) / ambiguous (a second transform within TIE_MARGIN) / confirmed (identity)
    / wrong_scale (another transform)."""
    n = len(pairs)
    if n < min_pairs:
        return {"verdict": "no_data", "samples": n, "reason": f"{n} {unit_word} (< {min_pairs})"}
    ys = [y for _, y, _ in pairs]
    if len(set(ys)) < min_distinct or max(ys) == min(ys):
        return {"verdict": "ambiguous", "samples": n, "reason": f"MES value did not move (fewer than {min_distinct} "
                "distinct values): any transform could match; vary the quantity"}
    fits = sorted((_fit(pairs, t, tol) for t in T),
                  key=lambda f: (-f["fit"], f["residual"] if f["residual"] is not None else 9e9))
    best = fits[0]
    ident = next(f for f in fits if f["transform"]["name"] == "identity")
    base = {"samples": n, "fit": round(best["fit"], 3), "residual": best["residual"],
            "transform": best["transform"], "identity_fit": round(ident["fit"], 3)}
    if best["fit"] < fit_frac:
        return {**base, "verdict": "ambiguous", "reason": f"no tested transform fits (best {best['transform']['name']} "
                f"agrees on {best['fit']:.0%} of pairs)"}
    rivals = [f for f in fits[1:] if f["fit"] >= best["fit"] - TIE_MARGIN and f["fit"] >= fit_frac]
    if rivals:
        return {**base, "verdict": "ambiguous", "reason": "equal fit: " + ", ".join(
            [best["transform"]["name"]] + [r["transform"]["name"] for r in rivals])}
    if best["transform"]["name"] == "identity":
        return {**base, "verdict": "confirmed", "reason": f"decoded value agrees with MES on {best['fit']:.0%} of pairs"}
    return {**base, "verdict": "wrong_scale",
            "reason": f"identity agrees on {ident['fit']:.0%}, {best['transform']['name']} on {best['fit']:.0%}"}


# --- run ----------------------------------------------------------------------------

def run(vin: str, mes_log_path: str, cuore_recording_path: str, tolerance: float = DEFAULT_TOLERANCE,
        mes_interval_s: Optional[float] = None, mes_start: str = "", lag_s: Optional[float] = None,
        max_lag_s: float = MAX_LAG_S, mode: str = "static") -> dict[str, Any]:
    """Compare the two recordings and return (and save) a verdict per aliased CUORE channel.

    ``mode="static"`` (default; one adapter, so the logs are made one after the other): both files
    are cut by tag number (1 ignition on/engine off/pedal up, 2 same/pedal fully down, 3 warm idle,
    4 optional steady 2000 rpm), the first 3 s of each tag dropped, the median per channel compared
    per condition. Confirmed needs agreement in every condition with data, at least 2; throttle
    candidates need tags 1 and 2. ``mode="timestamp"``: row-by-row pairing by time (graph CSVs)."""
    if mode not in ("static", "timestamp"):
        raise BadCommand("mode must be 'static' or 'timestamp'")
    from .channels import registry
    mp, cp = Path(mes_log_path), Path(cuore_recording_path)
    for p in (mp, cp):
        if not p.is_file():
            raise BadCommand(f"file not found: {p}")
    if not 0 < tolerance < 1:
        raise BadCommand("tolerance must be between 0 and 1 (relative, 0.05 = 5 %)")
    static = mode == "static"
    if static and not _is_csv(mp):
        me_all, me_meta = {}, {"kind": "fes_text", "duration_s": 0.0, "segments": {}}
    else:
        me_all, me_meta = _load_mes(mp, mes_interval_s)
    cu_all, cu_meta = _load_csv_series(cp, lower=False)   # exact case: "Engine RPM" (DID) != "engine rpm" (PID)

    # clocks
    notes: list[str] = []
    c0 = _stamp_from_name(cp)
    if c0 is None:
        c0 = datetime.fromtimestamp(cp.stat().st_mtime - cu_meta["duration_s"])
        notes.append("CUORE start taken from file mtime (no stamp in the file name)")
    if mes_start:
        try:
            m0 = datetime.fromisoformat(mes_start)
        except ValueError:
            raise BadCommand("mes_start must be an ISO time, e.g. 2026-11-02T10:03:00") from None
    else:
        m0 = _stamp_from_name(mp)
        if m0 is None or me_meta["kind"] == "csv":
            m0 = datetime.fromtimestamp(mp.stat().st_mtime - me_meta["duration_s"])
            notes.append("MES start taken from file mtime minus duration")
        else:
            notes.append("MES start taken from the log file name (minute resolution)")
    base = (m0 - c0).total_seconds()

    aliases = load_aliases()
    reg = registry()
    by_ch: dict[str, list[dict[str, Any]]] = {}
    for a in aliases["pairs"]:
        by_ch.setdefault(a["channel"], []).append(a)

    def cuore_series(cid: str) -> list[tuple[float, float]]:
        ch = reg.get(cid)
        return cu_all.get((ch.name.strip(), _unorm(ch.unit)), []) if ch else []

    def mes_series(a: dict[str, Any]) -> list[tuple[float, float]]:
        want, wu = a["mes_name"].strip().lower(), _unorm(a.get("mes_unit", ""))
        return me_all.get((want, wu), [])

    # engine speed lag
    lag, lag_src, lag_err = 0.0, "clock", None
    if static:
        lag_src = "none (static)"
    elif lag_s is not None:
        lag, lag_src = float(lag_s), "given"
    else:
        for a in by_ch.get("engine_rpm", []):
            cu, me = cuore_series("engine_rpm"), mes_series(a)
            if cu and me:
                l, e = _best_lag(cu, me, base, max_lag_s)
                if e is not None:
                    lag, lag_src, lag_err = l, "engine_speed", e
                break
    shift = base + lag

    channels: list[dict[str, Any]] = []
    for cid, entries in by_ch.items():
        ch = reg.get(cid)
        if ch is None:
            continue
        cu = cuore_series(cid)
        results = []
        for a in entries:
            me = mes_series(a)
            cseg, mseg = cu_meta.get("segments", {}), me_meta.get("segments", {})
            if static and not (cseg and mseg):
                r = {"verdict": "no_data", "samples": 0, "reason": "no tags" + (
                    " in the MES log" if not mseg else " in the CUORE recording")}
            elif not cu:
                r = {"verdict": "no_data", "samples": 0, "reason": "CUORE recording has no column for this channel"}
            elif not me:
                r = {"verdict": "no_data", "samples": 0, "reason": f"MES recording has no numeric '{a['mes_name']}'"}
            elif static:
                sp = _static_pairs(cu, me, cseg, mseg)
                T = _transforms(ch.unit, a.get("mes_unit", ""), ch.formula, a.get("also_try", []))
                if "degrees" in a.get("also_try", []) and not {1.0, 2.0} <= {p[2] for p in sp}:
                    r = {"verdict": "no_data", "samples": len(sp),
                         "reason": "throttle candidates need tags 1 and 2 in both files"}
                else:
                    r = _verdict(sp, T, tolerance, min_pairs=2, min_distinct=2, fit_frac=1.0,
                                 unit_word="conditions with data")
            else:
                r = _verdict(_pair(cu, me, shift), _transforms(ch.unit, a.get("mes_unit", ""), ch.formula,
                                                              a.get("also_try", [])), tolerance)
            results.append({**r, "mes_name": a["mes_name"], "mes_unit": a.get("mes_unit", ""),
                            "pairing": a["certainty"]})
        rank = lambda r: (r["pairing"] != "certain", r["verdict"] == "no_data", -(r.get("fit") or 0),  # noqa: E731
                          r.get("residual") if r.get("residual") is not None else 9e9)
        results.sort(key=rank)
        top, alts = results[0], results[1:]
        if top["pairing"] == "candidate" and alts and alts[0]["pairing"] == "candidate" \
                and top["verdict"] in ("confirmed", "wrong_scale") and alts[0]["verdict"] in ("confirmed", "wrong_scale") \
                and (alts[0].get("fit") or 0) >= (top.get("fit") or 0) - TIE_MARGIN:
            top = {**top, "verdict": "ambiguous",
                   "reason": f"two MES names fit equally: '{top['mes_name']}' and '{alts[0]['mes_name']}'"}
        spec_status = ch.confidence
        channels.append({"channel": cid, "name": ch.name, "unit": ch.unit, "current_confidence": spec_status,
                         "alternatives": [{k: v for k, v in r.items() if k in
                                           ("mes_name", "verdict", "fit", "samples", "pairing")} for r in alts],
                         **top})
    for u in aliases.get("unpaired", []):
        ch = reg.get(u["channel"])
        channels.append({"channel": u["channel"], "name": ch.name if ch else u["channel"], "unit": ch.unit if ch else "",
                         "current_confidence": ch.confidence if ch else "", "verdict": "no_data", "samples": 0,
                         "pairing": "none", "reason": u["reason"], "alternatives": []})

    summary: dict[str, int] = {}
    for c in channels:
        summary[c["verdict"]] = summary.get(c["verdict"], 0) + 1
    with _LOCK:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        n = 1
        while (d / f"{run_id}.json").exists():
            n += 1
            run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{n}"
        rec = {"run_id": run_id, "vin": vin, "at": datetime.now().isoformat(timespec="seconds"),
               "mes_log": str(mp), "cuore_recording": str(cp), "tolerance": tolerance, "mode": mode,
               "tags": {"mes": sorted(me_meta.get("segments", {})), "cuore": sorted(cu_meta.get("segments", {}))},
               "timing": {"cuore_start": c0.isoformat(), "mes_start": m0.isoformat(), "lag_s": lag, "lag_source": lag_src,
                          "lag_residual_rpm": lag_err, "pair_window_s": PAIR_WINDOW_S, "notes": notes,
                          **({"mes_note": me_meta["timing_note"]} if me_meta.get("timing_note") else {})},
               "summary": summary, "channels": channels, "accepted": []}
        atomic_write_text(d / f"{run_id}.json", json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


def list_runs(vin: str = "") -> dict[str, Any]:
    """Saved runs, newest first (summary only; use :func:`get_run` for the channels)."""
    out = []
    for p in sorted(_dir().glob("*.json"), reverse=True) if _dir().is_dir() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if vin and r.get("vin") and r["vin"].upper() != vin.upper():
            continue
        out.append({k: r.get(k) for k in ("run_id", "vin", "at", "mes_log", "cuore_recording", "summary", "accepted")})
    return {"runs": out}


def get_run(run_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}(-[0-9]+)?", run_id or ""):
        raise BadCommand("bad run id")
    try:
        return json.loads((_dir() / f"{run_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BadCommand(f"no decode-confirm run {run_id!r}") from None


def accept(vin: str, run_id: str, channel: str, confirm_pairing: bool = False) -> dict[str, Any]:
    """Record the owner's acceptance of one channel's verdict in ``did_overrides.json``.

    Only ``confirmed`` and ``wrong_scale`` verdicts can be accepted. A ``candidate`` pairing also
    needs ``confirm_pairing=True`` (the owner vouches that the MES name is the same quantity).
    wrong_scale is accepted for DID channels only; a legislated PID decoding is never rewritten."""
    from . import channels as channels_mod
    from . import did_catalog
    run_rec = get_run(run_id)
    row = next((c for c in run_rec["channels"] if c["channel"] == channel), None)
    if row is None:
        raise BadCommand(f"channel {channel!r} is not in run {run_id}")
    if row["verdict"] not in ("confirmed", "wrong_scale"):
        raise BadCommand(f"{channel}: verdict is {row['verdict']} ({row.get('reason', '')}); nothing to accept")
    if row.get("pairing") == "candidate" and not confirm_pairing:
        raise BadCommand(f"{channel}: the MES name '{row['mes_name']}' is only a candidate pairing; pass "
                         "confirm_pairing=true if you vouch that it is the same quantity")
    ch = channels_mod.registry().get(channel)
    if ch is None:
        raise BadCommand(f"unknown channel {channel!r}")
    t = row.get("transform") or {"name": "identity", "a": 1.0, "b": 0.0, "unit": ch.unit}
    if row["verdict"] == "wrong_scale" and ch.kind != "did":
        raise BadCommand(f"{channel}: a legislated PID decoding is not overridden; the finding stays in the run")
    if row["verdict"] == "confirmed":
        # identity may carry a unit conversion (e.g. kPa -> mbar) that only describes the comparison:
        # the channel keeps its own scale and unit.
        t = {"name": "identity", "a": 1.0, "b": 0.0, "unit": ch.unit}
    entry = {"status": "confirmed", "a": t["a"], "b": t["b"], "unit": t.get("unit") or ch.unit,
             "transform": t["name"], "verdict": row["verdict"], "mes_name": row["mes_name"],
             "pairing": row["pairing"], "samples": row["samples"], "fit": row.get("fit"),
             "residual": row.get("residual"), "run_id": run_id, "vin": vin,
             "at": datetime.now().isoformat(timespec="seconds")}
    if ch.kind == "did" and ch.field:
        raise BadCommand(f"{channel}: multi-field DID channels are not overridden")
    with _LOCK:
        p = state_dir() / "did_overrides.json"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("channels", {})[channel] = entry
        atomic_write_text(p, json.dumps(data, indent=1, ensure_ascii=False))
        run_rec.setdefault("accepted", []).append({"channel": channel, "at": entry["at"], "verdict": row["verdict"]})
        atomic_write_text(_dir() / f"{run_id}.json", json.dumps(run_rec, indent=1, ensure_ascii=False))
    channels_mod.invalidate_registry()
    return {"accepted": channel, "override": entry, "file": str(p), "was": ch.confidence,
            "note": "the shipped catalogue is unchanged; did_catalog reads this file at load time"}


__all__ = ["run", "accept", "list_runs", "get_run", "load_aliases"]
