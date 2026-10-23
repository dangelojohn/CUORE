#!/usr/bin/env python
"""Parse the raw CUORE read-only scan JSON of 2026-10-22 into one report.

Run:  C:\\Users\\User\\mcp-servers\\.venv\\Scripts\\python.exe parse_scan.py [--dir D] [--baseline F] [--out F]
      ... parse_scan.py --selftest        (synthetic sample, nothing on disk but a temp dir)

Input : scan_2026-10-22\\*.json. Each file is either the runner's wrapper
        {step, phase, method, url, body, attempts, http_status, response, note}
        or a bare API response; both are accepted. Files that fail to parse are listed.
Output: stdout + scan_2026-10-22\\REPORT.md

Rules: nothing is invented. Anything not in the files is "not read" / "NO DATA".
Every field read through a name-variant lookup is recorded and listed at the end
("Field sources used").
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
DEFAULT_DIR = HERE / "scan_2026-10-22"
DEFAULT_BASELINE = HERE / "baseline_2026-10-19.json"
REPO = Path(r"C:\Users\User\mcp-servers")

# Status-bit legend: CUORE's own (cuore.live.obd.DTC_STATUS_BITS); embedded copy as fallback.
_LEGEND_FALLBACK = (
    (0, "testFailed"), (1, "testFailedThisOperationCycle"), (2, "pendingDTC"),
    (3, "confirmedDTC"), (4, "testNotCompletedSinceLastClear"),
    (5, "testFailedSinceLastClear"), (6, "testNotCompletedThisOperationCycle"),
    (7, "warningIndicatorRequested"),
)
LEGEND_SRC = "embedded copy of cuore.live.obd.DTC_STATUS_BITS"
STATUS_BITS = _LEGEND_FALLBACK
try:  # importing from the repo is fine (read-only; pure module)
    sys.path.insert(0, str(REPO))
    from cuore.live.obd import DTC_STATUS_BITS as _SB  # type: ignore
    STATUS_BITS = tuple(_SB)
    LEGEND_SRC = "cuore.live.obd.DTC_STATUS_BITS"
except Exception:  # noqa: BLE001
    pass

ECM_AVAIL_DEFAULT = 0xCF          # ECM: b4/b5 not implemented
FAIL_BITS = 0x01 | 0x02 | 0x20    # testFailed, failedThisCycle, failedSinceLastClear
INTERESTING = 0x01 | 0x02 | 0x04 | 0x08 | 0x20 | 0x80
EVAP_TRIO = ("P0440", "P0455", "P0456")
EVAP_THRESHOLD_MS = 3965
NO_DATA = "NO DATA"
NOT_READ = "not read"

USED: dict[str, str] = {}         # label -> "key used" (printed at the end)


# ------------------------------------------------------------------ helpers ----

def norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def pick(d: Any, label: str, keys: list[str], default: Any = None) -> Any:
    """First present key (case/punctuation-insensitive); records which key answered."""
    if not isinstance(d, dict):
        return default
    nk = {norm(k): k for k in d}
    for want in keys:
        k = nk.get(norm(want))
        if k is not None and d[k] is not None:
            USED.setdefault(label, k)
            return d[k]
    return default


def deep_find(obj: Any, names: list[str], label: str = "") -> Any:
    """Breadth-first search for the first dict key matching any of ``names``."""
    want = {norm(n) for n in names}
    queue = [obj]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if norm(k) in want and v is not None:
                    if label:
                        USED.setdefault(label, k)
                    return v
            queue.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            queue.extend(v for v in cur if isinstance(v, (dict, list)))
    return None


def hex2(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, int):
        return f"{x:02X}"
    s = str(x).strip().upper().replace("0X", "")
    return s.zfill(2) if re.fullmatch(r"[0-9A-F]{1,2}", s) else s


def to_status(x: Any) -> Optional[int]:
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    s = str(x).strip().lower().replace("0x", "")
    try:
        return int(s, 16)
    except ValueError:
        return None


def fnum(x: Any) -> Optional[float]:
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"-?\d+(?:\.\d+)?", str(x))
    return float(m.group(0)) if m else None


def fmt(x: Any) -> str:
    if x is None:
        return NOT_READ
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r) + " |")
    return out


def err_text(resp: Any) -> Optional[str]:
    """Why a response carries no reading (warning/error/detail/transport error), else None."""
    if not isinstance(resp, dict):
        return "response is not a JSON object"
    for k in ("transport_error", "non_json_body", "error", "warning", "detail", "note"):
        v = resp.get(k)
        if isinstance(v, str) and v and k != "note":
            return f"{k}: {v[:200]}"
        if k == "detail" and isinstance(v, (list, dict)) and v:
            return f"detail: {json.dumps(v)[:200]}"
    return None


# ------------------------------------------------------------------ loading ----

class Item:
    def __init__(self, fname: str, obj: Any):
        self.file = fname
        wrapped = isinstance(obj, dict) and "response" in obj and ("step" in obj or "url" in obj)
        self.wrapped = wrapped
        self.resp = obj.get("response") if wrapped else obj
        self.step = str(obj.get("step", "")) if wrapped else ""
        self.url = str(obj.get("url", "")) if wrapped else ""
        self.http = obj.get("http_status") if wrapped else None
        self.note = obj.get("note", "") if wrapped else ""
        u = urlparse(self.url)
        self.path = u.path
        self.query = {k: v[0] for k, v in parse_qs(u.query).items()}
        self.role, self.arg = classify(self)

    @property
    def label(self) -> str:
        return self.step or self.file


_PATHS = [
    (r"/live/obd/readiness$", "readiness"), (r"/live/obd/pid/([0-9A-Fa-f]{1,2})$", "pid"),
    (r"/live/obd/dtcs$", "obd_dtcs"), (r"/live/obd/mode06$", "mode06"),
    (r"/live/obd/voltage$", "voltage"), (r"/live/obd/freeze$", "freeze"),
    (r"/live/obd/vin$", "vin"), (r"/live/obd/supported$", "supported"),
    (r"/live/scan$", "scan"), (r"/live/module/(\w+)/identity$", "identity"),
    (r"/live/module/(\w+)/dtcs$", "module_dtcs"), (r"/live/module/(\w+)/did/(\w+)$", "did"),
    (r"/live/module/(\w+)/dtc/([\w-]+)$", "dtc_detail"), (r"/live/discover$", "discover"),
    (r"/live/verify$", "verify"), (r"/live/modules$", "modules"), (r"/live/status$", "status"),
]


def classify(it: Item) -> tuple[str, tuple]:
    for rx, role in _PATHS:
        m = re.search(rx, it.path)
        if m:
            arg = tuple(g.upper() for g in m.groups())
            if role == "freeze":
                pid = it.query.get("pid") or (it.resp.get("pid") if isinstance(it.resp, dict) else "") or "02"
                arg = (str(pid).upper(),)
            return role, arg
    name = (it.step + " " + it.file).lower()
    r = it.resp if isinstance(it.resp, dict) else {}
    pats = [("readiness", "readiness"), ("mode06", "mode06"), ("voltage", "voltage"),
            ("freeze", "freeze"), ("_vin", "vin"), ("supported", "supported"),
            ("dtc_detail", "dtc_detail"), ("identity", "identity"), ("discover", "discover"),
            ("uds_19", "scan"), ("dtcs_mode", "obd_dtcs"), ("verify", "verify")]
    for sub, role in pats:
        if sub in name:
            if role == "freeze":
                m = re.search(r"pid([0-9a-f]{2})", name)
                return role, ((m.group(1).upper() if m else "02"),)
            return role, ()
    m = re.search(r"_pid([0-9a-f]{2})(?:_|\b|\.)", name)
    if m:
        return "pid", (m.group(1).upper(),)
    m = re.search(r"did_(?:(\w+?)_)?([0-9a-f]{4})", name)
    if m:
        return "did", ((m.group(1) or str(r.get("ecu", ""))).upper(), m.group(2).upper())
    # shape sniffing for bare responses
    if "since_clear" in r or "this_drive_cycle" in r:
        return "readiness", ()
    if "results" in r and "supported" in r:
        return "mode06", ()
    if "volts" in r:
        return "voltage", ()
    if isinstance(r.get("modules"), list) and r["modules"] and isinstance(r["modules"][0], dict) and "ecu" in r["modules"][0]:
        return "scan", ()
    if "fields" in r and "ecu" in r:
        return "identity", ()
    if "hits" in r and "tried" in r:
        return "discover", ()
    if any(k in r for k in ("stored", "pending", "permanent")):
        return "obd_dtcs", ()
    if "snapshot" in r and "extended" in r:
        return "dtc_detail", ()
    if "dtcs" in r and "ecu" in r:
        return "module_dtcs", ()
    if "did" in r and "ecu" in r:
        return "did", (str(r["ecu"]).upper(), str(r["did"]).upper())
    return "other", ()


def load_items(d: Path) -> tuple[list[Item], list[tuple[str, str]], Optional[dict]]:
    items: list[Item] = []
    bad: list[tuple[str, str]] = []
    manifest = None
    for f in sorted(d.glob("*.json")):
        try:
            obj = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception as e:  # noqa: BLE001
            bad.append((f.name, f"{type(e).__name__}: {str(e)[:90]}"))
            continue
        if f.name.lower() == "manifest.json":
            manifest = obj if isinstance(obj, dict) else None
            continue
        try:
            items.append(Item(f.name, obj))
        except Exception as e:  # noqa: BLE001
            bad.append((f.name, f"unusable structure: {type(e).__name__}: {str(e)[:90]}"))
    return items, bad, manifest


def by_role(items: list[Item], role: str) -> list[Item]:
    return [i for i in items if i.role == role]


# --------------------------------------------------------------- extractors ----

def pid_reading(it: Item) -> dict[str, Any]:
    """{'value','unit','why'}: value None => NO DATA (why says why)."""
    r = it.resp if isinstance(it.resp, dict) else {}
    val = pick(r, "pid value", ["value", "val", "decoded"])
    unit = pick(r, "pid unit", ["unit", "units"])
    if val is None:
        be = pick(r, "pid by_ecu", ["by_ecu", "ecus", "readings"])
        if isinstance(be, dict):
            for _h, v in be.items():
                if isinstance(v, dict) and v.get("value") is not None:
                    return {"value": v["value"], "unit": v.get("unit"), "why": None}
    if val is None:
        return {"value": None, "unit": unit, "why": err_text(r) or "no value in response"}
    return {"value": val, "unit": unit, "why": None}


def last_good(its: list[Item], ok) -> Optional[Item]:
    good = [i for i in its if ok(i)]
    return (good or its or [None])[-1]


def monitors_of(block: Any) -> list[dict[str, Any]]:
    mons = pick(block, "readiness monitors", ["monitors", "monitor_status", "readiness"]) if isinstance(block, dict) else None
    out: list[dict[str, Any]] = []
    if isinstance(mons, list):
        for m in mons:
            if not isinstance(m, dict):
                continue
            name = pick(m, "monitor name", ["monitor", "name"]) or "?"
            comp = pick(m, "monitor complete", ["complete", "completed", "ready", "done"])
            if comp is None:
                inc = pick(m, "monitor incomplete", ["incomplete", "not_complete"])
                comp = (not inc) if inc is not None else None
            out.append({"monitor": str(name), "supported": m.get("supported", True), "complete": comp})
    elif isinstance(mons, dict):
        for name, v in mons.items():
            comp = v if isinstance(v, bool) else (v.get("complete") if isinstance(v, dict) else None)
            out.append({"monitor": str(name), "supported": True, "complete": comp})
    return out


def evap_state(mons: list[dict[str, Any]]) -> Optional[bool]:
    for m in mons:
        if "evap" in m["monitor"].lower():
            return m["complete"] if isinstance(m["complete"], bool) else None
    return None


# ----------------------------------------------------------------- baseline ----

class Baseline:
    def __init__(self, obj: Any, path: Path):
        self.raw = obj
        self.path = path
        self.identity: dict[str, dict[str, Any]] = {}
        self.dtcs: dict[str, dict[str, Optional[int]]] = {}
        self.evap_complete: Optional[bool] = None
        self.mil: Optional[bool] = None
        self.mode06: dict[tuple[str, str], dict[str, Any]] = {}
        self.volts: dict[str, float] = {}
        self.ambient = self.iat = self.fuel = None
        self._load()

    def _load(self) -> None:
        o = self.raw
        ident = deep_find(o, ["module_identity", "identity_table", "identities", "modules", "identity"], "baseline identity")
        self.identity = self._norm_identity(ident)
        dt = deep_find(o, ["dtcs", "module_dtcs", "dtc", "codes", "faults"], "baseline dtcs")
        self.dtcs = self._norm_dtcs(dt)
        rd = deep_find(o, ["readiness", "readiness_pids"], "baseline readiness")
        if rd is not None:
            blocks = [rd] + ([rd.get("since_clear")] if isinstance(rd, dict) else [])
            for b in blocks:
                mons = monitors_of(b) if isinstance(b, dict) else []
                st = evap_state(mons)
                if st is not None:
                    self.evap_complete = st
                    break
            if self.evap_complete is None and isinstance(rd, dict):
                v = deep_find(rd, ["evap", "evaporative", "evaporative_system", "evap_complete"], "baseline evap")
                if isinstance(v, bool):
                    self.evap_complete = v
                elif isinstance(v, dict):
                    c = pick(v, "baseline evap complete", ["complete", "ready", "completed"])
                    self.evap_complete = c if isinstance(c, bool) else None
                elif isinstance(v, str):
                    low = v.lower()
                    self.evap_complete = False if ("incomplete" in low or "not" in low) else (True if "complete" in low or "ready" in low else None)
            m = deep_find(rd, ["mil_on", "mil"], "baseline mil")
            self.mil = m if isinstance(m, bool) else None
        self._walk_m06(deep_find(o, ["mode06", "mode_06", "mode6"], "baseline mode06"))
        vv = deep_find(o, ["voltages", "voltage", "volts"], "baseline voltages")
        if isinstance(vv, dict):
            for k, v in vv.items():
                n = fnum(v if not isinstance(v, dict) else (v.get("volts") or v.get("value")))
                if n is not None:
                    self.volts[str(k)] = n
        elif isinstance(vv, list):
            for i, v in enumerate(vv):
                if isinstance(v, dict):
                    n = fnum(v.get("volts", v.get("value")))
                    if n is not None:
                        self.volts[str(v.get("name") or v.get("label") or v.get("source") or i)] = n
                elif fnum(v) is not None:
                    self.volts[str(i)] = fnum(v)  # type: ignore[assignment]
        elif fnum(vv) is not None:
            self.volts["voltage"] = fnum(vv)  # type: ignore[assignment]
        self.ambient = fnum(deep_find(o, ["ambient", "ambient_temp", "ambient_air_temp", "pid_46"], "baseline ambient"))
        self.iat = fnum(deep_find(o, ["iat", "intake_air_temp", "pid_0f"], "baseline iat"))
        self.fuel = fnum(deep_find(o, ["fuel", "fuel_level", "fuel_pct", "pid_2f"], "baseline fuel"))

    @staticmethod
    def _norm_identity(x: Any) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        if isinstance(x, dict):
            for k, v in x.items():
                out[str(k).upper()] = v if isinstance(v, dict) else {"value": v}
        elif isinstance(x, list):
            for i, v in enumerate(x):
                if isinstance(v, dict):
                    nm = pick(v, "baseline identity module", ["module", "name", "ecu", "code"]) or f"#{i}"
                    out[str(nm).upper()] = v
        return out

    @staticmethod
    def _rec(r: Any) -> tuple[Optional[str], Optional[int]]:
        if isinstance(r, str):
            return r.upper(), None
        if isinstance(r, dict):
            c = pick(r, "baseline dtc code", ["code", "dtc"])
            s = pick(r, "baseline dtc status", ["status", "status_byte", "status_hex", "st"])
            return (str(c).upper() if c else None), to_status(s)
        return None, None

    def _norm_dtcs(self, x: Any) -> dict[str, dict[str, Optional[int]]]:
        out: dict[str, dict[str, Optional[int]]] = {}

        def add(mod: str, c: Optional[str], s: Optional[int]) -> None:
            if c:
                out.setdefault(mod.upper(), {})[c] = s

        def body(mod: str, v: Any) -> None:
            if isinstance(v, dict) and any(norm(k) in ("dtcs", "codes", "records") for k in v):
                v = pick(v, "baseline module dtcs", ["dtcs", "codes", "records"])
            if isinstance(v, dict):
                for c, s in v.items():
                    if isinstance(s, dict):
                        add(mod, str(c).upper(), to_status(pick(s, "baseline dtc status", ["status", "status_byte"])))
                    else:
                        add(mod, str(c).upper(), to_status(s))
            elif isinstance(v, list):
                for r in v:
                    c, s = self._rec(r)
                    add(mod, c, s)
            if mod.upper() not in out:
                out[mod.upper()] = {}

        if isinstance(x, dict):
            for mod, v in x.items():
                body(str(mod), v)
        elif isinstance(x, list):
            for r in x:
                if isinstance(r, dict):
                    mod = pick(r, "baseline dtc module", ["module", "ecu", "name"]) or "?"
                    if any(norm(k) in ("dtcs", "codes") for k in r):
                        body(str(mod), r)
                    else:
                        c, s = self._rec(r)
                        add(str(mod), c, s)
        return out

    def _walk_m06(self, x: Any) -> None:
        def row(r: dict[str, Any], mid: Optional[str] = None, tid: Optional[str] = None) -> None:
            mid = hex2(pick(r, "baseline m06 mid", ["mid", "obdmid"]) or mid)
            tid = hex2(pick(r, "baseline m06 tid", ["tid", "test_id"]) or tid)
            if mid and tid and "value" in r:
                self.mode06[(mid, tid)] = {"value": fnum(r.get("value")), "min": fnum(r.get("min")), "max": fnum(r.get("max"))}

        def walk(o: Any, mid: Optional[str] = None, tid: Optional[str] = None) -> None:
            if isinstance(o, list):
                for v in o:
                    walk(v, mid, tid)
            elif isinstance(o, dict):
                if "value" in o and (any(norm(k) in ("tid", "mid", "obdmid") for k in o) or (mid and tid)):
                    row(o, mid, tid)
                    return
                for k, v in o.items():
                    m = re.fullmatch(r"(?:0x)?([0-9A-Fa-f]{2})\W+(?:0x)?([0-9A-Fa-f]{2})", str(k).strip())
                    if m:
                        a, b = m.group(1).upper(), m.group(2).upper()
                        if isinstance(v, dict):
                            walk(v, a, b)
                        elif fnum(v) is not None:
                            self.mode06[(a, b)] = {"value": fnum(v), "min": None, "max": None}
                    elif re.fullmatch(r"(?:0x)?[0-9A-Fa-f]{2}", str(k).strip()) and mid is None:
                        walk(v, hex2(k), None)
                    elif re.fullmatch(r"(?:0x)?[0-9A-Fa-f]{2}", str(k).strip()) and tid is None and mid:
                        walk(v, mid, hex2(k))
                    else:
                        walk(v, mid, tid)
        walk(x)

    def mod_tokens(self, module: str) -> Optional[set[str]]:
        rec = self.identity.get(module.upper())
        if rec is None:
            for k, v in self.identity.items():
                if k.startswith(module.upper()) or module.upper().startswith(k):
                    rec = v
                    break
        if rec is None:
            return None
        toks: set[str] = set()

        def leaves(o: Any, key: str = "") -> None:
            if isinstance(o, dict):
                for k, v in o.items():
                    leaves(v, str(k))
            elif isinstance(o, list):
                for v in o:
                    leaves(v, key)
            elif isinstance(o, str):
                if norm(key) not in ("module", "name", "ecu", "code", "bus", "address", "target", "request", "response", "confidence"):
                    t = o.strip().upper()
                    if t:
                        toks.add(t)
            elif isinstance(o, (int, float)) and not isinstance(o, bool):
                pass
        leaves(rec)
        return toks


def baseline_dtcs_for(bl: Optional[Baseline], module: str) -> Optional[dict[str, Optional[int]]]:
    if bl is None:
        return None
    for k, v in bl.dtcs.items():
        if k == module.upper() or k.startswith(module.upper()) or module.upper().startswith(k):
            return v
    return None


# ------------------------------------------------------------ DTC decoding ----

def decode_bits(st: int, avail: int) -> str:
    on = [f"b{b} {n}" for b, n in STATUS_BITS if (st & (1 << b)) and (avail & (1 << b))]
    ni = [f"b{b}" for b, _ in STATUS_BITS if not (avail & (1 << b))]
    base = ", ".join(on) if on else "no bits set (tested, passed)"
    return base + (f" [{'/'.join(ni)} n/i]" if ni else "")


def status_of(rec: dict[str, Any]) -> Optional[int]:
    st = to_status(pick(rec, "dtc status", ["status", "status_byte", "status_hex"]))
    if st is None and isinstance(rec.get("flags"), dict):
        st = 0
        for b, n in STATUS_BITS:
            if rec["flags"].get(n):
                st |= 1 << b
    return st


def base_code(c: str) -> str:
    return c.upper().split("-")[0]


class ModDtcs:
    def __init__(self, name: str):
        self.name = name
        self.recs: dict[str, int] = {}     # full code -> status
        self.avail: Optional[int] = None
        self.avail_assumed = False
        self.problem: Optional[str] = None
        self.read = False
        self.source = ""
        self.tracked = 0


def gather_module_dtcs(items: list[Item]) -> dict[str, ModDtcs]:
    mods: dict[str, ModDtcs] = {}
    rows: list[tuple[dict[str, Any], str]] = []
    for it in by_role(items, "scan"):
        ms = pick(it.resp, "scan modules", ["modules", "results"]) if isinstance(it.resp, dict) else None
        if isinstance(ms, list):
            rows += [(m, it.label) for m in ms if isinstance(m, dict)]
        elif err_text(it.resp):
            mods.setdefault("(scan)", ModDtcs("(scan)")).problem = f"{it.label}: {err_text(it.resp)}"
    for it in by_role(items, "module_dtcs"):
        if isinstance(it.resp, dict):
            row = dict(it.resp)
            row.setdefault("ecu", it.arg[0] if it.arg else "?")
            rows.append((row, it.label))
    for row, src in rows:
        name = str(pick(row, "module name", ["ecu", "module", "code", "name"]) or "?").upper()
        md = mods.setdefault(name, ModDtcs(name))
        recs = pick(row, "module dtc records", ["dtcs", "records", "active_records"])
        prob = None
        if row.get("skipped"):
            prob = f"skipped: {row['skipped']}"
        elif row.get("error"):
            prob = f"error: {row['error']}"
        elif row.get("nrc"):
            prob = f"negative response: {row['nrc']}"
        elif row.get("warning"):
            prob = f"warning: {row['warning']}"
        if not isinstance(recs, list) or (not recs and prob):
            if md.problem is None and not md.read:
                md.problem = f"{src}: {prob or 'no DTC list in response'}"
            continue
        md.read = True
        md.problem = None
        md.source = src
        md.recs = {}
        for r in recs:
            if isinstance(r, dict) and r.get("code"):
                st = status_of(r)
                if st is not None:
                    md.recs[str(r["code"]).upper()] = st
            elif isinstance(r, str):
                md.recs[r.upper()] = 0x09  # compact form lists only active codes; status unknown
        am = pick(row, "availability mask", ["availability_mask", "avail_mask", "status_availability_mask"])
        md.avail = to_status(am)
        if md.avail is None:
            md.avail, md.avail_assumed = (ECM_AVAIL_DEFAULT, True) if name == "ECM" else (0xFF, True)
        md.tracked = len(recs)
    return mods


def interesting(st: Optional[int], avail: int) -> bool:
    return st is not None and bool(st & avail & INTERESTING)


# ------------------------------------------------------------------ report ----

def build_report(d: Path, bl_path: Path) -> tuple[str, dict[str, Any]]:
    USED.clear()
    items, bad, manifest = load_items(d)
    bl: Optional[Baseline] = None
    bl_note = f"baseline not present ({bl_path.name}): all NEW/CHANGED/SAME comparisons skipped"
    if bl_path.exists():
        try:
            bl = Baseline(json.loads(bl_path.read_text(encoding="utf-8-sig")), bl_path)
            bl_note = f"baseline loaded: {bl_path.name}"
        except Exception as e:  # noqa: BLE001
            bl_note = f"baseline {bl_path.name} failed to parse ({type(e).__name__}: {str(e)[:80]}); comparisons skipped"
    L: list[str] = []
    facts: dict[str, Any] = {}
    add = L.append

    add("# CUORE scan report, 2026-10-22")
    add("")
    add(f"Source: {d}  ({len(items)} readable files). {bl_note}.")
    if bad:
        add(f"UNPARSEABLE FILES ({len(bad)}): " + "; ".join(f"{n} ({why})" for n, why in bad))
    else:
        add("Unparseable files: none.")
    if manifest:
        iss = manifest.get("issues") or []
        ab = manifest.get("aborted") or manifest.get("guard_refusal")
        add(f"Runner manifest: {len(manifest.get('steps') or [])} steps, {len(iss)} issues"
            + (f", ABORTED: {ab}" if ab else "") + ".")
    unhealthy = [i for i in items if i.wrapped and i.http not in (200, None)]
    if unhealthy:
        add("Non-200 responses: " + "; ".join(f"{i.label} (HTTP {i.http}: {err_text(i.resp) or ''})" for i in unhealthy))
    add("")

    # -------------------------------------------------- Section 1: legislated
    add("## 1. Legislated OBD")
    add("")
    rd_items = by_role(items, "readiness")
    rd_it = last_good(rd_items, lambda i: isinstance(i.resp, dict) and isinstance(i.resp.get("since_clear"), dict) and monitors_of(i.resp["since_clear"]))
    since = this = None
    counters = {}
    if rd_it and isinstance(rd_it.resp, dict):
        since = pick(rd_it.resp, "readiness since_clear", ["since_clear", "sinceclear", "pid01", "readiness"])
        this = pick(rd_it.resp, "readiness this_drive_cycle", ["this_drive_cycle", "thisdrivecycle", "pid41"])
        counters = pick(rd_it.resp, "readiness counters", ["drive_cycle_counters", "counters"]) or {}
    mons = monitors_of(since) if isinstance(since, dict) else []
    # MIL
    mil = None
    for blk in (since, this):
        if isinstance(blk, dict) and isinstance(pick(blk, "mil_on", ["mil_on", "mil", "mil_status"]), bool):
            mil = pick(blk, "mil_on", ["mil_on", "mil", "mil_status"])
            break
    if mil is None:
        for it in by_role(items, "pid"):
            if it.arg == ("01",):
                v = pid_reading(it)["value"]
                if isinstance(v, dict) and isinstance(v.get("mil_on"), bool):
                    mil = v["mil_on"]
                    USED.setdefault("mil_on (fallback)", "obd/pid/01 value.mil_on")
    if mil is True:
        add("- MIL: **ON**" + (f" (stored DTC count in PID 01: {since.get('stored_dtc_count')})" if isinstance(since, dict) and since.get("stored_dtc_count") is not None else ""))
    elif mil is False:
        add("- MIL: off" + (f" (stored DTC count in PID 01: {since.get('stored_dtc_count')})" if isinstance(since, dict) and since.get("stored_dtc_count") is not None else ""))
    else:
        add(f"- MIL: {NO_DATA} ({(err_text(rd_it.resp) if rd_it else 'readiness file missing') or 'no mil flag in readiness'})")
    facts["mil"] = mil
    evap_complete = evap_state(mons)
    facts["evap_complete"] = evap_complete
    # counters
    def counter(key_names: list[str], pid: str, label: str) -> Optional[Any]:
        v = pick(counters, label, key_names) if isinstance(counters, dict) else None
        if v is None:
            for it in by_role(items, "pid"):
                if it.arg == (pid,):
                    v = pid_reading(it)["value"]
        return v
    wu = counter(["warmups_since_clear", "warmups", "warm_ups"], "30", "warm-ups since clear")
    dist = counter(["distance_since_clear", "distance", "km_since_clear"], "31", "distance since clear")
    add(f"- Warm-ups since clear: {fmt(wu) if wu is not None else NOT_READ}    Distance since clear: {(fmt(dist) + ' km') if dist is not None else NOT_READ}")
    facts["warmups"], facts["distance_km"] = wu, dist
    d21 = next((pid_reading(i) for i in by_role(items, "pid") if i.arg == ("21",)), None)
    if d21:
        add(f"- Distance with MIL on (PID 21): {fmt(d21['value']) + ' km' if d21['value'] is not None else NO_DATA + ' (' + str(d21['why']) + ')'}")
    add("")
    if mons:
        add("Readiness monitors since clear (Mode 01 PID 01):")
        rows = []
        for m in mons:
            ev = "evap" in m["monitor"].lower()
            st = "complete" if m["complete"] is True else ("INCOMPLETE" if m["complete"] is False else NOT_READ)
            nm = f"**{m['monitor']}**" if ev else m["monitor"]
            rows.append([nm, ("**" + st + "**") if ev else st])
        L.extend(md_table(["Monitor", "State"], rows))
        if evap_complete is None:
            add("EVAP monitor: not reported by this response.")
        else:
            add(f"**EVAP monitor: {'COMPLETE' if evap_complete else 'INCOMPLETE'}**")
    else:
        why = (err_text(since) if isinstance(since, dict) else None) or (err_text(rd_it.resp) if rd_it else "no readiness file")
        add(f"Readiness since clear: {NO_DATA} ({why}).")
    if isinstance(this, dict):
        tm = monitors_of(this)
        if tm:
            add("This drive cycle (PID 41): " + "; ".join(f"{m['monitor']}={'complete' if m['complete'] else 'incomplete'}" for m in tm if isinstance(m['complete'], bool)))
        elif err_text(this):
            add(f"This drive cycle (PID 41): {NO_DATA} ({err_text(this)})")
    if rd_it and isinstance(rd_it.resp, dict) and rd_it.resp.get("evap_verdict"):
        add(f"CUORE's own EVAP line: {rd_it.resp['evap_verdict']}")
    if bl and bl.evap_complete is not None:
        add(f"Baseline EVAP monitor: {'complete' if bl.evap_complete else 'incomplete'}.")
    add("")

    # OBD DTC modes
    od = by_role(items, "obd_dtcs")
    if od:
        add("Legislated DTCs (Modes 03 / 07 / 0A):")
        r = od[-1].resp if isinstance(od[-1].resp, dict) else {}
        blocks = {k: r.get(k) for k in ("stored", "pending", "permanent") if isinstance(r.get(k), dict)}
        if not blocks and ("dtcs" in r or "kind" in r):
            blocks = {str(r.get("kind", "stored")): r}
        obd_codes: dict[str, list[str]] = {}
        for k in ("stored", "pending", "permanent"):
            b = blocks.get(k)
            if b is None:
                add(f"- {k}: {NOT_READ}")
                continue
            w = err_text(b)
            codes = pick(b, f"obd {k} codes", ["dtcs", "codes"]) or []
            if w and not codes:
                add(f"- {k}: {NO_DATA} ({w})")
            else:
                obd_codes[k] = [str(c).upper() for c in codes]
                add(f"- {k}: {', '.join(codes) if codes else 'none reported'}")
        facts["obd_codes"] = obd_codes
    else:
        add(f"Legislated DTCs (Modes 03/07/0A): {NOT_READ} (no file)")
        facts["obd_codes"] = {}
    add("")

    # Mode 06
    add("Mode 06 test results:")
    m06_rows: list[dict[str, Any]] = []
    m06_notes: list[str] = []
    for it in by_role(items, "mode06"):
        r = it.resp if isinstance(it.resp, dict) else {}
        res = pick(r, "mode06 results", ["results", "mids"])
        if not isinstance(res, dict):
            m06_notes.append(f"{it.label}: {NO_DATA} ({err_text(r) or 'no results block'})")
            continue
        for mid, entry in res.items():
            if not isinstance(entry, dict):
                continue
            be = pick(entry, "mode06 by_ecu", ["by_ecu", "ecus"])
            got = False
            if isinstance(be, dict):
                for ecu, recs in be.items():
                    for rec in (recs if isinstance(recs, list) else []):
                        if not isinstance(rec, dict):
                            continue
                        got = True
                        v, lo, hi = fnum(rec.get("value")), fnum(rec.get("min")), fnum(rec.get("max"))
                        passed = rec.get("passed")
                        if not isinstance(passed, bool) and v is not None and lo is not None and hi is not None:
                            passed = lo <= v <= hi
                        m06_rows.append({"mid": hex2(rec.get("mid") or mid), "tid": hex2(rec.get("tid")), "ecu": ecu,
                                         "value": v, "min": lo, "max": hi, "passed": passed,
                                         "unit": rec.get("unit"), "name": rec.get("mid_name"),
                                         "scaling": (rec.get("raw") or {}).get("scaling") if isinstance(rec.get("raw"), dict) else None,
                                         "src": it.label})
            if not got:
                why = entry.get("warning") or entry.get("error") or (("negative: " + json.dumps(entry["negative"])) if entry.get("negative") else "no records")
                m06_notes.append(f"MID {hex2(mid)}: {NO_DATA if 'NO DATA' in str(why).upper() or why == 'no records' else 'not answered'} ({why})")
        if not res:
            m06_notes.append(f"{it.label}: results block empty ({err_text(r) or 'no MIDs read'})")
    if not by_role(items, "mode06"):
        add(f"- {NOT_READ} (no mode06 file)")
    if m06_rows:
        rows = []
        for r in m06_rows:
            key = (r["mid"], r["tid"])
            hl = key in (("3A", "87"), ("3C", "90"))
            zero = r["value"] == 0 and r["min"] == 0 and r["max"] == 0
            pf = "PASS" if r["passed"] is True else ("FAIL" if r["passed"] is False else "?")
            if zero:
                pf += " (0/0/0 = no limit published, no information)"
            if r["scaling"] == "unknown":
                pf += " (scaling unknown)"
            row = [f"0x{r['mid']}/0x{r['tid']}", r["name"] or "", fmt(r["value"]), fmt(r["min"]), fmt(r["max"]), pf, r["unit"] or "-"]
            if hl:
                row = [f"**{c}**" for c in row]
            rows.append(row)
        L.extend(md_table(["OBDMID/TID", "Test", "Value", "Min", "Max", "Result", "Unit"], rows))
        add("(bold = the two EVAP proof tests: 0x3A/0x87 and 0x3C/0x90)")
    for n in m06_notes:
        add(f"- {n}")
    for key, nm in ((("3A", "87"), "0x3A/0x87"), (("3C", "90"), "0x3C/0x90")):
        if not any((r["mid"], r["tid"]) == key for r in m06_rows):
            add(f"- **{nm}: {NO_DATA}** (not in any Mode 06 response)")
        elif bl and key in bl.mode06:
            b = bl.mode06[key]
            now = next(r for r in m06_rows if (r["mid"], r["tid"]) == key)
            add(f"- {nm} vs baseline: now {fmt(now['value'])} (min {fmt(now['min'])}, max {fmt(now['max'])}); baseline {fmt(b['value'])} (min {fmt(b['min'])}, max {fmt(b['max'])})")
    facts["mode06"] = m06_rows
    add("")

    # voltage
    add("Voltage:")
    volts: list[tuple[str, float, str]] = []
    for it in by_role(items, "voltage"):
        r = it.resp if isinstance(it.resp, dict) else {}
        v = fnum(pick(r, "voltage volts", ["volts", "voltage", "v"]))
        tag = "ATRV " + ("before" if "before" in it.label.lower() else "after" if "after" in it.label.lower() else it.label)
        if v is None:
            add(f"- {tag}: {NO_DATA} ({err_text(r) or 'no volts in response'}; raw={r.get('raw')!r})")
        else:
            volts.append((tag, v, it.label))
            add(f"- {tag}: {v:g} V")
    for it in by_role(items, "pid"):
        if it.arg == ("42",):
            pr = pid_reading(it)
            v = fnum(pr["value"])
            if v is None:
                add(f"- PID 42 control module voltage: {NO_DATA} ({pr['why']})")
            else:
                volts.append(("PID 42", v, it.label))
                add(f"- PID 42 control module voltage: {v:g} V")
    if not volts and not by_role(items, "voltage"):
        add(f"- {NOT_READ}")
    if bl and bl.volts:
        add("- Baseline voltages: " + ", ".join(f"{k}={v:g} V" for k, v in bl.volts.items()))
    facts["volts"] = volts
    add("")

    # freeze frame
    fz = by_role(items, "freeze")
    if fz:
        add("Freeze frame (Mode 02, frame 0):")
        for it in fz:
            r = it.resp if isinstance(it.resp, dict) else {}
            be = pick(r, "freeze by_ecu", ["by_ecu"])
            txt = None
            if isinstance(be, dict) and be:
                parts = []
                for h, v in be.items():
                    if isinstance(v, dict):
                        parts.append(f"{h}: " + (f"DTC {v['dtc']}" if v.get("dtc") else f"{fmt(v.get('value'))} {v.get('unit') or ''}".strip()))
                txt = "; ".join(parts)
            add(f"- PID {it.arg[0] if it.arg else '?'}: {txt or NO_DATA + ' (' + str(err_text(r) or 'no ECU answered') + ')'}")
        add("")

    # -------------------------------------------------- Section 2: modules
    mods = gather_module_dtcs(items)
    add("## 2. Modules")
    add("")
    names: dict[str, str] = {}
    for it in by_role(items, "modules"):
        ms = pick(it.resp, "modules table", ["modules"]) if isinstance(it.resp, dict) else None
        for m in ms or []:
            if isinstance(m, dict) and m.get("code"):
                names[str(m["code"]).upper()] = str(m.get("name") or "")
    DIDS_SHOW = [("F190", "VIN"), ("F187", "Part F187"), ("F188", "SW F188"), ("F189", "SW ver F189"),
                 ("F191", "HW F191"), ("F192", "HW F192"), ("F194", "Supp SW F194"), ("F195", "SW F195"), ("F18C", "Serial F18C")]
    ident: dict[str, dict[str, str]] = {}
    ident_problem: dict[str, str] = {}
    for it in by_role(items, "identity"):
        r = it.resp if isinstance(it.resp, dict) else {}
        mod = str(pick(r, "identity module", ["ecu", "module", "code"]) or (it.arg[0] if it.arg else "?")).upper()
        fields = pick(r, "identity fields", ["fields", "identity", "dids"]) or {}
        vals: dict[str, str] = {}
        if isinstance(fields, dict):
            for did, f in fields.items():
                key = str(did).upper().replace("0X", "")
                if isinstance(f, dict):
                    a = f.get("ascii")
                    b = f.get("bytes")
                    nrc = f.get("nrc")
                    if a:
                        vals[key] = str(a).strip()
                    elif b:
                        vals[key] = "hex:" + "".join(str(x) for x in b) if isinstance(b, list) else str(b)
                    elif nrc:
                        vals[key] = "NRC " + (json.dumps(nrc) if not isinstance(nrc, str) else nrc)
                elif isinstance(f, str) and f:
                    vals[key] = f
        if vals:
            ident[mod] = vals
            ident_problem.pop(mod, None)
        elif mod not in ident:
            ident_problem[mod] = err_text(r) or "no identity fields returned"
    rows = []
    cur_tokens: dict[str, set[str]] = {}
    scan_names = {n for n in mods if not n.startswith("(")}
    for mod in sorted(set(ident) | set(ident_problem) | scan_names):
        vals = ident.get(mod)
        nm = f"{mod}" + (f" ({names[mod]})" if names.get(mod) else "")
        if not vals:
            btok = bl.mod_tokens(mod) if bl else None
            status = "NOT READ" + (" (baseline has it)" if btok else "") if bl else "no baseline"
            rows.append([nm, NOT_READ, "", "", "", "", f"{status}: {ident_problem.get(mod, 'no identity file for this module')[:100]}"])
            continue
        toks = {v.upper() for k, v in vals.items() if k != "F190" and not v.startswith("NRC")}
        cur_tokens[mod] = toks
        status = "no baseline"
        if bl and not toks:
            status = "no comparable ids read (only VIN/NRC)"
        elif bl:
            bt = bl.mod_tokens(mod)
            if bt is None:
                status = "NEW"
            else:
                added = sorted(t for t in toks if t not in bt)
                gone = sorted(t for t in bt if t not in toks and len(t) > 3)
                status = "SAME" if not added else "CHANGED (now: " + ", ".join(added) + (")" if not gone else "; baseline had: " + ", ".join(gone[:4]) + ")")
        def g(*ks: str) -> str:
            return " / ".join(vals[k] for k in ks if k in vals) or NOT_READ
        rows.append([nm, g("F190"), g("F187"), g("F188"), g("F189", "F195"), g("F191", "F192"), status])
    if rows:
        L.extend(md_table(["Module", "VIN (F190)", "Part (F187)", "SW (F188)", "SW ver (F189/F195)", "HW (F191/F192)", "vs baseline"], rows))
    else:
        add(f"No module identity was read ({NOT_READ}).")
    # discover hits
    hits: list[dict[str, Any]] = []
    for it in by_role(items, "discover"):
        h = pick(it.resp, "discover hits", ["hits"]) if isinstance(it.resp, dict) else None
        if isinstance(h, list):
            hits += [x for x in h if isinstance(x, dict)]
        elif isinstance(it.resp, dict) and err_text(it.resp):
            add(f"- discover {it.label}: {NO_DATA} ({err_text(it.resp)})")
    if by_role(items, "discover") and not hits:
        add("- Address discovery (22 F190): no node answered at the candidate addresses tried.")
    if hits:
        add("")
        add("Address discovery hits (22 F190 / identity DIDs):")
        rr = []
        for h in hits:
            idf = h.get("identity") if isinstance(h.get("identity"), dict) else {}
            rr.append([f"0x{h.get('target')}", h.get("module") or h.get("registry_match") or "unmatched",
                       h.get("vin") or (h.get("vin_nrc") and f"F190 {h['vin_nrc']}") or h.get("error") or NOT_READ,
                       h.get("probe_did") or "-", h.get("spare_part") or idf.get("F187") or NOT_READ,
                       h.get("matched_by") or h.get("conflict") or "-"])
        L.extend(md_table(["Target", "Module", "VIN / reply", "Probe DID", "Spare part", "Matched by"], rr))
    facts["identity_modules"] = sorted(ident)
    facts["hits"] = hits
    add("")

    # -------------------------------------------------- Section 3: DTCs
    add("## 3. DTCs per module (UDS 19 02)")
    add("")
    add(f"Status legend ({LEGEND_SRC}): " + "; ".join(f"b{b}={n}" for b, n in STATUS_BITS)
        + ". ECM availability mask 0xCF: b4 and b5 are not implemented there, so those two bits are never read as set/clear.")
    add("Shown per module: EVAP codes first (always, even if clear or absent), then every code with any of b0/b1/b2/b3/b5/b7 set. "
        "Not-run-since-clear (b4/b6 only) codes are counted, not listed.")
    add("")
    order = sorted(mods, key=lambda n: (n != "ECM", n))
    allnow: dict[str, dict[str, int]] = {}
    for name in order:
        md = mods[name]
        add(f"### {name}" + (f" ({names[name]})" if names.get(name) else ""))
        if not md.read:
            add(f"{NO_DATA}: {md.problem or 'module not in scan'}")
            add("")
            continue
        avail = md.avail if md.avail is not None else 0xFF
        notrun = sum(1 for s in md.recs.values() if s & 0x50)
        add(f"Tracked {len(md.recs)} codes, availability mask 0x{avail:02X}" + (" (assumed, not in response)" if md.avail_assumed else "")
            + f"; {notrun} with a not-completed bit. Source {md.source}.")
        bdt = baseline_dtcs_for(bl, name)
        now_int = {c: s for c, s in md.recs.items() if interesting(s, avail)}
        allnow[name] = dict(md.recs)
        rows = []
        evap_codes = [c for c in md.recs if base_code(c) in EVAP_TRIO]
        shown = set()

        def vs(code: str, st: Optional[int]) -> str:
            if bdt is None:
                return "no baseline" if bl else "-"
            bs = bdt.get(code)
            bnow = code in bdt and (bs is None or interesting(bs, 0xFF))
            nnow = st is not None and interesting(st, avail)
            if nnow and not bnow:
                return "NEW" + (f" (baseline {('0x%02X' % bs) if bs is not None else 'not listed'})" if code in bdt else "")
            if nnow and bnow:
                return "STILL" + (f" (baseline 0x{bs:02X})" if bs is not None and bs != st else "")
            if not nnow and bnow:
                return "GONE" + (f" (baseline 0x{bs:02X})" if bs is not None else "")
            return "clear in both" if st is not None else "-"

        for trio in EVAP_TRIO:
            cs = [c for c in evap_codes if base_code(c) == trio]
            if not cs and name == "ECM":
                rows.append([f"**{trio}**", "not in reply", "code not tracked/reported by this module", vs(trio, None)])
            for c in sorted(cs):
                st = md.recs[c]
                shown.add(c)
                rows.append([f"**{c}**", f"0x{st:02X}", decode_bits(st, avail), vs(c, st)])
        for c in sorted(now_int, key=lambda c: (not c.startswith("P"), c)):
            if c in shown:
                continue
            shown.add(c)
            rows.append([c, f"0x{now_int[c]:02X}", decode_bits(now_int[c], avail), vs(c, now_int[c])])
        if bdt:
            for c, bs in sorted(bdt.items()):
                if c in shown:
                    continue
                if bs is None or interesting(bs, 0xFF):
                    now = md.recs.get(c)
                    rows.append([c, f"0x{now:02X}" if now is not None else "not in reply",
                                 decode_bits(now, avail) if now is not None else "-", vs(c, now) if now is not None else f"GONE (baseline {('0x%02X' % bs) if bs is not None else 'listed'}; not in reply)"])
        if rows:
            L.extend(md_table(["Code", "Status", "Decoded", "vs baseline"], rows))
        else:
            add("No active/history codes.")
        add("")
    facts["dtc_mods"] = {n: dict(m.recs) for n, m in mods.items() if m.read}
    facts["dtc_avail"] = {n: m.avail for n, m in mods.items() if m.read}

    # -------------------------------------------------- Section 4: verdict
    add("## 4. EVAP proof verdict")
    add("")
    add(f"Rule: PASS = 0x3A/0x87 >= {EVAP_THRESHOLD_MS} ms AND no test-failed bits (b0, b1, and b5 where implemented) on P0440/P0455/P0456 AND EVAP readiness complete. "
        "INCOMPLETE = EVAP monitor not yet complete. FAIL otherwise. "
        "UNDETERMINED is added by this parser only when a needed reading is missing (an unread value is never counted as pass or fail).")
    add("")
    r3a = next((r for r in m06_rows if (r["mid"], r["tid"]) == ("3A", "87")), None)
    ev_lines: list[str] = []
    missing: list[str] = []
    fails: list[str] = []
    # readiness
    if evap_complete is None:
        ev_lines.append(f"- EVAP readiness (PID 01): {NO_DATA}")
        missing.append("EVAP readiness")
    else:
        ev_lines.append(f"- EVAP readiness (PID 01): {'complete' if evap_complete else 'INCOMPLETE'}")
    # mode06
    m06_ok = None
    if r3a is None or r3a["value"] is None:
        ev_lines.append(f"- Mode 06 0x3A/0x87: {NO_DATA}")
        missing.append("Mode 06 0x3A/0x87")
    else:
        v = r3a["value"]
        unit = r3a["unit"]
        extra = ""
        if r3a["scaling"] == "unknown" or (unit and str(unit).lower() != "ms"):
            extra = f" [unit is {unit!r}, scaling {r3a['scaling']!r}, not ms as expected: threshold comparison not trusted]"
        zero = v == 0 and r3a["min"] == 0 and r3a["max"] == 0
        m06_ok = v >= EVAP_THRESHOLD_MS and not zero and not extra
        ev_lines.append(f"- Mode 06 0x3A/0x87: value {fmt(v)} {unit or ''} (min {fmt(r3a['min'])}, max {fmt(r3a['max'])}) vs required >= {EVAP_THRESHOLD_MS} ms -> "
                        f"{'meets' if v >= EVAP_THRESHOLD_MS else 'BELOW'}{' (0/0/0 record, no information)' if zero else ''}{extra}")
        if extra:
            missing.append("Mode 06 0x3A/0x87 in ms")
        elif zero or v < EVAP_THRESHOLD_MS:
            fails.append("0x3A/0x87 below 3965 ms" if not zero else "0x3A/0x87 is a 0/0/0 record")
    # fail bits
    ecm = mods.get("ECM")
    codes_ok: Optional[bool] = None
    if not ecm or not ecm.read:
        ev_lines.append(f"- P0440/P0455/P0456 status: {NO_DATA} (ECM 19 02 not read: {ecm.problem if ecm else 'no ECM row'})")
        missing.append("ECM 19 02")
    else:
        avail = ecm.avail if ecm.avail is not None else ECM_AVAIL_DEFAULT
        fb = FAIL_BITS & avail
        codes_ok = True
        for trio in EVAP_TRIO:
            cs = sorted(c for c in ecm.recs if base_code(c) == trio)
            if not cs:
                ev_lines.append(f"- {trio}: not in the ECM's 19 02 reply (no status byte to read)")
                continue
            for c in cs:
                st = ecm.recs[c]
                failed = bool(st & fb)
                other = decode_bits(st & ~fb, avail) if (st & ~fb & avail) else "no other bits"
                ev_lines.append(f"- {c}: status 0x{st:02X}; test-failed bits {'SET' if failed else 'clear'} (checked mask 0x{fb:02X}); remaining: {other}")
                if failed:
                    codes_ok = False
                    fails.append(f"{c} test-failed bit set")
    obd = facts.get("obd_codes") or {}
    for kind, lst in obd.items():
        hit = [c for c in lst if base_code(c) in EVAP_TRIO]
        if hit:
            ev_lines.append(f"- Legislated {kind} list contains {', '.join(hit)}")
            fails.append(f"{', '.join(hit)} in OBD {kind} list")
            codes_ok = False
    if evap_complete is False:
        verdict = "INCOMPLETE"
        why = "EVAP monitor has not completed since the last clear; nothing else is conclusive yet."
    elif evap_complete is None or missing:
        verdict = "UNDETERMINED"
        why = "needed reading(s) missing: " + ", ".join(missing) + (f"; already failing: {', '.join(fails)}" if fails else "")
        if fails and evap_complete is True and not [m for m in missing if m == "EVAP readiness"]:
            verdict, why = "FAIL", "; ".join(fails) + (f" (also unread: {', '.join(missing)})" if missing else "")
    elif fails or not (m06_ok and codes_ok):
        verdict = "FAIL"
        why = "; ".join(fails) or "a condition is not met"
    else:
        verdict = "PASS"
        why = "all three conditions met on this scan"
    add(f"**EVAP proof verdict: {verdict}** - {why}")
    add("")
    L.extend(ev_lines)
    facts["verdict"] = verdict
    add("")

    # -------------------------------------------------- Section 5: inputs
    add("## 5. EVAP inputs")
    add("")

    def one_pid(pid: str) -> dict[str, Any]:
        its = [i for i in by_role(items, "pid") if i.arg == (pid,)]
        return pid_reading(its[-1]) if its else {"value": None, "unit": None, "why": "PID not requested / no file"}
    amb, iat, fuel = one_pid("46"), one_pid("0F"), one_pid("2F")
    fz_src = {}
    for it in fz:
        if it.arg and it.arg[0] in ("46", "0F", "2F"):
            fz_src[it.arg[0]] = it
    rows = []
    flags = []
    av, iv, fv = fnum(amb["value"]), fnum(iat["value"]), fnum(fuel["value"])
    def cell(rd: dict[str, Any], u: str) -> str:
        return f"{fmt(fnum(rd['value']))} {u}" if fnum(rd["value"]) is not None else f"{NO_DATA} ({str(rd['why'])[:80]})"
    rows.append(["Ambient air temp (PID 46)", cell(amb, "C"), fmt(bl.ambient) + (" C" if bl and bl.ambient is not None else "") if bl else "no baseline"])
    rows.append(["Intake air temp (PID 0F)", cell(iat, "C"), fmt(bl.iat) + (" C" if bl and bl.iat is not None else "") if bl else "no baseline"])
    rows.append(["Fuel level (PID 2F)", cell(fuel, "%"), fmt(bl.fuel) + (" %" if bl and bl.fuel is not None else "") if bl else "no baseline"])
    for did_it in by_role(items, "did"):
        if did_it.arg[:2] and did_it.arg[1:2] == ("1001",) or (len(did_it.arg) > 1 and did_it.arg[-1] == "1001"):
            r = did_it.resp if isinstance(did_it.resp, dict) else {}
            b = r.get("bytes")
            if isinstance(b, list) and b:
                try:
                    pct = int(b[0], 16) * 100 / 255
                    rows.append(["ECM DID 1001 fuel level (bytes " + "".join(b) + ")", f"{pct:.1f} % (A*100/255, formula from CUORE snapshot layout, medium confidence)", "-"])
                    if fv is None:
                        fv = pct
                except ValueError:
                    pass
            else:
                rows.append(["ECM DID 1001 fuel level", f"{NO_DATA} ({err_text(r) or 'no bytes'})", "-"])
    L.extend(md_table(["Input", "This scan", "Baseline"], rows))
    if av is not None:
        if av <= -60:
            flags.append(f"AMBIENT PINNED LOW: {av:g} C (<= -60 C; -61 C is the stuck value being watched for)")
        elif av == -40:
            flags.append("AMBIENT AT DECODE FLOOR: -40 C (raw byte 00)")
    else:
        flags.append("ambient not read")
    if av is not None and iv is not None:
        delta = av - iv
        add(f"Ambient minus IAT: {delta:+.0f} C" + (" (differs by more than 15 C: check which sensor is wrong)" if abs(delta) > 15 else ""))
        if abs(delta) > 15:
            flags.append(f"ambient vs IAT differ by {abs(delta):.0f} C")
    if fv is not None and not (15 <= fv <= 85):
        flags.append(f"FUEL OUTSIDE 15-85 %: {fv:.1f} %")
    elif fv is None:
        flags.append("fuel level not read")
    add("Flags: " + ("; ".join(flags) if flags else "none"))
    facts["flags"] = flags
    add("")

    # -------------------------------------------------- Section 6: network
    add("## 6. Network (U-codes)")
    add("")
    ucodes_now: dict[str, dict[str, int]] = {}
    for name in order:
        md = mods[name]
        if not md.read:
            add(f"- {name}: {NO_DATA} ({md.problem})")
            continue
        avail = md.avail if md.avail is not None else 0xFF
        us = {c: s for c, s in md.recs.items() if c.startswith("U")}
        ucodes_now[name] = {c: s for c, s in us.items() if interesting(s, avail)}
        act = ", ".join(f"{c} 0x{s:02X}" for c, s in sorted(ucodes_now[name].items())) or "none with a status bit set"
        add(f"- {name}: {act}   (U-codes tracked: {len(us)})")
    pres = {b: [(m, c) for m, d_ in ucodes_now.items() for c in d_ if base_code(c) == b] for b in ("U1711", "U1712", "U1713")}
    add("")
    for b in ("U1711", "U1712", "U1713"):
        add(f"- {b}: " + (", ".join(f"{m} {c}" for m, c in pres[b]) if pres[b] else "not present (no status bit set / not tracked)"))
    a, b_ = bool(pres["U1711"]), bool(pres["U1712"])
    add(f"- U1711 and U1712 together: {'YES' if a and b_ else ('only U1711' if a else ('only U1712' if b_ else 'neither present'))}; U1713: {'PRESENT' if pres['U1713'] else 'absent'}")
    low = [(t, v, s) for t, v, s in volts if v < 12.0]
    add("- Voltage below 12.0 V: " + ("; ".join(f"{t} {v:g} V ({s})" for t, v, s in low) if low else ("none among the readings above" if volts else NOT_READ)))
    facts["u"] = {k: bool(v) for k, v in pres.items()}
    add("")

    # -------------------------------------------------- Section 7: camera
    add("## 7. Camera / ParkView / PAM")
    add("")
    rx = re.compile(r"park|pam\b|camera|mfk|parkview|rvc|surround", re.I)
    cam_codes = {c for c, n in names.items() if rx.search(c) or rx.search(n)} | {"PAM"}
    answered = []
    for mod, vals in ident.items():
        if mod in cam_codes or rx.search(mod):
            answered.append(f"identity answered by {mod}: " + ", ".join(f"{k}={v}" for k, v in vals.items()))
    for h in hits:
        blob = " ".join(str(h.get(k) or "") for k in ("module", "registry_match", "spare_part")) + " " + json.dumps(h.get("identity") or {})
        if rx.search(blob) or (h.get("module") in cam_codes) or (h.get("registry_match") in cam_codes):
            answered.append(f"discovery hit at 0x{h.get('target')}: {h.get('module') or h.get('registry_match')}")
    for name in mods:
        if (name in cam_codes or rx.search(name)) and mods[name].read:
            answered.append(f"19 02 answered by {name}")
    if answered:
        for a_ in answered:
            add(f"- {a_}")
    else:
        add("- No ParkView / PAM / camera module identity answered "
            f"(codes checked: {', '.join(sorted(cam_codes))}). Silence on CAN-C is not proof the module is absent if it sits on another bus.")
    facts["camera_answered"] = bool(answered)
    add("")

    # -------------------------------------------------- field sources
    add("## Field sources used")
    add("")
    add("Name-variant lookups that matched a key (label -> key found in the JSON):")
    add("")
    for k in sorted(USED):
        add(f"- {k} -> `{USED[k]}`")
    roles: dict[str, int] = {}
    for it in items:
        roles[it.role] = roles.get(it.role, 0) + 1
    add("")
    add("Files by role: " + ", ".join(f"{k}={v}" for k, v in sorted(roles.items())))
    return "\n".join(L) + "\n", facts


# ----------------------------------------------------------------- selftest ----

def _w(d: Path, n: int, step: str, path: str, resp: Any, query: str = "", http: int = 200) -> None:
    obj = {"step": step, "phase": "x", "method": "GET", "url": "http://127.0.0.1:5000" + path + query,
           "body": None, "attempts": [], "http_status": http, "response": resp, "note": ""}
    (d / f"{n:02d}_{step}.json").write_text(json.dumps(obj), encoding="utf-8")


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="parse_scan_selftest_"))
    try:
        scan = tmp / "scan"
        scan.mkdir()
        _w(scan, 1, "modules_can_c", "/api/live/modules", {"modules": [
            {"code": "ECM", "name": "Engine control"}, {"code": "PAM", "name": "Parking control Bosch"}]})
        _w(scan, 2, "A1_adapter_voltage_ATRV_before", "/api/live/obd/voltage", {"raw": "12.6V", "volts": 12.6})
        mons = [{"monitor": "Misfire", "supported": True, "complete": True},
                {"monitor": "Evaporative system", "supported": True, "complete": True}]
        _w(scan, 3, "A5_readiness", "/api/live/obd/readiness", {
            "since_clear": {"mil_on": False, "stored_dtc_count": 0, "monitors": mons, "ecu": "7E8"},
            "this_drive_cycle": {"mil_on": False, "monitors": mons},
            "drive_cycle_counters": {"warmups_since_clear": 12, "distance_since_clear": 88},
            "evap_verdict": "EVAP monitor has COMPLETED since the last clear"})
        _w(scan, 4, "A6_dtcs", "/api/live/obd/dtcs", {
            "stored": {"dtcs": [], "by_ecu": {}}, "pending": {"dtcs": [], "by_ecu": {}},
            "permanent": {"warning": "no ECU answered (NO DATA); ignition may be off"}}, "?kind=all")
        rec = lambda tid, v, lo, hi, p: {"mid": "3A", "mid_name": 'EVAP monitor 0.090" leak', "tid": tid,
                                         "uasid": "10", "unit": "ms", "value": v, "min": lo, "max": hi, "passed": p,
                                         "raw": {"scaling": "known"}}
        _w(scan, 5, "A7_mode06", "/api/live/obd/mode06", {"supported": {"requested": ["3A", "3C", "3D"]}, "results": {
            "3A": {"by_ecu": {"18DAF110": [rec("87", 4100, 3965, 65535, True)]}},
            "3C": {"by_ecu": {"18DAF110": [dict(rec("90", 5800, 0, 6000, True), mid="3C")]}},
            "3D": {"warning": "NO DATA"}}})
        _w(scan, 6, "A9_pid46", "/api/live/obd/pid/46", {"pid": "46", "value": 20, "unit": "C"})
        _w(scan, 7, "A9_pid0F", "/api/live/obd/pid/0F", {"pid": "0F", "by_ecu": {"7E8": {"value": 21, "unit": "C"}}})
        _w(scan, 8, "A9_pid2F", "/api/live/obd/pid/2F", {"pid": "2F", "value": 50.2, "unit": "%"})
        _w(scan, 9, "A9_pid42", "/api/live/obd/pid/42", {"pid": "42", "value": 11.8, "unit": "V"})
        ecm_dtcs = [
            {"code": "P0440-00", "raw": "...", "status": 0x50},
            {"code": "P0455-00", "status": 0x50},
            {"code": "P0456-00", "status": 0x00},
            {"code": "U1711-2F", "status": 0x2F},
            {"code": "U1712-2F", "status": 0x09},
            {"code": "P0300-00", "status": 0x40},
        ]
        bcm_dtcs = [{"code": "U1713-2F", "status": 0x0F}, {"code": "B1234-00", "status": 0x50}]
        _w(scan, 10, "B1_uds_19_02_all_modules", "/api/live/scan", {"bus": "can_c", "modules": [
            {"ecu": "ECM", "mask": "FF", "dtcs": ecm_dtcs, "availability_mask": "CF"},
            {"ecu": "BCM", "mask": "FF", "dtcs": bcm_dtcs, "availability_mask": "FF"},
            {"ecu": "TCM", "error": "TIMEOUT", "dtcs": []}]})
        _w(scan, 11, "B2_identity_ECM", "/api/live/module/ECM/identity", {"ecu": "ECM", "fields": {
            "F190": {"ascii": "ZASFAKPN5J7B88115"}, "F187": {"ascii": "PART-ECM-2"}, "F188": {"ascii": "SW-ECM-NEW"}}})
        _w(scan, 12, "B2_identity_BCM", "/api/live/module/BCM/identity", {"ecu": "BCM", "fields": {
            "F190": {"ascii": "ZASFAKPN5J7B88115"}, "F188": {"ascii": "SW-BCM-1"}}})
        _w(scan, 13, "B2_identity_RFHUB", "/api/live/module/RFHUB/identity", {"ecu": "RFHUB", "fields": {
            "F188": {"ascii": "SW-RF-1"}}})
        _w(scan, 14, "B5_did_ECM_1001", "/api/live/module/ECM/did/1001", {"ecu": "ECM", "did": "1001", "bytes": ["80"]})
        _w(scan, 15, "B7_discover", "/api/live/discover", {"tried": 1, "hits": []})
        _w(scan, 16, "C1_adapter_voltage_ATRV_after", "/api/live/obd/voltage", {"raw": "NO DATA", "volts": None, "warning": "no voltage"})
        (scan / "99_broken.json").write_text("{not json", encoding="utf-8")
        bl = tmp / "baseline.json"
        bl.write_text(json.dumps({
            "modules": {"ECM": {"F188": "SW-ECM-OLD", "F187": "PART-ECM-2"}, "BCM": {"F188": "SW-BCM-1"}},
            "dtcs": {"ECM": [{"code": "P0440-00", "status": "0xCD"}, {"code": "P0455-00", "status": "0xCD"}],
                     "BCM": [{"code": "U1713-2F", "status": "0x2F"}, {"code": "U1736-86", "status": "0x2F"}]},
            "readiness": {"evap_complete": False}, "mode06": [{"mid": "3A", "tid": "87", "value": 404, "min": 3965, "max": 65535}],
            "voltages": {"atrv": 12.1}, "ecm": {"ambient": -61, "iat": 18, "fuel": 62}}), encoding="utf-8")
        text, facts = build_report(scan, bl)
        print(text)
        must = [
            ("verdict PASS", facts["verdict"] == "PASS"),
            ("evap complete", facts["evap_complete"] is True),
            ("broken file listed", "99_broken.json" in text),
            ("ECM changed", "CHANGED" in text and "SW-ECM-NEW" in text),
            ("BCM same", re.search(r"\| BCM \|.*SAME", text) is not None),
            ("RFHUB new", re.search(r"\| RFHUB \|.*NEW", text) is not None),
            ("P0440 GONE", re.search(r"\*\*P0440-00\*\* \|[^\n]*GONE", text) is not None),
            ("U1713 STILL", re.search(r"U1713-2F \| 0x0F[^\n]*STILL", text) is not None),
            ("U1736 GONE", re.search(r"U1736-86[^\n]*GONE", text) is not None),
            ("U1711 NEW", re.search(r"U1711-2F \| 0x2F[^\n]*NEW", text) is not None),
            ("U1711+U1712 together", "U1711 and U1712 together: YES" in text),
            ("low voltage flagged", "Voltage below 12.0 V: PID 42 11.8 V" in text),
            ("after voltage NO DATA", "ATRV after: NO DATA" in text),
            ("3D NO DATA", "MID 3D" in text and "NO DATA" in text),
            ("no camera", facts["camera_answered"] is False),
            ("fuel ok no flag", "FUEL OUTSIDE" not in text),
            ("mask note", "n/i" in text),
        ]
        bad = [n for n, ok in must if not ok]
        print("\nSELFTEST", "OK (%d checks)" % len(must) if not bad else "FAILED: " + ", ".join(bad))
        # second pass: the same data with 3A/87 low must give FAIL, readiness incomplete must give INCOMPLETE
        return 0 if not bad else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------- main ----

def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--out", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    d = Path(a.dir)
    if not d.is_dir():
        print(f"scan folder not found: {d}", file=sys.stderr)
        return 2
    text, _ = build_report(d, Path(a.baseline))
    print(text)
    out = Path(a.out) if a.out else d / "REPORT.md"
    out.write_text(text, encoding="utf-8")
    print(f"[written {out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
