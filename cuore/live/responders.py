"""Responder records: who answered a discovery sweep, what they said they are,
and which MES-log module that most plausibly is.

Discovery (``POST /live/discover``, :mod:`discover11`) finds nodes that answer
``22 F190`` / ``3E 00`` but several of them (DTCM at 18DA29F1, ESM, DASM, AFLS,
PAM, HALF) never got a name in the modules table. This module keeps the three
steps apart so a human decides each one:

* :func:`record_sweep` -- right after a sweep, in the same session, read the
  ISO 14229 Annex C identity set from every responder (read-only ``22``) and
  store it with the address in ``<state>/responders.json``.
* :func:`name_responders` -- NO car contact. Compare each responder's identity
  strings with the per-module strings MultiEcuScan printed in its
  ``SCAN_*.txt`` / ``FESLog_*.txt`` (ISO code, hardware / software number,
  spare part number, drawing number, serial), and *propose* a module with the
  log and line cited. Never promotes anything.
* :func:`accept_responder` -- NO car contact. The owner's decision: promote
  one address to ``confirmed (owner)`` in the persisted modules table
  (``addresses.json``, which :func:`uds.resolve_module` reads).

The MES encrypted database is never opened; only the plain-text logs.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import store
from .addressing import by_code
from .config import state_dir
from .errors import BadCommand
from .identify import MIN_TOKEN, normalise

MES_DIR = Path(r"C:\Program Files (x86)\MultiEcuScan")
PROPOSED = "proposed by MES log match"
OWNER_CONFIRMED = "confirmed (owner)"

#: ISO 14229 Annex C identity DIDs behind GET /live/module/{code}/identity
#: (same set and order as :func:`uds.identity`).
ANNEX_C_DIDS: tuple[int, ...] = (0xF190, 0xF187, 0xF188, 0xF189, 0xF18C, 0xF191, 0xF192, 0xF194,
                                 0xF195)

_LOCK = threading.RLock()


def path() -> Path:
    return state_dir() / "responders.json"


def _load() -> dict[str, Any]:
    try:
        d = json.loads(path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict[str, Any]) -> None:
    p = path()
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _norm_address(address: str) -> str:
    a = str(address).strip().upper().replace("0X", "")
    if len(a) <= 2:
        return a.zfill(2)
    return a


def upsert(vin: str, rec: dict[str, Any]) -> dict[str, Any]:
    """Insert/refresh one responder record under ``vin`` keyed by its request id."""
    key = rec["address"]
    now = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        data = _load()
        cur = data.setdefault(vin or "UNKNOWN", {}).get(key, {})
        merged_id = dict(cur.get("identity") or {})
        for did, v in (rec.get("identity") or {}).items():
            if v and (v.get("ascii") or v.get("hex")):
                merged_id[did] = v
        out = {**cur, **{k: v for k, v in rec.items() if k != "identity"}, "identity": merged_id,
               "first_seen": cur.get("first_seen") or now, "last_seen": now,
               "sweeps": int(cur.get("sweeps") or 0) + 1}
        data[vin or "UNKNOWN"][key] = out
        _save(data)
    return out


def list_responders(vin: str = "") -> dict[str, Any]:
    data = _load()
    if vin:
        data = {vin: data.get(vin, {})}
    return {"path": str(path()), "responders": data}


# --- (a) record after a sweep -----------------------------------------------------

def _did_hex_ascii(q: dict[str, Any], did: str) -> Optional[dict[str, str]]:
    from .uds import _ascii, _did_reply
    payload, _nrc = _did_reply(q, did)
    if not payload:
        return None
    return {"ascii": _ascii(payload), "hex": " ".join(b.upper() for b in payload)}


def read_annex_c(sess: Any, request_hex: str, response_hex: str, *, timeout: float = 0.5,
                 cap_s: float = 8.0) -> dict[str, dict[str, str]]:
    """Read-only ``22`` of the Annex C set at one already-known address pair."""
    from .safety import assert_read_only_uds
    sess.target_raw(request_hex, response_hex)
    t0 = time.monotonic()
    out: dict[str, dict[str, str]] = {}
    for did in ANNEX_C_DIDS:
        if time.monotonic() - t0 > cap_s:
            break
        assert_read_only_uds(0x22, did.to_bytes(2, "big"))
        q = sess.query(f"22{did:04X}", "62", timeout)
        if q.get("error") and q["error"] != "TIMEOUT":
            break
        got = _did_hex_ascii(q, f"{did:04X}")
        if got:
            out[f"{did:04X}"] = got
    return out


def record_sweep(sess: Any, result: dict[str, Any], vin: str = "", *,
                 read_more: bool = True) -> dict[str, Any]:
    """Store a responder record for every real hit in a discovery ``result``.

    29-bit hits (``uds.discover``): the Annex C set is read again at the hit's
    address (hex and ASCII) and merged with what the sweep already read.
    11-bit hits (``discover11``): stored as returned. Never raises.
    """
    stored: list[str] = []
    try:
        for hit in result.get("hits") or []:
            if hit.get("error") or not hit.get("request"):
                continue
            ident = {d: {"ascii": a, "hex": ""} for d, a in (hit.get("identity") or {}).items() if a}
            if hit.get("vin"):
                ident["F190"] = {"ascii": hit["vin"], "hex": ""}
            is29 = len(str(hit["request"])) == 8
            if is29 and read_more:
                try:
                    ident.update(read_annex_c(sess, hit["request"], hit["response"]))
                except Exception as e:  # noqa: BLE001  -- a failed read must not lose the hit
                    hit["responder_read_error"] = f"{type(e).__name__}: {e}"
            car = hit.get("vin") or vin or ""
            rec = {"address": str(hit["request"]).upper(), "request": hit["request"],
                   "response": hit.get("response"), "bus": result.get("bus"),
                   "cable": result.get("cable"), "kind": "29bit" if is29 else "11bit",
                   "target": hit.get("target") if is29 else None, "identity": ident,
                   "vin_reported": hit.get("vin") or None, "vin_expected": vin or None,
                   "table_module": hit.get("module") or hit.get("registry_match")}
            upsert(car, rec)
            stored.append(rec["address"])
        if hasattr(sess, "untarget"):
            sess.untarget()
    except Exception as e:  # noqa: BLE001
        return {"stored": stored, "error": f"{type(e).__name__}: {e}"}
    return {"stored": stored, "path": str(path())}


# --- (b) parse the MES logs -----------------------------------------------------------

_FIELD = re.compile(r"^\s*([A-Za-z][A-Za-z ()/]*?)\s*:\s*(.*?)\s*$")
_VER = re.compile(r"\s+-\s+Ver:\s*\S+\s*$", re.I)
_FIELDS = {"iso code": "iso", "ecu iso code": "iso", "hardware number": "hw", "software number": "sw",
           "spare part number": "spare", "fiat drawing number": "drawing",
           "ecu serial number": "serial", "vin code": "vin"}
_SCAN_HDR = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*/\s*(.+)$")


def _new(kind: str, line: int, section: str, title: str, header: str) -> dict[str, Any]:
    return {"kind": kind, "line": line, "section": section, "title": title, "header": header,
            "fields": {}, "lines": {}}


def parse_scan_text(text: str, fname: str) -> list[dict[str, Any]]:
    """Module blocks of one SCAN_*.txt: ``Section / CODE (Long name)`` then the
    module title, ISO Code, VIN code, Hardware number, Software number."""
    out: list[dict[str, Any]] = []
    cur: Optional[dict[str, Any]] = None
    lines = text.splitlines()
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s:
            cur = None
            continue
        m = _FIELD.match(s)
        if cur is not None and m and m.group(1).strip().lower() in _FIELDS:
            key = _FIELDS[m.group(1).strip().lower()]
            val = _VER.sub("", m.group(2)).strip() if key in ("hw", "sw") else m.group(2).strip()
            cur["fields"][key] = val
            cur["lines"][key] = i
            continue
        nxt = lines[i].strip() if i < len(lines) else ""
        h = _SCAN_HDR.match(s)
        if h and nxt and not _FIELD.match(nxt) and not s.endswith("."):
            cur = _new("SCAN", i, h.group(1).strip(), nxt, s)
            cur["file"] = fname
            out.append(cur)
            continue
    for b in out:
        head = _SCAN_HDR.match(b["header"])
        code_part = head.group(2).split("(")[0].strip() if head else ""
        b["codes"] = [c.strip().upper() for c in code_part.split("/") if c.strip()]
    return out


def parse_fes_text(text: str, fname: str) -> list[dict[str, Any]]:
    """One FESLog_*.txt = one module: title is the line above the dashed rule."""
    lines = text.splitlines()
    rule = next((i for i, l in enumerate(lines) if l.strip().startswith("-----")), None)
    if rule is None or rule < 1:
        return []
    blk = _new("FES", rule, "", lines[rule - 1].strip(), lines[rule - 1].strip())
    blk["file"] = fname
    blk["codes"] = []
    for i, raw in enumerate(lines[rule + 1:], rule + 2):
        if raw.strip().upper().startswith("READING ERROR CODES"):
            break
        m = _FIELD.match(raw)
        if m and m.group(1).strip().lower() in _FIELDS:
            blk["fields"][_FIELDS[m.group(1).strip().lower()]] = m.group(2).strip()
            blk["lines"][_FIELDS[m.group(1).strip().lower()]] = i
    return [blk] if blk["fields"] else []


def load_mes_modules(vin: str, logs_dir: Optional[Path] = None) -> dict[str, Any]:
    """Every module block in the plain-text MES logs that belongs to ``vin``,
    newest log first. A block with its own VIN line must match; a block with
    none is kept only when another block of the same log carries ``vin``."""
    d = Path(logs_dir) if logs_dir else MES_DIR
    files = sorted([p for p in d.glob("*.txt")
                    if p.name.startswith(("SCAN_", "FESLog_"))], key=lambda p: p.name, reverse=True) \
        if d.is_dir() else []
    blocks: list[dict[str, Any]] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        got = parse_scan_text(text, p.name) if p.name.startswith("SCAN_") else parse_fes_text(text, p.name)
        log_has_vin = any(b["fields"].get("vin", "").upper() == vin.upper() for b in got)
        for b in got:
            v = b["fields"].get("vin", "").upper()
            if (v and v == vin.upper()) or (not v and log_has_vin):
                blocks.append(b)
    return {"dir": str(d), "files_scanned": len(files), "blocks": blocks}


def _label(b: dict[str, Any]) -> str:
    """Module name MES uses: SCAN header code if CUORE knows one, else the first
    code token, else the FES title."""
    for c in b.get("codes") or []:
        if by_code(c) is not None:
            return c
    if b.get("codes"):
        return b["codes"][0]
    return ""


def _mes_modules(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group blocks by (label, hw, sw); each group lists its log sources, newest first."""
    from .addressing import MODULES
    hw_to_code: dict[str, str] = {}
    for b in blocks:
        if b["kind"] == "SCAN" and _label(b) and b["fields"].get("hw"):
            hw_to_code[normalise(b["fields"]["hw"])] = _label(b)
    for m in MODULES:
        if m.hw_number:
            hw_to_code.setdefault(normalise(m.hw_number), m.code)
    groups: dict[tuple, dict[str, Any]] = {}
    for b in blocks:
        code = _label(b) or hw_to_code.get(normalise(b["fields"].get("hw", "")), "")
        key = (code or b["title"], normalise(b["fields"].get("hw")), normalise(b["fields"].get("sw")))
        g = groups.setdefault(key, {"code": code or None, "name": b["title"], "fields": {},
                                    "sources": {}})
        for f, v in b["fields"].items():
            if f == "vin":
                continue
            g["fields"].setdefault(f, v)
            g["sources"].setdefault(f, []).append({"log": b["file"], "line": b["lines"].get(f),
                                                   "text": v})
        if code and not g["code"]:
            g["code"] = code
    return list(groups.values())


def _tokens(identity: dict[str, dict[str, str]]) -> list[tuple[str, str, str]]:
    """(did, normalised ascii, compact hex) per identity DID."""
    out = []
    for did, v in identity.items():
        out.append((did, normalise(v.get("ascii")), re.sub(r"[^0-9A-F]", "", (v.get("hex") or "").upper())))
    return out


def _match_group(identity: dict[str, dict[str, str]], g: dict[str, Any]) -> list[dict[str, Any]]:
    ev: list[dict[str, Any]] = []
    toks = _tokens(identity)
    for field, val in g["fields"].items():
        is_iso = field == "iso"
        want = re.sub(r"[^0-9A-F]", "", val.upper()) if is_iso else normalise(val)
        if len(want) < MIN_TOKEN:
            continue
        for did, asc, hx in toks:
            got = hx if is_iso else asc
            if len(got) < MIN_TOKEN:
                continue
            if got == want or (not is_iso and (want in got or got in want)):
                src = (g["sources"].get(field) or [{}])[0]
                ev.append({"mes_field": field, "mes_value": val, "did": did, "reported": got,
                           "exact": got == want, "log": src.get("log"), "line": src.get("line"),
                           "also_in_logs": len(g["sources"].get(field) or []) - 1})
                break
    return ev


def name_responders(vin: str, *, logs_dir: Optional[Path] = None,
                    responders: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Propose a module name for each stored responder from MES log strings.

    Read-only on files; no car contact; never changes the modules table.
    """
    recs = responders if responders is not None else (_load().get(vin) or {})
    mes = load_mes_modules(vin, logs_dir)
    groups = _mes_modules(mes["blocks"])
    confirmed = store.confirmed_targets(vin)
    rows: list[dict[str, Any]] = []
    claimed: dict[str, list[str]] = {}
    for addr, rec in sorted(recs.items()):
        ident = rec.get("identity") or {}
        scored = []
        for g in groups:
            ev = _match_group(ident, g)
            if ev:
                score = sum(1.0 if e["exact"] else 0.5 for e in ev)
                scored.append((score, g, ev))
        scored.sort(key=lambda s: -s[0])
        row: dict[str, Any] = {"address": addr, "target": rec.get("target"), "bus": rec.get("bus"),
                               "identity": {d: v.get("ascii") for d, v in ident.items()}}
        if rec.get("accepted"):
            row["status"] = OWNER_CONFIRMED
            row["module"] = rec["accepted"].get("module")
            rows.append(row)
            continue
        if not scored:
            row.update(status="no MES log match", module=None,
                       reason=("no hardware/software/spare/drawing/ISO string in the responder's "
                               f"identity matches a {vin} module in {mes['files_scanned']} MES logs"
                               if ident else "no identity strings stored for this responder yet"))
            rows.append(row)
            continue
        top = scored[0][0]
        leaders = [s for s in scored if s[0] == top]
        names = {(s[1]["code"] or s[1]["name"]) for s in leaders}
        if len(names) > 1:
            row.update(status="ambiguous", module=None,
                       reason="identity matches several MES modules equally: " + ", ".join(sorted(names)),
                       candidates=[{"module": s[1]["code"], "name": s[1]["name"], "evidence": s[2]}
                                   for s in leaders])
            rows.append(row)
            continue
        score, g, ev = leaders[0]
        strong = score >= 2 or any(e["exact"] and e["mes_field"] in ("hw", "sw", "spare", "drawing")
                                   for e in ev)
        module = g["code"]
        parts = [f"{e['mes_field']} '{e['mes_value']}' = responder {e['did']} '{e['reported']}'"
                 f"{'' if e['exact'] else ' (partial)'} -- {e['log']} line {e['line']}" for e in ev]
        row.update(status=PROPOSED, module=module, mes_name=g["name"], strong=strong,
                   evidence=ev,
                   reason=f"MES prints '{g['name']}'"
                          f"{' as ' + module if module else ' (CUORE code not derivable from the log)'}"
                          f" with " + "; ".join(parts))
        if module:
            claimed.setdefault(module, []).append(addr)
            m = by_code(module)
            if m is None:
                row["note"] = f"{module} is not a code in the CUORE modules table"
            else:
                if rec.get("bus") and m.bus_key != rec["bus"]:
                    row["note"] = f"table has {module} on {m.bus_key}, responder was found on {rec['bus']}"
                have = confirmed.get(module)
                if have is not None and rec.get("target") and f"{have:02X}" != rec["target"]:
                    row["note"] = (row.get("note", "") + f" table already confirms {module} at "
                                   f"{have:02X}, not {rec['target']}").strip()
        rows.append(row)
    for r in rows:
        if r.get("status") == PROPOSED and r.get("module") and len(claimed.get(r["module"], [])) > 1:
            r["note"] = (r.get("note", "") + " also proposed for "
                         + ", ".join(a for a in claimed[r["module"]] if a != r["address"])).strip()
    return {"vin": vin, "mes_logs_dir": mes["dir"], "mes_logs_scanned": mes["files_scanned"],
            "mes_module_blocks": len(mes["blocks"]), "responders": rows,
            "note": "proposals only; nothing is promoted until accept_responder"}


# --- (c) owner acceptance ------------------------------------------------------------

def accept_responder(vin: str, address: str, module: str) -> dict[str, Any]:
    """Promote one responder's 29-bit target to ``confirmed (owner)`` for ``module``."""
    if not vin:
        raise BadCommand("vin is required")
    code = module.strip().upper()
    if by_code(code) is None:
        raise BadCommand(f"unknown module code {module!r}")
    want = _norm_address(address)
    with _LOCK:
        data = _load()
        recs = data.get(vin) or {}
        key = next((k for k, r in recs.items()
                    if k == want or (want and r.get("target") == want)), None)
        if key is None:
            raise BadCommand(f"no stored responder {address!r} for {vin}; run a discovery sweep first")
        rec = recs[key]
        if rec.get("kind") != "29bit" or not rec.get("target"):
            raise BadCommand("only 29-bit (18DAxxF1) responders can be promoted; this one is recorded "
                             "but the modules table has no field for an 11-bit pair")
        target = int(rec["target"], 16)
        before = store.confirmed_targets(vin)
        store.confirm_target(vin, code, target, source=OWNER_CONFIRMED)
        rec["accepted"] = {"module": code, "status": OWNER_CONFIRMED,
                           "at": datetime.now().isoformat(timespec="seconds")}
        _save(data)
    others = sorted(c for c, t in store.confirmed_targets(vin).items() if t == target and c != code)
    out = {"vin": vin, "address": key, "target": rec["target"], "module": code,
           "status": OWNER_CONFIRMED, "previous_target": (f"{before[code]:02X}" if code in before else None)}
    if others:
        out["warning"] = f"target {rec['target']} is also confirmed for {', '.join(others)}"
    return out


__all__ = ["ANNEX_C_DIDS", "path", "upsert", "list_responders", "record_sweep", "read_annex_c",
           "parse_scan_text", "parse_fes_text", "load_mes_modules", "name_responders",
           "accept_responder", "PROPOSED", "OWNER_CONFIRMED"]
