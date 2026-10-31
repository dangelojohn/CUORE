"""ONE data source for CUORE navigation: the header's full-screen Menu sheet.

Every page a mechanic can reach is one line in ``ITEMS``.  ``_navsheet.html``
(the Menu sheet, in base.html) reads ``nav_menu(...)`` -- add a page here and
it appears there.  The Menu is the only navigation (no tab strip); with a car
open every page is Menu + one tap.

Item fields
  key     stable id; per-vehicle items use the page's own ``tab`` value so the
          current page can be highlighted
  label   English fallback label;  i18n: optional ``t()`` key for translation
  href    path pattern; ``{vin}`` marks a per-vehicle page (only shown when a
          vehicle is active).  ``href_novin`` is an optional global fallback
  group   Cars / Diagnose / Look up / Service / Records / Shop (read by task: pick the
          car, work the fault, look something up, service it, write it up, shop-wide)
  icon    one icon word (CSS class hook ``ni-<word>``; no glyph required)
  roles   optional tuple; item shown only to those roles (None = everyone)
  primary True = an everyday page: its tile is drawn stronger in the Menu
"""

from __future__ import annotations

from typing import Any, Optional

GROUPS = ("Cars", "Diagnose", "Look up", "Service", "Records", "Shop")


def _i(key, label, href, group, icon, *, i18n=None, roles=None, primary=False, href_novin=None):
    return {"key": key, "label": label, "href": href, "group": group, "icon": icon,
            "i18n": i18n, "roles": roles, "primary": primary, "href_novin": href_novin}


V = "/v/{vin}"
ITEMS: list[dict[str, Any]] = [
    # ---- Cars (always shown: the landing page is the car picker)
    _i("home", "Change brand", "/", "Cars", "vehicles"),
    _i("cars", "Change car", "/cars", "Cars", "vehicles"),
    _i("start", "Add Service", "/add", "Cars", "start"),
    # ---- Diagnose
    _i("bench", "Bench", V, "Diagnose", "bench", i18n="bench", primary=True),
    _i("job", "Job", V + "/job", "Diagnose", "job", i18n="job", primary=True),
    _i("codes", "Codes", V + "/codes", "Diagnose", "codes", i18n="codes", primary=True),
    _i("liveboard", "Live", V + "/liveboard", "Diagnose", "live", i18n="live_board", primary=True),
    _i("tests", "Tests", V + "/tests", "Diagnose", "tests", i18n="tests", primary=True),
    _i("diagnosis", "Diagnosis", V + "/diagnosis", "Diagnose", "diagnosis", i18n="diagnosis"),
    _i("tree", "Fault tree", V + "/tree", "Diagnose", "tree", i18n="fault_tree"),
    _i("gate", "Evidence gate", V + "/gate", "Diagnose", "gate", i18n="evidence_gate"),
    _i("crosschecks", "Cross-checks", V + "/crosschecks", "Diagnose", "check", i18n="crosschecks"),
    _i("intermittent", "Intermittent", V + "/intermittent", "Diagnose", "intermittent", i18n="intermittent"),
    _i("trends", "Trends", V + "/trends", "Diagnose", "trends", i18n="trends"),
    _i("power-budget", "Power and ground", V + "/power-budget", "Diagnose", "power", i18n="power_budget"),
    # ---- Car
    _i("systems", "Systems", V + "/systems", "Look up", "systems", i18n="systems", primary=True),
    _i("sensors", "Sensors", V + "/sensors", "Look up", "sensors", primary=True),
    _i("fuses", "Fuses", V + "/fuses", "Look up", "fuses", primary=True),
    _i("electrical", "Electrical", V + "/electrical", "Look up", "electrical", i18n="electrical"),
    _i("harnesses", "Harnesses", V + "/harnesses", "Look up", "harness"),
    _i("modules", "Modules", V + "/modules", "Look up", "modules", i18n="modules"),
    _i("gauges", "Gauges", V + "/gauges", "Look up", "gauges", i18n="gauges"),
    _i("configuration", "Configuration", V + "/configuration", "Look up", "config"),
    # ---- Service
    _i("service-hub", "Service", V + "/service-hub", "Service", "service", i18n="service"),
    _i("adjustments", "Adjustments", V + "/adjustments", "Service", "adjust"),
    _i("witech-recording", "wiTECH recording", V + "/witech-recording", "Service", "witech"),
    _i("parity", "Parity", V + "/parity", "Service", "parity"),
    _i("parts", "Parts", V + "/parts", "Service", "parts", i18n="parts"),
    _i("mods", "Modifications", V + "/mods", "Service", "mods", i18n="mods"),
    _i("procedures", "Prototype procedures", V + "/procedures/prototype", "Service", "procedure"),
    _i("tsb", "TSB for this car", "/tsb?vin={vin}", "Look up", "tsb"),
    # ---- Records
    _i("report", "Report", V + "/report", "Records", "report", i18n="report", primary=True),
    _i("dossier", "Dossier", V + "/dossier", "Records", "dossier", i18n="dossier"),
    _i("timeline", "Timeline", V + "/timeline", "Records", "timeline", i18n="timeline"),
    _i("recordings", "Recordings", V + "/recordings", "Records", "recordings"),
    _i("scans", "Scans", V + "/scans", "Records", "scans", i18n="scans"),
    _i("scan", "Full scan", V + "/scan", "Records", "scan", i18n="full_scan"),
    _i("media", "Media", V + "/media", "Records", "media", i18n="media"),
    _i("labels", "Labels", V + "/labels", "Records", "labels", i18n="labels"),
    _i("inbox", "Inbox", V + "/inbox", "Records", "inbox", i18n="inbox"),
    _i("dashboard", "Dashboard", V + "/dashboard", "Records", "dashboard", i18n="dashboard"),
    _i("logs", "Logs for this car", "/logs?vin={vin}", "Records", "logs", i18n="logs"),
    _i("mobile", "Phone view / Tell CUORE", "/m/{vin}", "Records", "phone", i18n="mobile"),
    # ---- Shop (no vehicle needed)
    _i("facts", "Facts", "/v/{vin}/facts", "Look up", "facts", href_novin="/facts"),
    _i("vehicles", "Vehicles", "/vehicles", "Shop", "vehicles"),
    _i("catalog", "Parts catalogue", "/catalog", "Look up", "catalog"),
    _i("g-tsb", "TSB", "/tsb", "Shop", "tsb"),
    _i("slvt", "SLVT", "/slvt", "Shop", "slvt"),
    _i("tools", "Tools", "/tools", "Shop", "tools"),
    _i("live", "Live link", "/live", "Shop", "link"),
    _i("hardware", "Adapter", "/hardware", "Shop", "adapter"),
    _i("coverage", "Coverage", "/coverage", "Shop", "coverage"),
    _i("cables", "Cables", "/cables", "Shop", "cables"),
    _i("g-modules", "All modules", "/modules", "Shop", "modules"),
    _i("g-recordings", "All recordings", "/recordings", "Shop", "recordings"),
    _i("g-logs", "All logs", "/logs", "Shop", "logs"),
    _i("settings", "Settings", "/settings", "Shop", "settings"),
    _i("accounts", "Accounts", "/accounts", "Shop", "accounts", roles=("admin", "shop_lead")),
    _i("about", "About", "/about", "Shop", "about"),
    # ---- Added 2026-10-30: arrive-ready job, warranty evidence pack, field-quality early warning.
    _i("arrive-ready", "Arrive-ready", V + "/arrive-ready", "Diagnose", "arrive"),
    _i("warranty-pack", "Warranty pack", V + "/warranty-pack", "Records", "warranty"),
    _i("car-session", "Car session", V + "/car-session", "Service", "parity"),
    _i("bay-sheet", "Bay sheet", V + "/bay-sheet", "Records", "sheet"),
    _i("field-quality", "Field quality", "/field-quality", "Shop", "quality"),
    _i("library", "Library", "/library", "Look up", "library"),
    _i("handbook", "How-to guides", "/handbook", "Look up", "handbook"),
]


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
    "parity": ("parity, compare tools", "How CUORE results compare with other tools."),
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
    "field-quality": ("field quality, early warning, trend of failures", "Early warning of problems seen across cars."),
    "library": ("manual, document, service information, pdf", "Manufacturer documents and where their facts show."),
}
for _it in ITEMS:
    _w, _a = HELP.get(_it["key"], ("", ""))
    _it.setdefault("words", _w)
    _it.setdefault("answers", _a)


def resolve_href(item: dict[str, Any], vin: Optional[str]) -> Optional[str]:
    """Concrete href for ``item``, or None when it needs a vehicle and none is active."""
    href = item["href"]
    if "{vin}" not in href:
        return href
    if vin:
        return href.replace("{vin}", vin)
    return item.get("href_novin")


def nav_menu(vin: Optional[str] = None, tab: str = "", role: Optional[str] = None,
             path: str = "") -> dict[str, Any]:
    """Grouped, role-filtered, href-resolved menu for the current page."""
    tab = tab or ""
    cur = (path or "").split("?")[0]
    groups: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
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
        row = dict(it, href=href, on=on, per_car=per_car)
        groups[it["group"]].append(row)
    return {"groups": [{"title": g, "items": groups[g]} for g in GROUPS if groups[g]]}


def register(templates: Any) -> None:
    templates.env.globals["nav_menu"] = nav_menu
