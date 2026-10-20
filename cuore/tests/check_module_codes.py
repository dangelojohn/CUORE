"""Checks for tonight's module-code sweep (2018 Stelvio, 2026-10-13), plus the
14 Oct follow-up scan's two new codes (DTCM U0100, RFHUB U2054):

  1. ``mes.dtc.failure_type`` covers all seven failure-type bytes from the
     sweep (2F, 86, 87, 97, 4A, 64, 00), each with the standard SAE J2012-DA
     / ISO 14229-1 wording and a "...(CORROBORATED)" source.
  2. ``mes.dtc_descriptions.code_description`` returns, for each of the eight
     module codes (U1713, U1736, U1765, B1176, B10AA, B1040, U0100, U2054),
     either a sourced description or the honest UNKNOWN wording -- never an
     empty string either way.
  3. ``cuore/web/templates/_code_brief.html`` renders the "-2F: signal
     erratic (...)" suffix line for "U1713-2F" when its context supplies a
     ``failure_type`` global and an occurrence record naming the full code.
  4. U0100 (standard SAE lost-communication code) and U2054 (named member of
     the BCM/RFHUB/DTCM cascade) both count toward the network family's
     "one power or bus event" grouping -- ``mes.faulttree.NETWORK_CASCADE``
     and ``mes.electrical.code_electrical_path``.

Same posture as the other ``check_*`` scripts: plain script, ``check()``,
exit 1 on failure, no pytest.

Run:
    .venv/Scripts/python.exe cuore/tests/check_module_codes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mes-log-mcp"))

from mes import dtc as dtc_mod  # noqa: E402
from mes import dtc_descriptions as dtc_desc  # noqa: E402
from mes import electrical as electrical_mod  # noqa: E402
from mes import faulttree  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- 1. failure-type bytes --------------------------------------------------

EXPECTED_FTB = {
    "2F": "signal erratic",
    "86": "signal invalid",
    "87": "missing message",
    "97": "obstructed",  # "...obstructed/blocked"
    "4A": "incorrect component installed",
    "64": "signal plausibility failure",
    "00": "no sub type",
}

for byte, expect_substr in EXPECTED_FTB.items():
    ft = dtc_mod.failure_type(byte)
    check(f"failure_type({byte}) resolves", ft is not None, byte)
    if ft is not None:
        check(f"failure_type({byte}) text has standard wording",
              expect_substr in ft.text, ft.text)
        check(f"failure_type({byte}) source is CORROBORATED",
              "CORROBORATED" in ft.source and "SAE J2012-DA" in ft.source,
              ft.source)
        check(f"failure_type({byte}) confidence is confirmed",
              ft.confidence == "confirmed", ft.confidence)
        d = ft.to_dict()
        check(f"failure_type({byte}).to_dict() exposes text/source/confidence",
              {"text", "source", "confidence"} <= d.keys(), d)

# --- 2. code descriptions ---------------------------------------------------

SWEEP_CODES = ["U1713", "U1736", "U1765", "B1176", "B10AA", "B1040",
               "U0100", "U2054"]

for code in SWEEP_CODES:
    desc = dtc_desc.code_description(code)
    check(f"{code} description is a dict", isinstance(desc, dict), desc)
    text = desc.get("text", "")
    check(f"{code} description text is non-empty", bool(text and text.strip()), desc)
    conf = desc.get("confidence", "")
    check(f"{code} confidence is one of CONFIRMED/SINGLE-SOURCE/UNKNOWN",
          conf in ("CONFIRMED", "SINGLE-SOURCE", "UNKNOWN"), conf)
    if conf == "UNKNOWN":
        check(f"{code} UNKNOWN wording points at the service manual",
              "service manual" in text and "TechAuthority" in text, text)
    else:
        check(f"{code} sourced description carries a source", bool(desc.get("source")), desc)

# Also exercise the -FTB suffix form and the honest U-code range note.
check("code_description tolerates a full CODE-FTB token",
      dtc_desc.code_description("U1713-2F")["code"] == "U1713")
_u_unknown = dtc_desc.code_description("U1799")
check("an un-sourced U1xxx code still states the generic SAE J2012 range",
      "manufacturer-defined network" in _u_unknown["text"], _u_unknown["text"])

# --- 2b. the 14 Oct scan's two new codes fold into the network family ------

for new_code in ("U0100", "U2054"):
    desc = dtc_desc.code_description(new_code)
    check(f"{new_code} description is non-empty",
          bool(desc.get("text", "").strip()), desc)
    check(f"{new_code} carries a grade",
          desc.get("confidence") in ("CONFIRMED", "SINGLE-SOURCE", "UNKNOWN"),
          desc)
    check(f"{new_code} is a named member of NETWORK_CASCADE",
          new_code in faulttree.NETWORK_CASCADE.codes,
          sorted(faulttree.NETWORK_CASCADE.codes))
    path = electrical_mod.code_electrical_path(new_code)
    check(f"{new_code} resolves to the 'network' electrical family",
          path["family"] == "network", path)

check("U0100's own description counts it as lost-communication",
      "Lost Communication" in dtc_desc.code_description("U0100")["text"])
check("U0100 is graded CONFIRMED (standard SAE code)",
      dtc_desc.code_description("U0100")["confidence"] == "CONFIRMED")
check("U2054's own description carries a sourced URL (dtcdecode.com match)",
      bool(dtc_desc.code_description("U2054").get("url")))

# --- 3. _code_brief.html renders the suffix ---------------------------------

try:
    from jinja2 import Environment, FileSystemLoader

    TEMPLATE_DIR = REPO_ROOT / "cuore" / "web" / "templates"
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

    def _failure_type_global(byte: str):
        ft = dtc_mod.failure_type(byte)
        return ft.to_dict() if ft else None

    env.globals["failure_type"] = _failure_type_global

    tmpl = env.get_template("_code_brief.html")
    html = tmpl.render(
        vin="TESTVIN000000001",
        code="U1713",
        compact=True,
        records=[{"dtc": "U1713-2F", "modules": ["BCM"],
                  "occurrences": [{"status": "stored"}]}],
    )
    check("partial renders the FTB suffix text", "-2F" in html and "signal erratic" in html,
          html[:4000])
    check("partial renders the module name alongside the suffix",
          "BCM" in html, html[:4000])

    # per-code findings render (SAFETY marker for C104B-92)
    from mes import code_findings as _cfm
    env.globals["code_findings"] = _cfm.lookup
    html2 = tmpl.render(vin="TESTVIN000000001", code="C104B-92", compact=True,
                        records=[{"dtc": "C104B-92", "modules": ["ABS"],
                                  "occurrences": [{"status": "cleared"}]}])
    check("code findings load for C104B-92 (ABS) and the key codes",
          len(_cfm.lookup("C104B-92", "ABS")) == 1
          and all(_cfm.lookup(c) for c in ("U1700-87", "U1713-2F", "C141B-97", "B1176-97", "U1736-87", "P1DAD-00")))
    check("partial renders C104B-92 findings with the SAFETY marker and ABS-read proof",
          "SAFETY" in html2 and "READINGS" in html2 and "OUTSIDE LITERATURE" in html2
          and "no C104B-92" in html2 and "owner-attested" in html2, html2[:3000])
except Exception as exc:  # pragma: no cover - surfaced as a failed check, not a crash
    failures.append(f"template render raised: {exc!r}")
    checks += 1

# --- summary -----------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
