# Human-only consent gate

Status: built 2026-10-30. Code: `cuore/live/consent_gate.py`, `cuore/web/approve_routes.py`,
`cuore/web/templates/approve.html`. Tests: `cuore/tests/check_consent_gate.py`.

## The defect this closes

`run_actuator`, `clear_module_dtcs`, `clear_dtcs` and `send_raw` took their "consent" as ordinary
parameters (`consent: str`, `confirm: bool`, `i_understand_this_writes_to_the_vehicle: bool`), and
`assert_raw_write_allowed` only compared a string with the expected phrase; its refusal even printed
the phrase. Whoever calls the tool supplies those values, so a language model driving the MCP tools
could consent on its own behalf. Typed consent proved nothing about a person.

## What a car-affecting call does now

1. **Refused, request created.** A call with no valid approval is refused and creates a pending
   request in the CUORE server: the exact action (tool, module, service bytes, VIN, arguments) is
   hashed into `action_hash`; the request gets a random `request_id` (144 bits) and lives 120 s
   (`REQUEST_TTL_S`). The refusal returns `request_id` and the page `/approve/{request_id}`. It never
   contains a phrase or any secret that lets the caller approve itself. An identical pending action
   reuses one request, and at most 20 are held at once.
2. **A person approves in a browser.** `/approve/{request_id}` states in plain words what will be
   sent, to which module and car, what it changes, what evidence is saved first, and which guards
   still apply. The person types the existing consent phrase (`CLEAR ECM`, `CLEAR ALL EMISSIONS
   CODES`, `ACTUATE <MODULE> <NAME>` or `RUN ROUTINE ...`, `SEND RAW <SVC> TO <MODULE>`), which is
   shown on that page only, and submits a POST. Five wrong phrases void the request.
3. **The caller repeats the same call with `request_id`.** The gate checks: approved, not expired,
   not used, and `action_hash` equal to the hash of the call being made. Any changed argument
   refuses and voids the approval. The approval is consumed atomically, under one lock, before any
   traffic leaves the adapter. A replay is refused.
4. **Everything else still runs after approval,** in the same order as before: module blocklists,
   the configuration-write service block, MES interlock, poller guard, stationary/engine-off
   checks, dry-run, evidence capture and read-back. Approval is one more gate, not a replacement.
   (A state refusal after approval, for example "vehicle is moving", spends the approval; ask again.)

The old parameters still bind so existing callers do not break, but `consent` is ignored and
`confirm=True` alone authorises nothing. `confirm` and `i_understand_this_writes_to_the_vehicle`
remain as extra preconditions, and `confirm` is part of the hashed action.

## Where state lives

* The CUORE server process is the only holder of approvals: an in-memory `ConsentStore`. A
  restart voids every approval. Nothing is written to any file the caller could edit (the audit
  log names request ids, but the gate never reads it back).
* The obd2 MCP server is a client. It holds no approval state and reaches CUORE through
  `POST /api/consent/request` and `POST /api/consent/redeem` (machine token allowed there, because
  those can only ask and consume). There is no approve route under `/api`.
* **Fail closed.** If CUORE cannot be reached, the tool refuses; there is no in-process fallback
  for a car-affecting action. The `_via(...)` fallback may still run reads. As a second belt,
  `Session.cmd` in `cuore/live/transport.py` refuses every request that is not on the read
  allowlist (OBD modes 01 02 03 05 06 07 09 0A, UDS 19 22 3E, `10 01`) unless it runs inside a
  `write_scope` opened with a genuine `Grant` for that service byte. Mode 04, Mode 08, 10 (other
  than `10 01`), 11, 14, 27, 28, 2E, 2F, 31, 3B, 85 and any service nobody has heard of are gated
  there, whatever code path built them.
* `send_raw` now treats any hex service outside that read allowlist as a write (previously
  `classify_command` was a deny-list and let unlisted services such as 0x30 or 0x3B through as
  "reads").

## How the approve POST is protected

`POST /approve/{request_id}` accepts only a browser session:

* refused if an `x-cuore-token` header or `?token=` is present (the machine path);
* refused unless Origin (else Referer) equals Host, and `Sec-Fetch-Site`, if sent, is
  `same-origin`;
* needs the per-render CSRF nonce (hidden field) **and** the `cuore_consent` cookie set on the same
  render (HttpOnly, SameSite=Strict, scoped to that request path); a new render replaces both;
* accounts mode: a signed-in user whose role is in `APPROVER_ROLES` (`admin`, `shop_lead`,
  `technician`; tighten in `consent_gate.py`); the shared token, as header or session cookie, is not
  a person. The approver's username is recorded;
* the phrase typed must equal the one shown.

The GET page shows the phrase and form only to a session that could approve.

## Audit

Through `cuore/live/audit.py`: `consent_requested`, `consent_approved` (with approver),
`consent_approve_rejected` (with reason), `consent_consumed`, `consent_refused` (with reason),
`consent_expired`. The phrase and the nonces are never logged.

## Threat model

Protects against: a language model or script calling the MCP tools or the HTTP API with the machine
token, or inventing consent strings, flags or request ids; replaying or editing an approved call;
approving by cross-site request or by a forged form; a stale approval after a CUORE restart; a gate
bypass by a code path nobody enumerated (the transport belt).

Trusted: the CUORE and MCP Python code itself, the machine it runs on, and the person at the car.

## Residual risk (not solved, do not claim otherwise)

1. **Same-OS-user local process.** Anything that runs as the same Windows user can read the web token
   file and `CUORE_TOKEN` environment, log in at `/login?token=...` to get a session cookie, GET the
   approve page (receiving the cookie and nonce) and POST it with a matching Origin. The same holds for
   an automated browser the assistant can drive. **Token-only mode (no accounts) offers no
   protection against this**, because the human and the machine hold the same credential.
2. **Accounts mode raises the bar** (a person's own password, which the machine token does not
   know) but does not stop a process that can read the person's browser session or keystrokes.
3. **The person can approve without reading.** The page puts the action first, but a habit of
   typing the phrase blindly defeats it.
4. In-process Python (tests, scripts importing `cuore.live`) can construct a `Grant`. That code is
   the trusted base.
5. The approval is bound to the action's arguments, not to the car's state at the moment of
   sending; the existing state checks still run after it.

### Mitigations (options, not built)

* **Operating-system separation:** run CUORE and the browser under a different Windows account from
  the assistant (or the assistant in a container/VM), keep the token file readable only by the
  CUORE account, and turn on accounts mode so a person's password is required.
* **Physical presence read from the car:** require a step the assistant cannot perform, read back
  over the bus before the gate opens, for example an ignition key cycle (key off then on seen in
  the status PIDs), or a brake-pedal press read from the ABS/ECM status. A hold-to-confirm button
  is already sketched in `CUORE_INTERACTIVE_PROCEDURES_DESIGN.md`.
* **Out-of-band approval:** a hardware button or a second device on a separate channel that the
  CUORE process cannot synthesise.

## Findings from the mapping that are not new gates

* HTTP `/api` and every web route can only reach `Session.uds` through `cuore/live/uds.py`, which
  enforces the read-only UDS allowlist (10 01, 19, 22, 3E); the transport belt is a second check.
* `procedure_dry_run.py` calls `actuate.run_actuator` on a fake session that never touches a port;
  it is not gated (and must not be).
* `ATSH`, `STPX` and other adapter-state commands are not car-affecting in themselves and keep
  their existing flags (`allow_adapter_reconfiguration`); `send_raw` already refuses ATSH/STPX as
  writes.

## How to test

```
.venv/Scripts/python.exe -X utf8 cuore/tests/check_consent_gate.py   # the gate, end to end
.venv/Scripts/python.exe -X utf8 cuore/tests/check_clear.py          # guards after approval
.venv/Scripts/python.exe -X utf8 cuore/tests/check_actuate.py
.venv/Scripts/python.exe -X utf8 obd2-mcp/tests/test_raw_consent.py
```

All use fakes and a temporary `CUORE_STATE_DIR`; none opens a COM port. The existing safety tests
play the person with `cuore/tests/_consent_helper.py`; only `check_consent_gate.py` goes through the
real HTTP page. By hand: call a tool with no `request_id`, open the returned `/approve/...` page in
a logged-in browser, type the phrase, then repeat the call with the id.
