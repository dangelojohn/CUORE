"""Reference data: parts for the 2018 Alfa Romeo Stelvio 2.0T (US).

Read-only reference data -- nothing here touches the corpus or the car. It
is the parts-catalogue counterpart to ``mes.service_specs`` (torques, oil/
brakes ledger) and ``mes.maintenance_specs`` (recurring maintenance items):
this module answers "what part, what number, where, how much, where to buy
it" for a fixed set of commonly-needed parts, cross-linked to DTCs and to
the maintenance/service job keys that use them.

Confidence levels (never invented -- an absent value is recorded as
UNKNOWN, never guessed):

* ``CONFIRMED``     -- an actual manufacturer document (owner's manual,
                       Mopar/FCA parts catalog, FCA/Alfa TSB/service
                       information, TechAuthority excerpt).
* ``CORROBORATED``  -- two independent non-manufacturer sources agree.
* ``SINGLE_SOURCE`` -- exactly one source found, not cross-checked.
* ``UNKNOWN``       -- nothing credible found. ``number``/``price`` is
                       ``None``, never a placeholder -- ``notes`` always
                       points at the service manual.

Part numbers are never invented. Where a Mopar catalog or VIN-fit listing
was not found, the number is left ``None`` with ``confidence=UNKNOWN`` and
a ``TECHAUTHORITY`` note. Images are link-only (never copied into this
repo) and, like ``buy`` links, are only included here after being checked
to return HTTP 200 with a browser User-Agent during this research pass
(2026-10-07) -- anything that failed that check was dropped rather than
guessed at or left unverified.

Research sources for this pass: this repo's own ``docs/research/
EVAP_STELVIO.md`` (which itself transcribes NHTSA-hosted FCA/Alfa TSBs --
9100469 "ESIM vs canister" and 9100468 "canister filter"), the
``mes.service_specs`` / ``mes.maintenance_specs`` / ``mes.drivetrain_specs``
modules already researched in this repo, the user's own repair-history memory
for this VIN (``project_stelvio_evap.md``), and RockAuto's part-number search
(verified live, used only as a *buy* link, never as the source of a part
number's identity).
"""

from __future__ import annotations

from typing import Any, Optional

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"

CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN)

TECHAUTHORITY = "use the service manual (TechAuthority)"

VEHICLE = ("2018 Alfa Romeo Stelvio 2.0T (GU), 2.0L GME-T4 MultiAir turbo, "
           "sales code EC2, US market, Q4 AWD, ZF 8HP automatic")

FITS_VALUES = ("stelvio_2.0t", "giorgio", "specific_vins", "grecale", "levante")

#: ``fits`` values treated as "a sibling platform's car, not this one" --
#: see ``mes.platform``. No ``PARTS`` entry currently uses either value: a
#: 2026-10-07 pass found no Grecale/Levante-specific, sourced part number
#: that could be added without guessing a cross-reference; per house rule
#: (never present an unverified relationship as fact), none was fabricated.
#: ``include_siblings`` below is live plumbing with nothing yet to return.
SIBLING_FITS = frozenset({"grecale", "levante"})

OM_URL = ("https://vehicleinfo.mopar.com/assets/publications/en-us/"
          "Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf")

REQUIRED_KEYS: tuple[str, ...] = (
    "name", "what_it_does", "oem", "supersedes", "aftermarket", "fits",
    "location", "related_codes", "related_jobs", "torque_keys", "price",
    "buy", "images", "notes",
)


def _oem(number: Optional[str], brand: str = "Mopar", note: str = "",
         confidence: str = UNKNOWN, source: Optional[str] = None) -> dict[str, Any]:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    if confidence == UNKNOWN and not note:
        note = TECHAUTHORITY
    return {"number": number, "brand": brand, "note": note,
            "confidence": confidence, "source": source}


def _aftermarket(brand: str, number: Optional[str], confidence: str = UNKNOWN,
                  source: Optional[str] = None) -> dict[str, Any]:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    return {"brand": brand, "number": number, "confidence": confidence,
            "source": source}


def _buy(label: str, url: str) -> dict[str, str]:
    return {"label": label, "url": url}


def _image(url: str, source_page: str, source_name: str, kind: str,
           licence_note: str, verified_at: str = "2026-10-07",
           verified_how: str = "browser_cdp") -> dict[str, str]:
    """A link-only product image (never copied into this repo), verified by
    opening ``source_page`` in headless Edge over CDP, locating the largest
    product-image ``<img>`` in the page, and confirming it actually
    rendered (``naturalWidth`` > 100) before recording its ``src``."""
    if kind not in ("photo", "diagram", "exploded_view"):
        raise ValueError(f"bad image kind {kind!r}")
    return {"url": url, "source_page": source_page, "source_name": source_name,
            "kind": kind, "licence_note": licence_note,
            "verified_at": verified_at, "verified_how": verified_how}


def _rockauto(part_no: str) -> dict[str, str]:
    """A RockAuto part-number search link, verified HTTP 200 on 2026-10-07
    with a browser User-Agent. This is a *buy* convenience link only -- it
    is never the source of the part number's identity, and RockAuto returns
    200 for a search page regardless of whether that number yields a hit,
    so finding the actual part on the page is not guaranteed."""
    return _buy(f"Search RockAuto for {part_no}",
                f"https://www.rockauto.com/en/partsearch/?partnum={part_no}")


def _price(low: Optional[float], high: Optional[float], source: Optional[str],
           as_of: str = "2026-10-07", currency: str = "USD") -> Optional[dict[str, Any]]:
    if low is None and high is None:
        return None
    return {"low": low, "high": high, "currency": currency, "as_of": as_of,
            "source": source}


def _part(key: str, name: str, what_it_does: str, *,
          oem: Optional[list[dict[str, Any]]] = None,
          supersedes: Optional[list[str]] = None,
          aftermarket: Optional[list[dict[str, Any]]] = None,
          fits: str, location: str,
          related_codes: Optional[list[str]] = None,
          related_jobs: Optional[list[str]] = None,
          torque_keys: Optional[list[str]] = None,
          price: Optional[dict[str, Any]] = None,
          buy: Optional[list[dict[str, str]]] = None,
          images: Optional[list[dict[str, Any]]] = None,
          notes: str = "") -> None:
    if fits not in FITS_VALUES:
        raise ValueError(f"bad fits {fits!r} for {key!r}")
    PARTS[key] = {
        "name": name,
        "what_it_does": what_it_does,
        "oem": oem or [],
        "supersedes": supersedes or [],
        "aftermarket": aftermarket or [],
        "fits": fits,
        "location": location,
        "related_codes": related_codes or [],
        "related_jobs": related_jobs or [],
        "torque_keys": torque_keys or [],
        "price": price,
        "buy": buy or [],
        "images": images or [],
        "notes": notes.strip(),
    }


PARTS: dict[str, dict[str, Any]] = {}


# --- engine / oil service ----------------------------------------------------

_part(
    "oil_filter", "Engine oil filter (cartridge)",
    "Traps debris from the engine oil; this engine uses a screw-on plastic "
    "housing cap over a replaceable cartridge element, not a spin-on "
    "canister.",
    oem=[_oem("4892339", note="Suffix revised over production (BE/AB/AC "
              "seen); reported as 'same filter, revised part number'. Do "
              "NOT use 68191349AA/AC -- that is the 3.0L/3.2L/3.6L V6 "
              "filter.", confidence=SINGLE_SOURCE,
              source="https://www.giuliaforums.com/threads/oil-filter-2-0-part-number-change.49369/")],
    fits="giorgio",
    location="Top of the engine, under a screw-off plastic housing cap "
             "with its own O-ring (not a spin-on canister).",
    related_jobs=["oil_change"],
    torque_keys=["filter_cap"],
    buy=[_rockauto("4892339")],
    images=[_image(
        "https://www.rockauto.com/info/162/MR_04892339AB_Ang__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=4892339",
        "RockAuto listing photo, MOPAR 4892339AB", "photo",
        "linked from RockAuto; not copied. Listing is suffix AB (this "
        "record's sourced suffix is unresolved -- see notes); same "
        "filter family.",
    )],
    notes="Confirm the exact current suffix against this VIN at a Mopar"
          "parts counter before ordering. No confidently-sourced aftermarket "
          "cross-reference (Mann/Bosch/K&N) was found this pass.",
)

_part(
    "drain_plug_gasket", "Oil drain plug / gasket",
    "Seals the oil pan drain plug; this engine is reported to use a "
    "built-in/captive rubber gasket on the plug itself rather than a "
    "separate crush washer.",
    oem=[_oem(None, confidence=UNKNOWN)],
    fits="stelvio_2.0t",
    location="Bottom of the oil pan.",
    related_jobs=["oil_change"],
    torque_keys=["drain_plug"],
    notes="A washer part number (670050349) is documented for the "
          "Quadrifoglio V6, not the 2.0T -- do not assume it fits. "
          "Confirm plug design from TechAuthority or by inspecting the "
          "removed plug; if captive, the only way to renew the seal may "
          "be replacing the whole plug.",
)

_part(
    "engine_oil", "Engine oil, 0W-30 full synthetic",
    "The engine lubricant; this turbocharged engine requires full "
    "synthetic -- conventional oil is explicitly not approved.",
    oem=[_oem(None, brand="n/a", confidence=UNKNOWN,
              note="No specific Mopar-branded oil part/SKU sourced this "
                   "pass; buy to spec, not by part number. " + TECHAUTHORITY)],
    fits="giorgio",
    location="Fill at the oil filler cap on top of the engine; drain at "
             "the pan plug underneath.",
    related_jobs=["oil_change"],
    torque_keys=["drain_plug", "filter_cap"],
    notes="Spec: FCA/Mopar MS-13340, API SN (2017-2018 build; historically "
          "also cited as Fiat 9.55535-GS1), viscosity 0W-30. Capacity 5.5 "
          "qt (5.2 L) with filter. Do NOT use MS-12633 (Pennzoil 0W-40 "
          "SN) -- that is the Quadrifoglio/SRT V6 spec. See "
          "mes.service_specs.OIL_SPEC for full sourcing.",
)

_part(
    "spark_plug", "Spark plug",
    "Ignites the air/fuel mixture in each cylinder.",
    oem=[_oem("68292346AA", note="Also cross-referenced to NGK 90219 "
              "(NGK plug code ILZKR7G7G).", confidence=CORROBORATED,
              source="https://www.giuliaforums.com/threads/inconsistent-spark-plug-torque-specs-2-0l.64916/")],
    aftermarket=[_aftermarket("NGK", "90219 (ILZKR7G7G)", confidence=CORROBORATED,
                 source="https://www.giuliaforums.com/threads/inconsistent-spark-plug-torque-specs-2-0l.64916/")],
    fits="giorgio",
    location="One per cylinder, threaded into the aluminum cylinder head "
             "under the ignition coils.",
    related_codes=["P0300", "P0301", "P0302", "P0303", "P0304"],
    related_jobs=["oil_change", "spark_plugs"],
    torque_keys=["spark_plug"],
    buy=[_rockauto("68292346AA")],
    images=[_image(
        "https://www.rockauto.com/info/162/68292346AA-0-ANG__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=68292346AA",
        "RockAuto listing photo, MOPAR 68292346AA", "photo",
        "linked from RockAuto; not copied. Exact OEM part number match.",
    )],
    notes="Torque 19.5 Nm (range 19-20 Nm); do not over-torque into the "
          "aluminum head. Published specs vary slightly by source/year.",
)

_part(
    "ignition_coil", "Ignition coil",
    "Steps up battery voltage to fire the spark plug for one cylinder; "
    "pulls straight up off the plug once its retaining bolt/screw and "
    "connector are removed.",
    oem=[_oem(None, confidence=UNKNOWN,
              note="No sourced part number this pass -- do not order "
                   "speculatively. Confirm the failing cylinder via live "
                   "misfire counters first.")],
    fits="giorgio",
    location="One per cylinder, on top of each spark plug well.",
    related_codes=["P0300", "P0301", "P0302", "P0303", "P0304", "P0351",
                    "P0352", "P0353", "P0354"],
    related_jobs=["ignition_coils_inspect"],
    torque_keys=["coil_pack_bolt"],
    notes="Not a scheduled replacement item -- inspected/diagnosed on "
          "misfire codes. Check the spark plug well for oil intrusion, a "
          "common cause of coil-boot arcing on MultiAir-family engines. "
          + TECHAUTHORITY,
)

_part(
    "engine_air_filter", "Engine air filter",
    "Filters intake air before it reaches the turbo/engine.",
    oem=[_oem("68301538AA", confidence=CORROBORATED,
              source="https://www.giuliaforums.com/")],
    fits="giorgio",
    location="Air box ahead of the turbo intake, engine bay.",
    related_jobs=["engine_air_filter"],
    buy=[_rockauto("68301538AA")],
    images=[_image(
        "https://www.rockauto.com/info/162/68301538AA-0-ANG__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=68301538AA",
        "RockAuto listing photo, MOPAR 68301538AA", "photo",
        "linked from RockAuto; not copied. Exact OEM part number match.",
    )],
    notes="Giulia-sourced part number; same engine/intake as this Stelvio.",
)

_part(
    "cabin_air_filter", "Cabin air filter",
    "Filters air entering the HVAC system / cabin.",
    oem=[_oem("68444656AA", confidence=CORROBORATED,
              source="https://www.giuliaforums.com/")],
    fits="stelvio_2.0t",
    location="Behind the glovebox, in the HVAC intake housing.",
    related_jobs=["cabin_air_filter"],
    buy=[_rockauto("68444656AA")],
    images=[_image(
        "https://www.rockauto.com/info/162/MR_68444656AA_Ang__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=68444656AA",
        "RockAuto listing photo, MOPAR 68444656AA", "photo",
        "linked from RockAuto; not copied. Exact OEM part number match.",
    )],
)

_part(
    "drive_belt", "Accessory (serpentine) drive belt",
    "Drives the alternator, A/C compressor and other accessories off the "
    "crankshaft pulley.",
    oem=[_oem("68326261AA", confidence=CORROBORATED,
              source="https://www.giuliaforums.com/")],
    fits="giorgio",
    location="Front of the engine, looped around the crank, alternator, "
             "A/C compressor and tensioner pulleys.",
    related_jobs=["drive_belt"],
    buy=[_rockauto("68326261AA")],
    images=[_image(
        "https://www.rockauto.com/info/33/Multirib%20Belt%20Arc__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=68326261AA",
        "RockAuto listing photo, DAYCO 5060730", "photo",
        "linked from RockAuto; not copied. No Mopar-branded photo was "
        "listed on this fitment search -- this is the largest aftermarket "
        "cross-reference row (DAYCO 5060730), a serpentine belt of the "
        "correct generic type, not confirmed identical to Mopar "
        "68326261AA.",
    )],
    notes="Scheduled replacement at 36,000 mi / 60,000 km / 48 months per "
          "the owner's manual (CONFIRMED).",
)

_part(
    "battery_12v", "12V battery",
    "The vehicle's starting/accessory battery; factory-fit is EFB "
    "standard, AGM on some builds/options.",
    oem=[_oem("BBH8A001AA", brand="Mopar", note="AGM; reported to cross to "
              "a Group 94R-class battery.", confidence=SINGLE_SOURCE,
              source="https://www.stelvioforum.com/threads/mopar-replacement-battery.9201/")],
    fits="stelvio_2.0t",
    location="Trunk-mounted, under the floor panel. This platform uses a "
             "single 12V battery -- no separate/auxiliary battery is "
             "documented for the Stelvio.",
    related_jobs=["battery_12v"],
    torque_keys=["battery_terminal", "battery_hold_down"],
    buy=[_rockauto("BBH8A001AA")],
    images=[_image(
        "https://www.rockauto.com/info/162/BBH8A001AA.1__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=BBH8A001AA",
        "RockAuto listing photo, MOPAR BBH8A001AA", "photo",
        "linked from RockAuto; not copied. Exact OEM part number match.",
    )],
    notes="Do not downgrade to a plain flooded/EFB battery on an "
          "AGM-equipped car. After any battery disconnect, expect to reset "
          "the clock and relearn idiosyncrasies; no explicit "
          "'register battery replacement' procedure was found this pass.",
)

_part(
    "wiper_blades", "Windshield wiper blades",
    "Clears rain/debris from the windshield (front pair) and liftgate "
    "glass (rear single blade).",
    oem=[_oem(None, confidence=UNKNOWN,
              note="No confidently-sourced Mopar part number; buy to size. "
                   + TECHAUTHORITY)],
    fits="stelvio_2.0t",
    location="Front: driver (26 in / 660 mm) and passenger wiper arms. "
             "Rear: liftgate wiper arm (13 in / 330 mm).",
    related_jobs=["wipers"],
    notes="Sizes per autopadre.com's wiper-fitment database, cross-checked "
          "against windshieldwipers.com / allwipersize.com / "
          "wipersizechart.com (CORROBORATED on size, not on any OEM part "
          "number). Activate the windshield-wiper 'service position' "
          "function before removing blades.",
)


# --- EVAP system --------------------------------------------------------------

_part(
    "esim", "Evaporative System Integrity Module (ESIM, leak-detection pump)",
    "A small electric pump/switch that pressurizes the EVAP system and "
    "monitors for leaks; FCA's own bulletin treats it as separate and "
    "independently serviceable from the vapor canister.",
    oem=[
        _oem("04861961AD", note="Fitted to this VIN 2026-09-02; Alfa "
             "Online Parts lists it as Alfa OE, 'same as production "
             "Stelvio and Giulia'. Not independently VIN-fitment-verified "
             "beyond that listing.", confidence=SINGLE_SOURCE,
             source="https://www.alfaonlineparts.com/"),
        _oem("68300626AA", note="Alternate candidate name seen in parts "
             "catalogues for the same function; one listing scopes it to "
             "the 2.9L V6 only -- do not assume Stelvio 2.0T fitment "
             "without VIN-checking at a Mopar counter. The two OEM numbers "
             "above are NOT corroborating each other -- they are "
             "competing candidates from different sources.",
             confidence=UNKNOWN,
             source="https://static.nhtsa.gov/odi/tsbs/2024/MC-11011985-0001.pdf"),
    ],
    fits="giorgio",
    location="In the EVAP line near the fuel vapor canister; distinct "
             "from the canister itself.",
    related_codes=["P0440", "P0441", "P0455", "P0456", "P0457"],
    related_jobs=["evap_leak"],
    torque_keys=["evap_esim_mount"],
    buy=[_rockauto("04861961AD")],
    images=[_image(
        "https://www.rockauto.com/info/162/MR_4861961AC_Ang__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=04861961AD",
        "RockAuto listing photo, MOPAR 4861961AC", "photo",
        "linked from RockAuto; not copied. Listing is suffix AC, not this "
        "record's primary-candidate suffix AD -- same ESIM/leak-detection "
        "pump family (RockAuto categorizes it 'Vapor Leak Detection "
        "Pump'), suffix not independently confirmed for this VIN.",
    )],
    notes="TSB 9100469 (MY18-25 GA/GU, CONFIRMED): 'If an issue is "
          "detected with the EVAPORATIVE SYSTEM INTEGRITY MODULE DETECTOR "
          "and not the VAPOR CANISTER, only replace the EVAPORATIVE SYSTEM "
          "INTEGRITY MODULE DETECTOR.' Replacing the canister for an ESIM "
          "fault is a documented, bulletin-warned error. One forum report "
          "describes a ~$110 part ('leak detector pump') resolving a CEL "
          "after a dealer had replaced the whole purge system -- most "
          "likely this part under a colloquial name (SINGLE-SOURCE, "
          "unconfirmed against either OEM number above); source "
          "docs/research/EVAP_STELVIO.md section 2/7.",
)

_part(
    "purge_valve", "EVAP purge valve / solenoid",
    "An ECM-commanded solenoid valve that purges fuel vapor from the "
    "canister into the intake under computer control.",
    oem=[_oem("68337662AC", note="Fitment for this Alfa application not "
              "independently verified this pass.", confidence=UNKNOWN,
              source="docs/research/EVAP_STELVIO.md")],
    fits="giorgio",
    location="Engine bay, in the purge line between the canister and the "
             "intake/ejector tees; FCA's own labour operation calls this "
             "assembly the 'Boost Vacuum Purge Tube Assembly'.",
    related_codes=["P0440", "P0441", "P0455", "P0456", "P1CEA"],
    related_jobs=["evap_leak"],
    torque_keys=["evap_purge_valve_mount"],
    buy=[_rockauto("68337662AC")],
    images=[_image(
        "https://www.rockauto.com/info/162/68337662AA-0-ANG__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=68337662AC",
        "RockAuto listing photo, MOPAR 68337662AC", "photo",
        "linked from RockAuto; not copied. Listing text reads MOPAR "
        "68337662AC, an exact match on this record's OEM number "
        "(the image filename itself says '...AA', RockAuto's own naming "
        "quirk, not a different part).",
    )],
    notes="Field consensus (forum-grade, convergent across sources) is "
          "that a standalone purge-valve fault is low-yield for these "
          "codes -- several owners report replacing it alone with no "
          "resolution; weight diagnosis toward the vent/canister side "
          "first. KOEO actuator test (MES: 'Evaporation control valve', "
          "engine OFF) confirms the valve clicks before condemning it.",
)

_part(
    "evap_canister", "EVAP (fuel vapor) canister",
    "Stores fuel vapor from the tank (charcoal bed) until the ECM purges "
    "it into the intake; on NA cars the vent function is integrated into "
    "the canister module, not a separate valve.",
    oem=[_oem("68400620A_ / 68402531A_ / 68528496A_ / 68534104A_",
              note="Four part numbers listed for 'VAPOR CANISTER' in TSB "
                   "9100469 (MY18-25 GA/GU). The bulletin prints each "
                   "number with a trailing '$' wildcard for the suffix "
                   "letter(s) -- the exact current suffix for this VIN "
                   "was not resolved this pass; confirm at a Mopar parts "
                   "counter.", confidence=CONFIRMED,
              source="https://static.nhtsa.gov/odi/tsbs/2024/MC-11011985-0001.pdf")],
    fits="giorgio",
    location="Behind the driver's-side rear wheel liner.",
    related_codes=["P0440", "P0455", "P0456", "P2422"],
    related_jobs=["evap_leak"],
    torque_keys=["evap_canister_mount"],
    price=_price(275, None,
                 "docs/research/EVAP_STELVIO.md (forum-grade dealer quote "
                 "context: '$275+ canister'; a separate dealer quote cites "
                 "$579.45 parts for purge solenoid + canister combined)"),
    buy=[_rockauto("68528496AA")],
    notes="Design hypothesis (UNCERTAIN, forum-sourced but mechanically "
          "coherent): the original canister places the charcoal bed at "
          "the bottom, so topping off lets liquid fuel migrate in and "
          "saturate it; a revised design moves the bed to the top. "
          "'Pump clicks off during refuelling' plus P2422 is close to "
          "pathognomonic for a blocked/saturated canister on this "
          "platform. Check the canister FILTER first (TSB 9100468, "
          "CONFIRMED, scheduled item) -- cheap and precedes any canister "
          "decision. Distinguish from the ESIM before ordering (see "
          "that part's notes) -- replacing this for an ESIM fault is a "
          "bulletin-warned error.",
)

_part(
    "evap_quick_connect", "EVAP recirculation-line quick-connect fitting",
    "A quick-connect fitting on the EVAP recirculation line; FCA "
    "documents checking this connection first, before any deep EVAP "
    "diagnosis, for these exact leak/valve codes.",
    oem=[_oem(None, confidence=UNKNOWN,
              note="Not sold as a separately ordered part in this "
                   "research pass -- documented as a check/reseat point, "
                   "not a replacement part. If physically cracked, "
                   + TECHAUTHORITY)],
    fits="giorgio",
    location="Mid-point of the EVAP recirculation line; a related pair of "
             "quick connects also sit at the air cleaner cover (push-"
             "pull-push check per TSB 25-002-23, a same-engine-family "
             "Grand Cherokee 4xe bulletin).",
    related_codes=["P0440", "P0441", "P0455", "P0456", "P1CEA"],
    related_jobs=["evap_leak"],
    notes="STAR S2125000002 (2021-06-18, CONFIRMED -- FCA tech bulletin): "
          "explicitly the first check FCA documents for P0455/P0456/P0441/ "
          "P1CEA, ahead of any deeper diagnosis. Check that it is fully "
          "seated and latched; free, two minutes.",
)


# --- brakes -------------------------------------------------------------------

_part(
    "brake_pads_front", "Front brake pads",
    "Friction material that clamps the front rotors under braking; this "
    "car's front calipers are Brembo-fitted.",
    oem=[_oem(None, confidence=UNKNOWN)],
    fits="giorgio",
    location="Front calipers, one pad per side of each rotor.",
    related_jobs=["brakes_front"],
    torque_keys=["caliper_slider_front", "caliper_bracket_front", "wheel_lug"],
    notes="No sourced FCA minimum pad thickness this pass -- forum chatter "
          "cites a generic ~2-3 mm industry rule of thumb, not a "
          "manufacturer spec. This car has an electronic pad-wear sensor "
          "on the inner pad. " + TECHAUTHORITY,
)

_part(
    "brake_pads_rear", "Rear brake pads",
    "Friction material that clamps the rear rotors; the rear calipers "
    "carry an electric parking brake (EPB) motorized piston.",
    oem=[_oem(None, confidence=UNKNOWN)],
    fits="giorgio",
    location="Rear calipers (EPB-equipped), one pad per side of each "
             "rotor.",
    related_jobs=["brakes_rear"],
    torque_keys=["caliper_slider_rear", "caliper_bracket_rear", "wheel_lug"],
    notes="Must put the EPB into service mode (infotainment Settings > "
          "Passive Safety > Brake Service Mode) before retracting the "
          "rear piston -- forcing it back mechanically without service "
          "mode can strip the actuator's gears/spindle. No sourced FCA "
          "minimum pad thickness this pass. " + TECHAUTHORITY,
)

_part(
    "brake_rotor_front", "Front brake rotor",
    "The disc the front pads clamp against under braking.",
    oem=[_oem(None, confidence=UNKNOWN,
              note="No Mopar catalog number sourced; an aftermarket-"
                   "aggregator figure exists for dimensions only (see "
                   "notes). " + TECHAUTHORITY)],
    fits="giorgio",
    location="Front hub/knuckle, 330 mm diameter, 28 mm new thickness.",
    related_jobs=["brakes_front"],
    torque_keys=["wheel_lug", "rotor_retaining_screw"],
    notes="New thickness 28 mm, minimum (discard) thickness 25.5 mm per "
          "go-parts.com's fitment aggregator (SINGLE-SOURCE, aftermarket "
          "site, not a manufacturer document). Read the rotor's own "
          "cast-in 'MIN TH' marking as the most reliable check on the "
          "actual part.",
)

_part(
    "brake_rotor_rear", "Rear brake rotor",
    "The disc the rear pads clamp against; shares the hub with the EPB "
    "caliper.",
    oem=[_oem(None, confidence=UNKNOWN,
              note="No Mopar catalog number sourced. " + TECHAUTHORITY)],
    fits="giorgio",
    location="Rear hub/knuckle, 320 mm diameter, 22 mm new thickness.",
    related_jobs=["brakes_rear"],
    torque_keys=["wheel_lug", "rotor_retaining_screw"],
    notes="New thickness 22 mm per go-parts.com (SINGLE-SOURCE, "
          "aftermarket site). No sourced rear minimum/discard thickness "
          "this pass -- read the cast-in 'MIN TH' marking on the physical "
          "rotor. " + TECHAUTHORITY,
)

_part(
    "brake_fluid", "Brake fluid",
    "Hydraulic fluid for the brake circuit, ABS/ESC modulator and (via "
    "the rear calipers) the EPB hydraulics.",
    oem=[_oem(None, brand="n/a", confidence=UNKNOWN,
              note="Spec DOT 4, FCA MS.90039 -- buy to spec, not a Mopar "
                   "part number.")],
    fits="stelvio_2.0t",
    location="Reservoir at the master cylinder, engine bay.",
    related_jobs=["brake_fluid"],
    notes="Spec and capacity CONFIRMED from the 2018 US owner's manual "
          "('Fluids And Lubricants' / 'Fluid Capacities' tables): DOT 4, "
          "MS.90039, 0.9 L hydraulic circuit (reservoir + lines, not a "
          "drain-and-refill quantity). Change interval: every 2 years "
          "regardless of mileage (CONFIRMED, owner's manual). Bleed all "
          "four corners plus the ABS/ESC modulator; EPB service mode "
          "before disturbing the rear circuit.",
)


# --- coolant / drivetrain fluids ----------------------------------------------

_part(
    "coolant", "Engine coolant",
    "Long-life OAT coolant for the engine cooling circuit; the "
    "water-cooled intercooler on this turbo engine has its OWN separate "
    "circuit and reservoir, not covered by this fill.",
    oem=[_oem(None, brand="n/a", confidence=UNKNOWN,
              note="Spec FCA/Alfa MS.90032 -- buy to spec, not a Mopar "
                   "part number sourced this pass.")],
    fits="giorgio",
    location="Engine coolant reservoir (separate from the intercooler "
             "reservoir).",
    related_jobs=["coolant"],
    notes="Spec and capacity CONFIRMED from the 2018 US owner's manual: "
          "FCA/Alfa MS.90032 (CUNA NC956-16, ASTM D3306) OAT, used at 50% "
          "concentration (60/40 for harsh climates), engine circuit 8.8 L "
          "(2.3 US gal). Mandatory single change at 150,000 mi / 240,000 "
          "km / 15 years (CONFIRMED) -- not a periodic-interval item. Not "
          "mixable with different-formulation coolants. No sourced drain-"
          "plug location or bleed procedure for the 2.0T engine circuit "
          "this pass. " + TECHAUTHORITY,
)

_part(
    "transmission_fluid", "ZF 8HP transmission fluid (ATF)",
    "The automatic transmission's hydraulic/lubricating fluid.",
    oem=[_oem("68218925AA", brand="Mopar",
              note="Marketed as ZF LifeguardFluid 8 / Mopar '8 & 9 Speed "
                   "ATF'. NOT compatible with ATF+4 or any other current "
                   "FCA ATF.", confidence=SINGLE_SOURCE,
              source="docs/reference/ZF8HP_SERVICE_DATA.md #1 (ZF doc "
                     "1087.754.107c)")],
    fits="giorgio",
    location="ZF 8HP transmission, filled via the side plug with the "
             "unit tipped for an overhaul dry fill; service drain-and-"
             "fill via the pan.",
    related_jobs=["transmission_fluid"],
    torque_keys=["transmission_drain_plug", "transmission_fill_plug",
                 "transmission_pan_bolts"],
    buy=[_rockauto("68218925AA")],
    images=[_image(
        "https://www.rockauto.com/info/162/68218925AB_1__ra_m.jpg",
        "https://www.rockauto.com/en/partsearch/?partnum=68218925AA",
        "RockAuto listing photo, MOPAR 68218925AB", "photo",
        "linked from RockAuto; not copied. Listing is suffix AB, not this "
        "record's sourced AA -- same ZF LifeguardFluid 8 / 8-9 Speed ATF "
        "product, suffix not reconciled this pass.",
    )],
    notes="Fluid identity/incompatibility CONFIRMED via this repo's ZF "
          "service-data doc; the Mopar part number itself is "
          "SINGLE-SOURCE. Dry-fill capacity 9.0 L (9.5 qt), +0.7 L if the "
          "cooler is replaced (CONFIRMED, ZF doc Table 1). Service "
          "drain-and-fill quantity not established -- forum practice "
          "only. Fill/level-check temperature window 30-50 degC.",
)

_part(
    "transfer_case_fluid", "Q4 transfer case fluid",
    "Lubricates and provides friction characteristics for the Q4 active "
    "transfer case's multi-plate wet clutch.",
    oem=[_oem(None, brand="n/a", confidence=UNKNOWN,
              note="No Mopar-branded part number sourced this pass; buy "
                   "to spec, not by part number.")],
    fits="giorgio",
    location="Q4 transfer case, driveline.",
    related_jobs=["transfer_case_fluid"],
    torque_keys=["transfer_case_drain_plug", "transfer_case_fill_plug"],
    notes="Fluid identity CORROBORATED (two independent sources): Petronas "
          "Tutela Transmission Transfer Case (Q4) / Tutela Transmission "
          "Hypoide Gear Oil, synthetic SAE 75W, FIAT approval "
          "9.55550-DA11. Do not substitute ATF or generic 75W GL-5 -- "
          "friction characteristics are matched to the clutch pack. "
          "Capacity unreconciled: ~1 L (repo doc) vs 0.7 L (giuliatech.com) "
          "-- confirm exact fill quantity at a dealer parts counter.",
)


# --- misc ---------------------------------------------------------------------

_part(
    "tpms_sensor", "TPMS (tire pressure) sensor",
    "A wheel-mounted sensor reporting live tire pressure/temperature to "
    "the RFHUB module over RF.",
    oem=[_oem(None, confidence=UNKNOWN,
              note="No sourced Mopar sensor part number this pass. "
                   + TECHAUTHORITY)],
    fits="stelvio_2.0t",
    location="Inside each wheel, mounted on the valve stem/rim.",
    related_jobs=["wheels"],
    notes="Live pressure/temperature can be read from the RFHUB module "
          "over UDS at DIDs 0x40B1-0x40B4 (one per corner: FL/FR/RL/RR) -- "
          "see mes.service_specs.TPMS_DIDS and cuore/live/addressing.py "
          "(read-only mapping; this module performs no live reads).",
)

_part(
    "turbo_intercooler_hose", "Turbo / intercooler boost hose",
    "Carries pressurized charge air between the turbo, the water-cooled "
    "intercooler (CAC) and the throttle body.",
    oem=[_oem(None, confidence=UNKNOWN,
              note="No sourced Mopar hose part number this pass; FCA's "
                   "own labour-operation naming for the related purge "
                   "plumbing is the 'Boost Vacuum Purge Tube Assembly' "
                   "(see the purge_valve part), which is a distinct part "
                   "from a plain boost/charge-air hose. " + TECHAUTHORITY)],
    fits="giorgio",
    location="Between the turbocharger, the water-cooled intercooler "
             "(CAC) and the throttle body/intake, engine bay.",
    related_codes=["P1CEA", "P0299", "P0234"],
    related_jobs=["intake_boost_hoses_inspect"],
    notes="Push-pull-push check on the EVAP quick connects at the air "
          "cleaner cover is documented (TSB 25-002-23, a same-engine-"
          "family Grand Cherokee 4xe bulletin: 'EVAP vacuum lines not "
          "fully secured') as an early step on P1CEA before condemning "
          "hoses or hardware -- see the evap_quick_connect part.",
)


# --- lookups -------------------------------------------------------------------

def get(key: str) -> Optional[dict[str, Any]]:
    """Return one part's record by key, or ``None``."""
    rec = PARTS.get(key)
    return dict(rec) if rec is not None else None


def _tag_sibling(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["sibling_of"] = row.get("fits")
    out["verify_fit"] = True
    return out


def _split_siblings(rows: list[dict[str, Any]],
                     include_siblings: bool) -> list[dict[str, Any]]:
    primary = [r for r in rows if r.get("fits") not in SIBLING_FITS]
    if not include_siblings:
        return primary
    sibling_rows = [_tag_sibling(r) for r in rows if r.get("fits") in SIBLING_FITS]
    return primary + sibling_rows


def for_code(code: str, include_siblings: bool = False) -> list[dict[str, Any]]:
    """Parts whose ``related_codes`` includes ``code`` (case-insensitive).

    With ``include_siblings=True``, also returns any part whose ``fits`` is
    a sourced sibling platform (grecale/levante -- see ``mes.platform``),
    flagged ``{"sibling_of": <model>, "verify_fit": True}``. No current
    ``PARTS`` entry has such a ``fits`` value -- see ``SIBLING_FITS``.
    """
    code_u = code.strip().upper()
    out = []
    for key, rec in PARTS.items():
        if code_u in (c.upper() for c in rec.get("related_codes", [])):
            out.append({"key": key, **rec})
    return _split_siblings(out, include_siblings)


def for_job(job: str, include_siblings: bool = False) -> list[dict[str, Any]]:
    """Parts whose ``related_jobs`` includes ``job`` (case-insensitive).
    See :func:`for_code` for ``include_siblings``."""
    job_l = job.strip().lower()
    out = []
    for key, rec in PARTS.items():
        if job_l in (j.lower() for j in rec.get("related_jobs", [])):
            out.append({"key": key, **rec})
    return _split_siblings(out, include_siblings)


def all() -> dict[str, dict[str, Any]]:
    """Every part, keyed as stored."""
    return dict(PARTS)
