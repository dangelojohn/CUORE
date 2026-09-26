"""Reconstruct what wiTECH asked and heard, from a passive capture alone.

Nothing here talks to the adapter. Given the frame list :func:`capture.listen`
already returns (``[{"t", "id", "data"}]`` with headers on, ``data`` the
concatenated hex bytes of one raw CAN frame -- see :mod:`framing`), this
module rebuilds the ISO-TP messages, pairs UDS requests with responses,
groups per-(target, DID) time series, and correlates those series against
what a technician noted on wiTECH's own data display.

Addressing is generic 29-bit physical, per :mod:`addressing`: a request is
``18DA<TA><SA>`` and its response is the same two bytes swapped,
``18DA<SA><TA>``. The tester byte is whatever wiTECH used -- never assumed to
be ``F1``.

Pure functions, stdlib only.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Optional

_ID_RE = re.compile(r"^18DA([0-9A-F]{2})([0-9A-F]{2})$")

#: UDS service IDs that appear on the *request* side. A response is either
#: ``0x7F`` (negative) or ``request + 0x40`` (positive) -- this is what lets
#: pairing work without knowing in advance which byte is the tester.
REQUEST_SERVICES: frozenset[int] = frozenset({
    0x10, 0x11, 0x14, 0x19, 0x1A, 0x22, 0x23, 0x24, 0x27, 0x28, 0x29, 0x2A,
    0x2C, 0x2E, 0x2F, 0x31, 0x34, 0x35, 0x36, 0x37, 0x38, 0x3D, 0x3E, 0x85,
})

#: Services this module decodes DIDs for. Everything else is paired and kept
#: raw, per the spec ("only read services decoded").
_READ_SERVICES: frozenset[int] = frozenset({0x22, 0x2E})


# ===========================================================================
# ISO-TP reassembly
# ===========================================================================

def isotp_reassemble(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild ISO-TP messages per CAN ID from raw ``capture.listen`` frames.

    PCI types: ``0N`` single frame of N bytes, ``1N NN`` first frame with a
    12-bit length, ``2N`` consecutive frame (sequence number ignored --
    passive capture cannot lose frames the way a live bus can drop them, and
    nothing here needs to detect that), ``3N`` flow control (ignored: this
    tool never transmits and flow control from the real tester is not a
    payload). Interleaved IDs are tracked independently: one pending
    assembly per CAN ID.

    A new single/first frame that arrives while an assembly for that ID is
    still incomplete drops the old one (counted). Anything still incomplete
    when the frame list ends is dropped the same way.

    Returns ``{"messages": [{"t", "id", "data"}, ...], "dropped": int}``,
    messages sorted by ``t``. ``data`` is a list of hex byte strings.
    """
    pending: dict[str, dict[str, Any]] = {}
    messages: list[dict[str, Any]] = []
    dropped = 0

    for f in sorted(frames, key=lambda x: x["t"]):
        hdr = f["id"]
        raw = str(f.get("data") or "")
        if len(raw) < 2:
            continue
        b = [raw[i:i + 2] for i in range(0, len(raw) - 1, 2)]
        if not b:
            continue
        pci = int(b[0], 16)
        ftype = pci >> 4

        if ftype == 0:
            if hdr in pending:
                dropped += 1
                del pending[hdr]
            n = pci & 0x0F
            data = b[1:1 + n] if n else b[1:]
            messages.append({"t": f["t"], "id": hdr, "data": data})
        elif ftype == 1:
            if len(b) < 2:
                continue
            if hdr in pending:
                dropped += 1
            expected = ((pci & 0x0F) << 8) | int(b[1], 16)
            pending[hdr] = {"expected": expected, "data": list(b[2:]), "t": f["t"]}
        elif ftype == 2:
            st = pending.get(hdr)
            if st is None:
                continue  # orphan consecutive frame, no first frame seen -- ignore
            st["data"].extend(b[1:])
            if len(st["data"]) >= st["expected"]:
                messages.append({"t": st["t"], "id": hdr, "data": st["data"][:st["expected"]]})
                del pending[hdr]
        else:
            continue  # flow control (3N) or reserved -- never a payload

    dropped += len(pending)
    messages.sort(key=lambda m: m["t"])
    return {"messages": messages, "dropped": dropped}


# ===========================================================================
# UDS request/response pairing
# ===========================================================================

def _split_multi_did(payload: list[str], dids: list[int]
                     ) -> Optional[list[tuple[int, list[str]]]]:
    """Split a multi-DID ``0x22`` response into ``[(did, data), ...]``.

    Data lengths are unknown, so every way of cutting the response so that
    each DID's two echoed bytes land exactly where expected is tried. The
    split is used only when it is unique; more than one valid cut (or none)
    means the boundary is genuinely ambiguous from this data alone.
    """
    did_hex = [f"{d:04X}" for d in dids]
    n = len(payload)
    results: list[list[tuple[int, list[str]]]] = []

    def rec(pos: int, idx: int, acc: list[tuple[int, list[str]]]) -> None:
        if len(results) > 1:
            return
        if idx == len(dids):
            if pos == n:
                results.append(list(acc))
            return
        if pos + 2 > n or payload[pos] + payload[pos + 1] != did_hex[idx]:
            return
        min_remaining = 2 * (len(dids) - idx - 1)
        max_data_len = n - (pos + 2) - min_remaining
        for dl in range(0, max(0, max_data_len) + 1):
            rec(pos + 2 + dl, idx + 1, acc + [(dids[idx], payload[pos + 2:pos + 2 + dl])])
            if len(results) > 1:
                return

    rec(0, 0, [])
    return results[0] if len(results) == 1 else None


def _decode_read(tr: dict[str, Any], req_data: list[str], resp_data: list[str],
                 svc: int) -> None:
    if svc == 0x22:
        req_payload = req_data[1:]
        dids = [int(req_payload[k] + req_payload[k + 1], 16)
                for k in range(0, len(req_payload) - 1, 2)]
        resp_payload = resp_data[1:]
        if len(dids) == 1:
            dh = f"{dids[0]:04X}"
            tr["did"] = dh
            if len(resp_payload) >= 2 and resp_payload[0] + resp_payload[1] == dh:
                tr["data"] = resp_payload[2:]
            else:
                tr["data"] = resp_payload  # DID not echoed as expected -- keep raw
        elif len(dids) > 1:
            split = _split_multi_did(resp_payload, dids)
            if split is not None:
                tr["dids"] = [{"did": f"{d:04X}", "data": data} for d, data in split]
            else:
                tr["multi_did_raw"] = True
    elif svc == 0x2E:
        # WriteDataByIdentifier: the DID and the written value are in the
        # *request*; the response only echoes the DID.
        req_payload = req_data[1:]
        if len(req_payload) >= 2:
            tr["did"] = req_payload[0] + req_payload[1]
            tr["data"] = req_payload[2:]


def uds_transactions(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair UDS requests with responses, in time order.

    Each transaction: ``{t_req, t_resp, target, tester, service, request,
    response, nrc, did, data, dids, multi_did_raw}``. ``target``/``tester``
    are hex byte strings (``"10"``, ``"F1"``); ``did``/``data`` are set for a
    single-DID ``0x22``/``0x2E``; ``dids`` is a list of ``{"did","data"}``
    when a multi-DID ``0x22`` request could be split unambiguously;
    ``multi_did_raw`` is ``True`` when it could not be. A request with no
    matching response has ``t_resp``/``response`` as ``None``.
    """
    msgs = isotp_reassemble(frames)["messages"]
    used = [False] * len(msgs)
    out: list[dict[str, Any]] = []

    for i, m in enumerate(msgs):
        if used[i] or not m["data"]:
            continue
        mo = _ID_RE.match(m["id"])
        if not mo:
            continue
        svc = int(m["data"][0], 16)
        if svc not in REQUEST_SERVICES:
            continue
        ta, sa = mo.group(1), mo.group(2)
        resp_id = f"18DA{sa}{ta}"

        match_idx = None
        for j in range(i + 1, len(msgs)):
            if used[j] or msgs[j]["id"] != resp_id or not msgs[j]["data"]:
                continue
            rb = int(msgs[j]["data"][0], 16)
            if rb == 0x7F and len(msgs[j]["data"]) >= 2 and int(msgs[j]["data"][1], 16) == svc:
                match_idx = j
                break
            if rb == (svc + 0x40) & 0xFF:
                match_idx = j
                break

        tr: dict[str, Any] = {
            "t_req": m["t"], "t_resp": None, "target": ta, "tester": sa,
            "service": f"{svc:02X}", "request": m["data"], "response": None,
            "nrc": None, "did": None, "data": None, "dids": None,
            "multi_did_raw": False,
        }
        used[i] = True
        if match_idx is not None:
            used[match_idx] = True
            m2 = msgs[match_idx]
            tr["t_resp"] = m2["t"]
            tr["response"] = m2["data"]
            if int(m2["data"][0], 16) == 0x7F:
                tr["nrc"] = m2["data"][2] if len(m2["data"]) >= 3 else None
            elif svc in _READ_SERVICES:
                _decode_read(tr, m["data"], m2["data"], svc)
        out.append(tr)

    out.sort(key=lambda t: t["t_req"])
    return out


# ===========================================================================
# Per-DID time series
# ===========================================================================

def did_series(transactions: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """``{(target, did): [{"t", "bytes"}, ...]}`` in time order.

    ``target``/``did`` are hex strings (``"10"``, ``"1234"``). Both
    single-DID transactions and the individually-split entries of an
    unambiguous multi-DID transaction contribute.
    """
    series: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for tr in sorted(transactions, key=lambda t: t["t_req"]):
        t = tr["t_resp"] if tr["t_resp"] is not None else tr["t_req"]
        if tr.get("did") and tr.get("data") is not None:
            series[(tr["target"], tr["did"])].append({"t": t, "bytes": tr["data"]})
        for entry in (tr.get("dids") or []):
            series[(tr["target"], entry["did"])].append({"t": t, "bytes": entry["data"]})
    for pts in series.values():
        pts.sort(key=lambda p: p["t"])
    return dict(series)


# ===========================================================================
# Correlation against technician marks
# ===========================================================================

def _nearest(pts: list[dict[str, Any]], t: float) -> Optional[dict[str, Any]]:
    if not pts:
        return None
    return min(pts, key=lambda p: abs(p["t"] - t))


def _consistency(samples: list[tuple[Any, int]]) -> float:
    """1.0 when every label value maps to exactly one raw value and every
    label value maps to a *different* raw value; a partial score otherwise
    (the fraction of samples matching the modal raw value for their label)."""
    by_value: dict[Any, list[int]] = defaultdict(list)
    for lv, rv in samples:
        by_value[lv].append(rv)
    if len(by_value) < 2:
        return 0.0
    consistent = all(len(set(rvs)) == 1 for rvs in by_value.values())
    if consistent:
        reps = [rvs[0] for rvs in by_value.values()]
        if len(set(reps)) == len(reps):
            return 1.0
        return 0.6  # discriminates nothing -- same raw value regardless of label
    total = len(samples)
    correct = sum(Counter(rvs).most_common(1)[0][1] for rvs in by_value.values())
    return correct / total if total else 0.0


def _categorical_candidates(target: str, did: str, label: str, pts: list[dict[str, Any]],
                            marks: list[dict[str, Any]], max_len: int) -> list[dict[str, Any]]:
    cands: list[dict[str, Any]] = []
    for off in range(max_len):
        samples: list[tuple[Any, int]] = []
        ok = True
        for mk in marks:
            p = _nearest(pts, mk["t"])
            if p is None or off >= len(p["bytes"]):
                ok = False
                break
            samples.append((mk["value"], int(p["bytes"][off], 16)))
        if not ok:
            continue
        ev = [{"t": mk["t"], "value": mk["value"], "raw": rv}
              for mk, (_, rv) in zip(marks, samples)]
        cands.append({"target": target, "did": did, "label": label, "kind": "categorical",
                      "field": {"offset": off, "width": "byte"},
                      "score": _consistency(samples), "evidence": ev})
        for bit in range(8):
            bit_samples = [(lv, (rv >> bit) & 1) for lv, rv in samples]
            bev = [{"t": mk["t"], "value": mk["value"], "raw": rv}
                   for mk, (_, rv) in zip(marks, bit_samples)]
            cands.append({"target": target, "did": did, "label": label, "kind": "categorical",
                          "field": {"offset": off, "bit": bit},
                          "score": _consistency(bit_samples), "evidence": bev})
    for off in range(max_len - 1):
        samples = []
        ok = True
        for mk in marks:
            p = _nearest(pts, mk["t"])
            if p is None or off + 1 >= len(p["bytes"]):
                ok = False
                break
            v = (int(p["bytes"][off], 16) << 8) | int(p["bytes"][off + 1], 16)
            samples.append((mk["value"], v))
        if not ok:
            continue
        ev = [{"t": mk["t"], "value": mk["value"], "raw": rv}
              for mk, (_, rv) in zip(marks, samples)]
        cands.append({"target": target, "did": did, "label": label, "kind": "categorical",
                      "field": {"offset": off, "width": "u16"},
                      "score": _consistency(samples), "evidence": ev})
    return cands


def _linreg(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0
    scale = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    offset = my - scale * mx
    ss_res = sum((y - (scale * x + offset)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot == 0:
        return scale, offset, 1.0 if ss_res == 0 else 0.0
    return scale, offset, 1 - ss_res / ss_tot


def _numeric_candidates(target: str, did: str, label: str, pts: list[dict[str, Any]],
                        marks: list[dict[str, Any]], max_len: int) -> list[dict[str, Any]]:
    cands: list[dict[str, Any]] = []
    fields = [("byte", off, 1) for off in range(max_len)]
    fields += [("u16", off, 2) for off in range(max_len - 1)]
    for kind, off, width in fields:
        xs: list[float] = []
        ys: list[float] = []
        ev: list[dict[str, Any]] = []
        ok = True
        for mk in marks:
            p = _nearest(pts, mk["t"])
            if p is None or off + width > len(p["bytes"]):
                ok = False
                break
            raw = (int(p["bytes"][off], 16) if width == 1 else
                   (int(p["bytes"][off], 16) << 8) | int(p["bytes"][off + 1], 16))
            xs.append(raw)
            ys.append(mk["value"])
            ev.append({"t": mk["t"], "value": mk["value"], "raw": raw})
        if not ok or len(set(xs)) < 2:
            continue
        scale, offset, r2 = _linreg(xs, ys)
        cands.append({"target": target, "did": did, "label": label, "kind": "numeric",
                      "field": {"offset": off, "width": kind},
                      "scale": scale, "offset": offset, "score": r2, "r2": r2,
                      "evidence": ev})
    return cands


def correlate(series: dict[tuple[str, str], list[dict[str, Any]]],
             marks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank (target, did, field) candidates against technician-noted marks.

    ``marks``: ``[{"t", "label", "value"}, ...]``. Marks are grouped by
    ``label``; string values are treated categorically (every byte, every
    bit within a byte, and every 16-bit big-endian field are checked for a
    value that is the same whenever the label value repeats and different
    whenever it changes); numeric values get a linear least-squares fit
    (``value = scale*raw + offset``) over 1- and 2-byte fields, scored by
    R². Returns candidates sorted by score descending, each carrying its
    evidence (the raw byte(s) read back at each mark's nearest sample).
    """
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in marks:
        by_label[m["label"]].append(m)

    out: list[dict[str, Any]] = []
    for label, mks in by_label.items():
        numeric = all(isinstance(mk["value"], (int, float)) and not isinstance(mk["value"], bool)
                      for mk in mks)
        for (target, did), pts in series.items():
            if not pts:
                continue
            max_len = max(len(p["bytes"]) for p in pts)
            if max_len == 0:
                continue
            if numeric:
                out.extend(_numeric_candidates(target, did, label, pts, mks, max_len))
            else:
                out.extend(_categorical_candidates(target, did, label, pts, mks, max_len))
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


__all__ = ["isotp_reassemble", "uds_transactions", "did_series", "correlate",
           "REQUEST_SERVICES"]
