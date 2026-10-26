"""What engine-computer software this car is running, and how to ask if it is current.

FCA flash bulletins never print a calibration number -- they say "reprogram
the PCM with the latest available software" (e.g. 18-065-22, 18-018-25), and
the 18-0xx PCM flash family repeatedly lists P0440/P0441/P0455/P0456 among
the DTCs a flash fixes (TSB 18-030-17 REV. B; docs/reference/TSB_CATALOGUE.md).
So whether a car is on the latest calibration is answerable only by the
dealer's wiTECH flash check against the VIN. What the logs CAN do is state
exactly what is installed, so the request to the dealer is specific.

Sources for the installed identity, newest first:
- a live UDS identity read of the ECM recorded by cuore (``F188`` ECU
  software number, ``F194`` supplier software, ``F191``/``F192`` hardware);
- the header of the newest MES FES session on the engine ECU
  ("Software number", "FIAT drawing number", "Spare part number").
"""

from __future__ import annotations

from typing import Any, Optional

from . import fes as fes_mod, live_obs
from .catalog import CATALOG

_ENGINE_ECU_HINTS = ("IAW", "INJECTION", "EOBD", "MOTRONIC", "MED", "MPI")


def _is_engine_ecu(desc: str) -> bool:
    up = (desc or "").upper()
    return any(h in up for h in _ENGINE_ECU_HINTS)


def installed(vin: str) -> Optional[dict[str, Any]]:
    """The ECM software identity this car's own records show."""
    out: dict[str, Any] = {}
    # Live UDS identity, if cuore has read one from the car.
    for obs in reversed(live_obs.load(vin, "identity")):
        data = obs.get("data") or {}
        if str(data.get("ecu", "")).upper() != "ECM":
            continue
        fields = data.get("fields") or {}

        def val(did: str, fields=fields) -> Optional[str]:
            f = fields.get(did) or {}
            return (f.get("ascii") or "").strip() or None

        live = {k: v for k, v in {
            "ecu_software_number": val("F188"),
            "supplier_software": val("F194"),
            "hardware_number": val("F191"),
            "supplier_hardware": val("F192"),
            "spare_part_number": val("F187"),
        }.items() if v}
        if live:
            out["live"] = {"read_at": obs.get("at"), **live}
            break  # newest observation that actually carries fields; empty ones are skipped
    # Newest MES session on the engine ECU.
    for entry in CATALOG.select(kind="fes", vin=vin):
        if entry.parse_error:
            continue
        try:
            log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
        except Exception:
            continue
        if not _is_engine_ecu(log.ecu_description):
            continue
        ident = log.identity
        mes = {k: v for k, v in {
            "ecu": log.ecu_description,
            "software_number": ident.get("Software number"),
            "software_version": ident.get("Software version"),
            "hardware_number": ident.get("Hardware number"),
            "fiat_drawing_number": ident.get("FIAT drawing number"),
            "spare_part_number": ident.get("Spare part number"),
        }.items() if v}
        if mes.get("software_number"):
            out["mes"] = {"file": entry.name, "timestamp": entry.timestamp, **mes}
            break
    return out or None


def summary_line(ident: Optional[dict[str, Any]]) -> str:
    """One line naming the installed software, from whichever source exists."""
    if not ident:
        return "installed ECM software not found in this car's logs or live reads"
    parts = []
    live = ident.get("live") or {}
    mes = ident.get("mes") or {}
    if live.get("ecu_software_number"):
        parts.append(f"ECU software {live['ecu_software_number']}")
    sup = live.get("supplier_software") or mes.get("software_number")
    if sup:
        ver = mes.get("software_version")
        parts.append(f"supplier software {sup}" + (f" ver {ver}" if ver else ""))
    hw = mes.get("hardware_number") or live.get("supplier_hardware")
    if hw:
        parts.append(f"hardware {hw}")
    return ", ".join(parts) or "installed ECM software not recorded"


def _is_evap_code(code: str) -> bool:
    """SAE P0440-P0457 (EVAP system) and P0496 (EVAP flow during non-purge)."""
    c = (code or "").split("-")[0].upper()
    return len(c) == 5 and c.startswith("P04") and (c[3:] in {f"{n:02d}" for n in range(40, 58)} | {"96"})


def dealer_request(vin: str, codes: list[str],
                   ident: Optional[dict[str, Any]] = None,
                   evap_serviced: bool = False) -> str:
    """The exact request to read to a service advisor.

    The "after the EVAP system was serviced" clause is only stated when the caller says EVAP repairs are
    recorded (``evap_serviced=True``) AND at least one of the codes is an EVAP code; otherwise it is omitted.
    """
    ident = ident if ident is not None else installed(vin)
    code_text = ", ".join(sorted({c.split("-")[0] for c in codes})) or "these codes"
    after = (" after the EVAP system was serviced"
             if evap_serviced and any(_is_evap_code(c) for c in codes) else "")
    return (f"Please run a wiTECH ECU flash check on VIN {vin}. The engine computer "
            f"currently has {summary_line(ident)}. Is a newer PCM calibration available? "
            f"The car keeps setting {code_text}{after}, and the "
            f"18-0xx PCM flash family (TSB 18-030-17 REV. B and later) lists these codes "
            f"as fixed by a flash. If it can be done during an open recall visit, please "
            f"combine it.")


__all__ = ["installed", "summary_line", "dealer_request"]
