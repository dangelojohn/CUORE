"""Test support: stand in for the person at the approve page, in-process, fakes only.

The real flow is: a car-affecting call is refused (a pending request now exists), a person
opens /approve/<id> in a browser and types the phrase, the caller repeats the call with
``request_id``. :func:`approved` does the same against the test process's own
:class:`~cuore.live.consent_gate.ConsentStore` by calling the store's approve method the way
the page route does (nonce + cookie from a page render + the phrase shown there). It exists
so the existing safety tests keep exercising the guards that run AFTER approval. The tests of
the gate itself (check_consent_gate.py) go through the real HTTP page.
"""
from __future__ import annotations

from typing import Any, Callable

from cuore.live import consent_gate


def fresh_authority() -> consent_gate.ConsentStore:
    """A new empty store in this process (as after a CUORE restart)."""
    consent_gate.deactivate_authority()
    return consent_gate.activate_authority(consent_gate.ConsentStore())


def person_approves(request_id: str, who: str = "test person") -> None:
    store = consent_gate.authority()
    view = store.page_view(request_id)
    nonce, cookie = store.issue_secrets(request_id)
    store.approve(request_id, view["phrase"], nonce, cookie, who)


def approved(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call ``fn`` (an ops/tool function taking ``request_id=``) the way a person-approved
    caller does: first call must be refused with a pending request; approve it; repeat."""
    if consent_gate.authority() is None:
        fresh_authority()
    try:
        fn(*args, **kwargs)
    except consent_gate.ConsentRequired as e:
        person_approves(e.info["request_id"])
        return fn(*args, request_id=e.info["request_id"], **kwargs)
    raise AssertionError("the first call was not refused for want of approval")


def approved_tool(fn: Callable[..., str], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Same for an MCP tool function, which returns JSON text instead of raising: the first call
    must answer ``consent_required`` with a request id; approve it; repeat with that id."""
    import json
    if consent_gate.authority() is None:
        fresh_authority()
    first = json.loads(fn(*args, **kwargs))
    if not first.get("consent_required"):
        raise AssertionError(f"the first call was not refused for want of approval: {first}")
    person_approves(first["request_id"])
    return json.loads(fn(*args, request_id=first["request_id"], **kwargs))
