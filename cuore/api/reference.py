"""Static reference data: the module registry and the failure-type table.

Both are pure lookup tables compiled into the library, which is why they are
the only corpus-independent features the drive profile keeps -- they travel
fine on a node with no logs at all.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services import mes_bridge
from .deps import require_token

router = APIRouter(tags=["reference"], dependencies=[Depends(require_token)])


@router.get("/modules", summary="The module registry, grouped by domain")
def modules(domain: str = "") -> dict[str, Any]:
    """Every ECU module MES can name, with the aliases it prints for each.

    Resolves alias sets (``TCM/NCA/NCR``), Italian node names (``NBC`` to BCM,
    ``NFR`` to ABS), and the CTM collision -- the reason a scan's module list
    can be read at all.
    """
    return mes_bridge.module_registry(domain=domain)


@router.get("/modules/{abbrev}", summary="One module by any name MES prints")
def module(abbrev: str) -> dict[str, Any]:
    return mes_bridge.module_registry(abbrev=abbrev)


@router.get("/failure-type/{byte}", summary="Decode a UDS failure-type byte")
def failure_type(byte: str) -> dict[str, Any]:
    """The two hex digits after the dash in ``U0100-87``.

    This is what separates a component fault from a bus event: ``-2F`` erratic,
    ``-86`` invalid and ``-87`` missing-message are all messages that did not
    arrive as expected, not modules that failed. Entries marked ``corpus`` were
    read off these vehicles' own ECUs; an unrecognised byte is reported as
    unknown rather than guessed at.
    """
    return mes_bridge.failure_type(byte)
