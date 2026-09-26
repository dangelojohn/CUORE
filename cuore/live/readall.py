"""Session-level "read everything we know how to ask for" on one module.

Two pieces:

* A tiny, safe CarScanner-formula evaluator (no ``eval``). CarScanner/MES
  formulas are arithmetic over response-data byte letters (``A``, ``B``,
  ``C`` ... in order after the echoed DID), ``+ - * /``, parentheses, and
  ``SIGNED(...)``. That is a small enough grammar to hand-parse; anything
  outside it (a stray identifier, a bitwise operator, an unbalanced paren)
  raises :class:`FormulaError` rather than ever being handed to Python's
  ``eval``.
* :func:`read_all` and :func:`discover_dids`, both read-only, both going
  through :func:`uds.read_did` (so the read-only allowlist in
  :mod:`safety` still gates every byte on the wire).

Stdlib only besides the ``cuore.live`` imports.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from . import audit
from . import did_catalog
from . import uds as uds_mod
from .addressing import ECUAddress
from .transport import Session

# ===========================================================================
# formula evaluator
# ===========================================================================


class FormulaError(Exception):
    """Raised for anything that is not a safe, recognised CarScanner formula."""


_SIMPLE_OPS = frozenset("+-*/()")
_NRC_31 = "requestOutOfRange"


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in _SIMPLE_OPS:
            tokens.append((c, c))
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            seen_dot = False
            while j < n and (text[j].isdigit() or (text[j] == "." and not seen_dot)):
                seen_dot = seen_dot or text[j] == "."
                j += 1
            tokens.append(("NUM", text[i:j]))
            i = j
            continue
        if c.isalpha():
            j = i
            while j < n and text[j].isalpha():
                j += 1
            word = text[i:j]
            if word == "SIGNED":
                tokens.append(("SIGNED", word))
            elif len(word) == 1 and word.isupper():
                tokens.append(("LETTER", word))
            else:
                raise FormulaError(f"unsupported identifier {word!r} in formula {text!r}")
            i = j
            continue
        raise FormulaError(f"unsupported character {c!r} in formula {text!r}")
    return tokens


# AST nodes are plain tuples: ("num", value) | ("byte", "A") | ("signed", node)
# | ("unary", "-", node) | ("binop", "+", left, right)

class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[Optional[str], Optional[str]]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None, None

    def _advance(self) -> tuple[Optional[str], Optional[str]]:
        tok = self._peek()
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> None:
        got, _ = self._advance()
        if got != kind:
            raise FormulaError(f"expected {kind!r}, found {got!r}")

    def parse(self):
        node = self._expr()
        if self.pos != len(self.tokens):
            raise FormulaError(f"unexpected trailing input at token {self.pos}")
        return node

    def _expr(self):
        node = self._term()
        while self._peek()[0] in ("+", "-"):
            op, _ = self._advance()
            node = ("binop", op, node, self._term())
        return node

    def _term(self):
        node = self._factor()
        while self._peek()[0] in ("*", "/"):
            op, _ = self._advance()
            node = ("binop", op, node, self._factor())
        return node

    def _factor(self):
        kind, _ = self._peek()
        if kind in ("+", "-"):
            self._advance()
            return ("unary", kind, self._factor())
        return self._primary()

    def _primary(self):
        kind, val = self._advance()
        if kind == "NUM":
            return ("num", float(val) if "." in val else int(val))
        if kind == "LETTER":
            return ("byte", val)
        if kind == "SIGNED":
            self._expect("(")
            node = self._expr()
            self._expect(")")
            return ("signed", node)
        if kind == "(":
            node = self._expr()
            self._expect(")")
            return node
        raise FormulaError(f"unexpected token {kind!r}")


def _parse_expr(text: str):
    return _Parser(_tokenize(text)).parse()


def _signed(value: Any) -> int:
    """Two's-complement reinterpretation, byte-width chosen by magnitude.

    Covers both ``SIGNED(A)`` (one byte) and ``SIGNED((A*256)+B)`` (two
    bytes combined first, then sign-corrected) -- both forms are used in
    the sourced formulas.
    """
    try:
        iv = int(value)
    except (TypeError, ValueError):
        raise FormulaError(f"SIGNED() operand is not an integer: {value!r}")
    if float(iv) != float(value):
        raise FormulaError(f"SIGNED() operand is not an integer: {value!r}")
    for bits in (8, 16, 24, 32, 40, 48, 56, 64):
        span = 1 << bits
        if 0 <= iv < span:
            return iv - span if iv >= span // 2 else iv
    raise FormulaError(f"SIGNED() operand out of range: {value!r}")


def _eval_node(node, data: list[int]) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "byte":
        idx = ord(node[1]) - ord("A")
        if idx < 0 or idx >= len(data):
            raise FormulaError(
                f"formula references byte {node[1]!r} but only {len(data)} byte(s) were returned")
        return data[idx]
    if kind == "signed":
        return _signed(_eval_node(node[1], data))
    if kind == "unary":
        v = _eval_node(node[2], data)
        return -v if node[1] == "-" else v
    if kind == "binop":
        op = node[1]
        left = _eval_node(node[2], data)
        right = _eval_node(node[3], data)
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise FormulaError("division by zero")
            return left / right
    raise FormulaError(f"malformed AST node {node!r}")  # pragma: no cover - defensive


def eval_formula(formula: str, data: list[int]) -> Union[float, dict[str, float]]:
    """Evaluate one CarScanner-style formula against response-data bytes.

    ``data`` is the response payload after the echoed DID, in order (``A``
    is ``data[0]``, ``B`` is ``data[1]``, ...). A plain formula (no ``;`` or
    ``=``) returns one number. A multi-field formula such as
    ``"pressure=((A*256)+B)/1000; temp=E-50"`` (the RFHUB tire DIDs' shape)
    returns ``{"pressure": ..., "temp": ...}``.

    Raises :class:`FormulaError` for an empty formula, the ``"multi-field"``
    sentinel some catalog rows use in place of a real formula, or anything
    outside the safe grammar (unknown identifier, stray character, wrong
    argument count, missing byte, division by zero). There is no ``eval()``
    anywhere in this module: a formula that is not in the grammar simply
    cannot execute.
    """
    text = formula.strip()
    if not text:
        raise FormulaError("empty formula")
    if ";" in text or "=" in text:
        out: dict[str, float] = {}
        for clause in text.split(";"):
            clause = clause.strip()
            if not clause:
                continue
            if "=" not in clause:
                raise FormulaError(f"multi-field formula clause missing '=': {clause!r}")
            name, expr = clause.split("=", 1)
            name = name.strip()
            if not name:
                raise FormulaError(f"multi-field formula clause missing a name: {clause!r}")
            out[name] = _eval_node(_parse_expr(expr), data)
        return out
    return _eval_node(_parse_expr(text), data)


# ===========================================================================
# read_all
# ===========================================================================

def read_all(sess: Session, ecu: ECUAddress, include_unverified: bool = True) -> dict[str, Any]:
    """Annex C identity plus every catalog DID for ``ecu``, decoded where possible.

    Read-only: every byte on the wire goes through :func:`uds.read_did`,
    which goes through :func:`safety.assert_read_only_uds`. ``ecu`` must
    already carry a usable target (see :func:`uds.resolve_module`); this
    function does not resolve or discover addresses.

    ``include_unverified=False`` restricts the sweep to catalog rows whose
    ``confidence`` is exactly ``"confirmed"`` -- on this car today that is
    only the Annex C identity set, since no module DID here has been
    confirmed on the 2.0T yet.
    """
    identity = uds_mod.identity(sess, ecu)
    specs = did_catalog.all_dids(ecu.code, include_diesel=False)
    if not include_unverified:
        specs = [s for s in specs if s.confidence == "confirmed"]

    dids: list[dict[str, Any]] = []
    counts = {"answered": 0, "nrc": 0, "no_answer": 0, "error": 0}
    for spec in specs:
        r = uds_mod.read_did(sess, ecu, spec.did)
        entry: dict[str, Any] = {
            "did": f"{spec.did:04X}", "name": spec.name, "unit": spec.unit,
            "confidence": spec.confidence, "formula": spec.formula,
            "source": spec.source, "note": spec.note,
            "bytes": r.get("bytes"), "ascii": r.get("ascii"),
            "nrc": r.get("nrc"), "error": r.get("error"),
        }
        if r.get("error"):
            entry["status"] = "error"
            counts["error"] += 1
        elif r.get("bytes"):
            entry["status"] = "answered"
            counts["answered"] += 1
            if spec.formula and spec.formula != "multi-field":
                try:
                    entry["value"] = eval_formula(spec.formula,
                                                  [int(b, 16) for b in r["bytes"]])
                except FormulaError as e:
                    entry["decode_error"] = str(e)
        elif r.get("nrc"):
            entry["status"] = "nrc"
            counts["nrc"] += 1
        else:
            entry["status"] = "no_answer"
            counts["no_answer"] += 1
        dids.append(entry)

    audit.record("read_all", ecu=ecu.code, total=len(dids), **counts)
    return {
        "ecu": ecu.code, "bus": sess.bus.key, "identity": identity, "dids": dids,
        "summary": {"total": len(dids), **counts},
    }


# ===========================================================================
# discover_dids
# ===========================================================================

#: A conservative default sweep: Annex C plus the two blocks this project has
#: actually found live data in (0x1000s ECM/TCM signals, 0x0100s BCM/IPC).
DEFAULT_DISCOVERY_RANGES: tuple[tuple[int, int], ...] = (
    (0xF180, 0xF1FF), (0x1000, 0x10FF), (0x1900, 0x19FF), (0x0100, 0x01FF),
)


def discover_dids(sess: Session, ecu: ECUAddress,
                   ranges: Optional[tuple[tuple[int, int], ...]] = None,
                   per_did_timeout: float = 0.15, max_dids: int = 2000) -> dict[str, Any]:
    """Read-only ``0x22`` sweep over ``ranges`` against one already-targeted module.

    For CAN-C modules. This does not special-case or bypass the CAN-CH
    confirm-before-transmit gate: ``session()``/``assert_transmit_allowed()``
    already enforce it, and pointing this at a CAN-CH ``ecu`` without a
    confirmed session simply raises :class:`errors.Refused` on the first
    request, exactly as any other read would. On CAN-CH prefer a short,
    human-reviewed ``ranges`` list -- every DID here is a request against
    brakes, steering or airbag hardware.

    Stops early (``stopped_early`` set) on a bus-level error (anything
    other than a plain timeout, matching :func:`uds.discover`'s posture).
    A response with a positive payload is a hit; a negative response whose
    NRC is anything other than ``0x31`` (requestOutOfRange -- "no such
    DID", the overwhelming majority of the sweep) is recorded as
    interesting; plain requestOutOfRange and silent timeouts are neither.
    """
    if ranges is None:
        ranges = DEFAULT_DISCOVERY_RANGES
    hits: list[dict[str, Any]] = []
    interesting_nrcs: list[dict[str, Any]] = []
    tried = 0
    stopped_early: Optional[str] = None
    for start, end in ranges:
        if stopped_early:
            break
        for did in range(start, end + 1):
            if tried >= max_dids:
                stopped_early = stopped_early or "max_dids reached"
                break
            tried += 1
            r = uds_mod.read_did(sess, ecu, did, timeout=per_did_timeout)
            if r.get("error") and r["error"] != "TIMEOUT":
                stopped_early = r["error"]
                break
            if r.get("error") == "TIMEOUT":
                continue  # a single silent DID, not a bus fault
            if r.get("bytes"):
                hits.append({"did": f"{did:04X}", "bytes": r["bytes"], "ascii": r.get("ascii")})
                continue
            nrc = r.get("nrc")
            if nrc:
                interesting = {h: t for h, t in nrc.items() if t != _NRC_31}
                if interesting:
                    interesting_nrcs.append({"did": f"{did:04X}", "nrc": interesting})
            # else: silent (no answer / timeout) -- neither a hit nor interesting

    audit.record("discover_dids", ecu=ecu.code, tried=tried, hits=len(hits),
                 nrcs=len(interesting_nrcs), stopped_early=stopped_early)
    return {
        "ecu": ecu.code, "bus": sess.bus.key, "tried": tried, "stopped_early": stopped_early,
        "positive": hits, "nrcs": interesting_nrcs,
    }


__all__ = ["FormulaError", "eval_formula", "read_all", "discover_dids",
           "DEFAULT_DISCOVERY_RANGES"]
