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

#: The Italian language chooser has been removed from the UI (it did not
#: work); the app now always renders English regardless of any ``lang``
#: cookie. ``DEFAULT_LANG`` stays "en" rather than being deleted so the
#: rest of this module (and the still-present Italian strings below, kept
#: but unused) needs no further rewiring if a working chooser comes back.
DEFAULT_LANG = "en"

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
    "full_dossier": {"en": "Full dossier", "it": "Dossier completo"},
    "mark_done": {"en": "Mark done", "it": "Segna fatto"},
    "nothing_open": {"en": "Nothing open on the checklist.",
                     "it": "Nessun elemento aperto nella lista di controllo."},
    "have_it": {"en": "have", "it": "disponibile"},
    "need_it": {"en": "need", "it": "da procurare"},

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

    # -- mechanic-review pass: status strip, tabs, job/intake/release,
    #    symptom form (see job.html, _flow_bar.html, _vtabs.html,
    #    _vbar.html, intake.html, release.html, _symptom_form.html) -------
    "bench": {"en": "Bench", "it": "Banco"},
    "dossier": {"en": "Dossier", "it": "Dossier"},
    "systems": {"en": "Systems", "it": "Sistemi"},
    "report": {"en": "Report", "it": "Rapporto"},
    "timeline": {"en": "Timeline", "it": "Cronologia"},
    "media": {"en": "Media", "it": "Media"},
    "service": {"en": "Service", "it": "Assistenza"},
    "labels": {"en": "Labels", "it": "Etichette"},
    "more": {"en": "More", "it": "Altro"},
    "more_vehicle_tabs": {"en": "More vehicle tabs", "it": "Altre schede veicolo"},
    "more_vehicle_details": {"en": "More vehicle details", "it": "Altri dettagli veicolo"},
    "full_vin": {"en": "Full VIN", "it": "VIN completo"},
    "km_span": {"en": "km span", "it": "intervallo km"},
    "open_codes": {"en": "Open codes", "it": "Codici attivi"},
    "odometer_km": {"en": "Odometer km", "it": "Contachilometri km"},
    "fuel_at_code_set": {"en": "Fuel at code set", "it": "Carburante all'attivazione del codice"},
    "out_of_window": {"en": "out of window", "it": "fuori finestra"},
    "in_window": {"en": "in window", "it": "in finestra"},
    "next_label": {"en": "Next", "it": "Prossimo"},
    "not_yet": {"en": "Not yet", "it": "Non ancora"},
    "blocked_label": {"en": "blocker(s)", "it": "blocco/i"},

    "steps_label": {"en": "Steps", "it": "Passaggi"},
    "step_word": {"en": "Step", "it": "Passo"},
    "of_word": {"en": "of", "it": "di"},
    "show_all_steps": {"en": "Show all steps", "it": "Mostra tutti i passaggi"},
    "job_complete": {"en": "Job complete.", "it": "Lavoro completato."},
    "suggested_next": {"en": "Suggested next", "it": "Prossimo suggerito"},
    "ready_for_next_car": {"en": "Ready for the next car.", "it": "Pronta per la prossima vettura."},
    "tools_away_start_next": {"en": "Tools away. Start the next Stelvio",
                               "it": "Attrezzi riposti. Avvia la prossima Stelvio"},

    "job_lede": {"en": "The single workspace for this visit: the mechanic's flow, start to "
                        "release, one step per screen. Every section below is the same "
                        "partial used elsewhere in CUORE -- nothing here is a second copy of "
                        "the truth.",
                 "it": "Lo spazio di lavoro unico per questa visita: il percorso del "
                       "meccanico, dall'avvio al rilascio, un passaggio per schermata. Ogni "
                       "sezione qui sotto è lo stesso componente usato altrove in CUORE -- "
                       "qui non c'è una seconda copia della verità."},
    "no_complaint_recorded": {"en": "(no complaint recorded)", "it": "(nessun disturbo registrato)"},
    "opened_label": {"en": "Opened", "it": "Aperto"},
    "by_label": {"en": "by", "it": "da"},
    "closed_label": {"en": "closed", "it": "chiuso"},
    "no_visit_open": {"en": "No visit open for this car yet.", "it": "Nessuna visita aperta per questa vettura."},
    "start_intake": {"en": "Start intake", "it": "Avvia accettazione"},
    "no_symptom_reports": {"en": "No driver symptom reports yet.",
                            "it": "Nessuna segnalazione sintomo del guidatore."},
    "symptom_reported": {"en": "symptom reported", "it": "sintomo segnalato"},
    "codes_on_file": {"en": "Codes on file", "it": "Codici archiviati"},
    "read_car_now": {"en": "Read the car now", "it": "Leggi la vettura ora"},
    "codes_explained": {"en": "Open codes, explained", "it": "Codici attivi, spiegati"},
    "no_active_codes": {"en": "No active codes to explain right now.",
                         "it": "Nessun codice attivo da spiegare al momento."},
    "open_work_attachments": {"en": "Open work & attachments", "it": "Lavori aperti e allegati"},
    "evidence_for": {"en": "Evidence for:", "it": "Prove a favore:"},
    "evidence_against": {"en": "Evidence against:", "it": "Prove contrarie:"},
    "none_yet": {"en": "none yet", "it": "ancora nessuna"},
    "next_test_colon": {"en": "Next test:", "it": "Prossima prova:"},
    "no_hypotheses_yet": {"en": "No hypotheses on this case yet.", "it": "Ancora nessuna ipotesi su questo caso."},
    "suggested_from_tree": {"en": "Suggested — from this car's own fault tree & bulletins",
                             "it": "Suggerite — dall'albero dei guasti e dai bollettini di questa vettura"},
    "suggested_label": {"en": "suggested", "it": "suggerita"},
    "hypothesis_label": {"en": "Hypothesis", "it": "Ipotesi"},
    "system_label": {"en": "System", "it": "Sistema"},
    "system_placeholder": {"en": "e.g. EVAP", "it": "es. EVAP"},
    "next_test_label": {"en": "Next test", "it": "Prossima prova"},
    "last_stelvio_codes": {"en": "Last Stelvio with these codes", "it": "Ultima Stelvio con questi codici"},
    "path_label": {"en": "Path", "it": "Percorso"},
    "tools_label": {"en": "Tools:", "it": "Attrezzi:"},
    "pitfalls": {"en": "Pitfalls", "it": "Insidie"},
    "status_open": {"en": "open", "it": "aperta"},
    "status_supported": {"en": "supported", "it": "supportata"},
    "status_refuted": {"en": "refuted", "it": "respinta"},
    "status_confirmed": {"en": "confirmed", "it": "confermata"},
    "kind_test": {"en": "test", "it": "prova"},
    "kind_inspection": {"en": "inspection", "it": "ispezione"},
    "kind_repair": {"en": "repair", "it": "riparazione"},
    "kind_part": {"en": "part", "it": "ricambio"},
    "kind_clear": {"en": "clear", "it": "azzera"},
    "kind_note": {"en": "note", "it": "nota"},
    "what_was_done": {"en": "what was done", "it": "cosa è stato fatto"},
    "record_an_action": {"en": "Record an action", "it": "Registra un'azione"},
    "no_actions_recorded": {"en": "No actions recorded yet.", "it": "Nessuna azione registrata ancora."},
    "readiness_read_at": {"en": "Readiness read at:", "it": "Readiness letta il:"},
    "not_yet_read": {"en": "not yet read", "it": "non ancora letta"},
    "codes_returned_colon": {"en": "Codes returned:", "it": "Codici ritornati:"},
    "none_word": {"en": "none", "it": "nessuno"},
    "handover_report_pdf": {"en": "Handover report (PDF)", "it": "Rapporto di consegna (PDF)"},
    "open_count_suffix": {"en": "open", "it": "aperti"},
    "not_closed": {"en": "Not closed", "it": "Non chiuso"},
    "saved": {"en": "saved", "it": "salvato"},
    "required_before_closing": {"en": "required before closing", "it": "richiesto prima della chiusura"},
    "tools_review_hint": {"en": "Tick what you actually used, mark it right/wrong/unsure with a "
                                 "reason, note anything missing, and what you'd buy next time. "
                                 "This is what the next identical job on this car -- or any "
                                 "Stelvio -- sees first.",
                           "it": "Seleziona ciò che hai davvero usato, segna giusto/sbagliato/incerto "
                                 "con un motivo, annota cosa manca e cosa compreresti la prossima "
                                 "volta. Questo è ciò che il prossimo lavoro identico su questa "
                                 "vettura -- o su qualsiasi Stelvio -- vede per primo."},
    "other_tools_used": {"en": "Other tools used (not in the list above)",
                          "it": "Altri attrezzi utilizzati (non nell'elenco sopra)"},
    "tool_name_placeholder": {"en": "tool name", "it": "nome attrezzo"},
    "note_why_placeholder": {"en": "note (why right/wrong)", "it": "nota (perché giusto/sbagliato)"},
    "yes_word": {"en": "yes", "it": "sì"},
    "no_word": {"en": "no", "it": "no"},
    "unsure_word": {"en": "unsure", "it": "incerto"},
    "missing_tools": {"en": "Missing tools (comma separated)", "it": "Attrezzi mancanti (separati da virgola)"},
    "would_buy_next_time": {"en": "Would buy next time", "it": "Da acquistare la prossima volta"},
    "tool_to_buy_placeholder": {"en": "tool to buy", "it": "attrezzo da acquistare"},
    "why_placeholder": {"en": "why", "it": "perché"},
    "minutes_spent": {"en": "Minutes spent", "it": "Minuti impiegati"},
    "by_initials_label": {"en": "By", "it": "Da"},
    "name_initials_placeholder": {"en": "name/initials", "it": "nome/iniziali"},
    "outcome_label": {"en": "Outcome", "it": "Esito"},
    "choose_placeholder": {"en": "(choose)", "it": "(scegli)"},
    "outcome_fixed": {"en": "fixed", "it": "risolto"},
    "outcome_not_fixed": {"en": "not_fixed", "it": "non risolto"},
    "outcome_deferred": {"en": "deferred", "it": "rinviato"},
    "codes_returned_field": {"en": "Codes returned (comma separated, if any)",
                              "it": "Codici ritornati (separati da virgola, se presenti)"},
    "verdict_closing_note": {"en": "Verdict / closing note", "it": "Verdetto / nota di chiusura"},
    "skip_tools_review_reason": {"en": "Skip tools review -- reason (required if not saved above)",
                                  "it": "Salta la revisione attrezzi -- motivo (richiesto se non salvata sopra)"},

    "start_this_stelvio": {"en": "Start this Stelvio", "it": "Avvia questa Stelvio"},
    "not_started": {"en": "Not started", "it": "Non avviata"},
    "intake_lede": {"en": "One car, start to finish. Pick a VIN already in the corpus, or "
                           "type a new one, and this opens the visit and its case together "
                           "-- then drops straight into the job page to start the diagnostic "
                           "work.",
                     "it": "Una vettura, dall'inizio alla fine. Scegli un VIN già nel corpus, "
                           "o digitane uno nuovo, e questo apre la visita e il caso insieme "
                           "-- per poi passare direttamente alla pagina del lavoro e iniziare "
                           "la diagnosi."},
    "vin_placeholder": {"en": "17-character VIN", "it": "VIN a 17 caratteri"},
    "complaint_label": {"en": "Complaint — the driver's own words", "it": "Disturbo — nelle parole del guidatore"},
    "technician_label": {"en": "Technician", "it": "Tecnico"},

    "release_lede": {"en": "Advisory, not a gate — each item below with its evidence. "
                            "Release with one tap whenever the car is ready; if "
                            "verification isn't in yet, say why and it's recorded as "
                            "released unverified.",
                      "it": "Consultivo, non un blocco — ogni voce qui sotto con la sua "
                            "prova. Rilascia con un tocco quando la vettura è pronta; se la "
                            "verifica non è ancora arrivata, indica il motivo e verrà "
                            "registrata come rilasciata non verificata."},
    "visit_label": {"en": "Visit", "it": "Visita"},
    "in_label": {"en": "In", "it": "Entrata"},
    "bay_label": {"en": "bay", "it": "baia"},
    "out_label": {"en": "out", "it": "uscita"},
    "verification": {"en": "Verification", "it": "Verifica"},
    "no_data_chip": {"en": "no data", "it": "nessun dato"},
    "no_dossier_verdict": {"en": "No dossier verdict available for this vehicle yet.",
                            "it": "Nessun verdetto dossier disponibile per questa vettura."},
    "not_verified_note": {"en": "Not verified — releasing now records this car as released unverified.",
                           "it": "Non verificata — il rilascio ora registra questa vettura come rilasciata non verificata."},
    "not_released": {"en": "Not released", "it": "Non rilasciata"},
    "report_printed": {"en": "Report printed", "it": "Rapporto stampato"},
    "print_labels_link": {"en": "Print labels", "it": "Stampa etichette"},
    "parts_logged": {"en": "Parts logged", "it": "Ricambi registrati"},
    "tools_reviewed": {"en": "Tools reviewed", "it": "Attrezzi revisionati"},
    "not_reviewed": {"en": "not reviewed", "it": "non revisionato"},
    "released_unverified": {"en": "Released unverified", "it": "Rilasciata non verificata"},
    "reason_colon": {"en": "Reason:", "it": "Motivo:"},
    "released_on": {"en": "Released", "it": "Rilasciata il"},
    "notes_label": {"en": "Notes", "it": "Note"},
    "reason_release_early": {"en": "Reason (if releasing before verification)",
                              "it": "Motivo (se rilasciata prima della verifica)"},
    "why_release_now_placeholder": {"en": "why release now", "it": "perché rilasciare ora"},
    "tools_away_h3": {"en": "Tools away", "it": "Attrezzi riposti"},
    "tools_away_advisory": {"en": "Advisory only — recording this never blocks moving on to the next car.",
                             "it": "Solo informativo — registrarlo non blocca mai il passaggio alla vettura successiva."},
    "no_tool_review": {"en": "No tool-usage review on file for this car yet.",
                        "it": "Nessuna revisione d'uso attrezzi registrata per questa vettura."},
    "put_away_suffix": {"en": "— put away", "it": "— riposto"},
    "location_placeholder": {"en": "location (optional)", "it": "posizione (opzionale)"},
    "available_opt": {"en": "available", "it": "disponibile"},
    "damaged_opt": {"en": "damaged", "it": "danneggiato"},
    "missing_opt": {"en": "missing", "it": "mancante"},
    "empty_opt": {"en": "empty", "it": "vuoto"},
    "loaned_opt": {"en": "loaned", "it": "prestato"},
    "restock_label": {"en": "Restock (consumables used up)", "it": "Riapprovvigionamento (consumabili esauriti)"},
    "restock_placeholder": {"en": "e.g. 2x EVAP smoke solution", "it": "es. 2x soluzione fumo EVAP"},

    "symptom_q": {"en": "What did the driver feel?", "it": "Cosa ha percepito il guidatore?"},
    "conditions_label": {"en": "Conditions", "it": "Condizioni"},
    "reporter_label": {"en": "Reporter", "it": "Segnalatore"},
    "driver_opt": {"en": "Driver", "it": "Guidatore"},
    "mechanic_opt": {"en": "Mechanic", "it": "Meccanico"},
    "when_label": {"en": "When", "it": "Quando"},
    "odometer_optional": {"en": "Odometer (km, optional)", "it": "Contachilometri (km, opzionale)"},
    "edit_hint": {"en": "tap to edit", "it": "tocca per modificare"},
    "notes_optional": {"en": "Notes (optional)", "it": "Note (opzionale)"},
    "symptom_text_placeholder": {"en": "e.g. smelled fuel right after filling up, gone by the next morning",
                                  "it": "es. odore di carburante subito dopo il rifornimento, sparito entro il mattino dopo"},
    "recorded_label": {"en": "Recorded", "it": "Registrato"},
    "symptom_saved": {"en": "Symptom report saved.", "it": "Segnalazione sintomo salvata."},
    "not_recorded_label": {"en": "Not recorded", "it": "Non registrato"},

    # per-tag labels for the symptom-report <select> (replaces the plain
    # key|replace("_"," ") humanisation with a real translation; "Drives
    # normally" itself stays a literal string in the template, not routed
    # through t(), so it reads identically regardless of language -- an
    # existing test (check_timeline_page.py) asserts that exact English
    # text with no language cookie set).
    "symptom_mil_on": {"en": "MIL on", "it": "Spia MIL accesa"},
    "symptom_fuel_smell": {"en": "fuel smell", "it": "odore di carburante"},
    "symptom_hard_start": {"en": "hard start", "it": "avviamento difficile"},
    "symptom_rough_idle": {"en": "rough idle", "it": "minimo instabile"},
    "symptom_hesitation": {"en": "hesitation", "it": "esitazione"},
    "symptom_loss_of_power": {"en": "loss of power", "it": "perdita di potenza"},
    "symptom_hard_to_refuel": {"en": "hard to refuel", "it": "difficoltà di rifornimento"},
    "symptom_noise": {"en": "noise", "it": "rumore"},
    "symptom_vibration": {"en": "vibration", "it": "vibrazione"},
    "symptom_warning_message": {"en": "warning message", "it": "messaggio di avviso"},
    "symptom_other": {"en": "other", "it": "altro"},
    "cond_cold_start": {"en": "cold start", "it": "partenza a freddo"},
    "cond_hot": {"en": "hot", "it": "a caldo"},
    "cond_just_refuelled": {"en": "just refuelled", "it": "appena rifornita"},
    "cond_highway": {"en": "highway", "it": "autostrada"},
    "cond_city": {"en": "city", "it": "città"},
    "cond_idle": {"en": "idle", "it": "al minimo"},
    "cond_rain": {"en": "rain", "it": "pioggia"},
}


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """Return the English text for ``key`` (or the bare key if ``key``
    isn't in STRINGS at all -- never raises, a missing translation must
    degrade, not break the page).

    The language chooser has been removed (it did not work), so ``lang``
    -- whatever a caller or a leftover cookie passes -- is ignored; this
    always resolves to :data:`_FALLBACK_LANG` ("en"). The ``it`` entries
    in STRINGS are kept in place, unused, in case a working chooser comes
    back later."""
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(_FALLBACK_LANG, key)


def lang_from_cookie(cookie_value: Optional[str]) -> str:
    """Always returns :data:`DEFAULT_LANG` ("en") -- the ``lang`` cookie is
    no longer read now that the language chooser is gone. Kept (rather than
    removed) because it's still called from this module's own request-context
    plumbing below."""
    return DEFAULT_LANG


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


for _module_name in (
    "routes", "service_routes", "media_routes", "labels_routes", "bench_routes",
    "timeline_routes", "drivetrain_routes", "jobs_routes", "shop_routes",
    "electrical_routes", "systems_routes", "modules_routes", "inbox_routes",
    "report_routes", "tools_routes", "parts_routes",
):
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
