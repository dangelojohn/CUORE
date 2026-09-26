"""Match an anonymous UDS responder to a registry module by what it says it is.

Address discovery finds live nodes by asking every target for ``22 F190``.
A node whose address is already in the registry is named by that address;
until 2026-09-25 every other hit was thrown away, which is why five modules
this car demonstrably has (ESM, DASM, AFLS, PAM, HALF) stayed at "address
unknown" forever. Each of them is recorded in Table A with the hardware and
software numbers MES printed for it, and a UDS node reports the same numbers
in its Annex C identity DIDs. Matching the two names the node.

Pure: no I/O, no device state. Stdlib only.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from .addressing import ECUAddress

#: Annex C identity DIDs worth reading from an anonymous node, in the order
#: most likely to carry a Table A number.
IDENTITY_DIDS: tuple[int, ...] = (0xF187, 0xF188, 0xF191, 0xF192, 0xF194, 0xF18C)

_VERSION_SUFFIX = re.compile(r"\s*\([0-9A-Fa-f]{1,4}\)\s*$")
_NOISE = re.compile(r"[^0-9A-Z]")

#: Shorter than this and a substring hit is coincidence, not identity.
MIN_TOKEN = 6


def normalise(value: Optional[str]) -> str:
    """``"MRR1evo14F (00)"`` -> ``"MRR1EVO14F"``: drop the MES version suffix,
    upper-case, keep only alphanumerics."""
    if not value:
        return ""
    return _NOISE.sub("", _VERSION_SUFFIX.sub("", value).upper())


def registry_tokens(module: ECUAddress) -> dict[str, str]:
    """The identifying numbers Table A holds for ``module``, normalised."""
    out: dict[str, str] = {}
    for field in ("hw_number", "sw_number"):
        tok = normalise(getattr(module, field, None))
        if len(tok) >= MIN_TOKEN:
            out[field] = tok
    return out


def match(fields: dict[str, Optional[str]],
          modules: Iterable[ECUAddress]) -> dict[str, Any]:
    """Best registry module for a node that reported ``fields``.

    ``fields`` maps DID hex (``"F192"``) to the ASCII the node returned.
    A module scores one point per Table A number found in any field
    (exact or containment, both normalised). The result is ``matched`` only
    when exactly one module has the top score; a tie is reported as
    ``ambiguous`` with the candidates, never resolved by guessing.
    """
    seen = {did: normalise(val) for did, val in fields.items() if normalise(val)}
    scored: list[tuple[int, ECUAddress, list[dict[str, str]]]] = []
    for module in modules:
        evidence: list[dict[str, str]] = []
        for field, tok in registry_tokens(module).items():
            for did, got in seen.items():
                if tok == got or (len(got) >= MIN_TOKEN and (tok in got or got in tok)):
                    evidence.append({"registry_field": field, "registry_value": tok,
                                     "did": did, "reported": got})
                    break
        if evidence:
            scored.append((len(evidence), module, evidence))
    if not scored:
        return {"matched": None, "reason": "no Table A hardware/software number in the reply"}
    scored.sort(key=lambda s: -s[0])
    top = scored[0][0]
    leaders = [s for s in scored if s[0] == top]
    if len(leaders) > 1:
        return {"matched": None, "ambiguous": [s[1].code for s in leaders],
                "reason": "several modules share the matched numbers"}
    score, module, evidence = leaders[0]
    return {"matched": module.code, "score": score, "evidence": evidence}


__all__ = ["IDENTITY_DIDS", "MIN_TOKEN", "normalise", "registry_tokens", "match"]
