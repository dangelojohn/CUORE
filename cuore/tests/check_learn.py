"""Regression checks for cuore.live.learn / cuore.live.learned.

Same posture as ``cuore/tests/check_live.py``: plain script, ``check()``,
exit 1 on failure, no pytest, no mocking framework -- hand-built frame lists
in the exact shape :func:`cuore.live.capture.listen` returns them.

Run:
    .venv/Scripts/python.exe cuore/tests/check_learn.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: state must go to a throwaway directory.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-learn-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import learned  # noqa: E402
from cuore.live.learn import correlate, did_series, isotp_reassemble, uds_transactions  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


def frame(t: float, can_id: str, byte_list: list[str]) -> dict:
    return {"t": t, "id": can_id, "data": "".join(byte_list)}


def sf(byte_values: list[int]) -> list[str]:
    """Single-frame ISO-TP bytes: PCI 0N + N data bytes."""
    n = len(byte_values)
    assert n <= 7
    return [f"0{n:X}"] + [f"{v:02X}" for v in byte_values]


def ff(total_len: int, first_bytes: list[int]) -> list[str]:
    """First-frame ISO-TP bytes: PCI 1N NN (12-bit length) + up to 6 data bytes."""
    pci_hi = 0x10 | ((total_len >> 8) & 0x0F)
    pci_lo = total_len & 0xFF
    return [f"{pci_hi:02X}", f"{pci_lo:02X}"] + [f"{v:02X}" for v in first_bytes]


def cf(seq: int, more_bytes: list[int]) -> list[str]:
    """Consecutive-frame ISO-TP bytes: PCI 2N + up to 7 data bytes."""
    return [f"{0x20 | (seq & 0x0F):02X}"] + [f"{v:02X}" for v in more_bytes]


# ===========================================================================
# 1. isotp_reassemble
# ===========================================================================

# Single frame.
frames = [frame(0.0, "18DAF110", sf([0x62, 0xF1, 0x90]))]
r = isotp_reassemble(frames)
check_eq("isotp single frame: one message", len(r["messages"]), 1)
check_eq("isotp single frame: data", r["messages"][0]["data"], ["62", "F1", "90"])
check_eq("isotp single frame: no drops", r["dropped"], 0)

# Multi-frame: 10 total bytes, FF carries 6, one CF carries the last 4.
mf_frames = [
    frame(0.0, "18DAF110", ff(10, [0x62, 0x10, 0x05, 0x00, 0x00, 0x00])),
    frame(0.01, "18DAF110", cf(1, [0x00, 0x00, 0x00, 0x00])),
]
r = isotp_reassemble(mf_frames)
check_eq("isotp multi-frame: one message", len(r["messages"]), 1)
check_eq("isotp multi-frame: length", len(r["messages"][0]["data"]), 10)
check_eq("isotp multi-frame: starts at FF time", r["messages"][0]["t"], 0.0)
check_eq("isotp multi-frame: no drops", r["dropped"], 0)

# Interleaved IDs: two different ECUs' FF/CF frames woven together in time.
interleaved = [
    frame(0.00, "18DAF110", ff(10, [0x62, 0x10, 0x05, 0x00, 0x00, 0x00])),
    frame(0.01, "18DAF118", ff(9, [0x62, 0x20, 0x01, 0x00, 0x00, 0x00])),
    frame(0.02, "18DAF110", cf(1, [0x00, 0x00, 0x00, 0x00])),
    frame(0.03, "18DAF118", cf(1, [0x00, 0x00, 0x00])),
]
r = isotp_reassemble(interleaved)
check_eq("isotp interleaved: two messages", len(r["messages"]), 2)
by_id = {m["id"]: m for m in r["messages"]}
check_eq("isotp interleaved: F110 length", len(by_id["18DAF110"]["data"]), 10)
check_eq("isotp interleaved: F118 length", len(by_id["18DAF118"]["data"]), 9)
check_eq("isotp interleaved: no drops", r["dropped"], 0)

# Incomplete message (FF with no CF ever arriving) is dropped, counted.
incomplete = [frame(0.0, "18DAF110", ff(10, [0x62, 0x10, 0x05, 0x00, 0x00, 0x00]))]
r = isotp_reassemble(incomplete)
check_eq("isotp incomplete: no messages", len(r["messages"]), 0)
check_eq("isotp incomplete: one drop counted", r["dropped"], 1)

# A new first frame for the same ID while one is pending drops the old one.
superseded = [
    frame(0.0, "18DAF110", ff(10, [0x62, 0x10, 0x05, 0x00, 0x00, 0x00])),
    frame(0.05, "18DAF110", ff(10, [0x62, 0x10, 0x06, 0x00, 0x00, 0x00])),
    frame(0.06, "18DAF110", cf(1, [0x00, 0x00, 0x00, 0x00])),
]
r = isotp_reassemble(superseded)
check_eq("isotp superseded: one completed message", len(r["messages"]), 1)
check_eq("isotp superseded: one drop counted", r["dropped"], 1)


# ===========================================================================
# 2. uds_transactions: pairing, incl. NRC
# ===========================================================================

req_resp = [
    frame(1.000, "18DA10F1", sf([0x22, 0x12, 0x34])),
    frame(1.020, "18DAF110", sf([0x62, 0x12, 0x34, 0xAA, 0xBB])),
]
tx = uds_transactions(req_resp)
check_eq("uds_transactions: one transaction", len(tx), 1)
t0 = tx[0]
check_eq("uds_transactions: target", t0["target"], "10")
check_eq("uds_transactions: tester", t0["tester"], "F1")
check_eq("uds_transactions: service", t0["service"], "22")
check_eq("uds_transactions: did", t0["did"], "1234")
check_eq("uds_transactions: data", t0["data"], ["AA", "BB"])
check_eq("uds_transactions: nrc is None on positive", t0["nrc"], None)

# NRC 7F 22 31 (requestOutOfRange on a read-DID request).
nrc_frames = [
    frame(2.000, "18DA10F1", sf([0x22, 0x12, 0x34])),
    frame(2.015, "18DAF110", sf([0x7F, 0x22, 0x31])),
]
tx_nrc = uds_transactions(nrc_frames)
check_eq("uds_transactions NRC: one transaction", len(tx_nrc), 1)
check_eq("uds_transactions NRC: nrc byte", tx_nrc[0]["nrc"], "31")
check_eq("uds_transactions NRC: did unset (no positive data)", tx_nrc[0]["did"], None)

# A tester address other than F1 must pair correctly (never hard-coded).
other_tester = [
    frame(3.000, "18DA1005", sf([0x22, 0x12, 0x34])),
    frame(3.020, "18DA0510", sf([0x62, 0x12, 0x34, 0x01])),
]
tx_other = uds_transactions(other_tester)
check_eq("uds_transactions non-F1 tester: paired", len(tx_other), 1)
check_eq("uds_transactions non-F1 tester: tester byte", tx_other[0]["tester"], "05")
check_eq("uds_transactions non-F1 tester: data", tx_other[0]["data"], ["01"])

# Multi-DID request, unambiguous split (each DID's data length differs
# enough that the DID bytes only line up one way). Response payload (after
# the 0x62 service byte, 9 bytes total): DID1=1000 + 3 data bytes (AA BB CC),
# then DID2=1002 + 1 data byte (01). FF carries the first 6 payload bytes
# (service + DID1 + its 3 data bytes), one CF carries the last 3.
multi_frames = [
    frame(4.000, "18DA10F1", sf([0x22, 0x10, 0x00, 0x10, 0x02])),
    frame(4.020, "18DAF110", ff(9, [0x62, 0x10, 0x00, 0xAA, 0xBB, 0xCC])),
    frame(4.021, "18DAF110", cf(1, [0x10, 0x02, 0x01])),
]
tx_multi = uds_transactions(multi_frames)
check_eq("uds_transactions multi-DID: one transaction", len(tx_multi), 1)
dids_out = {d["did"]: d["data"] for d in (tx_multi[0]["dids"] or [])}
check_eq("uds_transactions multi-DID: DID1 data", dids_out.get("1000"), ["AA", "BB", "CC"])
check_eq("uds_transactions multi-DID: DID2 data", dids_out.get("1002"), ["01"])

# Request with no response at all.
lonely = [frame(5.0, "18DA10F1", sf([0x22, 0x12, 0x34]))]
tx_lonely = uds_transactions(lonely)
check_eq("uds_transactions lonely request: still recorded", len(tx_lonely), 1)
check_eq("uds_transactions lonely request: no response", tx_lonely[0]["response"], None)
check_eq("uds_transactions lonely request: t_resp None", tx_lonely[0]["t_resp"], None)


# ===========================================================================
# 3. did_series
# ===========================================================================

series = did_series(tx)
check("did_series: key present", ("10", "1234") in series)
check_eq("did_series: one point", len(series[("10", "1234")]), 1)
check_eq("did_series: point bytes", series[("10", "1234")][0]["bytes"], ["AA", "BB"])


# ===========================================================================
# 4. correlate: EVAP pressure switch -> byte 2 bit 0
# ===========================================================================
#
# DID 0x1234 on target 0x10, 4-byte payload. Byte 2 varies noisily (other
# unrelated flags in the same byte) but its bit 0 tracks Closed/Open exactly;
# no whole-byte or 16-bit field is consistent across the noisy values, so
# only the bit-level candidate should reach a perfect score.

switch_marks = [
    {"t": 1.0, "label": "EVAP pressure switch", "value": "Closed"},
    {"t": 2.0, "label": "EVAP pressure switch", "value": "Open"},
    {"t": 3.0, "label": "EVAP pressure switch", "value": "Closed"},
    {"t": 4.0, "label": "EVAP pressure switch", "value": "Open"},
]
switch_byte2 = {1.0: 0x01, 2.0: 0x00, 3.0: 0x05, 4.0: 0x02}  # bit0: 1,0,1,0

switch_frames = []
for mk in switch_marks:
    t = mk["t"]
    switch_frames.append(frame(t, "18DA10F1", sf([0x22, 0x12, 0x34])))
    b2 = switch_byte2[t]
    switch_frames.append(frame(t + 0.01, "18DAF110",
                               sf([0x62, 0x12, 0x34, 0x00, 0x00, b2, 0x00])))

switch_tx = uds_transactions(switch_frames)
check_eq("switch capture: 4 transactions", len(switch_tx), 4)
switch_series = did_series(switch_tx)
switch_candidates = correlate(switch_series, switch_marks)
check("switch correlate: candidates found", len(switch_candidates) > 0)
top = switch_candidates[0] if switch_candidates else {}
check_eq("switch correlate: top target", top.get("target"), "10")
check_eq("switch correlate: top did", top.get("did"), "1234")
check_eq("switch correlate: top score is perfect", top.get("score"), 1.0)
check_eq("switch correlate: top field is byte2 bit0", top.get("field"), {"offset": 2, "bit": 0})
n_perfect = sum(1 for c in switch_candidates if c["score"] == 1.0)
check_eq("switch correlate: exactly one perfect candidate", n_perfect, 1,
        str([c["field"] for c in switch_candidates if c["score"] == 1.0]))


# ===========================================================================
# 5. correlate: numeric fuel level -> scale/offset recovery
# ===========================================================================

fuel_marks = [
    {"t": 10.0, "label": "Fuel level", "value": 10.0},
    {"t": 20.0, "label": "Fuel level", "value": 42.5},
    {"t": 30.0, "label": "Fuel level", "value": 75.0},
]
# raw = value * 2  (scale 0.5, offset 0) -> 20, 85, 150, all fit one byte
fuel_frames = []
for mk in fuel_marks:
    t = mk["t"]
    raw = round(mk["value"] * 2)
    fuel_frames.append(frame(t, "18DA10F1", sf([0x22, 0x10, 0x05])))
    fuel_frames.append(frame(t + 0.01, "18DAF110", sf([0x62, 0x10, 0x05, raw])))

fuel_tx = uds_transactions(fuel_frames)
fuel_series = did_series(fuel_tx)
fuel_candidates = correlate(fuel_series, fuel_marks)
check("fuel correlate: candidates found", len(fuel_candidates) > 0)
fuel_top = fuel_candidates[0] if fuel_candidates else {}
check_eq("fuel correlate: top target/did", (fuel_top.get("target"), fuel_top.get("did")),
        ("10", "1005"))
check("fuel correlate: r2 near 1.0", abs(fuel_top.get("r2", 0.0) - 1.0) < 1e-6,
     repr(fuel_top.get("r2")))
check("fuel correlate: scale near 0.5", abs(fuel_top.get("scale", 0.0) - 0.5) < 1e-6,
     repr(fuel_top.get("scale")))
check("fuel correlate: offset near 0.0", abs(fuel_top.get("offset", 1.0) - 0.0) < 1e-6,
     repr(fuel_top.get("offset")))


# ===========================================================================
# 6. learned.py persistence round trip
# ===========================================================================

entry = learned.accept(
    VIN, "ECM", "1234", "EVAP pressure switch", {"offset": 2, "bit": 0},
    evidence=top.get("evidence"),
)
check_eq("learned.accept: confidence stamped", entry["confidence"], learned.CONFIDENCE)

got = learned.learned(VIN)
check_eq("learned.learned: vin key present", list(got.keys()), [VIN])
check_eq("learned.learned: one entry", len(got[VIN]), 1)
check_eq("learned.learned: round-tripped did", got[VIN][0]["did"], "1234")
check_eq("learned.learned: round-tripped field", got[VIN][0]["field"], {"offset": 2, "bit": 0})
check_eq("learned.learned: confidence text", got[VIN][0]["confidence"],
        "learned from wiTECH capture")

# Re-accepting the same (module, did, field) replaces, does not duplicate.
learned.accept(VIN, "ECM", "1234", "EVAP pressure switch (renamed)", {"offset": 2, "bit": 0})
got2 = learned.learned(VIN)
check_eq("learned.accept: replace not duplicate", len(got2[VIN]), 1)
check_eq("learned.accept: replaced name", got2[VIN][0]["name"], "EVAP pressure switch (renamed)")

# reject() records separately and does not disturb the accepted entry.
learned.reject(VIN, "ECM", "1234", {"offset": 0, "width": "byte"}, reason="pure noise")
got3 = learned.learned(VIN)
check_eq("learned.reject: appended alongside accepted", len(got3[VIN]), 2)
statuses = sorted(e["status"] for e in got3[VIN])
check_eq("learned.reject: one accepted one rejected", statuses, ["accepted", "rejected"])

# Actually persisted to disk, not just held in memory.
check("learned.path: file exists on disk", learned.path().exists())
raw_json = learned.path().read_text(encoding="utf-8")
check("learned.path: VIN present in raw file", VIN in raw_json)


# ===========================================================================
# report
# ===========================================================================

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
