"""The human-only consent gate for every request that can change the car.

Why it exists
-------------
Until 2026-10-30 the consent for a clear, an actuator test or a raw write was a
plain parameter of the MCP tool (``consent="CLEAR ECM"``, ``confirm=True``,
``i_understand_this_writes_to_the_vehicle=True``). Whoever calls the tool
supplies those values, and the refusal message even printed the phrase. A
language model driving the tool could therefore "consent" on its own. Typed
consent proved nothing about a person.

What it does now
----------------
A car-affecting call with no valid approval is REFUSED and creates a pending
request: the exact action (tool, module, service bytes, VIN, arguments) is
hashed, the request gets a random id and lives 120 s. The refusal carries the id
and the page to open (``/approve/<id>``) and never the phrase. A person opens
that page in a browser, reads what will be sent, types the consent phrase shown
there and submits. The caller then repeats the SAME call with ``request_id``;
the gate checks approved / not expired / not used / identical action hash, and
consumes the approval atomically before any traffic is sent. All state is in
this process's memory (the CUORE server): a restart voids every approval and no
file holds one.

Where things live
-----------------
* The CUORE server process is the *authority*: :func:`activate_authority`
  (called from ``create_app``) gives it the one :class:`ConsentStore`.
* Any other process (the obd2 MCP server) is a *client*: it holds no approval
  state. :func:`set_remote` points it at CUORE's ``/api/consent/request`` and
  ``/api/consent/redeem``. If CUORE cannot be reached the answer is a refusal --
  there is no in-process fallback for a car-affecting action.
* Approving is possible only through the browser page (``POST /approve/<id>``);
  the machine token has no route to it.

A second belt sits in :meth:`cuore.live.transport.Session.cmd`: every request
that is not on the read allowlist (:func:`gated_service`) must run inside
:func:`write_scope` with a genuine :class:`Grant` for that service, whatever
code path produced it.

Honest limit: a process running as the same OS user, or an automated browser,
can still drive the approve page. See docs/design/CONSENT_GATE.md.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from . import audit
from .errors import Refused

#: Seconds a request stays usable, counted from the moment it was created.
REQUEST_TTL_S = 120.0
#: Pending/approved requests held at once; a flood of requests is refused.
MAX_PENDING = 20
#: Wrong phrases tolerated on one request before it is voided.
MAX_PHRASE_TRIES = 5
#: Accounts-mode roles allowed to approve (the shared machine token never is).
APPROVER_ROLES = ("admin", "shop_lead", "technician")

TOOLS = ("clear_module_dtcs", "clear_dtcs", "run_actuator", "send_raw")

_SCALARS = (str, int, float, bool, type(None))


# --- errors ---------------------------------------------------------------------------------

class ConsentRefused(Refused):
    """No valid approval for this action. Never carries the consent phrase."""


class ConsentUnavailable(ConsentRefused):
    """The consent authority (the CUORE server) cannot be reached: fail closed."""


class ConsentRequired(ConsentRefused):
    """First call: refused, and a pending request now exists for a person to approve."""

    def __init__(self, info: dict[str, Any]) -> None:
        self.info = dict(info)
        super().__init__(
            "this action changes the car and needs a person's approval; none was given. "
            f"A request was created: open {self.info.get('approve_path', '/approve/<request_id>')} "
            "in the CUORE browser, read it and approve it there, then repeat this same call "
            "with request_id. This tool cannot approve for you.")

    def payload(self, base_url: str = "") -> dict[str, Any]:
        path = self.info.get("approve_path") or f"/approve/{self.info.get('request_id', '')}"
        return {"refused": str(self), "consent_required": True,
                "request_id": self.info.get("request_id"),
                "approve_page": (base_url.rstrip("/") + path) if base_url else path,
                "expires_in_s": self.info.get("expires_in_s"),
                "action_hash": self.info.get("action_hash")}


# --- the action -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    """Exactly what will be sent. Everything here is hashed; change anything and the
    approval no longer matches."""

    tool: str
    module: str
    service: str            # comma-separated two-hex-digit service bytes, e.g. "14" or "10,2F,31"
    vin: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    def canonical(self) -> str:
        return json.dumps({"v": 1, "tool": self.tool, "module": self.module.strip().upper(),
                           "service": self.service.strip().upper(),
                           "vin": self.vin.strip().upper(), "args": self.args},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def hash(self) -> str:
        return hashlib.sha256(self.canonical().encode("ascii")).hexdigest()

    def services(self) -> frozenset[str]:
        return frozenset(s.strip().upper() for s in self.service.split(",") if s.strip())

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "module": self.module, "service": self.service,
                "vin": self.vin, "args": self.args}

    @staticmethod
    def from_dict(d: Any) -> "Action":
        """Strict parse of an action sent over HTTP; anything odd is refused."""
        if not isinstance(d, dict):
            raise ConsentRefused("malformed action")
        tool, module, service, vin, args = (d.get("tool"), d.get("module"), d.get("service"),
                                            d.get("vin", ""), d.get("args", {}))
        if tool not in TOOLS:
            raise ConsentRefused("unknown tool in action")
        if not all(isinstance(x, str) for x in (module, service, vin)) or not isinstance(args, dict):
            raise ConsentRefused("malformed action")
        if len(module) > 32 or len(service) > 64 or len(vin) > 32:
            raise ConsentRefused("malformed action")
        for k, v in args.items():
            ok = isinstance(v, _SCALARS) or (isinstance(v, list)
                                             and all(isinstance(i, _SCALARS) for i in v))
            if not isinstance(k, str) or len(k) > 40 or not ok or len(json.dumps(v)) > 400:
                raise ConsentRefused("malformed action arguments")
        return Action(tool=tool, module=module, service=service, vin=vin, args=dict(args))


def phrase_for(action: Action) -> str:
    """The existing consent phrase for this action. Shown on the approve page only."""
    from . import actuate, clear
    from .safety import raw_write_phrase
    a = action.args
    if action.tool == "clear_module_dtcs":
        return clear.consent_phrase(action.module)
    if action.tool == "clear_dtcs":
        return clear.CLEAR_ALL_PHRASE
    if action.tool == "run_actuator":
        return actuate.consent_phrase(action.module, str(a.get("name", "")),
                                      routine=bool(a.get("routine")))
    if action.tool == "send_raw":
        return raw_write_phrase(str(a.get("command", "")), action.module)
    raise ConsentRefused("unknown tool in action")


def validate_action(action: Action) -> None:
    """Refuse, before any request exists, an action the static blocklists already forbid.

    Pure and cheap. The tools run the full existing gates as well; this only keeps a
    forbidden action from ever becoming something a person is asked to approve."""
    from . import addressing
    from .safety import (ACTUATION_BLOCKED_MODULES, CONFIGURATION_WRITE_SERVICES,
                         RAW_WRITE_BLOCKED_MODULES)
    if action.tool not in TOOLS:
        raise ConsentRefused("unknown tool in action")
    code = action.module.strip().upper()
    ecu = addressing.by_code(code) if code and code != "ALL" else None
    can_ch = bool(ecu and ecu.bus_key == "can_ch")
    if action.tool == "run_actuator" and (code in ACTUATION_BLOCKED_MODULES or can_ch):
        raise Refused(f"actuator tests are refused on {code}: safety-critical module or CAN-CH; "
                      "use MultiEcuScan or wiTECH, never a replay here")
    if action.tool == "send_raw":
        if code in RAW_WRITE_BLOCKED_MODULES or can_ch:
            raise Refused(f"raw writes are refused on {code}: safety-critical module or CAN-CH; "
                          "use MultiEcuScan or wiTECH, never a raw send here")
        for s in action.services():
            if int(s, 16) in CONFIGURATION_WRITE_SERVICES:
                raise Refused(f"UDS service 0x{s} is a configuration/coding write and is refused "
                              "on every module, with no override")


def describe(action: Action) -> dict[str, Any]:
    """Plain words for the approve page: what is sent, where, what changes, what is saved first."""
    from . import addressing
    a = action.args
    code = action.module.strip().upper()
    ecu = addressing.by_code(code) if code and code != "ALL" else None
    where = (f"{code} ({ecu.name}) on {ecu.bus_key}" if ecu else
             ("every module that answers a legislated emissions request" if code == "ALL" else code))
    car = action.vin.strip().upper() or "the car currently connected (no VIN was given)"
    if action.tool == "clear_module_dtcs":
        return {
            "title": f"Clear the fault codes stored in {code}", "car": car, "to": where,
            "sends": f"UDS service 0x14 ClearDiagnosticInformation, group {a.get('group', 'FFFFFF')}",
            "changes": "Erases that module's stored fault codes, their snapshot and extended data, "
                       "and the occurrence counters. It cannot be undone.",
            "evidence": "Before the clear CUORE reads all of the module's codes (19 02 FF) plus the "
                        "snapshot and extended data of every active code and saves them to a file "
                        "in the CUORE state folder and the observation store. It reads back after.",
            "guards": "Refused if the car reads moving or the speed cannot be read."}
    if action.tool == "clear_dtcs":
        return {
            "title": "Clear ALL emissions codes (OBD-II Mode 04)", "car": car, "to": where,
            "sends": "OBD-II Mode 04 (functional, to every emissions module)",
            "changes": "Erases stored, pending and permanent emissions codes, the freeze frame and "
                       "the readiness monitors. A clean re-scan proves nothing until the monitors "
                       "have run again. It cannot be undone.",
            "evidence": "Before the clear CUORE saves the stored, pending and permanent codes, the "
                        "freeze-frame code and the readiness state to a file in the CUORE state "
                        "folder. It reads back after.",
            "guards": "Refused if the car reads moving or the speed cannot be read; refused while "
                      "MultiEcuScan is connected or a live-data poll holds the adapter."}
    if action.tool == "run_actuator":
        routine = bool(a.get("routine"))
        what = ("starts a module ROUTINE whose effect CUORE cannot know; it may be an adaptation "
                "reset, not an output test" if routine else
                "physically drives hardware in that module (a valve, relay or motor)")
        return {
            "title": f"Run learned {'routine' if routine else 'actuator test'} '{a.get('name', '')}' on {code}",
            "car": car, "to": where,
            "sends": f"UDS service(s) {action.service.replace(',', ', ')} replayed from a procedure "
                     f"learned from a dealer tool, for at most {a.get('max_seconds', '?')} s",
            "changes": f"This {what}. CUORE always tries to hand control back afterwards.",
            "evidence": "No snapshot of fault memory is taken first. Every step sent and every reply "
                        "is saved as an observation and in the audit log afterwards.",
            "guards": "Refused unless the engine is off and the car is stationary (RPM and speed "
                      "must be readable) and the module is not safety-critical."}
    if action.tool == "send_raw":
        return {
            "title": f"Send one raw command to {code}", "car": car, "to": where,
            "sends": f"{a.get('command', '')} (UDS service 0x{action.service})",
            "changes": "A raw service request that can change state in that module. CUORE does not "
                       "know the exact effect of the bytes beyond the service name.",
            "evidence": "No snapshot is taken first. The command and the reply are saved in the "
                        "audit log.",
            "guards": "Refused on safety-critical modules, on CAN-CH, for configuration/coding "
                      "services, while MultiEcuScan is connected or a poll holds the adapter."}
    raise ConsentRefused("unknown tool in action")


# --- the grant --------------------------------------------------------------------------------

_MINT = object()


@dataclass(frozen=True)
class Grant:
    """Proof that a person approved exactly this action and it was consumed just now.

    Only :class:`ConsentStore`/:func:`authorize` mint one. (Python cannot stop code running
    inside the process from forging one; that code is the trusted computing base. It is the
    MCP caller, which can only pass strings, that cannot.)"""

    request_id: str
    action_hash: str
    tool: str
    approver: str
    services: frozenset[str]
    _mint: object = field(default=None, repr=False, compare=False)


def is_genuine(grant: Any) -> bool:
    return isinstance(grant, Grant) and grant._mint is _MINT


def _mint(request_id: str, action: Action, approver: str) -> Grant:
    return Grant(request_id=request_id, action_hash=action.hash(), tool=action.tool,
                 approver=approver, services=action.services(), _mint=_MINT)


# --- the store (authority process only) -----------------------------------------------------------

def _norm_phrase(s: str) -> str:
    return " ".join((s or "").split()).upper()


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class _Req:
    request_id: str
    action: Action
    action_hash: str
    phrase: str
    created: float
    expires: float
    state: str = "pending"      # pending | approved | consumed | voided | expired
    approver: str = ""
    approved_at: float = 0.0
    tries: int = 0
    nonce_h: str = ""
    cookie_h: str = ""
    expiry_audited: bool = False


class ConsentStore:
    """Pending and approved requests. In memory only, behind one lock."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self._reqs: dict[str, _Req] = {}

    # internal; caller holds the lock
    def _purge(self, now: float) -> None:
        for r in list(self._reqs.values()):
            if now >= r.expires and r.state in ("pending", "approved"):
                r.state = "expired"
            if r.state == "expired" and not r.expiry_audited:
                r.expiry_audited = True
                audit.record("consent_expired", request_id=r.request_id,
                             action_hash=r.action_hash, tool=r.action.tool,
                             module=r.action.module)
            if now >= r.expires + 600:
                del self._reqs[r.request_id]

    def create(self, action: Action, requested_by: str = "") -> dict[str, Any]:
        validate_action(action)
        ah = action.hash()
        with self._lock:
            now = self.clock()
            self._purge(now)
            for r in self._reqs.values():     # one page per identical pending action
                if r.state == "pending" and r.action_hash == ah:
                    return self._info(r, now, reused=True)
            live = sum(1 for r in self._reqs.values() if r.state in ("pending", "approved"))
            if live >= MAX_PENDING:
                audit.record("consent_refused", reason="too many pending requests",
                             action_hash=ah, tool=action.tool)
                raise ConsentRefused("too many approval requests are waiting; let them expire "
                                     "or approve them first")
            rid = secrets.token_urlsafe(18)
            r = _Req(request_id=rid, action=action, action_hash=ah, phrase=phrase_for(action),
                     created=now, expires=now + REQUEST_TTL_S)
            self._reqs[rid] = r
            audit.record("consent_requested", request_id=rid, action_hash=ah, tool=action.tool,
                         module=action.module, vin=action.vin, service=action.service,
                         args=action.args, requested_by=requested_by or None)
            return self._info(r, now)

    def _info(self, r: _Req, now: float, reused: bool = False) -> dict[str, Any]:
        return {"request_id": r.request_id, "approve_path": f"/approve/{r.request_id}",
                "expires_in_s": max(0, int(r.expires - now)), "action_hash": r.action_hash,
                "reused": reused}

    def page_view(self, request_id: str) -> Optional[dict[str, Any]]:
        """What the approve page shows, phrase included. Only the page route calls this."""
        with self._lock:
            now = self.clock()
            self._purge(now)
            r = self._reqs.get(request_id)
            if r is None:
                return None
            return {"request_id": r.request_id, "state": r.state, "action": r.action.to_dict(),
                    "action_hash": r.action_hash, "phrase": r.phrase,
                    "expires_in_s": max(0, int(r.expires - now)), "approver": r.approver,
                    "description": describe(r.action)}

    def status(self, request_id: str) -> Optional[str]:
        with self._lock:
            self._purge(self.clock())
            r = self._reqs.get(request_id)
            return r.state if r else None

    def issue_secrets(self, request_id: str) -> Optional[tuple[str, str]]:
        """A fresh (nonce, cookie) pair for one page render; the previous pair stops working."""
        with self._lock:
            self._purge(self.clock())
            r = self._reqs.get(request_id)
            if r is None or r.state != "pending":
                return None
            nonce, cookie = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
            r.nonce_h, r.cookie_h = _h(nonce), _h(cookie)
            return nonce, cookie

    def approve(self, request_id: str, typed_phrase: str, nonce: str, cookie: str,
                approver: str) -> None:
        """Record a person's approval. Called only by the browser POST route."""
        def reject(r: Optional[_Req], reason: str) -> ConsentRefused:
            audit.record("consent_approve_rejected", request_id=request_id, reason=reason,
                         action_hash=r.action_hash if r else None, approver=approver or None)
            return ConsentRefused(reason)

        with self._lock:
            now = self.clock()
            self._purge(now)
            r = self._reqs.get(request_id)
            if r is None:
                raise reject(None, "unknown or expired request")
            if r.state != "pending":
                raise reject(r, f"this request is {r.state} and cannot be approved")
            if not (r.nonce_h and r.cookie_h and nonce and cookie
                    and hmac.compare_digest(_h(nonce), r.nonce_h)
                    and hmac.compare_digest(_h(cookie), r.cookie_h)):
                raise reject(r, "this page is out of date; reload it and try again")
            if not hmac.compare_digest(_h(_norm_phrase(typed_phrase)), _h(_norm_phrase(r.phrase))):
                r.tries += 1
                if r.tries >= MAX_PHRASE_TRIES:
                    r.state = "voided"
                raise reject(r, "the phrase typed does not match"
                             + ("; the request is voided" if r.state == "voided" else ""))
            r.state, r.approver, r.approved_at = "approved", approver, now
            r.nonce_h = r.cookie_h = ""          # the page secrets are spent
            audit.record("consent_approved", request_id=request_id, action_hash=r.action_hash,
                         tool=r.action.tool, module=r.action.module, vin=r.action.vin,
                         approver=approver)

    def redeem(self, request_id: str, action: Action) -> Grant:
        """Verify and consume an approval atomically. Raises :class:`ConsentRefused`."""
        ah = action.hash()

        def refuse(r: Optional[_Req], reason: str) -> ConsentRefused:
            audit.record("consent_refused", request_id=request_id, reason=reason,
                         action_hash=ah, tool=action.tool, module=action.module)
            return ConsentRefused(reason)

        with self._lock:
            now = self.clock()
            self._purge(now)
            r = self._reqs.get(request_id)
            if r is None:
                raise refuse(None, "unknown or expired approval request")
            if r.state == "consumed":
                raise refuse(r, "this approval was already used; a new request is needed")
            if r.state == "expired":
                raise refuse(r, "this approval request expired; a new request is needed")
            if r.state == "voided":
                raise refuse(r, "this approval request was voided; a new request is needed")
            if r.state != "approved":
                raise refuse(r, "no person has approved this request yet")
            if not hmac.compare_digest(ah, r.action_hash):
                r.state = "voided"
                raise refuse(r, "the call differs from the action that was approved "
                                "(an argument changed); the approval is voided")
            r.state = "consumed"
            audit.record("consent_consumed", request_id=request_id, action_hash=ah,
                         tool=action.tool, module=action.module, vin=action.vin,
                         approver=r.approver)
            return _mint(request_id, action, r.approver)


# --- authority / client wiring ---------------------------------------------------------------------

_authority: Optional[ConsentStore] = None
_remote: Optional[Callable[..., Any]] = None
_remote_errors: tuple[type[BaseException], ...] = ()


def activate_authority(store: Optional[ConsentStore] = None) -> ConsentStore:
    """Make THIS process the consent authority (the CUORE server). Idempotent."""
    global _authority
    if store is not None:
        _authority = store
    elif _authority is None:
        _authority = ConsentStore()
    return _authority


def deactivate_authority() -> None:
    """Tests only: forget the store (a restart would do the same)."""
    global _authority
    _authority = None


def authority() -> Optional[ConsentStore]:
    return _authority


def set_remote(call: Optional[Callable[..., Any]],
               errors: tuple[type[BaseException], ...] = ()) -> None:
    """Client processes: ``call(method, path, body=..., timeout=...)`` reaches CUORE's /api."""
    global _remote, _remote_errors
    _remote, _remote_errors = call, errors


def authorize(action: Action, request_id: str = "") -> Grant:
    """The gate. Returns a :class:`Grant` only for an approved, unexpired, unused request whose
    action hash equals ``action``'s, and consumes it. Otherwise raises:

    * :class:`ConsentRequired` -- no ``request_id``: a pending request was created;
    * :class:`ConsentRefused` -- anything else wrong with the approval;
    * :class:`ConsentUnavailable` -- the authority cannot be reached (fail closed);
    * :class:`Refused` -- the action is forbidden outright (blocklists).
    """
    try:
        validate_action(action)
    except Refused as e:
        audit.record("consent_refused", reason=str(e), tool=action.tool, module=action.module,
                     action_hash=action.hash())
        raise
    rid = (request_id or "").strip()
    if _authority is not None:
        if not rid:
            raise ConsentRequired(_authority.create(action))
        return _authority.redeem(rid, action)
    if _remote is None:
        audit.record("consent_refused", reason="no consent authority", tool=action.tool,
                     module=action.module, action_hash=action.hash())
        raise ConsentUnavailable("the CUORE server that owns approvals is not available, so "
                                 "nothing that changes the car can run; start CUORE and retry")
    try:
        if not rid:
            res = _remote("POST", "/consent/request", body={"action": action.to_dict()}, timeout=15)
        else:
            res = _remote("POST", "/consent/redeem",
                          body={"request_id": rid, "action": action.to_dict()}, timeout=15)
    except _remote_errors as e:
        audit.record("consent_refused", reason=f"authority unreachable: {type(e).__name__}",
                     tool=action.tool, module=action.module, action_hash=action.hash())
        raise ConsentUnavailable("the CUORE server that owns approvals is not reachable, so "
                                 "nothing that changes the car can run; no approval, no traffic")
    if not isinstance(res, dict) or res.get("error"):
        detail = str(res.get("error")) if isinstance(res, dict) else "bad reply"
        audit.record("consent_refused", reason=f"authority said: {detail}"[:200],
                     tool=action.tool, module=action.module, action_hash=action.hash())
        raise ConsentRefused(f"approval refused: {detail}")
    if not rid:
        if not res.get("request_id"):
            raise ConsentUnavailable("the CUORE server gave no request id")
        raise ConsentRequired(res)
    if res.get("granted") is not True or res.get("action_hash") != action.hash():
        raise ConsentRefused("approval refused: the authority did not grant this action")
    return _mint(rid, action, str(res.get("approver") or ""))


# --- the write scope and the transport belt ----------------------------------------------------------

_SCOPE: contextvars.ContextVar[Optional[Grant]] = contextvars.ContextVar("cuore_write_scope",
                                                                         default=None)


@contextlib.contextmanager
def write_scope(grant: Any) -> Iterator[Grant]:
    """Allow the gated requests named by ``grant`` to leave the adapter inside this block."""
    if not is_genuine(grant):
        raise ConsentRefused("no valid approval: a car-affecting request cannot run")
    token = _SCOPE.set(grant)
    try:
        yield grant
    finally:
        _SCOPE.reset(token)


#: First bytes of requests that only read: legislated OBD modes 01 02 03 05 06 07 09 0A, and
#: UDS 19 / 22 / 3E. (Mode 04 clears and Mode 08 actuates, so they are not here; 10 is allowed
#: only for sub-function 01, the default session.)
_READ_FIRST_BYTES = frozenset({"01", "02", "03", "05", "06", "07", "09", "0A", "19", "22", "3E"})
_HEX = frozenset("0123456789ABCDEF")


def gated_service(command: str) -> Optional[str]:
    """The service byte (two hex digits) if this adapter command could change the car, else None.

    AT/ST adapter commands and anything non-hex are not decided here (the adapter-state and
    classification rules own them). Fail closed: any hex request not on the read allowlist is
    gated, including services nobody has heard of."""
    compact = (command or "").strip().upper().replace(" ", "")
    if not compact or any(c not in _HEX for c in compact):
        return None
    first = compact[:2]
    if first in _READ_FIRST_BYTES:
        return None
    if first == "10" and compact[2:4] == "01":
        return None
    return first if len(first) == 2 else compact


def assert_request_permitted(command: str) -> None:
    """Transport belt: refuse a car-affecting request that is not inside a matching write scope."""
    svc = gated_service(command)
    if svc is None:
        return
    grant = _SCOPE.get()
    if not is_genuine(grant) or svc not in grant.services:
        audit.record("consent_refused", reason="car-affecting request outside an approved scope",
                     service=svc)
        raise ConsentRefused(
            f"service 0x{svc} changes the car and has no matching approval in force; "
            "nothing was sent")


def _reset_for_tests() -> None:
    global _authority, _remote, _remote_errors
    _authority, _remote, _remote_errors = None, None, ()


__all__ = [
    "REQUEST_TTL_S", "MAX_PENDING", "MAX_PHRASE_TRIES", "APPROVER_ROLES", "TOOLS",
    "ConsentRefused", "ConsentUnavailable", "ConsentRequired", "Action", "Grant", "ConsentStore",
    "phrase_for", "validate_action", "describe", "is_genuine", "activate_authority",
    "deactivate_authority", "authority", "set_remote", "authorize", "write_scope",
    "gated_service", "assert_request_permitted",
]
