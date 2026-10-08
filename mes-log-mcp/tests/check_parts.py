"""Smoke checks for mes.parts.

Plain script style, like check_maintenance_specs.py: no test framework, no
corpus/state dependency -- this module is pure data plus a few lookup
functions.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_parts.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mes import parts as p  # noqa: E402
from mes import service_specs  # noqa: E402
from mes import drivetrain_specs  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


EXPECTED_KEYS = {
    "oil_filter", "drain_plug_gasket", "spark_plug", "ignition_coil",
    "engine_air_filter", "cabin_air_filter", "drive_belt", "battery_12v",
    "esim", "purge_valve", "evap_canister", "evap_quick_connect",
    "brake_pads_front", "brake_pads_rear", "brake_rotor_front",
    "brake_rotor_rear", "brake_fluid", "coolant", "engine_oil",
    "transmission_fluid", "transfer_case_fluid", "wiper_blades",
    "tpms_sensor", "turbo_intercooler_hose",
}

ALL_TORQUE_KEYS = ({t["key"] for t in service_specs.TORQUES}
                    | {t["key"] for t in drivetrain_specs.TORQUES})


def _is_url(u: str) -> bool:
    try:
        r = urlparse(u)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except Exception:
        return False


# --- shape ---------------------------------------------------------------

check("PARTS has exactly the specified keys",
      set(p.PARTS.keys()) == EXPECTED_KEYS,
      str(set(p.PARTS.keys()) ^ EXPECTED_KEYS))

for key, rec in p.PARTS.items():
    check(f"{key}: has every required key",
          set(p.REQUIRED_KEYS).issubset(rec.keys()),
          str(set(p.REQUIRED_KEYS) - rec.keys()))
    check(f"{key}: fits is a valid enum value",
          rec.get("fits") in p.FITS_VALUES, rec.get("fits"))
    check(f"{key}: name and what_it_does are non-empty strings",
          bool(rec.get("name")) and bool(rec.get("what_it_does")))
    check(f"{key}: location is a non-empty string",
          bool(rec.get("location")))
    check(f"{key}: oem/supersedes/aftermarket/related_codes/related_jobs/"
          "torque_keys/buy/images are lists",
          all(isinstance(rec.get(f), list) for f in
              ("oem", "supersedes", "aftermarket", "related_codes",
               "related_jobs", "torque_keys", "buy", "images")))

    # every non-UNKNOWN OEM number has a source
    for oem in rec.get("oem", []):
        check(f"{key}: oem entry has a valid confidence",
              oem.get("confidence") in p.CONFIDENCE_LEVELS,
              oem.get("confidence"))
        if oem.get("number") is not None:
            # Any number present -- even one carried at UNKNOWN confidence
            # because fitment/correctness is unresolved -- must trace to a
            # source; nothing is ever typed in from nowhere.
            check(f"{key}: oem number {oem.get('number')!r} "
                  f"(confidence {oem.get('confidence')}) has a source",
                  bool(oem.get("source")))
        else:
            check(f"{key}: oem entry with no number has a note pointing "
                  "to the service manual or explaining why",
                  bool(oem.get("note")))

    for am in rec.get("aftermarket", []):
        if am.get("number") is not None and am.get("confidence") != p.UNKNOWN:
            check(f"{key}: aftermarket number {am.get('number')!r} has a "
                  "source", bool(am.get("source")))

    # price, if present, is well-formed and sourced
    price = rec.get("price")
    if price is not None:
        check(f"{key}: price has a source",
              bool(price.get("source")))
        check(f"{key}: price has at least one of low/high",
              price.get("low") is not None or price.get("high") is not None)
        check(f"{key}: price has as_of and currency",
              bool(price.get("as_of")) and bool(price.get("currency")))

    # buy URLs are well-formed
    for b in rec.get("buy", []):
        check(f"{key}: buy entry has label and well-formed url",
              bool(b.get("label")) and _is_url(b.get("url", "")),
              b)

    # images are well-formed and carry verified_at/verified_how (link-only,
    # never copied into the repo -- see module docstring)
    for img in rec.get("images", []):
        check(f"{key}: image entry has a well-formed url",
              _is_url(img.get("url", "")), img)
        check(f"{key}: image entry has verified_at and verified_how",
              bool(img.get("verified_at")) and bool(img.get("verified_how")),
              img)
        check(f"{key}: image kind is one of photo/diagram/exploded_view",
              img.get("kind") in ("photo", "diagram", "exploded_view"),
              img.get("kind"))

    # torque_keys resolve against service_specs or drivetrain_specs
    for tk in rec.get("torque_keys", []):
        check(f"{key}: torque_key {tk!r} resolves in service_specs or "
              "drivetrain_specs", tk in ALL_TORQUE_KEYS)


# --- lookup functions ------------------------------------------------------

check("get('oil_filter') returns the oil filter record",
      p.get("oil_filter") is not None and p.get("oil_filter")["name"].lower().startswith("engine oil filter"))

check("get('does_not_exist') returns None",
      p.get("does_not_exist") is None)

code_hits = {h["key"] for h in p.for_code("P0455")}
check("for_code('P0455') returns esim/purge_valve/evap_canister/"
      "evap_quick_connect",
      {"esim", "purge_valve", "evap_canister", "evap_quick_connect"}.issubset(code_hits),
      str(code_hits))

code_hits_lower = {h["key"] for h in p.for_code("p0455")}
check("for_code is case-insensitive",
      code_hits_lower == code_hits)

job_hits = {h["key"] for h in p.for_job("evap_leak")}
check("for_job('evap_leak') returns the EVAP parts",
      {"esim", "purge_valve", "evap_canister", "evap_quick_connect"}.issubset(job_hits),
      str(job_hits))

check("for_job('nonexistent_job') returns an empty list",
      p.for_job("nonexistent_job") == [])

check("all() returns every part keyed consistently with PARTS",
      set(p.all().keys()) == EXPECTED_KEYS)


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
