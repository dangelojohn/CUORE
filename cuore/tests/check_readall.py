"""Checks for the DID catalog, the formula evaluator, and readall.py.

Same posture as check_live.py / check_coverage.py: plain script, ``check()``,
exit 1 on failure. Runs against a temporary state directory so it never
touches the bench's real audit log or address store.

Run:
    .venv/Scripts/python.exe cuore/tests/check_readall.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: state must go to a throwaway directory.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-readall-")
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import addressing, did_catalog  # noqa: E402
from cuore.live import readall  # noqa: E402
from cuore.live import uds as uds_mod  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.readall import FormulaError, eval_formula  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


def raises(exc, fn) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


# ===========================================================================
# 1. formula evaluator: known-value cases
# ===========================================================================

check_eq("plain RPM formula", eval_formula("((A*256)+B)/4", [0x0B, 0x4C]), 723.0)
check_eq("A-40 coolant-style formula", eval_formula("A-40", [40]), 0)
check_eq("SIGNED(A) positive byte", eval_formula("SIGNED(A)", [0x7F]), 127)
check_eq("SIGNED(A) negative byte", eval_formula("SIGNED(A)", [0xFF]), -1)
check_eq("SIGNED(A) zero byte", eval_formula("SIGNED(A)", [0x00]), 0)
check_eq("coolant temp formula, zero raw", eval_formula("(((A*256)+B)*0.02)-40", [0x00, 0x00]),
         -40.0)
# EPS steering angle, from addressing.DIDS 0x083C: SIGNED(A)*256+B, all over 16.
check_eq("EPS steering-angle formula", eval_formula("(SIGNED(A)*256+B)/16", [0xFF, 0x00]), -16.0)
check_eq("division formula", eval_formula("A/10", [100]), 10.0)
check_eq("unary minus", eval_formula("-A", [5]), -5)
check_eq("nested parens and precedence", eval_formula("(A+B)*2-C", [1, 2, 3]), 3)

multi = eval_formula("pressure=((A*256)+B)/1000; temp=E-50",
                     [0x00, 0xC8, 0, 0, 70])  # A=0,B=200 -> 200/1000=0.2 bar; E=70-50=20
check_eq("multi-field formula returns a dict", set(multi), {"pressure", "temp"})
check_eq("multi-field pressure sub-value", multi["pressure"], 0.2)
check_eq("multi-field temp sub-value", multi["temp"], 20)

check("missing byte raises FormulaError",
      raises(FormulaError, lambda: eval_formula("A+B", [1])))
check("division by zero raises FormulaError",
      raises(FormulaError, lambda: eval_formula("A/B", [5, 0])))
check("empty formula raises FormulaError", raises(FormulaError, lambda: eval_formula("", [1])))


# ===========================================================================
# 2. formula evaluator: rejects anything unsafe, including the catalog's own
#    "multi-field" sentinel (BCM 0x1005) and every diesel/empty formula
# ===========================================================================

UNSAFE = [
    "multi-field",                      # the sentinel some rows use in place of a formula
    "__import__('os').system('x')",
    "os.system(1)",
    "eval(A)",
    "A**B",                             # exponent not in the grammar
    "A|B",                              # bitwise, not arithmetic
    "A&B",
    "A;DROP",
    "{Giri motore}",                    # cross-PID reference syntax from the raw CSV
    "A@256",
    "lambda: A",
]
for bad in UNSAFE:
    check(f"rejects unsafe formula {bad!r}",
          raises(FormulaError, lambda bad=bad: eval_formula(bad, list(range(1, 27)))))

# Every formula actually shipped in addressing.DIDS and did_catalog.EXTRA_DIDS
# either parses safely against 26 synthetic bytes (A..Z all present) or is one
# of the two known non-formula sentinels ("" for diesel-only rows, and the
# BCM composite's "multi-field").
DUMMY = list(range(1, 27))
all_specs = list(addressing.DIDS) + list(did_catalog.EXTRA_DIDS)
check("catalog is non-empty", len(all_specs) > 20, str(len(all_specs)))
bad_formulas: list[str] = []
for spec in all_specs:
    if not spec.formula or spec.formula == "multi-field":
        continue
    try:
        eval_formula(spec.formula, DUMMY)
    except FormulaError as e:
        bad_formulas.append(f"{spec.module} {spec.did:04X} {spec.formula!r}: {e}")
check("every real catalog formula parses and evaluates safely", not bad_formulas,
      "; ".join(bad_formulas))

# did_catalog never re-adds a DID addressing.DIDS already has.
existing = {(d.module, d.did) for d in addressing.DIDS}
overlap = [(d.module, f"{d.did:04X}") for d in did_catalog.EXTRA_DIDS
          if (d.module, d.did) in existing]
check_eq("EXTRA_DIDS has no overlap with addressing.DIDS", overlap, [])

# all_dids() merges and de-duplicates.
ecm_all = did_catalog.all_dids("ECM")
ecm_dids = [d.did for d in ecm_all]
check_eq("all_dids(ECM) has no duplicate DIDs", len(ecm_dids), len(set(ecm_dids)))
check("all_dids(ECM) includes an addressing.DIDS row (RPM 0x1000)",
      any(d.did == 0x1000 for d in ecm_all))
check("all_dids(ECM) includes an EXTRA_DIDS row (fuel tank 0x1001)",
      any(d.did == 0x1001 for d in ecm_all))
check("all_dids(ECM) excludes diesel-only rows by default",
      all(not d.diesel_only for d in ecm_all))
check("BROADCAST_SIGNALS is non-empty and passive-only (no request field)",
      len(did_catalog.BROADCAST_SIGNALS) > 0 and
      all("request" not in s for s in did_catalog.BROADCAST_SIGNALS))


# ===========================================================================
# 3. read_all against a fake adapter: identity, a decoded value, an NRC, and
#    a genuine no-answer, from the BusStream pattern in check_coverage.py.
# ===========================================================================

def _frames(header: str, payload: str) -> str:
    """ISO-TP framing with headers on, as an STN prints it."""
    n = len(payload) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload}"
    out = [f"{header}1{n:03X}{payload[:12]}"]
    rest, seq = payload[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


def _ascii_hex(s: str) -> str:
    return "".join(f"{ord(c):02X}" for c in s)


class BusStream(Stream):
    """Answers per target: the reply depends on the last ATSH. Copied from
    cuore/tests/check_coverage.py's BusStream (same shape, same contract)."""

    def __init__(self, nodes: dict[int, dict[str, str]]) -> None:
        self.nodes = nodes
        self.target: int | None = None
        self.sent: list[str] = []
        self._buf = bytearray()
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def _reply(self, cmd: str) -> str:
        if cmd.startswith("ATSH18DA") and len(cmd) == 12:
            self.target = int(cmd[8:10], 16)
            return "OK"
        if cmd == "ATI":
            return "ELM327 v2.3"
        if cmd == "STI":
            return "STN1170 v4.3.2"
        if cmd.startswith(("AT", "ST")):
            return "OK"
        node = self.nodes.get(self.target or -1)
        if node is None:
            return "NO DATA"
        header = f"18DAF1{self.target:02X}"
        payload = node.get(cmd)
        if payload is None:
            return _frames(header, "7F" + cmd[:2] + "31")
        return _frames(header, payload)

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        self._buf.extend(self._reply(cmd).encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    def in_waiting(self) -> int:
        return len(self._buf)

    @property
    def describe(self) -> str:
        return "readall-fake"


ECM = addressing.by_code("ECM")

_RPM_DID = "221000"          # 0x1000, formula ((A*256)+B)/4
_NO_ANSWER_DID = "221009"    # 0x1009, EXTRA_DIDS "Time since start"
_NRC_OTHER_DID = "22192F"    # 0x192F, EXTRA_DIDS "A/C refrigerant pressure"


class ReadAllStream(BusStream):
    """0x1000 answers positively, 0x1009 is genuinely silent (NO DATA), 0x192F
    comes back with NRC 0x22 conditionsNotCorrect (not 0x31); everything
    else at target 0x10 falls through to the default 0x31 NRC."""

    def _reply(self, cmd: str) -> str:
        if self.target == 0x10:
            header = "18DAF110"
            if cmd == _NO_ANSWER_DID:
                return "NO DATA"
            if cmd == _NRC_OTHER_DID:
                return _frames(header, "7F2222")
        return super()._reply(cmd)


vin_hex = _ascii_hex(VIN)
nodes = {0x10: {"22F190": "62F190" + vin_hex, _RPM_DID: "621000" + "0B4C"}}
stream = ReadAllStream(nodes)
link = AdapterLink(stream_factory=lambda p, b: stream, process="check_readall")
set_link(link)
link.mark_verified(CAN_C, 10)

with link.session("read-all-test", bus=CAN_C) as sess:
    result = readall.read_all(sess, ECM)

check_eq("read_all names the ecu", result["ecu"], "ECM")
check_eq("read_all identity carries the VIN", result["identity"]["fields"]["F190"]["ascii"], VIN)
by_did = {d["did"]: d for d in result["dids"]}
check("read_all covers the RPM DID", "1000" in by_did)
check_eq("RPM DID decodes to 723.0 rpm", by_did["1000"].get("value"), 723.0)
check_eq("RPM DID status is answered", by_did["1000"]["status"], "answered")
check_eq("silent DID status is no_answer", by_did["1009"]["status"], "no_answer")
check("silent DID carries no value", "value" not in by_did["1009"])
check_eq("NRC-other-than-31 DID status is nrc", by_did["192F"]["status"], "nrc")
check("that NRC is reported as conditionsNotCorrect, not requestOutOfRange",
      "conditionsNotCorrect" in (by_did["192F"]["nrc"] or {}).values(),
      str(by_did["192F"]["nrc"]))
# Every other DID at target 0x10 defaults to NRC 0x31 requestOutOfRange.
other = by_did["195A"]  # boost pressure, addressing.DIDS, not planted above
check_eq("an unplanted DID gets the default 0x31 NRC", other["status"], "nrc")
check("requestOutOfRange is reported for unplanted DIDs",
      "requestOutOfRange" in (other["nrc"] or {}).values(), str(other["nrc"]))
check_eq("summary total matches the dids list length",
         result["summary"]["total"], len(result["dids"]))
check("summary counts add up to the total",
      sum(result["summary"][k] for k in ("answered", "nrc", "no_answer", "error"))
      == result["summary"]["total"], str(result["summary"]))
check("summary reflects at least one answered, one nrc, one no_answer",
      result["summary"]["answered"] >= 1 and result["summary"]["nrc"] >= 1 and
      result["summary"]["no_answer"] >= 1, str(result["summary"]))

with link.session("read-all-confirmed-only", bus=CAN_C) as sess:
    confirmed_only = readall.read_all(sess, ECM, include_unverified=False)
check("include_unverified=False drops every unverified catalog DID",
      all(d["confidence"] == "confirmed" for d in confirmed_only["dids"]),
      str({d["confidence"] for d in confirmed_only["dids"]}))
check_eq("include_unverified=False leaves nothing on this car today (no DID is CONFIRMED yet)",
         confirmed_only["dids"], [])


# ===========================================================================
# 4. discover_dids: finds planted DIDs, skips 0x31, stops on a bus error
# ===========================================================================

_PLANTED_POSITIVE = "221005"   # arbitrary DID inside the 0x1000-0x10FF range
_PLANTED_NRC = "221006"        # NRC 0x22, must be reported
_PLANTED_ERROR = "221007"      # triggers an early stop


class DiscoverStream(BusStream):
    def _reply(self, cmd: str) -> str:
        if self.target == 0x10:
            header = "18DAF110"
            if cmd == _PLANTED_POSITIVE:
                return _frames(header, "6210052A")
            if cmd == _PLANTED_NRC:
                return _frames(header, "7F2222")
            if cmd == _PLANTED_ERROR:
                return "CAN ERROR"
        return super()._reply(cmd)


dnodes = {0x10: {}}  # present but empty: unset DIDs get the default 0x31
dstream = DiscoverStream(dnodes)
dlink = AdapterLink(stream_factory=lambda p, b: dstream, process="check_readall")
set_link(dlink)
dlink.mark_verified(CAN_C, 10)

with dlink.session("discover-dids-test", bus=CAN_C) as sess:
    disc = readall.discover_dids(sess, ECM, ranges=((0x1000, 0x100A),), per_did_timeout=0.2)

positive_dids = {h["did"] for h in disc["positive"]}
nrc_dids = {h["did"] for h in disc["nrcs"]}
check_eq("discover_dids finds the planted positive DID", positive_dids, {"1005"})
check_eq("discover_dids reports the planted non-0x31 NRC", nrc_dids, {"1006"})
check("discover_dids stops before the range's end on the bus error",
      disc["stopped_early"] is not None and disc["tried"] < (0x100A - 0x1000 + 1),
      str(disc))
check("no DID past the error was tried",
      not any(h["did"] > "1007" for h in disc["positive"] + disc["nrcs"]))

# A clean sweep (no bus error) reports stopped_early as None and respects max_dids.
dnodes2 = {0x10: {"221005": "6210052A"}}
dstream2 = BusStream(dnodes2)
dlink2 = AdapterLink(stream_factory=lambda p, b: dstream2, process="check_readall")
set_link(dlink2)
dlink2.mark_verified(CAN_C, 10)
with dlink2.session("discover-dids-clean", bus=CAN_C) as sess:
    disc2 = readall.discover_dids(sess, ECM, ranges=((0x1000, 0x1005),), per_did_timeout=0.2)
check_eq("a clean sweep has no stopped_early", disc2["stopped_early"], None)
check_eq("a clean sweep tries every DID in the range", disc2["tried"], 0x1005 - 0x1000 + 1)
check_eq("the sole positive DID is found", {h["did"] for h in disc2["positive"]}, {"1005"})
check_eq("no 0x31 NRCs are reported (they are the majority of the sweep)",
         disc2["nrcs"], [])

with dlink2.session("discover-dids-max", bus=CAN_C) as sess:
    disc3 = readall.discover_dids(sess, ECM, ranges=((0x1000, 0x10FF),), per_did_timeout=0.2,
                                  max_dids=3)
check_eq("max_dids caps how many are tried", disc3["tried"], 3)
check("max_dids is reported as the stop reason", "max_dids" in (disc3["stopped_early"] or ""))


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
