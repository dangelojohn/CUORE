"""Others' experience: reputable YouTube how-tos and direct forum threads.

A mechanic's dossier is codes, specs and bulletins; what it is missing is the
thing a shop floor actually runs on -- "I've seen this exact code on this
exact car, here's what it was." This module is a small, hand-curated,
link-verified table pointing at that: specific YouTube videos showing the
actual Alfa Romeo/Stellantis Giorgio-platform part being worked on, and (where
verification allowed it -- see below) direct forum threads, keyed by DTC,
fault family or service job.

Every entry was checked on 2026-10-07 (``verified_at``) by one of:
- an HTTP GET returning 200 with a browser User-Agent (``verified_how:
  "http_200"``);
- the YouTube oEmbed endpoint returning 200 with a title (``verified_how:
  "youtube_oembed"``, and that returned title is stored verbatim);
- a real headless-browser navigation over the Chrome DevTools Protocol,
  reading ``document.title`` and the first post's text off the rendered page
  (``verified_how: "browser_cdp"``). Nothing below was invented and nothing
  that failed verification was kept.

FORUM THREADS -- stelvioforum.com, giuliaforums.com, alfabb.com and
alfaowner.com (all XenForo, apparently sharing one vendor) sit behind a
JavaScript proof-of-work bot challenge that returns HTTP 202 with a
challenge page to any plain HTTP client, never the real thread -- confirmed
against a dozen thread URLs across all four domains during the original
build. A plain ``urllib``/``requests`` GET cannot pass that challenge (it
requires executing the page's JS), so no thread on those four domains could
be verified as HTTP 200 that way. A later pass (2026-10-07) drove headless
Edge over CDP instead -- a real browser session executes the challenge JS
like any visitor -- and that got through cleanly for every candidate thread
tried, so forum_thread entries verified ``browser_cdp`` are now included
below. Any thread that still returns a bot-wall title ("Just a moment",
"Attention Required", etc.) or has no readable post text under that method
is left out, same as before.

Lookup is by exact key membership in ``keys`` -- no fuzzy matching, no family
fallback (unlike :mod:`mes.code_feel`): a code with no entry simply returns
an empty list, which is the honest answer when nothing verified.

Sibling platforms (2026-10-07 pass, see :mod:`mes.platform`): this project's
car is a Stelvio; the user has described the Maserati Grecale and Maserati
Levante as "similar" sibling cars. A quick pass looked for a Grecale- or
Levante-specific, verifiable (oEmbed or browser_cdp) EVAP/P0455, ZF 8HP
fluid, or wheel-bearing-noise video or thread and found nothing that was
both model-specific and verifiable in the time available -- the ZF 8HP
fluid-change videos found were generic (BMW/Jeep/Dodge), not
Maserati-specific, and the P0455 hits were generic write-ups, not Maserati
ones. Per house rule (never present an unverified relationship as fact),
nothing was added rather than mistagging a generic video as Maserati-
specific. ``SIBLING_FITS`` and ``include_siblings`` below are therefore live
plumbing with nothing yet to return -- an entry only gets tagged if its own
``vehicle_fit`` is literally ``"grecale"`` or ``"levante"``, never guessed.
"""

from __future__ import annotations

import re
from typing import Any

_CODE_RE = re.compile(r"^[PBCU][0-9A-F]{4}$", re.IGNORECASE)

#: Non-code keys this table recognises. A code (matches _CODE_RE) is always
#: a valid key regardless of whether anything is tabulated for it yet.
FAMILIES = {"EVAP", "network_cascade", "misfire"}
JOBS = {
    "esim", "purge_valve", "canister",
    "oil_change", "spark_plugs", "engine_air_filter", "cabin_air_filter",
    "brake_fluid", "transfer_case", "drive_belt", "battery_12v",
    "window_riser", "tpms", "zf8hp_fluid",
}
#: Sound tags the media library's audio clips can carry (see
#: ``cuore.live.media.SOUND_TAGS``, the superset this is a subset of --
#: only the tags with a verified reference clip below are tabulated here).
#: An entry keyed by one of these is ``kind: "sound_reference"``: a verified
#: "here's what that sounds like" clip a mechanic's own recording can be
#: compared against, not a repair how-to.
SOUND_TAGS = {"wheel_bearing", "cv_joint", "belt_squeal", "turbo_whine", "exhaust_leak"}
KNOWN_NON_CODE_KEYS = FAMILIES | JOBS | SOUND_TAGS

VERIFIED_AT = "2026-10-07"

LINKS: tuple[dict[str, Any], ...] = (
    # --- EVAP family: P0440/P0441/P0455/P0456/P0457, ESIM, purge valve, canister ---
    {
        "id": "yt-evap-p0440-fixed",
        "keys": ["P0440", "P0441", "P0455", "P0456", "EVAP"],
        "title": "P0440 EVAP Fault on Alfa Romeo Giulia & Stelvio 2.0 — FIXED!",
        "url": "https://www.youtube.com/watch?v=G9M--Poudm8",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Hands-on diagnosis and fix of an EVAP fault on a Giulia/Stelvio 2.0, "
                  "walking the actual leak path on the car.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-evap-canister-giulia",
        "keys": ["P0455", "P0456", "EVAP", "canister"],
        "title": "Evap Canister Replacement Alfa Romeo Giulia",
        "url": "https://www.youtube.com/watch?v=UJh89VxrVIA",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Full R&R of the EVAP canister on a Giulia, the same canister fitted to "
                  "the Stelvio 2.0T.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-evap-esim-tips",
        "keys": ["P0455", "P0456", "EVAP", "esim", "canister"],
        "title": "Evaporative System Integrity Module (ESIM) Replacement Tips",
        "url": "https://www.youtube.com/watch?v=40h9LbzwVxQ",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "ESIM replacement/diagnosis tips from a parts-channel tech, relevant "
                  "wherever the ESIM is the suspect part rather than the canister body.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-evap-purge-valve-fiat-alfa",
        "keys": ["P0440", "P0441", "EVAP", "purge_valve"],
        "title": "PURGE CONTROL VALVE LOCATION REPLACEMENT EXPLAINED FIAT, ALFA ROMEO",
        "url": "https://www.youtube.com/watch?v=YfXQWoCncA4",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Purge control valve location and replacement across the shared "
                  "Fiat/Alfa Romeo platform parts bin.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- misfire: P0300-P0304 ---------------------------------------------
    {
        "id": "yt-misfire-p0300-coil",
        "keys": ["P0300", "P0301", "P0302", "P0303", "P0304", "misfire"],
        "title": "How To Fix An Engine Misfire-P0300 (Bad Ignition Coil)",
        "url": "https://www.youtube.com/watch?v=6icmfICvyp0",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Generic coil-pack misfire diagnosis walkthrough -- not Alfa-specific, "
                  "no platform-specific misfire video verified; included as the general "
                  "diagnostic method (swap-the-coil test) that does apply to the 2.0T.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- oil_change ---------------------------------------------------------
    {
        "id": "yt-oil-change-giulia-stelvio",
        "keys": ["oil_change"],
        "title": "Alfa Romeo Giulia/Stelvio 2.0T Engine Oil Change",
        "url": "https://www.youtube.com/watch?v=ItBj8KNYrMQ",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Full DIY oil and filter change on the 2.0T shared by Giulia and Stelvio.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-oil-change-reset",
        "keys": ["oil_change"],
        "title": "Alfa Romeo Stelvio/Giulia oil change & maintenance reset",
        "url": "https://www.youtube.com/watch?v=MD7LqasnmzA",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Oil change paired with the service-interval reset, done on a 2018 "
                  "Stelvio -- the MES/manual reset step this project's oil_change job needs.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- spark_plugs ---------------------------------------------------------
    {
        "id": "yt-spark-plug-install-giulia-stelvio",
        "keys": ["spark_plugs"],
        "title": "Alfa Romeo Gulia/Stelvio spark plug install",
        "url": "https://www.youtube.com/watch?v=8MfCso-Qhn4",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Spark plug and coil-boot R&R on the 2.0T (NGK 90219 fitment).",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-spark-plug-2018-stelvio",
        "keys": ["spark_plugs"],
        "title": "How to Change Spark Plugs on a 2018 Alfa Romeo Stelvio",
        "url": "https://www.youtube.com/watch?v=ACzj-N1VvDk",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Spark plug change on a 2018 Stelvio -- same model year as this car.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- cabin_air_filter -----------------------------------------------
    {
        "id": "yt-cabin-filter-30min",
        "keys": ["cabin_air_filter"],
        "title": "Alfa Romeo Stelvio HVAC Cabin Filter Replacement | 30 Minutes of Fun",
        "url": "https://www.youtube.com/watch?v=QmrlOwPSvYQ",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Full teardown of the awkward Stelvio cabin filter box behind the "
                  "passenger footwell panel.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-cabin-filter-alfatech",
        "keys": ["cabin_air_filter"],
        "title": "Alfa Romeo Stelvio cabin air filter replacement",
        "url": "https://www.youtube.com/watch?v=sGRjlOnN8rM",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Second independent cabin air filter replacement walkthrough on a Stelvio.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- engine_air_filter -----------------------------------------------
    {
        "id": "yt-engine-filter-quadrifoglio",
        "keys": ["engine_air_filter"],
        "title": "How To Replace Air Filter In Alfa Romeo Stelvio/Giulia Quadrifoglio - Step By Step",
        "url": "https://www.youtube.com/watch?v=KxBRCCChQp0",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Engine air filter box opening and filter swap, step by step.",
        "vehicle_fit": "giorgio",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-engine-filter-giulia-stelvio",
        "keys": ["engine_air_filter"],
        "title": "Alfa Romeo Giulia/Stelvio Air Filter Change",
        "url": "https://www.youtube.com/watch?v=GgePKewmUkY",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Quick engine air filter change on the shared Giulia/Stelvio intake box.",
        "vehicle_fit": "giorgio",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- brake_fluid (+ EPB service mode) -----------------------------------
    {
        "id": "yt-brake-fluid-flush-stelvio",
        "keys": ["brake_fluid"],
        "title": "2018-2022 Alfa Romeo Stelvio 2.0 brake fluid flush service",
        "url": "https://www.youtube.com/watch?v=PLftfWIJIWQ",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Full brake fluid flush/bleed on a 2.0T Stelvio.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-brake-service-mode-qf",
        "keys": ["brake_fluid"],
        "title": "Alfa Romeo Stelvio/Giulia Quadrifoglio Brake Service Mode and Replacement- Step-By-Step",
        "url": "https://www.youtube.com/watch?v=VHTnQ6o1fNE",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Putting the EPB into Brake Service Mode to retract the rear caliper "
                  "motors before pad/fluid work -- the step a fluid flush needs on this "
                  "platform's electric parking brake.",
        "vehicle_fit": "giorgio",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- drive_belt ----------------------------------------------------------
    {
        "id": "yt-serpentine-belt-stelvio-2.0l",
        "keys": ["drive_belt"],
        "title": "Alfa Romeo Stelvio serpentine belt replacement 2.0L engine",
        "url": "https://www.youtube.com/watch?v=u1B4eVCVzZc",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Serpentine/auxiliary belt replacement on the 2.0L turbo Stelvio.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-serpentine-belt-giulia-stelvio-2.0t",
        "keys": ["drive_belt"],
        "title": "Alfa Romeo Giulia/Stelvio 2.0T Serpentine Belt Change",
        "url": "https://www.youtube.com/watch?v=T9ocCL2jNzQ",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "Second independent serpentine belt change walkthrough for the 2.0T.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- battery_12v -----------------------------------------------------
    {
        "id": "yt-12v-battery-stelvio-diy",
        "keys": ["battery_12v"],
        "title": "Alfa Romeo Stelvio DIY Battery Replacement | Electrical Problems Solved",
        "url": "https://www.youtube.com/watch?v=cjPr4TU-3wI",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "12V main battery replacement on a Stelvio, framed around chasing "
                  "electrical gremlins back to a weak battery.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-12v-battery-giulia",
        "keys": ["battery_12v"],
        "title": "🍀 Alfa Romeo Giulia Battery Replacement 🍀",
        "url": "https://www.youtube.com/watch?v=RvVCRASmRc8",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "12V battery swap on a Giulia, same procedure/location as the Stelvio.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- tpms ----------------------------------------------------------------
    {
        "id": "yt-tpms-reset-giulia",
        "keys": ["tpms"],
        "title": "How to Reset Tire Pressure on an Alfa Romeo Giulia",
        "url": "https://www.youtube.com/shorts/aZozbSTK_ec",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "In-cluster/infotainment menu walk to reset the TPMS pressure warning "
                  "on a Giulia; same menu path as the Stelvio.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- zf8hp_fluid -----------------------------------------------------
    {
        "id": "yt-zf8hp-transmission-service",
        "keys": ["zf8hp_fluid"],
        "title": "Alfa Romeo Gulia/Stelvio transmission service",
        "url": "https://www.youtube.com/watch?v=PcCrAYIjLTU",
        "source": "youtube",
        "kind": "how_to_video",
        "covers": "ZF 8HP fluid/filter service on the shared Giulia/Stelvio AWD drivetrain.",
        "vehicle_fit": "giorgio",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },

    # --- forum threads (verified via browser_cdp, 2026-10-07) --------------
    {
        "id": "sf-evap-canister-p0440-p0456-2018-stelvio",
        "keys": ["P0440", "P0456", "EVAP", "canister", "purge_valve"],
        "title": "2018 Alfa Romeo Stelvio EVAP Canister/EVAP Leak Sensor - P0440 and P0456",
        "url": "https://www.stelvioforum.com/threads/2018-alfa-romeo-stelvio-evap-canister-evap-leak-sensor-p0440-and-p0456.24981/",
        "source": "stelvioforum.com",
        "kind": "forum_thread",
        "covers": "Owner replaced the purge solenoid on a 2018 Stelvio chasing P0440/P0456, "
                  "linking the ~$50 Amazon part used.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "gf-p0456-canister-replaced-still-persists",
        "keys": ["P0456", "EVAP", "canister"],
        "title": "P0456",
        "url": "https://www.giuliaforums.com/threads/p0456.51472/",
        "source": "giuliaforums.com",
        "kind": "forum_thread",
        "covers": "Owner's dealer replaced the charcoal canister and reflashed the computer "
                  "for a recurring P0456, but the code returned within a few startups.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "high",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "gf-p0440-purge-valve-solenoid-location",
        "keys": ["P0440", "EVAP", "purge_valve"],
        "title": "P0440 CEL - Purge Valve / Solenoid Location",
        "url": "https://www.giuliaforums.com/threads/p0440-cel-purge-valve-solenoid-location.64584/",
        "source": "giuliaforums.com",
        "kind": "forum_thread",
        "covers": "2018 Giulia owner at ~60,000km gets a P0440 and asks how to read the "
                  "freeze-frame data pointing at the purge solenoid.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "gf-p2422-canister-replacement-how-to",
        "keys": ["P2422", "EVAP", "canister"],
        "title": "P2422 Evap Canister Malfunction Replacement / removal How-To",
        "url": "https://www.giuliaforums.com/threads/p2422-evap-canister-malfunction-replacement-removal-how-to.63784/",
        "source": "giuliaforums.com",
        "kind": "forum_thread",
        "covers": "Owner fixes a recurring P2422 (fuel-pump shutoff, limp mode) by replacing "
                  "the EVAP canister and writes up the removal/install job as straightforward.",
        "vehicle_fit": "giulia_2.0t",
        "date": None,
        "reputation": "high",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "sf-squadra-logger-p219c-p0455-p0457",
        "keys": ["P219C", "P0455", "P0457", "EVAP"],
        "title": "Squadra Logger Reading Codes (P219C, P0455, P0457) - No real issues but "
                 "question for the group?",
        "url": "https://www.stelvioforum.com/threads/squadra-logger-reading-codes-p219c-p0455-p0457-no-real-issues-but-question-for-the-group.22705/",
        "source": "stelvioforum.com",
        "kind": "forum_thread",
        "covers": "Owner's data logger captured P219C/P0455/P0457 with no CEL or limp mode, "
                  "after the car had already been in for EVAP leak service.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "sf-vapor-canister-part-numbers",
        "keys": ["EVAP", "canister", "P0456"],
        "title": "How many different Vapor Canister P/Ns are there?",
        "url": "https://www.stelvioforum.com/threads/how-many-different-vapor-canister-p-ns-are-there.22360/",
        "source": "stelvioforum.com",
        "kind": "forum_thread",
        "covers": "Owner researching a persistent small-leak P0456 catalogs at least four "
                  "different vapor canister part numbers across two canister styles.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "high",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "sf-remote-window-up-down-coding",
        "keys": ["window_riser"],
        "title": "Remote Window Up/Down",
        "url": "https://www.stelvioforum.com/threads/remote-window-up-down.6497/",
        "source": "stelvioforum.com",
        "kind": "forum_thread",
        "covers": "European owner asks about, and the thread discusses, coding the BCM for "
                  "the remote-key press-and-hold window up/down feature.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "high",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "sf-network-cascade-odometer-dna-awd",
        "keys": ["network_cascade", "U0102", "battery_12v"],
        "title": "Odometer blinking, DNA not working, C-1408-86 (ESC), C141C-86 (camera), "
                 "U0102-00 (AWD0 failure",
        "url": "https://www.stelvioforum.com/threads/odometer-blinking-dna-not-working-c-1408-86-esc-c141c-86-camera-u0102-00-awd0-failure.24275/",
        "source": "stelvioforum.com",
        "kind": "forum_thread",
        "covers": "Owner traces a cascade of odometer/DNA/ESC/camera/AWD fault codes back to "
                  "a low 12V battery after the rear window and mirror heaters stopped working.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "ao-stelvio-12v-battery-replacement",
        "keys": ["battery_12v"],
        "title": "Stelvio 12v Battery Replacement",
        "url": "https://www.alfaowner.com/threads/stelvio-12v-battery-replacement.1222865/",
        "source": "alfaowner.com",
        "kind": "forum_thread",
        "covers": "2019 Stelvio owner asks whether the 12V battery is DIY-replaceable "
                  "without causing electrical problems, having heard it can be hit-or-miss.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "ao-stelvio-transfer-case-leak",
        "keys": ["transfer_case"],
        "title": "Stelvio 2.2 4x4 - Transfer Case Leak",
        "url": "https://www.alfaowner.com/threads/stelvio-2-2-4x4-transfer-case-leak.1215443/",
        "source": "alfaowner.com",
        "kind": "forum_thread",
        "covers": "Owner finds a substantial oil leak at the transfer-case front-differential "
                  "shaft seal while working underneath a Stelvio 2.2 4x4.",
        "vehicle_fit": "giorgio",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },
    {
        "id": "sf-oil-change-interval-reset-dealer-trick",
        "keys": ["oil_change"],
        "title": "Oil Change Interval Reset",
        "url": "https://www.stelvioforum.com/threads/oil-change-interval-reset.11605/",
        "source": "stelvioforum.com",
        "kind": "forum_thread",
        "covers": "Owner relays a dealer technician's button-press procedure (start twice, "
                  "brake pedal three times) for resetting the oil change interval without a "
                  "dealer visit.",
        "vehicle_fit": "stelvio_2.0t",
        "date": None,
        "reputation": "high",
        "verified_at": VERIFIED_AT,
        "verified_how": "browser_cdp",
    },

    # --- sound references: "here's what that sounds like" (verified via ---
    # --- the YouTube oEmbed endpoint, 2026-10-07) -- generic, not          ---
    # --- Alfa/Stelvio-specific; a mechanic's own recording (the media     ---
    # --- library's audio clips) gets compared against the failure mode,  ---
    # --- not against this platform. ---------------------------------------
    {
        "id": "yt-sound-wheel-bearing",
        "keys": ["wheel_bearing"],
        "title": "What a bad wheel bearing sounds like and how to diagnose "
                 "which one it is (best audio capture yet)",
        "url": "https://www.youtube.com/watch?v=liBzed1tQTA",
        "source": "youtube",
        "kind": "sound_reference",
        "covers": "Clear audio capture of a failing wheel bearing's growl/hum, plus how "
                  "to tell which corner it's coming from.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-sound-cv-joint",
        "keys": ["cv_joint"],
        "title": "How To Diagnose A Bad CV Axle",
        "url": "https://www.youtube.com/watch?v=BC5NOoznHXw",
        "source": "youtube",
        "kind": "sound_reference",
        "covers": "The rhythmic clicking/popping a worn outer CV joint makes while "
                  "turning, and how to reproduce it on a test drive.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-sound-belt-squeal",
        "keys": ["belt_squeal"],
        "title": "Diagnosing Belt Noise squeak or squeal on a Serpentine Belt",
        "url": "https://www.youtube.com/watch?v=Is_02fID1_g",
        "source": "youtube",
        "kind": "sound_reference",
        "covers": "The squeak/squeal a glazed, worn or misaligned serpentine belt makes, "
                  "and the water-spray test that confirms it's the belt.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-sound-turbo-whine",
        "keys": ["turbo_whine"],
        "title": "Turbo Whining? Do THIS Before Your Engine Explodes!",
        "url": "https://www.youtube.com/watch?v=SNCtezZHCNw",
        "source": "youtube",
        "kind": "sound_reference",
        "covers": "The rising high-pitched whine a spooling turbo makes under boost, "
                  "versus the sharper, louder whine that signals bearing wear.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
    {
        "id": "yt-sound-exhaust-leak",
        "keys": ["exhaust_leak"],
        "title": "What An Exhaust Leak May Sound Like",
        "url": "https://www.youtube.com/watch?v=B9vCVByesGI",
        "source": "youtube",
        "kind": "sound_reference",
        "covers": "The ticking/tapping-to-rumble a manifold or pipe exhaust leak makes, "
                  "most pronounced cold at idle.",
        "vehicle_fit": "generic_obd",
        "date": None,
        "reputation": "medium",
        "verified_at": VERIFIED_AT,
        "verified_how": "youtube_oembed",
    },
)


#: ``vehicle_fit`` values treated as "a sibling platform's car, not this
#: one" -- see :mod:`mes.platform`. Kept in sync with
#: ``mes.platform.SIBLING_MODELS`` but re-declared here (no import) so this
#: module stays the same kind of standalone lookup table its docstring
#: already promises.
SIBLING_FITS = frozenset({"grecale", "levante"})


def _norm(key: str) -> str:
    return (key or "").strip()


def _tag_sibling(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    out["sibling_of"] = entry.get("vehicle_fit")
    out["verify_fit"] = True
    return out


def _filtered(matches: list[dict[str, Any]], include_siblings: bool) -> list[dict[str, Any]]:
    primary = [e for e in matches if e.get("vehicle_fit") not in SIBLING_FITS]
    if not include_siblings:
        return primary
    sibling_entries = [_tag_sibling(e) for e in matches if e.get("vehicle_fit") in SIBLING_FITS]
    return primary + sibling_entries


def for_code(code: str, include_siblings: bool = False) -> list[dict[str, Any]]:
    """All entries tagged with this exact DTC (e.g. ``"P0455"``).

    With ``include_siblings=True``, also returns any entry whose
    ``vehicle_fit`` is a sourced sibling platform (grecale/levante -- see
    :mod:`mes.platform`), each flagged ``{"sibling_of": <model>,
    "verify_fit": True}``. Nothing is tagged unless the entry's own
    ``vehicle_fit`` already says so -- see module docstring.
    """
    key = _norm(code).upper()
    return _filtered([e for e in LINKS if key in e["keys"]], include_siblings)


def for_family(family: str, include_siblings: bool = False) -> list[dict[str, Any]]:
    """All entries tagged with this fault family (e.g. ``"EVAP"``). See
    :func:`for_code` for ``include_siblings``."""
    key = _norm(family)
    return _filtered([e for e in LINKS if key in e["keys"]], include_siblings)


def for_job(job: str, include_siblings: bool = False) -> list[dict[str, Any]]:
    """All entries tagged with this service job (e.g. ``"oil_change"``).
    See :func:`for_code` for ``include_siblings``."""
    key = _norm(job)
    return _filtered([e for e in LINKS if key in e["keys"]], include_siblings)


def for_sound(sound: str, include_siblings: bool = False) -> list[dict[str, Any]]:
    """All entries tagged with this sound tag (e.g. ``"wheel_bearing"``) --
    mechanically identical to :func:`for_job` (lookup is exact key
    membership regardless of what kind of key it is), kept as its own named
    entry point since the media gallery's "Sounds" section calls it for a
    different reason: comparing a mechanic's own recording against a
    verified reference clip, not finding a repair how-to. See
    :func:`for_code` for ``include_siblings``."""
    key = _norm(sound)
    return _filtered([e for e in LINKS if key in e["keys"]], include_siblings)


def all() -> list[dict[str, Any]]:
    """Every tabulated entry, unfiltered."""
    return list(LINKS)
