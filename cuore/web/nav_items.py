"""ONE data source for CUORE navigation: the header's full-screen Menu sheet.

Every page a mechanic can reach is one line in ``ITEMS``.  ``_navsheet.html``
(the Menu sheet, in base.html) reads ``nav_menu(...)`` -- add a page here and
it appears there.  The Menu is the only navigation (no tab strip).  Nothing is
ever deleted from ``ITEMS`` to tidy the Menu (``services/find.py`` searches it):
a page that is not an everyday one is folded under "More" with ``more=True``.

Item fields
  key     stable id; per-vehicle items use the page's own ``tab`` value so the
          current page can be highlighted
  label   English fallback label;  i18n: optional ``t()`` key for translation.
          Leave ``i18n`` empty on a renamed tile, or the old ``t()`` text wins.
  sub     one plain line under the label, under 40 characters (SUB below)
  href    path pattern; ``{vin}`` marks a per-vehicle page (only shown when a
          vehicle is active).  ``href_novin`` is an optional global fallback
  group   Cars / Diagnose / Look up / Service / Records / Shop (read by task: pick the
          car, work the fault, look something up, service it, write it up, shop-wide)
  icon    one icon word (CSS class hook ``ni-<word>``, symbol ``#ni-<word>`` in nav_icons.svg)
  roles   optional tuple; item shown only to those roles (None = everyone)
  primary True = an everyday page: its tile is drawn stronger in the Menu
  top     1..n = place in the everyday top row when a car is open (None = not in it)
  top_novin  same, when no car is open (the car picker comes first then)
  more    True = folded under "More" (car open);  more_novin overrides it when no
          car is open (None = same as ``more``)
"""

from __future__ import annotations

from typing import Any, Optional

GROUPS = ("Cars", "Diagnose", "Look up", "Service", "Records", "Shop")
# Section order on the sheet: with a car open the car's work comes first, the car
# picker moves lower; with no car open the picker is the first thing.
GROUP_ORDER_CAR = ("Diagnose", "Look up", "Service", "Records", "Shop", "Cars")


def _i(key, label, href, group, icon, *, i18n=None, roles=None, primary=False, href_novin=None,
       top=None, top_novin=None, more=True, more_novin=None):
    return {"key": key, "label": label, "href": href, "group": group, "icon": icon,
            "i18n": i18n, "roles": roles, "primary": primary, "href_novin": href_novin,
            "top": top, "top_novin": top_novin, "more": more, "more_novin": more_novin}


V = "/v/{vin}"
ITEMS: list[dict[str, Any]] = [
    # ---- Cars (the landing page is the car picker)
    _i("home", "Brands", "/", "Cars", "vehicles", top_novin=1),
    _i("cars", "Change car", "/cars", "Cars", "vehicles", top=8, top_novin=2),
    _i("start", "Add Service", "/add", "Cars", "start", top_novin=3),
    # ---- Diagnose
    _i("bench", "Bench", V, "Diagnose", "bench", i18n="bench", primary=True, top=1),
    _i("scan", "Full scan", V + "/scan", "Diagnose", "scan", i18n="full_scan", top=2),
    _i("codes", "Codes", V + "/codes", "Diagnose", "codes", i18n="codes", primary=True, top=3),
    _i("liveboard", "Live", V + "/liveboard", "Diagnose", "live", i18n="live_board", primary=True, top=4),
    _i("job", "Job", V + "/job", "Diagnose", "job", i18n="job", primary=True, top=5),
    _i("unread", "What could not be read", V + "/modules#module-lead", "Diagnose", "unread", more=False),
    _i("tests", "Tests", V + "/tests", "Diagnose", "tests", i18n="tests", primary=True, more=False),
    _i("diagnosis", "Diagnosis", V + "/diagnosis", "Diagnose", "diagnosis", i18n="diagnosis"),
    _i("tree", "Fault tree", V + "/tree", "Diagnose", "tree", i18n="fault_tree"),
    _i("gate", "Ready to repair?", V + "/gate", "Diagnose", "gate"),
    _i("crosschecks", "Readings agree?", V + "/crosschecks", "Diagnose", "check"),
    _i("intermittent", "Intermittent", V + "/intermittent", "Diagnose", "intermittent", i18n="intermittent"),
    _i("trends", "Trends", V + "/trends", "Diagnose", "trends", i18n="trends"),
    _i("power-budget", "Power and ground", V + "/power-budget", "Diagnose", "power", i18n="power_budget"),
    # ---- Car
    _i("systems", "Systems", V + "/systems", "Look up", "systems", i18n="systems", primary=True, more=False),
    _i("sensors", "Sensors", V + "/sensors", "Look up", "sensors", primary=True),
    _i("fuses", "Fuses", V + "/fuses", "Look up", "fuses", primary=True, more=False),
    _i("electrical", "Electrical", V + "/electrical", "Look up", "electrical", i18n="electrical", top=6),
    _i("harnesses", "Harnesses", V + "/harnesses", "Look up", "harness"),
    _i("modules", "Modules", V + "/modules", "Look up", "modules", i18n="modules", more=False),
    _i("gauges", "Gauges", V + "/gauges", "Look up", "gauges", i18n="gauges"),
    _i("configuration", "Configuration", V + "/configuration", "Look up", "config"),
    _i("tsb", "TSB for this car", "/tsb?vin={vin}", "Look up", "tsb", more=False),
    # ---- Service
    _i("service-hub", "Service resets", V + "/service-hub", "Service", "service", more=False),
    _i("adjustments", "Adjustments", V + "/adjustments", "Service", "adjust"),
    _i("arrive-ready", "Arrive-ready", V + "/arrive-ready", "Service", "arrive"),
    _i("parts", "Parts", V + "/parts", "Service", "parts", i18n="parts", more=False),
    _i("mods", "Modifications", V + "/mods", "Service", "mods", i18n="mods"),
    _i("witech-recording", "wiTECH recording", V + "/witech-recording", "Service", "witech"),
    _i("parity", "CUORE vs MES", V + "/parity", "Service", "parity"),
    _i("procedures", "Prototype procedures", V + "/procedures/prototype", "Service", "procedure"),
    # ---- Records
    _i("report", "Report", V + "/report", "Records", "report", i18n="report", primary=True, top=7),
    _i("bay-sheet", "Bay sheet", V + "/bay-sheet", "Records", "sheet"),
    _i("bay-service-sheet", "Bay Service Sheet", V + "/bay-service-sheet", "Records", "sheet"),
    _i("car-session", "Car session", V + "/car-session", "Records", "session"),
    _i("dossier", "Dossier", V + "/dossier", "Records", "dossier", i18n="dossier"),
    _i("timeline", "Timeline", V + "/timeline", "Records", "timeline", i18n="timeline"),
    _i("warranty-pack", "Warranty pack", V + "/warranty-pack", "Records", "warranty"),
    _i("recordings", "Recordings", V + "/recordings", "Records", "recordings"),
    _i("scans", "Scans", V + "/scans", "Records", "scans", i18n="scans"),
    _i("media", "Media", V + "/media", "Records", "media", i18n="media"),
    _i("labels", "Labels", V + "/labels", "Records", "labels", i18n="labels"),
    _i("inbox", "Inbox", V + "/inbox", "Records", "inbox", i18n="inbox"),
    _i("dashboard", "Dashboard", V + "/dashboard", "Records", "dashboard", i18n="dashboard"),
    _i("logs", "Logs for this car", "/logs?vin={vin}", "Records", "logs", i18n="logs"),
    _i("mobile", "Phone view / Tell CUORE", "/m/{vin}", "Records", "phone", i18n="mobile"),
    # ---- Shop (no vehicle needed)
    _i("facts", "Facts", "/v/{vin}/facts", "Look up", "facts", href_novin="/facts"),
    _i("vehicles", "Vehicles", "/vehicles", "Shop", "vehicles"),
    _i("catalog", "Parts catalogue", "/catalog", "Look up", "catalog", more_novin=False),
    _i("g-tsb", "TSB", "/tsb", "Shop", "tsb", more_novin=False),
    _i("slvt", "SLVT", "/slvt", "Shop", "slvt"),
    _i("tools", "Tools", "/tools", "Shop", "tools", more_novin=False),
    _i("live", "Live link", "/live", "Shop", "link"),
    _i("hardware", "Adapter", "/hardware", "Shop", "adapter"),
    _i("coverage", "What can be read", "/coverage", "Shop", "coverage", more_novin=False),
    _i("cables", "Cables", "/cables", "Shop", "cables"),
    _i("g-modules", "All modules", "/modules", "Shop", "modules", more_novin=False),
    _i("g-recordings", "All recordings", "/recordings", "Shop", "recordings"),
    _i("g-logs", "All logs", "/logs", "Shop", "logs"),
    _i("settings", "Settings", "/settings", "Shop", "settings", more_novin=False),
    _i("accounts", "Accounts", "/accounts", "Shop", "accounts", roles=("admin", "shop_lead")),
    _i("about", "About", "/about", "Shop", "about"),
    _i("field-quality", "Field quality", "/field-quality", "Shop", "quality"),
    _i("library", "Library", "/library", "Look up", "library"),
    _i("handbook", "How-to guides", "/handbook", "Look up", "handbook", more_novin=False),
]

# One plain line under each tile label (under 40 characters), from the HELP wording below.
SUB: dict[str, str] = {
    "home": "Pick a brand", "cars": "Pick a car or add one", "start": "Find the car, open a job",
    "bench": "What is wrong, what to do next", "scan": "Read every module for codes",
    "codes": "Every fault code and its meaning", "liveboard": "Live readings as you watch",
    "job": "Actions, evidence, proof of fix", "unread": "Modules that were not read",
    "tests": "Guided tests for a cause", "diagnosis": "Most likely cause from evidence",
    "tree": "Possible causes, ranked", "gate": "Enough evidence to commit?",
    "crosschecks": "Readings that should match", "intermittent": "Catch a fault that comes and goes",
    "trends": "How readings changed by visit", "power-budget": "Power and ground to each module",
    "systems": "Systems with modules and parts", "sensors": "Where each sensor is",
    "fuses": "Fuse and relay maps", "electrical": "Wiring paths and connectors",
    "harnesses": "Harnesses and where they run", "modules": "Every module and its state",
    "gauges": "Gauges of the main readings", "configuration": "Module settings (PROXI)",
    "tsb": "Bulletins and recalls, this car", "service-hub": "Routine service in one place",
    "adjustments": "Run resets, see what is ready", "arrive-ready": "Prepare before the car arrives",
    "parts": "Parts for this car", "mods": "Changes recorded on this car",
    "witech-recording": "Record what a dealer tool does", "parity": "What other tools do vs CUORE",
    "procedures": "Procedures still being proven", "report": "The finished report",
    "bay-sheet": "The page that travels with the car", "bay-service-sheet": "Windshield card with a scan code", "car-session": "Checklist for next connection",
    "dossier": "Everything CUORE knows", "timeline": "What happened, in order",
    "warranty-pack": "Evidence for a warranty claim", "recordings": "Recordings of this car's data",
    "scans": "Earlier scans of this car", "media": "Photos and videos", "labels": "Printable labels",
    "inbox": "Your notes and CUORE's answers", "dashboard": "Car status at a glance",
    "logs": "Logs for this car", "mobile": "Phone view, tell CUORE", "facts": "Specs and facts",
    "vehicles": "Every car MES has logged", "catalog": "Parts and torque by name or number",
    "g-tsb": "All bulletins and recalls", "slvt": "Software level check",
    "tools": "Tools and which job needs them", "live": "Is CUORE linked to the car",
    "hardware": "Adapter and connection status", "coverage": "What CUORE can read, by car",
    "cables": "Which cable fits what", "g-modules": "All modules across cars",
    "g-recordings": "All recordings across cars", "g-logs": "All logs across cars",
    "settings": "CUORE settings", "accounts": "Who can sign in", "about": "Which CUORE version",
    "field-quality": "Early warning across cars", "library": "Manufacturer documents",
    "handbook": "Step-by-step guides",
}
for _it in ITEMS:
    _it["sub"] = SUB.get(_it["key"], "")


def resolve_href(item: dict[str, Any], vin: Optional[str]) -> Optional[str]:
    """Concrete href for ``item``, or None when it needs a vehicle and none is active."""
    href = item["href"]
    if "{vin}" not in href:
        return href
    if vin:
        return href.replace("{vin}", vin)
    return item.get("href_novin")


def _folded(row: dict[str, Any], vin: Optional[str]) -> bool:
    if not vin and row.get("more_novin") is not None:
        return bool(row["more_novin"])
    return bool(row["more"])


def nav_menu(vin: Optional[str] = None, tab: str = "", role: Optional[str] = None,
             path: str = "") -> dict[str, Any]:
    """Role-filtered, href-resolved menu for the current page.

    ``groups``       every visible item by group, GROUPS order (search and tests read this)
    ``top``          the everyday row, in order
    ``open_groups``  the other tiles shown open, by group
    ``more_groups``  everything folded under "More", by group
    """
    tab = tab or ""
    cur = (path or "").split("?")[0]
    rows: list[dict[str, Any]] = []
    for it in ITEMS:
        if it["roles"] and role not in it["roles"]:
            continue
        href = resolve_href(it, vin)
        if not href:
            continue
        per_car = "{vin}" in it["href"] and bool(vin)
        on = bool(cur) and href.split("?")[0] == cur
        if per_car and tab and it["key"] == tab:
            on = True
        rows.append(dict(it, href=href, on=on, per_car=per_car))

    def by_group(sel: list[dict[str, Any]], order: tuple[str, ...]) -> list[dict[str, Any]]:
        return [{"title": g, "items": [r for r in sel if r["group"] == g]}
                for g in order if any(r["group"] == g for r in sel)]

    slot = "top" if vin else "top_novin"
    top = sorted((r for r in rows if r.get(slot)), key=lambda r: r[slot])
    rest = [r for r in rows if not r.get(slot)]
    order = GROUP_ORDER_CAR if vin else GROUPS
    shown = [r for r in rest if not _folded(r, vin)]
    return {"groups": by_group(rows, GROUPS), "top": top,
            "open_groups": by_group(shown, order),
            "more_groups": by_group([r for r in rest if _folded(r, vin)], order),
            "open_count": len(top) + len(shown)}


# Plain-words search help for /find: key -> (extra words a mechanic might type, one sentence on what the page answers).
HELP: dict[str, tuple[str, str]] = {
    "car-session": ("car session, checklist, next connection", "Printable checklist for the next car connection."),
    "bench": ("home, overview, start of job, summary", "The car overview: what is wrong and what to do next."),
    "job": ("work order, repair, hypothesis, proof, fixed", "Your open job: actions, evidence and the proof that the fix worked."),
    "codes": ("dtc, fault code, check engine, mil, trouble code", "Every fault code on this car with what it means and what to test."),
    "liveboard": ("live data, readings, gauges, pids, scan tool", "Live readings from the car, updating as you watch."),
    "tests": ("test, pinpoint, step by step, check", "Guided tests to prove or rule out a cause."),
    "diagnosis": ("verdict, cause, what is wrong", "CUORE's reading of the evidence and its most likely cause."),
    "tree": ("fault tree, why, possible causes", "The possible causes of a fault, ranked by evidence."),
    "gate": ("evidence, enough proof", "Whether there is enough evidence to commit to a repair."),
    "crosschecks": ("compare, cross check, disagree", "Readings that should agree with each other, and whether they do."),
    "intermittent": ("comes and goes, sometimes, random", "Help catching a fault that comes and goes."),
    "trends": ("history, over time, graph", "How readings changed over visits."),
    "power-budget": ("battery, voltage, ground, power", "Power and ground feeds to each module."),
    "systems": ("system, engine, brakes, steering, transmission", "The car split into systems with their modules and parts."),
    "sensors": ("sensor, where is, location", "Where each sensor is and what it reads."),
    "fuses": ("fuse, relay, blown, fuse box", "Fuse and relay maps for this car."),
    "electrical": ("wiring, circuit, pinout, connector, ground, schematic", "Wiring paths, pinouts and connectors."),
    "harnesses": ("harness, loom, wire", "Wiring harnesses and where they run."),
    "modules": ("module, ecu, control unit, bcm, ecm", "Every control module on the car and its state."),
    "gauges": ("gauge, dial, meter", "Gauges of the main readings."),
    "configuration": ("proxi, paddle, market, coding, variant, option", "Module configuration (PROXI) and what each setting means."),
    "service-hub": ("service, maintenance, routine", "Everything for routine service in one place."),
    "adjustments": ("oil reset, service reset, battery registration, proxi alignment, key learning, bleed, tpms, relearn, calibrate", "Run service resets and see which procedures are ready."),
    "witech-recording": ("witech, record dealer, dealer tool", "Record what a dealer tool does so CUORE can learn it."),
    "parity": ("parity, compare tools, mes, alfaobd, gap, missing function", "What MES and AlfaOBD do that CUORE does yet or not."),
    "unread": ("not read, unread, missing module, no answer, did not answer, could not read", "Modules that were not read, so not to be treated as clean."),
    "parts": ("part, part number, mopar, replace", "Parts for this car and what they are tied to."),
    "mods": ("modification, aftermarket, tune", "Modifications recorded on this car."),
    "procedures": ("procedure, prototype", "Procedures still being proven."),
    "tsb": ("bulletin, recall, campaign, csn, technical service", "Bulletins and recalls that apply to this car."),
    "report": ("print, summary, customer", "The finished report for the car."),
    "dossier": ("history, file, everything about the car", "Everything CUORE knows about this car."),
    "timeline": ("history, events, what happened when", "What happened to the car, in order."),
    "recordings": ("recording, capture, log", "Recordings of the car data."),
    "scans": ("scan, past scans", "Earlier scans of the car."),
    "scan": ("full scan, read all modules", "Read every module for codes."),
    "media": ("photo, picture, video, image", "Photos and videos of this car."),
    "labels": ("label, tag, qr", "Printable labels."),
    "inbox": ("feedback, notes to cuore, questions", "Messages you sent CUORE and its answers."),
    "dashboard": ("dashboard, status", "The car status at a glance."),
    "logs": ("log, session log", "Logs for this car."),
    "mobile": ("phone, tell cuore, mobile", "The phone view for telling CUORE what you see."),
    "home": ("home, landing, brand, logo, alfa, maserati, ferrari", "The start page: pick a brand."),
    "cars": ("switch car, choose car, pick car, all cars, vin", "The cars of one brand: pick one or add one."),
    "start": ("add service, start, begin, new car, add car, intake, help, lost", "Find the car (plug in or type the VIN), then open a service job."),
    "facts": ("specification, spec, torque, capacity", "Specifications and facts for the car."),
    "vehicles": ("car list, corpus, vin, logs per car", "The log corpus: every vehicle MES has logged."),
    "handbook": ("how to, guide, help, handbook, manual, instructions, getting started", "Step-by-step guides for using CUORE and working a job."),
    "catalog": ("part, part number, mopar, diagram, exploded view", "Look up parts and torque values by name or number."),
    "g-tsb": ("bulletin, recall, campaign, csn", "All technical service bulletins and recalls."),
    "slvt": ("slvt, software level", "Software level check."),
    "tools": ("tool, special tool", "Tools and which job needs them."),
    "live": ("live link, connection", "Whether CUORE is linked to the car."),
    "hardware": ("adapter, obd, vlinker, cable, mes, connect", "Adapter and connection status."),
    "coverage": ("coverage, supported", "What CUORE can read on which car."),
    "cables": ("cable, pinout cable, obd cable", "Cables and which one fits."),
    "g-modules": ("module, ecu", "All modules across cars."),
    "g-recordings": ("recording", "All recordings across cars."),
    "g-logs": ("log", "All logs across cars."),
    "settings": ("setting, language, option, theme", "CUORE settings."),
    "accounts": ("account, user, password, login", "Who can sign in."),
    "about": ("version, about", "Which CUORE version this is."),
    "arrive-ready": ("before the car arrives, booking, prepare, appointment", "Get the job ready before the car arrives."),
    "warranty-pack": ("claim, warranty, evidence pack", "The evidence pack for a warranty claim."),
    "bay-sheet": ("print, job sheet, clipboard, paper", "The one-page sheet that travels with the car."),
    "bay-service-sheet": ("windshield, wiper, qr, barcode, scan, card, service manager", "Print the windshield card with a scan code."),
    "field-quality": ("field quality, early warning, trend of failures", "Early warning of problems seen across cars."),
    "library": ("manual, document, service information, pdf", "Manufacturer documents and where their facts show."),
}
for _it in ITEMS:
    _w, _a = HELP.get(_it["key"], ("", ""))
    _it.setdefault("words", _w)
    _it.setdefault("answers", _a)


def register(templates: Any) -> None:
    templates.env.globals["nav_menu"] = nav_menu
