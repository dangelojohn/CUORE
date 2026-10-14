"""Best-effort decoder for the bytes ``cuore.live.dtc_detail`` honestly
refuses to parse.

``dtc_detail.decode_snapshot_record`` (19 04) and ``decode_extended_data``
(19 06) already stop and return raw bytes under ``undecoded_from`` the
moment a DID or extended-data record number has no known length -- by
design, never guessing. This module does NOT change that behaviour or that
file. It adds one more honest pass on top, for the specific case this was
written against: a live Stelvio BCM read of U1713-2F (status 0x0F, UDS
19 04/19 06) on 2026-10-13, where the 19 04 reply stalled at DID 0x1008 with
38 raw bytes left (see
``docs/vehicles/ZASFAKPN5J7B88115/sessions/2026-10-13-live-read-3.json``,
key ``bcm_u1713.snapshot.undecoded_from``):

    10 08 00 03 BE 84 10 09 00 0E 20 0A 38 F7 60 82 00 19 21 40 00 03 00 00
    00 00 04 00 10 02 00 10 04 89 01 37 00 0A

Every length produced here is attributed to exactly one of two sources,
named on the record itself:

  1. ``ISO 14229-1 standard`` -- the identification DIDs ISO 14229-1 fixes
     independent of the ECU (the F1xx block, e.g. F190 = VIN, 17 ASCII
     chars). Source: ISO 14229-1 Annex C.
  2. ``inferred from record layout, SINGLE-SOURCE`` -- for the FCA/
     Stellantis 0x10xx snapshot DIDs, which have no public length table.
     This record itself carries DID 0x1008 immediately followed by the tag
     for DID 0x1009 four bytes later, so DID 0x1008's payload is inferred to
     be those 4 bytes -- a structural read of this one record, nothing else.
     When no next ascending DID tag can be found in the remaining bytes
     (as happens after 0x1009 in the record above -- no 0x100A tag ever
     appears in the trailing 30 bytes), the rest is reported as an honest,
     unlabelled remainder. No length is ever invented for it.

No value from an FCA/Stellantis 0x10xx DID is ever given a meaning or a
unit here -- only "UNKNOWN (use the service manual, TechAuthority)". A
one-line hint is attached to a DID ONLY when a public source for that hint
is cited right next to it in ``_PUBLIC_HINTS`` below; there are none yet for
the 0x10xx block, so none are attached.

Extended data (19 06) record numbers 0x01-0x03 are labelled using the
occurrence/aging/aged-counter convention -- but that convention is AUTOSAR
Dem, not ISO 14229-1 Annex D: Annex D leaves extended-data record numbers
manufacturer-specific and assigns no meaning to any of them (confirmed by
the research already recorded in ``cuore/live/dtc_detail.py``'s module
docstring, sources: https://automotive.wiki/index.php/Diagnostic_Event_Manager
and https://uds.readthedocs.io/en/latest/pages/knowledge_base/dtc.html).
This module reuses that existing, already-sourced decoder
(``dtc_detail.decode_extended_data``) rather than re-labelling the same
bytes under a different, less accurate citation.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import dtc_detail

# ---------------------------------------------------------------------------
# Standard (ISO 14229-1) identification DIDs -- source: ISO 14229-1 Annex C.
# ---------------------------------------------------------------------------

_STANDARD_DIDS: dict[int, dict[str, Any]] = {
    0xF190: {"name": "VIN", "length": 17, "decode": "ascii",
             "source": "ISO 14229-1 Annex C (identification option F190)"},
    0xF186: {"name": "ActiveDiagnosticSessionDataIdentifier", "length": 1,
             "decode": "raw", "source": "ISO 14229-1 Annex C (identification option F186)"},
}

#: Public, cited hints for FCA/Stellantis 0x10xx snapshot DIDs. Empty on
#: purpose: no public source for any 0x10xx snapshot DID's meaning was
#: found for this record, so no hint is attached to 0x1008/0x1009/etc.
#: Add an entry here ONLY as {did: (hint_text, "<public source>")}.
_PUBLIC_HINTS: dict[int, tuple[str, str]] = {}

_UNKNOWN_MEANING = "UNKNOWN (use the service manual, TechAuthority)"


def _standard_meaning(did: int, data: list[str]) -> Optional[dict[str, Any]]:
    spec = _STANDARD_DIDS.get(did)
    if spec is None:
        return None
    out: dict[str, Any] = {"name": spec["name"], "source": spec["source"]}
    if spec["decode"] == "ascii":
        try:
            out["value"] = bytes.fromhex("".join(data)).decode("ascii")
        except ValueError:
            out["value"] = None
            out["decode_error"] = "non-ASCII bytes in a DID ISO 14229-1 defines as ASCII"
    return out


def decode_standard_did(did: int, data: list[str]) -> dict[str, Any]:
    """Decode one DID's raw byte list if (and only if) it is in
    ``_STANDARD_DIDS``. Returns ``{"meaning": "UNKNOWN (...)"}`` otherwise --
    never a guess.
    """
    meaning = _standard_meaning(did, data)
    if meaning is not None:
        return {"did": f"{did:04X}", "bytes": list(data), "length": len(data),
                "length_source": "ISO 14229-1 standard", "meaning": meaning}
    return {"did": f"{did:04X}", "bytes": list(data), "length": len(data),
            "length_source": "unknown", "meaning": _UNKNOWN_MEANING}


# ---------------------------------------------------------------------------
# Structural walk for the undecoded FCA/Stellantis 0x10xx tail
# ---------------------------------------------------------------------------


def walk_structural_snapshot(raw: list[str]) -> dict[str, Any]:
    """Walk ``raw`` (a flat list of two-char hex byte strings, starting at a
    DID tag) as a sequence of ``(DID tag, payload)`` pairs.

    A payload's length is the number of bytes between its DID tag and the
    next tag whose value is exactly one more (``0x1008`` -> look for
    ``0x1009`` -> look for ``0x100A`` ...), found anywhere later in ``raw``.
    That is a read of this record's own layout, not a published table, and
    every entry produced this way says so (``"inferred from record layout,
    SINGLE-SOURCE"``). The run stops -- honestly, with no length guessed --
    the moment no such ascending tag can be found; the remaining bytes are
    returned as ``"entries"`` with ``length_source == "honest remainder"``.

    Standard ISO 14229-1 DIDs (F1xx) are recognised and decoded in place if
    one happens to start a segment; everything else gets
    ``"UNKNOWN (use the service manual, TechAuthority)"``.
    """
    n = len(raw)
    entries: list[dict[str, Any]] = []
    idx = 0
    while idx + 2 <= n:
        tag = int(raw[idx] + raw[idx + 1], 16)
        payload_start = idx + 2
        next_pos: Optional[int] = None
        for j in range(payload_start, n - 1):
            if int(raw[j] + raw[j + 1], 16) == tag + 1:
                next_pos = j
                break
        if next_pos is None:
            payload = raw[payload_start:]
            std = _standard_meaning(tag, payload)
            entries.append({
                "did": f"{tag:04X}",
                "bytes": list(payload),
                "length": len(payload),
                "length_source": ("ISO 14229-1 standard" if std is not None
                                  else "honest remainder -- no further ascending DID "
                                       "tag found in this record; not a guess"),
                "meaning": std if std is not None else _UNKNOWN_MEANING,
            })
            idx = n
            break
        payload = raw[payload_start:next_pos]
        std = _standard_meaning(tag, payload)
        hint = _PUBLIC_HINTS.get(tag)
        meaning: Any
        if std is not None:
            meaning = std
        elif hint is not None:
            meaning = {"hint": hint[0], "source": hint[1]}
        else:
            meaning = _UNKNOWN_MEANING
        entries.append({
            "did": f"{tag:04X}",
            "bytes": list(payload),
            "length": len(payload),
            "length_source": ("ISO 14229-1 standard" if std is not None
                              else "inferred from record layout, SINGLE-SOURCE"),
            "meaning": meaning,
        })
        idx = next_pos
    leftover = raw[idx:] if idx < n else []
    return {"entries": entries, "leftover_bytes": leftover}


_UNDECODED_DID_RE = re.compile(r"DID ([0-9A-Fa-f]{4})")
_UNDECODED_BYTES_RE = re.compile(r"'([0-9A-Fa-f]{2})'")
_UNDECODED_RECORD_RE = re.compile(r"record 0x([0-9A-Fa-f]{2})")


def _extract_raw_bytes(undecoded_from: str) -> list[str]:
    """Pull the trailing python-repr byte list back out of a
    ``dtc_detail.decode_snapshot_record``/``decode_extended_data``
    ``undecoded_from`` message, e.g.
    ``"DID 1008 (length unknown); 38 raw byte(s) remain from here: ['10', '08', ...]"``.
    """
    return [b.upper() for b in _UNDECODED_BYTES_RE.findall(undecoded_from)]


def enrich_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Given the dict ``dtc_detail.dtc_snapshot``/``ops.module_dtc_detail``
    already produced for a 19 04 reply, add a ``structural_decode`` key when
    (and only when) it stopped at an ``undecoded_from`` remainder. Every
    other key is passed through byte-for-byte, untouched.
    """
    out = dict(snapshot)
    undecoded = snapshot.get("undecoded_from")
    if not isinstance(undecoded, str):
        return out
    raw = _extract_raw_bytes(undecoded)
    if not raw:
        return out
    walk = walk_structural_snapshot(raw)
    out["structural_decode"] = {
        "raw_bytes": raw,
        "entries": walk["entries"],
        "leftover_bytes": walk["leftover_bytes"],
        "note": ("Structural inference only -- see cuore.live.dtc_records module "
                "docstring for exactly what each length_source means."),
    }
    return out


def enrich_extended(extended: dict[str, Any]) -> dict[str, Any]:
    """Given the dict for a 19 06 reply, add a ``structural_decode`` key
    listing the raw remainder when ``dtc_detail.decode_extended_data``
    stopped on an unrecognised record number. ``dtc_detail``'s own
    occurrence/aging/aged-counter decoding (already labelled
    ``"confidence": "unverified for FCA"`` and sourced in its module
    docstring) is left exactly as it produced it -- this never relabels it
    as an ISO 14229 Annex D convention, because Annex D itself assigns no
    meaning to extended-data record numbers.
    """
    out = dict(extended)
    undecoded = extended.get("undecoded_from")
    if not isinstance(undecoded, str):
        return out
    raw = _extract_raw_bytes(undecoded)
    out["structural_decode"] = {
        "raw_bytes": raw,
        "note": ("No further decoding attempted: ISO 14229-1 Annex D leaves "
                "extended-data record numbers manufacturer-specific, and no "
                "FCA/Stellantis-specific public source for this record number "
                "was found. Raw bytes only -- no meaning invented."),
    }
    return out


def enrich_dtc_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Wrap the full dict ``ops.module_dtc_detail``/``dtc_detail.dtc_detail``
    returns: pass every key through untouched except ``snapshot`` and
    ``extended``, which get the honest structural add-on above. Safe to call
    on any shape of input -- a dict missing ``snapshot``/``extended``, or one
    that was already fully decoded by ``dtc_detail`` (no ``undecoded_from``),
    comes back unchanged.
    """
    out = dict(detail)
    if isinstance(detail.get("snapshot"), dict):
        out["snapshot"] = enrich_snapshot(detail["snapshot"])
    if isinstance(detail.get("extended"), dict):
        out["extended"] = enrich_extended(detail["extended"])
    return out


__all__ = [
    "decode_standard_did", "walk_structural_snapshot", "enrich_snapshot",
    "enrich_extended", "enrich_dtc_detail",
]
