"""Cross-session analysis: the judgements a flat log dump cannot make.

Everything here exists because a per-file view of the corpus is misleading in a
specific, repeatable way:

* **A code's history is the diagnosis.** ``P0456`` present at 114,008 km and
  again at 140,572 km is a chronic leak of 26,500 km; the same code reported as
  "latest seen 2026-08-27" reads as a fresh fault. :func:`dtc_history` keeps
  both ends.
* **Clearing is not fixing.** After a clear the ECU reports nothing until the
  monitor runs again, so a clean scan minutes later means almost nothing.
  :func:`post_clear_assessment` says so explicitly instead of letting silence
  look like success.
* **A network event is one fault, not five.** When several modules each report
  only "missing message" or "erratic" against *other* modules, that is one
  power or bus event. Listing five module faults sends a technician chasing
  five repairs. :func:`detect_network_event` collapses them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from . import dtc_text, modules
from .catalog import CATALOG, LogEntry
from .dtc import Dtc, DtcStatus

#: Failure-type bytes that mean "I could not talk to something", as opposed to
#: "a component I own is faulty". Corpus-grounded from MES's own phrasing.
COMMUNICATION_FTBS = {"2F", "86", "87", "88", "64"}

#: Minimum distinct modules holding only communication codes before we call it
#: a network event rather than a set of module faults.
NETWORK_EVENT_MIN_MODULES = 3


def is_communication_dtc(dtc: Dtc) -> bool:
    """True for a code that reports a failure to communicate, not a component.

    ``U`` codes are network by definition. ``C`` and ``B`` codes qualify only
    when the failure-type byte is a messaging one *and* the description talks
    about another module -- ``B1176-97`` (window riser obstructed) is a real
    component fault that happens to live on a body module.
    """
    letter = dtc.code[:1].upper()
    if letter == "U":
        return True
    if dtc.ftb and dtc.ftb.upper() in COMMUNICATION_FTBS:
        text = f"{dtc.component} {dtc.description}".lower()
        hints = ("communication", "can", "message", "node", "module",
                 "lost communication", "bus")
        return any(h in text for h in hints)
    return False


@dataclass
class NetworkEvent:
    """Several modules reporting communication faults against each other."""

    modules_involved: list[str] = field(default_factory=list)
    dtcs: list[Dtc] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)

    @property
    def confident(self) -> bool:
        return len(self.modules_involved) >= NETWORK_EVENT_MIN_MODULES

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding": "network / power event",
            "confidence": "high" if self.confident else "possible",
            "modules_reporting": self.modules_involved,
            "module_count": len(self.modules_involved),
            "dtc_count": len(self.dtcs),
            "dtcs": [d.full for d in self.dtcs],
            "subjects_referenced": self.subjects,
            "interpretation": (
                f"{len(self.modules_involved)} modules each report only "
                "communication faults against other modules, with no "
                "component-level fault of their own. Every failure-type byte "
                "here is a message-integrity class, not a component-internal "
                "one. That pattern is one network or power event, not "
                f"{len(self.modules_involved)} separate module failures."
            ),
            "first_test": (
                "Read extended DTC data (DTC EX in MES) on every code BEFORE "
                "clearing: odometer, occurrence count, aging counter. If they "
                "all share one odometer value and a single occurrence, the "
                "diagnostic session itself produced them. Clearing first "
                "destroys the only evidence that settles this."
            ),
            "ranked_causes_giorgio": [
                {
                    "cause": "BCM power feed - F82 fuse in the rear PDC, and "
                             "the BCM A901 circuit",
                    "confidence": "FCA STAR case S1808000005, on-platform",
                    "why": "'No Start, Multiple Modules Are Not Responding', "
                           "2018-2020 Stelvio. FCA's instruction is explicit: "
                           "'For GU / Stelvio inspect the F82 fuse in the "
                           "rear PDC to the BCM A901 circuit.' A BCM that "
                           "loses its supply drops off the bus, and every "
                           "module gatewaying through it throws U-codes. "
                           "This attacks the SUPPLY side, which a "
                           "ground-strap hypothesis misses entirely.",
                    "test": "check F82 in the rear power distribution centre "
                            "and the BCM A901 / B+ A0 feed before anything "
                            "else. Cheap and high-yield.",
                },
                {
                    "cause": "inline connector XY201 and frame grounds "
                             "G003A / G003B",
                    "confidence": "FCA STAR case S2008000032 - the closest "
                                  "published match to this fault pattern",
                    "why": "'EVIC Displays Multiple Warning Messages': "
                           "multiple warnings, multiple active DTCs across "
                           "modules, resolved by securing a loose inline "
                           "connector XY201 and cleaning/securing frame "
                           "grounds G003A/G003B. NO PARTS REQUIRED. This is "
                           "a documented FCA fix for exactly this cascade "
                           "shape. NHTSA associates it with 2020 Stelvio, "
                           "but the GU platform circuitry is shared.",
                    "test": "inspect inline connector XY201 for security; "
                            "clean and secure frame grounds G003A and G003B",
                },
                {
                    "cause": "spread or backed-out connector terminals",
                    "confidence": "FCA STAR case S1708000262 REV. A",
                    "why": "'Check Engine Lamp Is On, Intermittent Module CAN "
                           "Private Or LIN BUS Codes' - intermittent "
                           "multi-module U-codes attributed to pushed-out or "
                           "spread terminals rather than a failed module.",
                    "test": "inspect involved connector terminals for "
                            "pushed-out or spread pins",
                },
                {
                    "cause": "the diagnostic session itself",
                    "confidence": "plausible and common",
                    "why": "Putting a module into an extended UDS session "
                           "makes many FCA modules reduce or stop normal "
                           "broadcasts; every subscriber then logs a missing "
                           "or erratic message. A tool that walks module by "
                           "module through a whole-vehicle scan does this "
                           "serially to the entire bus.",
                    "test": "see first_test - occurrence counters settle it",
                },
                {
                    "cause": "BCM water intrusion (recall 18V205000 / FCA U36)",
                    "confidence": "recall covering all 12,595 MY2018 Stelvio",
                    "why": "Water tracks down the front cowl into the "
                           "passenger footwell where the BCM lives. The BCM "
                           "is the B-CAN to C-CAN gateway, so corroded pins "
                           "produce faults in both directions at once. The "
                           "remedy was a sealing kit, not a redesign, and "
                           "recurrence after it was performed is documented.",
                    "test": "pull the passenger kick panel; look for "
                            "staining, a silt line, or green/white corrosion "
                            "on the BCM connectors. Verify U36 and U34 were "
                            "performed on this VIN.",
                },
                {
                    "cause": "corroded engine/transmission-to-body ground strap",
                    "confidence": "owner-reported pattern only - NO FCA "
                                  "BULLETIN EXISTS",
                    "why": "13 NHTSA complaints on 2018-2019 Stelvio describe "
                           "this, several dealer-diagnosed at 54k-102k miles, "
                           "and the mechanism is sound: a high-resistance "
                           "strap shifts powertrain ground reference during a "
                           "high-current event, pushing CAN transceivers "
                           "outside common-mode range. BUT a full-text sweep "
                           "of all 287 readable FCA bulletins for these "
                           "vehicles found NOTHING describing a ground strap "
                           "as a failing part. Ranked below the three "
                           "documented causes above rather than first.",
                    "test": "voltage-drop test the transmission-to-body strap "
                            "and both front knuckle straps under load; target "
                            "below 0.1 V across each path",
                },
                {
                    "cause": "failing 12V battery or IBS sensor",
                    "confidence": "general platform issue, weakly evidenced",
                    "why": "Only 1 of 371 NHTSA complaints names the battery "
                           "sensor. FCA STAR case S1408000384 REV. J does "
                           "give a specific test for U113E 'lost "
                           "communication with intelligent battery': wiggle "
                           "the IBS 2-way harness takeout and watch whether "
                           "the code responds.",
                    "test": "battery test, IBS connection (wiggle the 2-way "
                            "takeout), parasitic draw. Note FCA's DO NOT "
                            "BLIND CHARGE rule.",
                },
            ],
            "caution": (
                "Do not replace any module on the strength of a "
                "communication cascade alone. Note also that a missing-message "
                "code names the module that went quiet, not the module that "
                "is faulty - on Giorgio the transfer case reporting 'no "
                "communication with ECU' means ECM frames stopped arriving on "
                "the shared bus, which does not implicate the transfer case."
            ),
        }


def detect_network_event(dtcs_by_module: dict[str, list[Dtc]]) -> NetworkEvent | None:
    """Collapse a communication-fault cascade into a single finding.

    A module qualifies only if *every* code it holds is a communication code.
    One genuine component fault on a module means that module has a real
    problem and is excluded from the cascade.
    """
    involved: list[str] = []
    collected: list[Dtc] = []
    subjects: set[str] = set()

    for module_name, dtcs in dtcs_by_module.items():
        if not dtcs:
            continue
        if all(is_communication_dtc(d) for d in dtcs):
            involved.append(module_name)
            collected.extend(dtcs)
            for d in dtcs:
                if d.component:
                    subjects.add(d.component)

    if len(involved) < 2:
        return None
    return NetworkEvent(sorted(involved), collected, sorted(subjects))


@dataclass
class DtcRecord:
    """One code's whole life across the corpus."""

    dtc: str
    descriptions: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    vins: list[str] = field(default_factory=list)
    vehicles: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    occurrences: list[dict[str, Any]] = field(default_factory=list)

    @property
    def first_seen(self) -> str:
        stamps = [o["timestamp"] for o in self.occurrences if o.get("timestamp")]
        return min(stamps) if stamps else ""

    @property
    def last_seen(self) -> str:
        stamps = [o["timestamp"] for o in self.occurrences if o.get("timestamp")]
        return max(stamps) if stamps else ""

    @property
    def session_count(self) -> int:
        return len({o["file"] for o in self.occurrences})

    @property
    def odometer_span(self) -> tuple[float | None, float | None]:
        odos = [o["odometer_km"] for o in self.occurrences
                if o.get("odometer_km") is not None]
        return (min(odos), max(odos)) if odos else (None, None)

    @property
    def chronic(self) -> bool:
        """Seen in more than one session with meaningful distance between."""
        lo, hi = self.odometer_span
        if lo is not None and hi is not None and hi - lo >= 1000:
            return True
        return self.session_count >= 3

    @property
    def returned_after_clear(self) -> bool:
        return DtcStatus.RETURNED.value in self.statuses

    def to_dict(self) -> dict[str, Any]:
        lo, hi = self.odometer_span
        d: dict[str, Any] = {
            "dtc": self.dtc,
            "descriptions": self.descriptions,
            "modules": self.modules,
            "vins": self.vins,
            "vehicles": self.vehicles,
            "statuses_seen": self.statuses,
            "sessions": self.session_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "occurrences": self.occurrences,
        }
        if not self.descriptions:
            # No log ever carried text for this code (every occurrence was a
            # bare code, e.g. inside a FAILED clear block). Offer whatever
            # MES's own shipped language files know, kept separate from
            # ``descriptions`` (which is exclusively "what a log said") and
            # clearly labelled. See mes/dtc_text.py: against the currently
            # installed English.dat/English.txt this is a documented no-op.
            module = self.modules[0] if self.modules else None
            fallback = dtc_text.describe(self.dtc, module)
            if fallback:
                d["mes_description"] = fallback
        if lo is not None:
            d["odometer_first_km"] = lo
            d["odometer_last_km"] = hi
            if hi is not None and hi > lo:
                d["distance_span_km"] = round(hi - lo, 1)
        if self.chronic:
            d["assessment"] = "chronic - recurs across sessions"
        if self.returned_after_clear:
            d["assessment"] = ("returned after being cleared - the fault is "
                               "reproducing")
        return d


def dtc_history(entries: Sequence[LogEntry] | None = None, *,
                vin: str = "", vehicle: str = "",
                include_simulation: bool = False) -> dict[str, DtcRecord]:
    """Build the full per-code history across the selected logs.

    Occurrences are counted per *file*, not per regex hit. v1 counted mentions,
    so a code read, cleared and re-read inside one session looked like two
    sightings of a recurring fault.
    """
    from . import fes, scan

    if entries is None:
        entries = CATALOG.select(vin=vin, vehicle=vehicle,
                                 include_simulation=include_simulation)

    history: dict[str, DtcRecord] = {}
    for entry in entries:
        if entry.parse_error:
            continue
        odometer: float | None = None
        try:
            if entry.kind == "scan":
                log = scan.load_scan(entry.path, timestamp=entry.timestamp)
                dtcs = log.all_dtcs
            else:
                log = fes.load_fes(entry.path, timestamp=entry.timestamp)
                dtcs = log.dtcs
                odometer = log.odometer_km
        except Exception:
            continue

        for d in dtcs:
            rec = history.setdefault(d.full, DtcRecord(dtc=d.full))
            if d.description and d.description not in rec.descriptions:
                rec.descriptions.append(d.description)
            if d.module and d.module not in rec.modules:
                rec.modules.append(d.module)
            if entry.vin and entry.vin not in rec.vins:
                rec.vins.append(entry.vin)
            if entry.vehicle and entry.vehicle not in rec.vehicles:
                rec.vehicles.append(entry.vehicle)
            if d.status.value not in rec.statuses:
                rec.statuses.append(d.status.value)
            if not any(o["file"] == entry.name for o in rec.occurrences):
                rec.occurrences.append({
                    "file": entry.name,
                    "timestamp": entry.timestamp,
                    "status": d.status.value,
                    "odometer_km": odometer,
                })

    for rec in history.values():
        rec.occurrences.sort(key=lambda o: o.get("timestamp") or "")
    return history


@dataclass
class ClearAssessment:
    """What a clear operation actually proved."""

    cleared: list[str] = field(default_factory=list)
    returned: list[str] = field(default_factory=list)
    uncleared: list[str] = field(default_factory=list)
    reread_after_clear: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "codes_cleared": self.cleared,
            "codes_returned_in_session": self.returned,
            "codes_that_would_not_clear": self.uncleared,
            "re_read_after_clear": self.reread_after_clear,
        }
        if self.returned:
            d["verdict"] = (
                "Fault is live: these codes were erased and the ECU set them "
                "again before the session ended. This is the strongest "
                "evidence available short of a scope."
            )
        elif self.uncleared:
            d["verdict"] = (
                "These codes could not be erased. On FCA transmissions that "
                "usually means a calibration or self-learn procedure must be "
                "completed before the code will clear - the code is a state "
                "flag, not a failure."
            )
        elif self.cleared and self.reread_after_clear:
            d["verdict"] = (
                "Codes cleared and did not return before the session ended. "
                "This is NOT proof of repair: after a clear the ECU reports "
                "nothing until each monitor runs again. A clean re-read "
                "minutes later mostly proves the erase worked."
            )
            d["next_step"] = (
                "Complete the relevant drive cycle, then re-scan. Until the "
                "monitor has run, absence of a code carries no information."
            )
        elif self.cleared:
            d["verdict"] = (
                "Codes were erased but never re-read in this session, so "
                "nothing is known about whether they returned."
            )
        return d


def post_clear_assessment(fes_log: Any) -> ClearAssessment | None:
    """Interpret the clear events in one FES session."""
    if not getattr(fes_log, "clear_events", 0):
        return None
    out = ClearAssessment(
        cleared=[d.full for d in fes_log.cleared],
        returned=[d.full for d in fes_log.returned_after_clear],
        uncleared=[d.full for d in fes_log.dtcs
                   if d.status is DtcStatus.UNCLEARED],
        reread_after_clear=fes_log.read_sections > 1,
    )
    return out


def module_report(dtcs: Iterable[Dtc]) -> list[dict[str, Any]]:
    """Group codes by module, annotated and ordered by clinical priority."""
    grouped: dict[str, list[Dtc]] = defaultdict(list)
    for d in dtcs:
        grouped[d.module or "(unknown module)"].append(d)

    rows = []
    for name, items in grouped.items():
        abbrev = _abbrev_from_name(name)
        info = modules.describe(abbrev)
        rows.append({
            "module": name,
            "module_code": info["code"],
            "module_name": info["name"],
            "domain": info["domain"],
            "tier": info["tier"],
            "dtc_count": len(items),
            "all_communication_faults": all(is_communication_dtc(d)
                                            for d in items),
            "dtcs": [d.to_dict(include_freeze=False) for d in items],
        })
    rows.sort(key=lambda r: (modules.Tier(r["tier"]).rank, r["module_code"]))
    return rows


def _abbrev_from_name(name: str) -> str:
    """Recover the abbreviation from a printed module heading."""
    if " / " in name:
        rest = name.split(" / ", 1)[1]
        return rest.split(" (", 1)[0].strip()
    return name.split(" (", 1)[0].strip()


def vehicle_summary(vin: str = "", vehicle: str = "") -> dict[str, Any]:
    """A whole-vehicle picture: identity, history, open questions."""
    entries = CATALOG.select(vin=vin, vehicle=vehicle)
    if not entries:
        return {"error": "no logs match", "vin": vin, "vehicle": vehicle}

    history = dtc_history(entries)
    chronic = sorted((r for r in history.values() if r.chronic),
                     key=lambda r: r.first_seen)
    returned = [r for r in history.values() if r.returned_after_clear]

    odos: list[tuple[str, float]] = []
    for entry in entries:
        if entry.kind != "fes":
            continue
        try:
            from . import fes as _fes
            log = _fes.load_fes(entry.path, timestamp=entry.timestamp)
            if log.odometer_km is not None:
                odos.append((entry.timestamp, log.odometer_km))
        except Exception:
            continue
    odos.sort()

    newest = entries[0]
    return {
        "vin": newest.vin or vin,
        "vehicle": newest.vehicle or vehicle,
        "ecu_seen": sorted({e.ecu for e in entries if e.ecu}),
        "log_count": len(entries),
        "first_log": min((e.timestamp for e in entries if e.stamp), default=""),
        "last_log": max((e.timestamp for e in entries if e.stamp), default=""),
        "odometer_first_km": odos[0][1] if odos else None,
        "odometer_last_km": odos[-1][1] if odos else None,
        "distinct_dtcs": len(history),
        "chronic_dtcs": [r.to_dict() for r in chronic],
        "returned_after_clear": [r.to_dict() for r in returned],
        "note": (
            "Simulation logs are excluded. SCAN logs carry no simulation "
            "marker at all, so their provenance is unverifiable rather than "
            "confirmed."
        ),
    }
