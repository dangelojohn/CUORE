"""The live-data channel model: a registry of everything the poller can sample.

A channel is ``{id, name, unit, source}``. Four source kinds:

* ``pid``    -- a Mode 01 PID (hex), decoded by :func:`obd.decode_pid`.
* ``did``    -- a module code + UDS DID (hex) + CarScanner formula, evaluated
  with :func:`readall.eval_formula`. Every catalogued DID for ECM, TCM, BCM,
  IPC and RFHUB (:func:`did_catalog.all_dids`) is included, at its recorded
  confidence. A DID whose formula answers with several named fields (the
  RFHUB tire DIDs: ``pressure=...; temp=...``) is expanded into one channel
  per field, sharing the one DID read.
* ``computed`` -- an arithmetic expression over other channel ids, evaluated
  by the small safe evaluator below (no ``eval()`` anywhere in this module).
* ``battery``  -- adapter ``ATRV``.

:func:`available_channels` returns the whole registry; :func:`presets`
groups channel ids for one-click starts on this car.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from . import did_catalog
from .addressing import by_code
from .errors import BadCommand
from .obd import PIDS_BY_HEX

FAST_HZ = 5.0
MED_HZ = 1.0
SLOW_HZ = 0.5

#: PIDs worth sampling quickly -- the ones that change fast enough to matter
#: for a live dashboard (RPM, speed, throttle).
_FAST_PIDS = {"engine_rpm", "vehicle_speed", "throttle_position"}
#: Slow-moving readings: temperatures, ambient/barometric pressure, fuel level.
_SLOW_PIDS = {"engine_coolant_temp", "intake_air_temp", "ambient_air_temp",
             "barometric_pressure", "fuel_level", "engine_oil_temp"}

#: Modules whose catalogued DIDs are worth exposing as channels.
DID_MODULES: tuple[str, ...] = ("ECM", "TCM", "BCM", "IPC", "RFHUB")


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    unit: str
    kind: str                       # "pid" | "did" | "computed" | "battery"
    bus: str                        # "can_c" | "can_ihs" | "can_ch" | ""
    confidence: str
    default_rate_hz: float
    pid: str = ""
    module: str = ""
    did: int = 0
    formula: str = ""
    field: str = ""                 # sub-field name for a multi-field DID formula
    expr: str = ""
    depends_on: tuple[str, ...] = ()
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id, "name": self.name, "unit": self.unit, "kind": self.kind,
            "bus": self.bus, "confidence": self.confidence,
            "default_rate_hz": self.default_rate_hz,
        }
        if self.kind == "pid":
            out["pid"] = self.pid
        elif self.kind == "did":
            out["module"] = self.module
            out["did"] = f"{self.did:04X}"
            if self.formula:
                out["formula"] = self.formula
            if self.field:
                out["field"] = self.field
        elif self.kind == "computed":
            out["expr"] = self.expr
            out["depends_on"] = list(self.depends_on)
        if self.note:
            out["note"] = self.note
        return out


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "field"


def _pid_rate(name: str) -> float:
    if name in _FAST_PIDS:
        return FAST_HZ
    if name in _SLOW_PIDS:
        return SLOW_HZ
    return MED_HZ


def _pid_channels() -> list[Channel]:
    return [
        Channel(id=spec.name, name=spec.name.replace("_", " "), unit=spec.unit,
               kind="pid", bus="can_c", confidence="legislated",
               default_rate_hz=_pid_rate(spec.name), pid=spec.pid,
               note=spec.description)
        for spec in PIDS_BY_HEX.values()
    ]


def _battery_channel() -> Channel:
    return Channel(id="battery_voltage", name="battery voltage", unit="V",
                   kind="battery", bus="can_c", confidence="legislated",
                   default_rate_hz=SLOW_HZ)


def _multi_field_names(formula: str) -> Optional[list[str]]:
    """Field names of a real multi-field formula (``a=...; b=...``).

    Distinguishes an actual multi-clause CarScanner formula from the
    ``"multi-field"`` sentinel some catalog rows use in place of a real,
    machine-parseable formula (e.g. the BCM IBS composite DID, whose fields
    are only described in prose) -- those get a single undecoded channel.
    """
    if not formula or formula == "multi-field":
        return None
    if ";" not in formula and "=" not in formula:
        return None
    names: list[str] = []
    for clause in formula.split(";"):
        clause = clause.strip()
        if not clause or "=" not in clause:
            return None
        name, _, _expr = clause.partition("=")
        name = name.strip()
        if not name:
            return None
        names.append(name)
    return names or None


def _did_channels() -> list[Channel]:
    out: list[Channel] = []
    for code in DID_MODULES:
        ecu = by_code(code)
        bus = ecu.bus_key if ecu else "can_c"
        for spec in did_catalog.all_dids(code, include_diesel=False):
            base_id = f"{code.lower()}_{spec.did:04x}"
            fields = _multi_field_names(spec.formula)
            if fields:
                for fname in fields:
                    out.append(Channel(
                        id=f"{base_id}_{_slug(fname)}", name=f"{spec.name} ({fname})",
                        unit=spec.unit, kind="did", bus=bus, confidence=spec.confidence,
                        default_rate_hz=MED_HZ, module=code, did=spec.did,
                        formula=spec.formula, field=fname, note=spec.note))
            else:
                formula = "" if spec.formula == "multi-field" else spec.formula
                out.append(Channel(
                    id=base_id, name=spec.name, unit=spec.unit, kind="did", bus=bus,
                    confidence=spec.confidence, default_rate_hz=MED_HZ, module=code,
                    did=spec.did, formula=formula, note=spec.note))
    return out


def _computed_channels() -> list[Channel]:
    return [
        Channel(id="boost", name="boost (MAP - baro)", unit="kPa", kind="computed",
               bus="can_c", confidence="computed", default_rate_hz=MED_HZ,
               expr="intake_map - barometric_pressure",
               depends_on=("intake_map", "barometric_pressure"),
               note="derived from the two legislated PIDs; compare against the "
                    "unverified ECM boost DID 195A"),
    ]


def available_channels() -> list[Channel]:
    """Every channel this project knows how to sample."""
    return _pid_channels() + _did_channels() + [_battery_channel()] + _computed_channels()


_REGISTRY: Optional[dict[str, Channel]] = None


def registry() -> dict[str, Channel]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = {c.id: c for c in available_channels()}
    return _REGISTRY


def by_id(channel_id: str) -> Channel:
    ch = registry().get(channel_id)
    if ch is None:
        raise BadCommand(f"unknown channel id {channel_id!r}")
    return ch


#: One-click starts. Every id here must resolve through :func:`by_id`; a
#: mismatch would be a bug in this file, not caller input, so it is not
#: guarded -- :func:`resolve_channels` raising KeyError on a typo here during
#: development is preferable to silently dropping a channel from a preset.
PRESETS: dict[str, tuple[str, ...]] = {
    "engine_basics": ("engine_rpm", "vehicle_speed", "engine_coolant_temp",
                      "intake_air_temp", "absolute_load", "throttle_position",
                      "battery_voltage"),
    "boost": ("intake_map", "barometric_pressure", "boost", "ecm_195a"),
    "evap_job": ("commanded_evap_purge", "fuel_level", "evap_vapor_pressure",
                "evap_vapor_pressure_abs", "engine_coolant_temp", "intake_air_temp"),
    "transmission": ("tcm_04fe", "tcm_0518"),
    "tpms": ("rfhub_40b1_pressure", "rfhub_40b1_temp", "rfhub_40b2_pressure",
            "rfhub_40b2_temp", "rfhub_40b3_pressure", "rfhub_40b3_temp",
            "rfhub_40b4_pressure", "rfhub_40b4_temp"),
}


def presets() -> dict[str, list[dict[str, Any]]]:
    reg = registry()
    return {name: [reg[cid].to_dict() for cid in ids if cid in reg]
            for name, ids in PRESETS.items()}


def resolve_channels(channel_ids: Optional[list[str]] = None, preset: str = "") -> list[Channel]:
    """``channel_ids`` and/or a named preset, deduplicated, computed channels'
    dependencies pulled in automatically so they are always polled too."""
    chosen: list[str] = []
    if preset:
        if preset not in PRESETS:
            raise BadCommand(f"unknown preset {preset!r}; one of {sorted(PRESETS)}")
        chosen.extend(PRESETS[preset])
    for cid in (channel_ids or []):
        if cid not in chosen:
            chosen.append(cid)
    if not chosen:
        raise BadCommand("pass channels=[...] or preset=...")

    result: list[Channel] = []
    seen: set[str] = set()

    def add(cid: str) -> None:
        if cid in seen:
            return
        ch = by_id(cid)
        seen.add(cid)
        for dep in ch.depends_on:
            add(dep)
        result.append(ch)

    for cid in chosen:
        add(cid)
    return result


# ===========================================================================
# the computed-channel evaluator: arithmetic over channel ids, no eval()
# ===========================================================================

class ComputedError(Exception):
    """Raised for anything outside the safe arithmetic grammar below."""


_OPS = frozenset("+-*/()")


def _tokenize_expr(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in _OPS:
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
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(("ID", text[i:j]))
            i = j
            continue
        raise ComputedError(f"unsupported character {c!r} in expression {text!r}")
    return tokens


# AST nodes: ("num", value) | ("ref", channel_id) | ("unary", op, node)
# | ("binop", op, left, right)

class _ExprParser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[Optional[str], Optional[str]]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _advance(self) -> tuple[Optional[str], Optional[str]]:
        tok = self._peek()
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> None:
        got, _ = self._advance()
        if got != kind:
            raise ComputedError(f"expected {kind!r}, found {got!r}")

    def parse(self):
        node = self._expr()
        if self.pos != len(self.tokens):
            raise ComputedError(f"unexpected trailing input at token {self.pos}")
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
            return ("num", float(val))
        if kind == "ID":
            return ("ref", val)
        if kind == "(":
            node = self._expr()
            self._expect(")")
            return node
        raise ComputedError(f"unexpected token {kind!r}")


def _eval_node(node, values: dict[str, float]) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "ref":
        v = values.get(node[1])
        if v is None:
            raise ComputedError(f"expression references unavailable channel {node[1]!r}")
        return v
    if kind == "unary":
        v = _eval_node(node[2], values)
        return -v if node[1] == "-" else v
    if kind == "binop":
        op = node[1]
        left = _eval_node(node[2], values)
        right = _eval_node(node[3], values)
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise ComputedError("division by zero")
            return left / right
    raise ComputedError(f"malformed AST node {node!r}")  # pragma: no cover - defensive


def eval_expr(expr: str, values: dict[str, float]) -> float:
    """Evaluate a computed-channel expression over ``{channel_id: value}``.

    Arithmetic only (``+ - * /``, parentheses, unary minus, numbers and
    channel-id identifiers) -- there is no ``eval()`` anywhere in this
    module, so an expression outside the grammar simply cannot execute.
    """
    text = expr.strip()
    if not text:
        raise ComputedError("empty expression")
    return _eval_node(_ExprParser(_tokenize_expr(text)).parse(), values)


__all__ = ["Channel", "available_channels", "registry", "by_id", "PRESETS", "presets",
          "resolve_channels", "ComputedError", "eval_expr", "DID_MODULES",
          "FAST_HZ", "MED_HZ", "SLOW_HZ"]
