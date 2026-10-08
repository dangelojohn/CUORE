"""UI string dictionary + the ``t`` / ``lang`` Jinja globals.

CUORE's mechanics mostly don't read English as a first language (see
``cuore/web/icons.py`` for the pictogram half of the same mitigation), so
every page-chrome label collected here (headings and button text, grepped
from ``<h1>``-``<h3>`` and ``.btn`` across ``cuore/web/templates/*.html``)
gets a translation, not just English. DTC codes, part numbers and VINs are
never put in here -- those are data, not UI chrome, and stay as-is wherever
a template renders them directly.

Language model
---------------
``SUPPORTED_LANGS`` is the set actually filled in below (Italian, English
today); the dict shape -- one ``{lang: text}`` map per key -- is already
right for French/German/Spanish to be added later by just adding another
key to each entry and that language's code to ``SUPPORTED_LANGS``, with no
change to ``t()`` or the templates that call it.

``DEFAULT_LANG`` is ``"it"``: most of this shop's mechanics default to
Italian, and an unset or unrecognised ``lang`` cookie should not silently
mean English. ``t(key, lang)`` looks up the requested language first and
only falls back to English (never to Italian, and never to ``DEFAULT_LANG``
if that differs from the requested language) when that specific key has no
translation for it -- a half-translated page beats a page that 500s or
shows raw keys.

Registered as the Jinja globals ``t`` and ``lang`` on the same four
template environments ``experience_globals`` / ``icons`` register against
(see those modules' docstrings for why four). Both are context-aware
(``jinja2.pass_context``) so they read the ``lang`` cookie straight off the
current request rather than needing every route to pass it through
explicitly -- FastAPI's ``Jinja2Templates`` already puts ``request`` in
every template's context, which is what makes that possible. Importing this
module is the side effect that does the registration; wiring it in is the
same one-line ``from ..web import i18n  # noqa: F401`` move the other
``*_globals`` modules use -- left for the integration pass.

``set_lang_cookie(response, lang)`` and ``pick_language_html(current)`` are
plain, router-free helpers (no FastAPI import here) for that same
integration pass: the first sets the cookie on a response, the second
renders a 44px-tall Italiano/English chooser to drop in the header and on
first visit.
"""

from __future__ import annotations

import importlib
from html import escape
from typing import Any, Optional

try:  # pragma: no cover -- ships with Jinja2; keep the import optional anyway
    from jinja2 import pass_context
except Exception:  # noqa: BLE001 -- must not stop this module from loading
    def pass_context(f):  # type: ignore[no-redef]
        return f

try:  # pragma: no cover -- ships with Jinja2
    from markupsafe import Markup
except Exception:  # noqa: BLE001
    def Markup(s: str) -> str:  # type: ignore[no-redef]
        return s


#: Languages this module actually has translations for. Order matters only
#: for ``pick_language_html``'s button order. Extending to French/German/
#: Spanish later is: add "fr"/"de"/"es" here and fill that key in STRINGS --
#: nothing else changes.
SUPPORTED_LANGS: tuple[str, ...] = ("it", "en")

#: Most CUORE mechanics' first language -- an unset/unknown cookie means
#: this, not English.
DEFAULT_LANG = "it"

#: English is the one language every key is guaranteed to have, so it is
#: ``t()``'s fallback when the requested language's translation is missing
#: for that specific key (not when the *cookie* is merely unset -- that
#: case uses DEFAULT_LANG before t() is ever called, via lang_from_cookie).
_FALLBACK_LANG = "en"

STRINGS: dict[str, dict[str, str]] = {
    # -- the 12 flow-step headings ------------------------------------
    "start": {"en": "Start", "it": "Avvio"},
    "complaint_symptoms": {"en": "Complaint & symptoms", "it": "Disturbo e sintomi"},
    "verdict": {"en": "Verdict", "it": "Verdetto"},
    "scan_codes": {"en": "Scan & codes", "it": "Scansione e codici"},
    "understand_fault": {"en": "Understand the fault", "it": "Comprendere il guasto"},
    "tests_inspections": {"en": "Tests & inspections", "it": "Prove e controlli"},
    "hypotheses": {"en": "Hypotheses", "it": "Ipotesi"},
    "plan_repair": {"en": "Plan the repair", "it": "Pianificare la riparazione"},
    "repair": {"en": "Repair", "it": "Riparazione"},
    "verify": {"en": "Verify", "it": "Verifica"},
    "document": {"en": "Document", "it": "Documentare"},
    "release": {"en": "Release", "it": "Rilascio"},

    # -- base chrome ------------------------------------------------------
    "home": {"en": "Home", "it": "Home"},
    "menu": {"en": "Menu", "it": "Menu"},
    "toggle_theme": {"en": "Toggle dark/light theme", "it": "Cambia tema chiaro/scuro"},
    "print_page": {"en": "Print this page", "it": "Stampa questa pagina"},
    "vehicles": {"en": "Vehicles", "it": "Veicoli"},
    "modules": {"en": "Modules", "it": "Moduli"},
    "recordings": {"en": "Recordings", "it": "Registrazioni"},
    "logs": {"en": "Logs", "it": "Log"},
    "live_link": {"en": "Live link", "it": "Collegamento live"},
    "coverage": {"en": "Coverage", "it": "Copertura"},
    "tools": {"en": "Tools", "it": "Attrezzi"},

    # -- headings ----------------------------------------------------------
    "adaptation_relearn": {"en": "Adaptation relearn", "it": "Riapprendimento adattivo"},
    "adapter": {"en": "Adapter", "it": "Adattatore"},
    "add_hypothesis": {"en": "Add a hypothesis", "it": "Aggiungi un'ipotesi"},
    "add_note": {"en": "Add a note", "it": "Aggiungi una nota"},
    "add_media": {"en": "Add photos, video, sounds or documents", "it": "Aggiungi foto, video, audio o documenti"},
    "alarms_markers": {"en": "Alarms & markers", "it": "Allarmi e segnalatori"},
    "already_attempted": {"en": "Already attempted", "it": "Già tentato"},
    "blind_spots": {"en": "Blind spots", "it": "Punti ciechi"},
    "brake_tyre_spec": {"en": "Brake / tyre specification", "it": "Specifiche freni / pneumatici"},
    "brakes_wheels_tyres": {"en": "Brakes, wheels & tyres", "it": "Freni, ruote e pneumatici"},
    "bulletins": {"en": "Bulletins", "it": "Bollettini"},
    "buses": {"en": "Buses", "it": "Bus dati"},
    "by_family": {"en": "By family", "it": "Per famiglia"},
    "cable": {"en": "Cable", "it": "Cavo"},
    "calibrate": {"en": "Calibrate", "it": "Calibrare"},
    "carried_forward": {"en": "Carried forward from last time", "it": "Riportato dalla volta precedente"},
    "checks": {"en": "Checks", "it": "Controlli"},
    "choose_job": {"en": "Choose a job", "it": "Scegli un lavoro"},
    "choose_job_category": {"en": "Choose a job category", "it": "Scegli una categoria di lavoro"},
    "choose_items_visit": {"en": "Choose items for this visit", "it": "Scegli gli elementi per questa visita"},
    "co_occurrence": {"en": "Co-occurrence", "it": "Co-occorrenza"},
    "code_timeline": {"en": "Code timeline", "it": "Cronologia dei codici"},
    "codes": {"en": "Codes", "it": "Codici"},
    "codes_vs_driver": {"en": "Codes vs. what the driver notices", "it": "Codici rispetto a ciò che nota il guidatore"},
    "columns": {"en": "Columns", "it": "Colonne"},
    "considerations_next": {"en": "Considerations for next time", "it": "Considerazioni per la prossima volta"},
    "corners": {"en": "Corners", "it": "Angoli (ruote)"},
    "corpus": {"en": "Corpus", "it": "Corpus"},
    "current_picture": {"en": "Current picture", "it": "Quadro attuale"},
    "custom_sheet_dims": {"en": "Custom sheet dimensions (mm)", "it": "Dimensioni foglio personalizzate (mm)"},
    "dtc_report": {"en": "DTC report", "it": "Rapporto DTC"},
    "dtcs_0x1902": {"en": "DTCs (0x19 02)", "it": "DTC (0x19 02)"},
    "dtcs_by_module": {"en": "DTCs by module", "it": "DTC per modulo"},
    "dashboard": {"en": "Dashboard", "it": "Cruscotto"},
    "dealer_results": {"en": "Dealer (wiTECH) results", "it": "Risultati concessionaria (wiTECH)"},
    "dependency_graph": {"en": "Dependency graph", "it": "Grafo delle dipendenze"},
    "discoveries": {"en": "Discoveries", "it": "Scoperte"},
    "discoveries_considerations": {"en": "Discoveries & considerations", "it": "Scoperte e considerazioni"},
    "drain_condition": {"en": "Drain & condition", "it": "Scarico e condizione"},
    "drive_cycle_counters": {"en": "Drive-cycle counters", "it": "Contatori ciclo di guida"},
    "due_status": {"en": "Due status", "it": "Stato scadenza"},
    "epb_rear": {"en": "Electric parking brake (rear)", "it": "Freno di stazionamento elettrico (posteriore)"},
    "electrical": {"en": "Electrical", "it": "Impianto elettrico"},
    "electrical_path": {"en": "Electrical path", "it": "Percorso elettrico"},
    "elements": {"en": "Elements", "it": "Elementi"},
    "every_code": {"en": "Every code this car has set", "it": "Ogni codice impostato da questa vettura"},
    "every_occurrence": {"en": "Every occurrence", "it": "Ogni occorrenza"},
    "everything_corpus": {"en": "Everything in the corpus", "it": "Tutto il corpus"},
    "evidence_gate": {"en": "Evidence gate", "it": "Soglia delle prove"},
    "excursions": {"en": "Excursions", "it": "Escursioni"},
    "fault_tree": {"en": "Fault tree", "it": "Albero dei guasti"},
    "filter": {"en": "Filter", "it": "Filtro"},
    "flash_check": {"en": "Flash check", "it": "Controllo flash"},
    "fluid": {"en": "Fluid", "it": "Fluido"},
    "fluid_condition": {"en": "Fluid condition", "it": "Condizione del fluido"},
    "freeze_frames": {"en": "Freeze frames", "it": "Fotogrammi congelati"},
    "front_differential": {"en": "Front differential", "it": "Differenziale anteriore"},
    "gauges": {"en": "Gauges", "it": "Strumenti"},
    "general_service": {"en": "General service", "it": "Tagliando generale"},
    "history": {"en": "History", "it": "Storico"},
    "identity_annex_c": {"en": "Identity (Annex C)", "it": "Identità (Allegato C)"},
    "inbox": {"en": "Inbox", "it": "Posta in arrivo"},
    "inspection_tag_fields": {"en": "Inspection tag fields", "it": "Campi etichetta ispezione"},
    "job": {"en": "Job", "it": "Lavoro"},
    "job_tag_fields": {"en": "Job tag fields", "it": "Campi etichetta lavoro"},
    "keyboard": {"en": "Keyboard", "it": "Tastiera"},
    "kind_template": {"en": "Kind & template", "it": "Tipo e modello"},
    "known_issues": {"en": "Known issues", "it": "Problemi noti"},
    "labels_printed": {"en": "Labels printed", "it": "Etichette stampate"},
    "last_90_days": {"en": "Last 90 days", "it": "Ultimi 90 giorni"},
    "last_maintenance_visit": {"en": "Last maintenance visit", "it": "Ultimo intervento di manutenzione"},
    "last_oil_change": {"en": "Last oil change", "it": "Ultimo cambio olio"},
    "latest_all_systems_scan": {"en": "Latest all-systems scan", "it": "Ultima scansione di tutti i sistemi"},
    "latest_session": {"en": "Latest session", "it": "Ultima sessione"},
    "legislated_obd": {"en": "Legislated OBD (CAN-C)", "it": "OBD legale (CAN-C)"},
    "live": {"en": "Live", "it": "Live"},
    "live_status": {"en": "Live status", "it": "Stato live"},
    "live_vs_log": {"en": "Live vs log", "it": "Live rispetto al log"},
    "log_symptom": {"en": "Log a symptom", "it": "Registra un sintomo"},
    "log_index": {"en": "Log index", "it": "Indice dei log"},
    "mes_and_lock": {"en": "MES and lock", "it": "MES e blocco"},
    "maintenance_reminder_fields": {"en": "Maintenance reminder fields", "it": "Campi promemoria manutenzione"},

    # -- buttons -------------------------------------------------------
    "back_to_dossier": {"en": "Back to dossier", "it": "Torna al dossier"},
    "add_to_ledger": {"en": "Add to ledger", "it": "Aggiungi al registro"},
    "all": {"en": "All", "it": "Tutti"},
    "all_domains": {"en": "All domains", "it": "Tutti i domini"},
    "answer": {"en": "Answer", "it": "Rispondi"},
    "assess": {"en": "Assess", "it": "Valuta"},
    "back_to_tree": {"en": "Back to the tree", "it": "Torna all'albero"},
    "clear": {"en": "Clear", "it": "Pulisci"},
    "clear_filter": {"en": "Clear filter", "it": "Rimuovi filtro"},
    "close": {"en": "Close", "it": "Chiudi"},
    "close_case": {"en": "Close case", "it": "Chiudi il caso"},
    "connect": {"en": "Connect", "it": "Connetti"},
    "custom_channels": {"en": "Custom channels", "it": "Canali personalizzati"},
    "declare_cable": {"en": "Declare cable", "it": "Dichiara cavo"},
    "discard_session": {"en": "Discard this session", "it": "Scarta questa sessione"},
    "dismiss": {"en": "Dismiss", "it": "Ignora"},
    "download_pdf": {"en": "Download PDF", "it": "Scarica PDF"},
    "edit_layout": {"en": "Edit layout", "it": "Modifica layout"},
    "exclude_simulation": {"en": "Exclude simulation", "it": "Escludi simulazione"},
    "export": {"en": "Export", "it": "Esporta"},
    "find_excursions": {"en": "Find excursions", "it": "Trova escursioni"},
    "go_to_release": {"en": "Go to release", "it": "Vai al rilascio"},
    "hud": {"en": "HUD", "it": "HUD"},
    "hide": {"en": "Hide", "it": "Nascondi"},
    "i_dont": {"en": "I don't", "it": "Io no"},
    "i_have_this": {"en": "I have this", "it": "Io sì"},
    "import_": {"en": "Import", "it": "Importa"},
    "include_simulation": {"en": "Include simulation", "it": "Includi simulazione"},
    "load_checklist": {"en": "Load checklist", "it": "Carica lista di controllo"},
    "load_fields_checked": {"en": "Load fields for checked items", "it": "Carica campi per gli elementi selezionati"},
    "load_job": {"en": "Load job", "it": "Carica lavoro"},
    "mark": {"en": "Mark", "it": "Segna"},
    "mark_applied": {"en": "Mark applied", "it": "Segna come applicato"},
    "open_original": {"en": "Open original", "it": "Apri originale"},
    "pause_all": {"en": "Pause all", "it": "Pausa generale"},
    "print_test_grid": {"en": "Print test grid (plain paper)", "it": "Stampa griglia di prova (carta semplice)"},
    "probe_adapter": {"en": "Probe adapter", "it": "Adattatore sonda"},
    "read_dtcs": {"en": "Read DTCs", "it": "Leggi DTC"},
    "read_readiness": {"en": "Read readiness", "it": "Leggi readiness"},
    "read_with_confirmation": {"en": "Read with confirmation", "it": "Leggi con conferma"},
    "readiness": {"en": "Readiness", "it": "Readiness"},
    "record": {"en": "Record", "it": "Registra"},
    "record_dtc_report": {"en": "Record DTC report", "it": "Registra rapporto DTC"},
    "record_slvt": {"en": "Record SLVT", "it": "Registra SLVT"},
    "record_action": {"en": "Record action", "it": "Registra azione"},
    "record_brakes_wheels_tyres": {"en": "Record brakes/wheels/tyres service", "it": "Registra intervento freni/ruote/pneumatici"},
    "record_flash_check": {"en": "Record flash check", "it": "Registra controllo flash"},
    "record_inspection": {"en": "Record inspection", "it": "Registra ispezione"},
    "record_maintenance_visit": {"en": "Record maintenance visit", "it": "Registra intervento di manutenzione"},
    "record_oil_change": {"en": "Record oil change", "it": "Registra cambio olio"},
    "record_recall_status": {"en": "Record recall status", "it": "Registra stato richiamo"},
    "record_routine": {"en": "Record routine", "it": "Registra routine"},
    "record_service": {"en": "Record service", "it": "Registra intervento"},
    "registry_entry": {"en": "Registry entry", "it": "Voce di registro"},
    "release_car": {"en": "Release car", "it": "Rilascia la vettura"},
    "reopen": {"en": "Reopen", "it": "Riapri"},
    "route": {"en": "Route", "it": "Instrada"},
    "run_this_pass": {"en": "Run this pass", "it": "Esegui questo passaggio"},
    "save": {"en": "Save", "it": "Salva"},
    "save_as": {"en": "Save as", "it": "Salva come"},
    "save_calibration": {"en": "Save calibration", "it": "Salva calibrazione"},
    "save_inspection": {"en": "Save inspection", "it": "Salva ispezione"},
    "save_symptom_report": {"en": "Save symptom report", "it": "Salva segnalazione sintomo"},
    "save_tools_review": {"en": "Save tools review", "it": "Salva revisione attrezzi"},
    "search": {"en": "Search", "it": "Cerca"},
    "send": {"en": "Send", "it": "Invia"},
    "skip": {"en": "Skip", "it": "Salta"},
    "snapshot": {"en": "Snapshot", "it": "Istantanea"},
    "start_coverage_session": {"en": "Start coverage session", "it": "Avvia sessione di copertura"},
    "stop": {"en": "Stop", "it": "Stop"},
    "take_car_in": {"en": "Take this car in", "it": "Accetta la vettura"},
    "take_to_gate": {"en": "Take it to the gate", "it": "Portalo alla soglia delle prove"},
    "triggers": {"en": "Triggers", "it": "Trigger"},
    "update_preview": {"en": "Update preview", "it": "Aggiorna anteprima"},
    "upload": {"en": "Upload", "it": "Carica"},
    "vin": {"en": "VIN", "it": "VIN"},
    "verify_passive_listen": {"en": "Verify (passive listen)", "it": "Verifica (ascolto passivo)"},
    "voltage": {"en": "Voltage", "it": "Tensione"},
    "parts": {"en": "Parts", "it": "Ricambi"},

    # -- common automotive/diagnostic terms (kept here since they recur
    #    across many of the headings/buttons above and are easy to get
    #    wrong in Italian if translated ad hoc per page) ------------------
    "fault": {"en": "Fault", "it": "Guasto"},
    "fault_code": {"en": "Fault code", "it": "Codice errore"},
    "symptoms": {"en": "Symptoms", "it": "Sintomi"},
    "smoke_test": {"en": "Smoke test", "it": "Prova fumo"},
    "purge_valve": {"en": "Purge valve", "it": "Valvola di spurgo"},
    "ecm": {"en": "Engine control module", "it": "Centralina motore"},
    "wiring_harness": {"en": "Wiring harness", "it": "Impianto elettrico"},

    # -- language chooser (used by pick_language_html below) -------------
    "language": {"en": "Language", "it": "Lingua"},
}


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """Translate ``key`` into ``lang``, falling back to English, then to
    the bare key if ``key`` isn't in STRINGS at all (never raises -- a
    missing translation must degrade, not break the page)."""
    entry = STRINGS.get(key)
    if not entry:
        return key
    use_lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    val = entry.get(use_lang)
    if val:
        return val
    return entry.get(_FALLBACK_LANG, key)


def lang_from_cookie(cookie_value: Optional[str]) -> str:
    """Normalise a raw ``lang`` cookie value to a supported language,
    defaulting to :data:`DEFAULT_LANG` ("it") for anything missing or
    unrecognised."""
    v = (cookie_value or "").strip().lower()
    return v if v in SUPPORTED_LANGS else DEFAULT_LANG


def set_lang_cookie(response: Any, lang: str) -> Any:
    """Router-free helper for the integration pass: set the ``lang``
    cookie on a (FastAPI/Starlette-shaped) ``response``. Degrades to a
    no-op rather than raising if ``response`` doesn't support
    ``set_cookie`` -- callers should still get their response object back
    either way."""
    use_lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    try:
        response.set_cookie("lang", use_lang, max_age=60 * 60 * 24 * 365,
                             samesite="lax")
    except Exception:  # noqa: BLE001 -- must never break the response
        pass
    return response


def pick_language_html(current: str) -> Any:
    """A tiny, dependency-free Italiano/English chooser: two 44px-tall
    buttons (comfortable touch targets for a shop floor), the current
    language marked with ``aria-pressed``/a ``lang-btn-active`` class. The
    integration pass drops this in the header and on first visit, and
    wires its buttons' ``data-lang`` to a small script that POSTs/redirects
    to whatever route calls :func:`set_lang_cookie`.
    """
    cur = current if current in SUPPORTED_LANGS else DEFAULT_LANG
    buttons = (("it", "Italiano"), ("en", "English"))

    def _btn(code: str, label: str) -> str:
        active = cur == code
        cls = "lang-btn lang-btn-active" if active else "lang-btn"
        return (
            f'<button type="button" class="{cls}" data-lang="{code}" '
            f'aria-pressed="{"true" if active else "false"}" '
            f'style="height:44px;min-width:44px;">{escape(label)}</button>'
        )

    html = (
        '<span class="lang-picker" role="group" aria-label="Italiano / English">'
        + "".join(_btn(code, label) for code, label in buttons)
        + "</span>"
    )
    return Markup(html)


@pass_context
def _t_global(ctx: Any, key: str, lang: Optional[str] = None) -> str:
    if lang is None:
        lang = _ctx_lang(ctx)
    return t(key, lang)


@pass_context
def _lang_global(ctx: Any) -> str:
    return _ctx_lang(ctx)


def _ctx_lang(ctx: Any) -> str:
    try:
        request = ctx.get("request")
        cookie = request.cookies.get("lang") if request is not None else None
    except Exception:  # noqa: BLE001 -- template globals must never raise
        cookie = None
    return lang_from_cookie(cookie)


def _register(templates: Any) -> None:
    templates.env.globals["t"] = _t_global
    templates.env.globals["lang"] = _lang_global


for _module_name in ("routes", "service_routes", "drivetrain_routes", "timeline_routes"):
    try:
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None:
            _register(_tmpl)
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


__all__ = [
    "SUPPORTED_LANGS", "DEFAULT_LANG", "STRINGS",
    "t", "lang_from_cookie", "set_lang_cookie", "pick_language_html",
]
