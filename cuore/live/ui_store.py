"""Dashboard-UI-only state: custom (Torque-style) channels, snapshots, triggers.

Nothing here talks to the adapter. Custom channels are validated against the
same safe arithmetic grammar the built-in computed channels use
(:func:`cuore.live.channels.eval_expr`) so there is still no ``eval()`` in the
system; :func:`load_custom_channels` hands back ordinary
:class:`~cuore.live.channels.Channel` objects so a future wiring step can fold
them into the poller's registry with no special case.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..services.errors import BadRequest, NotFound
from . import channels as channels_mod
from .addressing import by_code
from .config import state_dir

_LOCK = threading.Lock()

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
_DID_RE = re.compile(r"^[0-9A-Fa-f]{4}$")

#: Sample bytes A, B, C, ... used to validate a Torque-style byte formula.
#: (Arbitrary but fixed and documented, per the task's own example.)
_SAMPLE_BYTES = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0]
_BYTE_NAMES = "ABCDEFGH"


# ===========================================================================
# custom channels
# ===========================================================================

def custom_channels_path() -> Path:
    return state_dir() / "custom_channels.json"


def _load_raw() -> list[dict[str, Any]]:
    p = custom_channels_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return list(data.get("channels", [])) if isinstance(data, dict) else []


def _save_raw(channels: list[dict[str, Any]]) -> None:
    custom_channels_path().write_text(
        json.dumps({"channels": channels}, indent=2), encoding="utf-8")


def _validate_formula(cid: str, formula: str) -> None:
    if not isinstance(formula, str) or not formula.strip():
        raise BadRequest(f"custom channel {cid!r}: formula is required for kind='did'")
    values = {name: float(b) for name, b in zip(_BYTE_NAMES, _SAMPLE_BYTES)}
    try:
        channels_mod.eval_expr(formula, values)
    except channels_mod.ComputedError as exc:
        raise BadRequest(f"custom channel {cid!r}: invalid formula {formula!r}: {exc}") from exc


_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _referenced_ids(expr: str) -> set[str]:
    """Every identifier ``expr`` names -- channel ids it depends on.

    Uses a plain identifier scan rather than the private tokenizer in
    :mod:`channels`, since all that is needed here is the set of names, not a
    parse tree; the arithmetic grammar itself is still enforced by
    :func:`channels.eval_expr` below.
    """
    return set(_IDENT_RE.findall(expr))


def _validate_computed(cid: str, expr: str, known_ids: set[str]) -> set[str]:
    if not isinstance(expr, str) or not expr.strip():
        raise BadRequest(f"custom channel {cid!r}: expr is required for kind='computed'")
    refs = _referenced_ids(expr)
    unknown = refs - known_ids
    if unknown:
        raise BadRequest(f"custom channel {cid!r}: expr references unknown channel(s) "
                         f"{sorted(unknown)}")
    dummy = {r: 1.0 for r in refs}
    try:
        channels_mod.eval_expr(expr, dummy)
    except channels_mod.ComputedError as exc:
        raise BadRequest(f"custom channel {cid!r}: invalid expr {expr!r}: {exc}") from exc
    return refs


def _check_cycles(deps: dict[str, set[str]]) -> None:
    """Raise :class:`BadRequest` if the computed-channel dependency graph has a cycle."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {cid: WHITE for cid in deps}

    def visit(cid: str, stack: list[str]) -> None:
        color[cid] = GRAY
        for dep in deps.get(cid, ()):
            if dep not in deps:
                continue  # depends on a registry channel, not another custom one
            if color.get(dep) == GRAY:
                cycle = " -> ".join(stack + [dep])
                raise BadRequest(f"custom channels have a cycle: {cycle}")
            if color.get(dep) == WHITE:
                visit(dep, stack + [dep])
        color[cid] = BLACK

    for cid in deps:
        if color[cid] == WHITE:
            visit(cid, [cid])


def validate_custom_channels(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate the whole submitted list at once (ids must be unique, cycle-free)."""
    if not isinstance(raw, list):
        raise BadRequest("channels must be a list")
    registry_ids = set(channels_mod.registry())
    seen: set[str] = set()

    # Pass 1: shape/id checks only, so a computed channel may forward-reference
    # another custom channel defined later in the same submitted list.
    for ch in raw:
        if not isinstance(ch, dict):
            raise BadRequest("each custom channel must be an object")
        cid = ch.get("id")
        if not isinstance(cid, str) or not _ID_RE.match(cid):
            raise BadRequest(f"custom channel id must match {_ID_RE.pattern!r}, got {cid!r}")
        if cid in seen:
            raise BadRequest(f"duplicate custom channel id {cid!r}")
        if cid in registry_ids:
            raise BadRequest(f"custom channel id {cid!r} collides with a built-in channel")
        seen.add(cid)
        name = ch.get("name")
        if not isinstance(name, str) or not name.strip():
            raise BadRequest(f"custom channel {cid!r}: name is required")
        unit = ch.get("unit", "")
        if not isinstance(unit, str):
            raise BadRequest(f"custom channel {cid!r}: unit must be a string")
        kind = ch.get("kind")
        if kind not in ("did", "computed"):
            raise BadRequest(f"custom channel {cid!r}: kind must be 'did' or 'computed', "
                             f"got {kind!r}")

    known_ids = registry_ids | seen

    # Pass 2: per-kind validation, now that every id in this submission is known.
    out: list[dict[str, Any]] = []
    deps: dict[str, set[str]] = {}
    for ch in raw:
        cid = ch["id"]
        entry: dict[str, Any] = {"id": cid, "name": ch["name"], "unit": ch.get("unit", ""),
                                 "kind": ch["kind"]}
        if ch["kind"] == "did":
            module = ch.get("module")
            if not isinstance(module, str) or by_code(module.upper()) is None:
                raise BadRequest(f"custom channel {cid!r}: unknown module {module!r}")
            did = ch.get("did")
            if not isinstance(did, str) or not _DID_RE.match(did):
                raise BadRequest(f"custom channel {cid!r}: did must be 4 hex digits, "
                                 f"got {did!r}")
            formula = ch.get("formula", "")
            _validate_formula(cid, formula)
            entry.update({"module": module.upper(), "did": did.upper(), "formula": formula})
        else:
            expr = ch.get("expr", "")
            refs = _validate_computed(cid, expr, known_ids)
            entry["expr"] = expr
            deps[cid] = refs
        out.append(entry)

    _check_cycles(deps)
    return out


def load_custom_channels_raw() -> dict[str, Any]:
    return {"channels": _load_raw()}


def save_custom_channels(raw: list[dict[str, Any]]) -> dict[str, Any]:
    validated = validate_custom_channels(raw)
    with _LOCK:
        _save_raw(validated)
    return {"channels": validated}


def load_custom_channels() -> list[channels_mod.Channel]:
    """User-defined channels as ordinary :class:`Channel` objects.

    Marked ``confidence="USER-DEFINED"`` so the registry can tell them apart
    from anything catalogued from the vehicle. Not wired into
    :func:`channels.registry` here -- that integration belongs to whoever owns
    the poller/registry wiring; this function only hands back well-formed
    objects for that step.
    """
    out: list[channels_mod.Channel] = []
    for ch in _load_raw():
        if ch.get("kind") == "did":
            out.append(channels_mod.Channel(
                id=ch["id"], name=ch["name"], unit=ch.get("unit", ""), kind="did",
                bus="can_c", confidence="USER-DEFINED", default_rate_hz=channels_mod.MED_HZ,
                module=ch.get("module", ""), did=int(ch.get("did", "0"), 16),
                formula=ch.get("formula", ""),
                note="Torque-style byte algebra: A, B, C... map to successive "
                     "response bytes"))
        else:
            refs = tuple(sorted(_referenced_ids(ch.get("expr", ""))))
            out.append(channels_mod.Channel(
                id=ch["id"], name=ch["name"], unit=ch.get("unit", ""), kind="computed",
                bus="can_c", confidence="USER-DEFINED", default_rate_hz=channels_mod.MED_HZ,
                expr=ch.get("expr", ""), depends_on=refs))
    return out


# ===========================================================================
# snapshots
# ===========================================================================

_VALID_SOURCES = {"live", "replay", "demo"}


def snapshots_path() -> Path:
    return state_dir() / "live_snapshots.jsonl"


def save_snapshot(layout: str, page: str, source: str, values: dict[str, Any],
                  note: str = "") -> dict[str, Any]:
    if source not in _VALID_SOURCES:
        raise BadRequest(f"source must be one of {sorted(_VALID_SOURCES)}, got {source!r}")
    if not isinstance(values, dict):
        raise BadRequest("values must be an object of {channel: {value, unit, ...}}")
    for cid, v in values.items():
        if not isinstance(v, dict) or "value" not in v:
            raise BadRequest(f"values[{cid!r}] must be an object with at least 'value'")
    entry = {
        "id": f"snap_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "at": datetime.now().isoformat(timespec="seconds"),
        "layout": layout, "page": page, "source": source, "values": values,
        "note": note or "",
    }
    with _LOCK:
        with snapshots_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    return entry


def _read_all_snapshots() -> list[dict[str, Any]]:
    p = snapshots_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def list_snapshots(limit: int = 50) -> list[dict[str, Any]]:
    entries = _read_all_snapshots()
    return list(reversed(entries))[:limit]


def get_snapshot(snapshot_id: str) -> dict[str, Any]:
    for e in _read_all_snapshots():
        if e.get("id") == snapshot_id:
            return e
    raise NotFound(f"no snapshot {snapshot_id!r}")


def snapshot_csv(entry: dict[str, Any]) -> str:
    """One-row MES-format CSV: names row, units row, one data row, no TAG."""
    values: dict[str, Any] = entry.get("values", {})
    cids = list(values)
    names = ["Time"] + cids + ["TAG"]
    units = ["sec"] + [str(values[c].get("unit", "")) for c in cids] + [" "]
    cells = ["0.000"]
    for c in cids:
        v = values[c].get("value")
        cells.append("" if v is None else str(v))
    cells.append("")
    lines = [
        "\t".join(f'"{n}"' for n in names),
        "\t".join(f'"{u}"' for u in units),
        "\t".join(cells[:-1] + [f'"{cells[-1]}"']),
    ]
    return "\n".join(lines) + "\n"


# ===========================================================================
# triggers
# ===========================================================================

_OPS = {">", "<", ">=", "<=", "==", "crosses_above", "crosses_below"}
_ALARM_LEVELS = {"warn", "alarm"}
_ACTIONS = {"record_start", "record_stop", "snapshot", "beep", "speak", "mark"}


def triggers_path() -> Path:
    return state_dir() / "live_triggers.json"


def _known_channel_ids() -> set[str]:
    return set(channels_mod.registry()) | {c["id"] for c in _load_raw()}


def validate_trigger_rule(rule: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise BadRequest("each trigger rule must be an object")
    rid = rule.get("id")
    if not isinstance(rid, str) or not rid.strip():
        raise BadRequest("trigger rule id is required")
    enabled = rule.get("enabled", True)
    if not isinstance(enabled, bool):
        raise BadRequest(f"trigger {rid!r}: enabled must be a boolean")
    when = rule.get("when")
    if not isinstance(when, dict):
        raise BadRequest(f"trigger {rid!r}: when must be an object")
    known = _known_channel_ids()
    if "op" in when or "value" in when:
        op = when.get("op")
        if op not in _OPS:
            raise BadRequest(f"trigger {rid!r}: when.op must be one of {sorted(_OPS)}, "
                             f"got {op!r}")
        channel = when.get("channel")
        if not isinstance(channel, str) or channel not in known:
            raise BadRequest(f"trigger {rid!r}: when.channel {channel!r} is unknown")
        value = when.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise BadRequest(f"trigger {rid!r}: when.value must be a number")
        when_out = {"channel": channel, "op": op, "value": float(value)}
    elif "alarm" in when:
        level = when.get("alarm")
        if level not in _ALARM_LEVELS:
            raise BadRequest(f"trigger {rid!r}: when.alarm must be one of "
                             f"{sorted(_ALARM_LEVELS)}, got {level!r}")
        channel = when.get("channel")
        if channel is not None and channel not in known:
            raise BadRequest(f"trigger {rid!r}: when.channel {channel!r} is unknown")
        when_out = {"alarm": level}
        if channel is not None:
            when_out["channel"] = channel
    else:
        raise BadRequest(f"trigger {rid!r}: when must specify either "
                         "channel/op/value or alarm")

    action = rule.get("action")
    if action not in _ACTIONS:
        raise BadRequest(f"trigger {rid!r}: action must be one of {sorted(_ACTIONS)}, "
                         f"got {action!r}")
    cooldown = rule.get("cooldown_s", 0)
    if not isinstance(cooldown, (int, float)) or isinstance(cooldown, bool) or cooldown < 0:
        raise BadRequest(f"trigger {rid!r}: cooldown_s must be a non-negative number")

    out = {"id": rid, "enabled": enabled, "when": when_out, "action": action,
          "cooldown_s": float(cooldown)}
    text = rule.get("text")
    if text is not None:
        if not isinstance(text, str):
            raise BadRequest(f"trigger {rid!r}: text must be a string")
        out["text"] = text
    return out


def load_triggers() -> dict[str, Any]:
    p = triggers_path()
    if not p.exists():
        return {"rules": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rules": []}
    return {"rules": list(data.get("rules", []))} if isinstance(data, dict) else {"rules": []}


def save_triggers(rules: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(rules, list):
        raise BadRequest("rules must be a list")
    seen: set[str] = set()
    validated = []
    for r in rules:
        vr = validate_trigger_rule(r)
        if vr["id"] in seen:
            raise BadRequest(f"duplicate trigger id {vr['id']!r}")
        seen.add(vr["id"])
        validated.append(vr)
    with _LOCK:
        triggers_path().write_text(json.dumps({"rules": validated}, indent=2),
                                   encoding="utf-8")
    return {"rules": validated}


__all__ = ["custom_channels_path", "load_custom_channels_raw", "save_custom_channels",
          "load_custom_channels", "snapshots_path", "save_snapshot", "list_snapshots",
          "get_snapshot", "snapshot_csv", "triggers_path", "load_triggers", "save_triggers",
          "validate_custom_channels", "validate_trigger_rule"]
