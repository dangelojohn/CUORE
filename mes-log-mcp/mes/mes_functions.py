"""Knowledge table: what MultiEcuScan (MES) itself documents as a function,
for the Alfa Romeo Giulia/Stelvio 2.0T (Giorgio platform, GME engine family)
-- the data half of the MES-vs-CUORE capability matrix
(``docs/research/MES_VS_CUORE_CAPABILITY_2026-10-14.md`` is the human-
readable half; this module is what that doc's own table is generated from
and what :mod:`cuore.services.mes_handoff_bridge` looks functions up in).

Same house rules as :mod:`mes.mechanic_tests` / :mod:`mes.known_good`:
nothing here is invented. Every row carries a ``source`` (a URL or the local
MES install path actually read) and a ``confidence`` --

* ``CONFIRMED``     -- multiecuscan.net's own supported-vehicle page, or the
                       local install's own files.
* ``CORROBORATED``  -- two independent owner/forum sources agree on the
                       same menu path or byte.
* ``SINGLE-SOURCE``  -- one forum/owner source, named as such.
* ``UNKNOWN``       -- MES's own menu path was not found in any source read
                       for this pass; ``menu_path`` says so in prose rather
                       than guessing one.

Research pass done 2026-10-14: multiecuscan.net's own supported-vehicle
listing, the MultiEcuScan support forum, and owner-community writeups
(giuliaforums.com, stelvioforum.com, giuliatech.com, alfaowner.com,
mhhauto.com) -- all public, all cited per row below. No paywalled/bot-gated
source was read. The local install at
``C:\\Program Files (x86)\\MultiEcuScan`` was also checked (its FES logs,
``FES_Tags.ini``) -- real parameter names recorded there (e.g. "Throttle
learning stage", "Learned VVT tooth position") corroborate a few PRM rows
below but the install ships no menu-tree text file and no actuator/
adjustment list in cleartext (the database itself is encrypted, per this
pass's own instructions, and was not touched).

Four read-only lookups, the whole public surface:

* :func:`all_functions`       -- every function, as a list.
* :func:`function`             -- one function by id, or ``None``.
* :func:`functions_for_module` -- functions touching one module/ECU.
* :func:`search`                -- functions whose name/keywords match a
                                   free-text string (job-step/test-name
                                   matching -- see ``mes_handoff_bridge``).
"""

from __future__ import annotations

from typing import Any, Optional

from .systems import CONFIDENCE_LEVELS, CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN

#: read       -- MES shows this without writing anything to the car.
#: actuator   -- MES commands an output/relay/motor live (a write, momentary).
#: adjustment -- MES writes a setting/calibration (a write, persistent).
#: coding     -- MES writes a configuration byte/variant-coding value.
KINDS = ("read", "actuator", "adjustment", "coding")

FUNCTIONS: dict[str, dict[str, Any]] = {}
_ORDER: list[str] = []


def _f(id_: str, module: str, kind: str, name: str, menu_path: str,
      prerequisites: list[str], record_after: str, source: str,
      confidence: str, *, cable: str = "", test_id: str = "",
      log_expected: bool = False, mes_support: str = "yes",
      cuore_today: str = "no", notes: str = "") -> None:
    if id_ in FUNCTIONS:
        raise ValueError(f"duplicate mes function id {id_!r}")
    if kind not in KINDS:
        raise ValueError(f"bad kind {kind!r} for {id_!r}")
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r} for {id_!r}")
    FUNCTIONS[id_] = {
        "id": id_, "module": module, "kind": kind, "name": name,
        "menu_path": menu_path, "prerequisites": list(prerequisites),
        "cable": cable, "record_after": record_after, "test_id": test_id,
        "log_expected": log_expected, "mes_support": mes_support,
        "cuore_today": cuore_today, "source": source,
        "confidence": confidence, "notes": notes,
    }
    _ORDER.append(id_)


# ===========================================================================
# Read: whole-vehicle scan, module identity, live parameters, freeze frames
# ===========================================================================

_SRC_SUPPORTED = ("https://www.multiecuscan.net/SupportedVehiclesList.aspx "
                 "(Alfa Romeo Giulia/Stelvio 2.0T MultiAir entries)")

_f("all_module_scan", "ALL (CAN-C/IHS/CH)", "read", "All-systems scan",
  "main toolbar -> Scan vehicle (sweeps every module MES has a database "
  "entry for, across the car's CAN buses)",
  ["ignition on", "A5 cable for CAN-C-only reads; A6 (or A5+adapter) to "
   "also reach IHS/CH comfort-bus modules -- see the MES cable guide"],
  "the resulting SCAN_YYMMDDHHMM.txt -- import it (mes_handoff_bridge."
  "import_mes_log) so it gets the same health report a CUORE live scan gets",
  _SRC_SUPPORTED, CONFIRMED, cable="A5/A6", log_expected=True,
  cuore_today="built -- cuore.live.fullscan.run over the modules with a "
             "confirmed address. Recorded answers on the Stelvio: ECM, TCM, "
             "BCM, IPC, RF hub, DTCM, ESM, DASM on CAN-C and two unnamed "
             "CAN-IHS nodes; ABS on CAN-CH answered once (2026-10-15), not "
             "since; climate, ESEM, TVM never answered. Not compared with MES")

_f("module_info_identity", "ALL", "read", "Module info / identity (INFO)",
  "each module's own screen -> Info tab (ECU part number, HW/SW version, "
  "calibration ID)",
  ["ignition on"], "nothing to record beyond what's shown -- read-only",
  _SRC_SUPPORTED, CONFIRMED,
  cuore_today="partial -- identity fields read on the Stelvio for ECM, TCM, "
             "BCM, IPC, RF hub, DTCM, ESM, DASM and equal to MES for 1 to 7 "
             "fields each (no ISO code, homologation or counters); climate, "
             "ESEM, TVM and the CAN-CH modules other than one ABS answer "
             "have no CUORE identity read")

_f("live_parameters", "ALL", "read", "Live parameters with name/unit/scaling "
  "(PRM)", "each module's own screen -> Parameters tab",
  ["ignition on; engine running for most engine/transmission channels"],
  "nothing to record for a plain look -> use graphs_recording_csv to keep "
  "a record",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80 "
  "(2026-10-14) + this install's own FES logs (e.g. \"Throttle learning "
  "stage\", \"Learned VVT tooth position\" -- "
  "C:\\Program Files (x86)\\MultiEcuScan\\FESLog_2606071008_...txt)",
  CORROBORATED,
  cuore_today="partial -- CUORE's live_obs/channels.py covers the OBD-II "
             "PIDs/DIDs it has learned; MES's own scaled names for "
             "TCM/BCM/ABS-specific channels (no public DID) are not in "
             "CUORE's channel table")

_f("graphs_recording_csv", "ALL", "read", "Live-data graph + CSV recording",
  "Parameters tab -> graph icon, then Record (writes a .csv under MES's "
  "configured Export Folder)",
  ["a parameter selected and visible"],
  "the .csv it writes -- point mes.catalog's CSV root at it (already "
  "rescans) and link it from the handoff card's Import button",
  "https://shop.alfissimo.com/diagnostic-softwarehardware-"
  "multiecuscanalfaobd/1600-multiecuscan-diagnostic-software-for-alfa-"
  "romeo.html (2026-10-14, \"Live data graphical view\")", CORROBORATED,
  log_expected=True,
  cuore_today="built, never compared with MES -- CUORE has a live board "
             "with record, tags and MES-format CSV export; mes.csvlog also "
             "reads an MES-written CSV once it exists")

_f("freeze_frames_per_module", "ALL", "read", "Freeze frames per module "
  "(DTC EX)", "each module's own screen -> DTC EX tab",
  ["ignition on"], "nothing to record -- read-only",
  _SRC_SUPPORTED, CONFIRMED,
  cuore_today="partial -- cuore.live.obd read_freeze_frame covers OBD-II "
             "freeze frames; module-specific DTC-EX detail (ABS/TCM/BCM "
             "beyond the generic DID) is MES-only")

# ===========================================================================
# Actuators
# ===========================================================================

_f("esim_commanded_vent_test", "Engine/ECM (EVAP)", "actuator",
  "ESIM commanded vent test",
  "Engine -> ECM -> Actuators tab -> ESIM / purge solenoid vent command",
  ["fuel level 15-85% (EVAP verification window)", "engine running, purge "
   "active", "only one scan tool on the OBD port"],
  "switch-state transition and whether vacuum built, plus fuel level and "
  "commanded_evap_purge at the time",
  "http://forum.multiecuscan.net/viewtopic.php?t=9514 (\"Alfa Stelvio F6 "
  "Actuators Turbo Vacuum Valve\", 2026-10-14) + this repo's own "
  "mes.mechanic_tests.esim_commanded_vent_test (sourced research pass, "
  "2026-10-08)",
  CORROBORATED, cable="A5", test_id="esim_commanded_vent_test",
  mes_support="yes -- Actuators tab (or wiTECH bidirectional control)",
  cuore_today="no -- MCP-only via obd2.run_actuator with the ACTUATE ECM "
             "consent phrase; never exposed over CUORE's HTTP job/tests "
             "API because it writes a live command to the car",
  notes="the catalogue test (mechanic_tests.py) already states this "
       "explicitly in its own when_to_use text")

_f("turbo_boost_waste_gate_actuator", "Engine/ECM (intake/boost)",
  "actuator", "Boost/waste-gate actuator test",
  "Engine -> ECM -> Actuators tab -> boost control solenoid / waste-gate",
  ["engine running or KOEO per the on-screen prompt",
   "only one scan tool on the OBD port"],
  "MAP/boost reading before and during the commanded actuation",
  "http://forum.multiecuscan.net/viewtopic.php?t=9514 (2026-10-14)",
  SINGLE_SOURCE, cable="A5",
  cuore_today="no -- no CUORE actuator route for this channel; MCP-only, "
             "consent-gated, same posture as the ESIM test above")

_f("zf_gear_shift_actuator", "Gearbox/ZF Electronic Gear Shift Module",
  "actuator", "Gear-shift actuator test (ACT)",
  "Gearbox -> ZF Electronic Gear Shift Module -> Actuators tab",
  ["ignition on per MES prompt", "park brake set"],
  "the module's own pass/fail readout for the commanded actuation",
  _SRC_SUPPORTED, CONFIRMED,
  cuore_today="no -- no OBD-II DID for this actuator; MES/wiTECH-only")

# ===========================================================================
# Adjustments / procedures
# ===========================================================================

_f("proxi_alignment_952", "Body/BCM (CAN Setup)", "adjustment",
  "PROXI alignment procedure (952)",
  "Body -> CAN Setup / PROXI ALIGNMENT PROCEDURE (952) -- Adjustment tab; "
  "Ctrl+Alt+C opens the raw PROXI byte dialog",
  ["cable switching mid-procedure per MES's own on-screen prompts",
   "battery support recommended -- a long write"],
  "the resulting PROXI byte set (export/screenshot) and which modules were "
  "written",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " + https://www.multiecuscan.net/forum/viewtopic.php?t=7784 (\"2018 Alfa "
  "Giulia - Proxi Alignment issue\") -- both 2026-10-14",
  CORROBORATED, cable="A5/A6 (switched per prompt)",
  cuore_today="no -- CUORE never writes PROXI/configuration bytes over "
             "HTTP; MCP-only with consent, and only for the few catalogued "
             "below -- most PROXI byte edits have no CUORE DID at all",
  notes="this is the base procedure several of the coding rows below "
       "(battery type, race mode, paddle logic, etc.) are performed inside")

_f("oil_change_reset_ecm", "Engine/ECM (Magneti Marelli IAW 10JA)",
  "adjustment", "Oil-change reset (engine side)",
  "Engine -> Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0) -> "
  "Adjustments tab -> Oil Change",
  ["oil actually changed", "ignition on"],
  "odometer/date of the oil change, confirmation the ECM reset accepted",
  "https://www.alfaowner.com/threads/oil-change-and-service-reset-using-"
  "multiecuscan.705170/ + https://www.stelvioforum.com/threads/mes-oil-"
  "change-routines.24067/ (both 2026-10-14)", CORROBORATED,
  cuore_today="no -- write-side, never over HTTP; MCP-only with consent",
  notes="per the same sources, this is a SEPARATE reset from "
       "service_interval_reset below -- both are needed after an oil "
       "change on these model years")

_f("service_interval_reset", "Service module (dash/BCM-side)", "adjustment",
  "Service interval / \"next service\" reset",
  "Service -> Service Interval Reset -> Adjustments tab -> NEXT SERVICE KM "
  "RESET",
  ["oil/service actually performed",
   "SGW bypass may be required on cars with a Security Gateway (later "
   "model years) -- MES cannot write past the SGW without one"],
  "the new service-due distance/date MES wrote",
  "https://www.stelvioforum.com/threads/scheduled-maintenance-reset.24621/"
  " + https://www.stelvioforum.com/threads/multiecuscan-help.19957/ "
  "(2026-10-14)", CORROBORATED,
  cuore_today="no -- write-side; MCP-only with consent",
  notes="owners report newer cars cannot be written to a HIGHER interval "
       "than stock, and a coupon-number-0 car can only do the ECM oil "
       "reset above, not this one -- record which applied")

_f("battery_type_registration", "Body/BCM (CAN Setup, byte 63)", "coding",
  "Battery type registration",
  "Body -> CAN Setup -> Adjustments tab -> PROXI byte 63, bits 0-3 (80Ah "
  "680A / 95Ah 800A / H7 flooded / H7 AGM / H8 flooded / H8 AGM patterns)",
  ["new battery's type/capacity known", "proxi_alignment_952 access path"],
  "which byte 63 pattern was written and the battery's actual type/plate",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " + https://www.giuliaforums.com/threads/what-are-proxi-parameters-for-"
  "agm-battery-on-giulia-2-2.65519/page-3 (2026-10-14)", CORROBORATED,
  cuore_today="no -- coding write; MCP-only with consent",
  notes="not the same as IBS/BMS learning below -- this is static "
       "configuration, not a live-learn routine")

_f("ibs_battery_sensor_read", "Body/BCM (IBS)", "read",
  "Intelligent Battery Sensor (IBS) parameters",
  "Body -> BCM -> Parameters tab -> IBS group (charge status, SoC, SoH)",
  ["ignition on; some fields need a drive cycle to populate"],
  "IBS charge status reading at time of battery service",
  "https://www.alfaowner.com/threads/multiecuscan-question-regarding-ibs."
  "1214903/ (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- no CUORE DID for IBS; this is read-only in MES so "
             "there is no write-side gap, just a read CUORE lacks",
  notes="per the source, 2020+ Giulia/Stelvio IBS interface changed and "
       "only \"IBS Battery Charge Status\" is reliably trustworthy -- "
       "treat other IBS fields on later cars with caution in MES too, not "
       "just in CUORE")

_f("sas_calibration", "Chassis/ABS (Continental MK C1)", "adjustment",
  "Steering angle sensor (SAS) calibration / reset",
  "ABS -> Continental ABS MK C1 module -> Parameters tab to check 0 deg, "
  "then Adjustments tab -> Reset steering angle",
  ["gray cable for this ABS variant", "wheels straight, car on level "
   "ground", "ignition on, engine may need to be running per prompt"],
  "the 0 deg check reading before and after, and the result code MES "
  "returns",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE, cable="gray (ABS-specific)",
  cuore_today="no -- write-side; MCP-only with consent",
  notes="named explicitly by the owner in task scope (SAS calibration)")

_f("abs_accel_sensor_calibration", "Chassis/ABS (Continental MK C1)",
  "adjustment", "Lateral/longitudinal acceleration sensor calibration",
  "ABS -> Continental ABS MK C1 module -> Adjustments tab -> accel sensor "
  "calibration",
  ["car stationary, level ground", "gray cable"],
  "the calibration result MES returns",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE, cable="gray",
  cuore_today="no -- write-side; MCP-only with consent")

_f("abs_pressure_sensor_calibration", "Chassis/ABS (Continental MK C1)",
  "adjustment", "Brake pressure sensor calibration",
  "ABS -> Continental ABS MK C1 module -> Adjustments tab -> pressure "
  "sensor calibration",
  ["gray cable", "brake system at rest, no pedal applied"],
  "the calibration result MES returns",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE, cable="gray",
  cuore_today="no -- write-side; MCP-only with consent")

_f("epb_service_mode", "Chassis/EPB", "adjustment",
  "Electric parking brake service/retract mode",
  "NOT in MES, per owner reports -- Settings -> Driver Assistance -> "
  "Brake Service on the car's own infotainment screen retracts the EPB "
  "motors; MES's own \"EPB maintenance mode\" menu item is reported "
  "non-functional",
  ["park on level ground, engine off", "infotainment screen, not a scan "
   "tool, does the retract"],
  "which pads were replaced; use MES afterward only to clear the "
  "resulting brake-system DTC, not to run service mode",
  "https://www.giuliaforums.com/threads/brake-service-mode-within-"
  "multiecuscan-software.54344/ + https://servicereset.net/maintenance/"
  "alfa-romeo-stelvio-2017-present-epb-service-mode/ (both 2026-10-14)",
  CORROBORATED, mes_support="no -- native infotainment menu does this, "
  "not MES",
  cuore_today="no",
  notes="deliberately honest exception: this is the one catalogued "
       "procedure where MES is NOT the better tool -- the car's own menu "
       "is. The handoff card for this one points at the infotainment "
       "screen, not at MES")

_f("tpms_pressure_threshold", "Body/RF Hub", "adjustment",
  "TPMS pressure-warning threshold",
  "Body -> RFHub -> Adjustments tab -> TPMS pressure threshold (MES "
  ">=4.7R3)",
  ["RF Hub module present/communicating"],
  "the threshold value written",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- write-side; MCP-only with consent")

_f("seat_belt_chime_disable", "Dashboard/Instrument Panel", "coding",
  "Seat-belt chime disable",
  "Dashboard -> Instrument Panel -> Adjustments tab -> seat belt chime",
  ["ignition on"], "which seats were affected",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- CUORE never performs coding writes")

_f("race_mode_dynamic_control_selector", "Body/BCM (CAN Setup)", "coding",
  "Race mode / Dynamic Control Selector configuration",
  "Body -> CAN Setup (Dynamic Control Selector) -> Adjustments tab "
  "(MES 4.5+)",
  ["proxi_alignment_952 access path"], "which DCS option was selected",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " + https://www.multiecuscan.net/forum/viewtopic.php?t=7707 (\"Giulia/"
  "Stelvio BCM adjustment for Race Mode\") -- both 2026-10-14",
  CORROBORATED,
  cuore_today="no -- coding write; MCP-only with consent")

_f("acc_cruise_enable", "Body/BCM (CAN Setup)", "coding",
  "Cruise control / ACC+ enable",
  "Body -> CAN Setup -> Adjustments tab -> Cruise Control/ACC settings",
  ["proxi_alignment_952 access path", "ACC hardware actually fitted"],
  "which ACC option was enabled",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- coding write; MCP-only with consent")

_f("paddle_shifter_logic", "Body/BCM (CAN Setup, byte 156)", "coding",
  "Paddle shifter (EU) logic configuration",
  "Body -> CAN Setup -> Adjustments tab -> PROXI byte 156, bits 4-5",
  ["proxi_alignment_952 access path"], "which bit pattern was written",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- coding write; MCP-only with consent")

_f("window_comfort_logic", "Body/BCM (CAN Setup, byte 58)", "coding",
  "Window comfort open/close enable",
  "Body -> CAN Setup -> Adjustments tab -> PROXI byte 58, bit 1",
  ["proxi_alignment_952 access path"], "whether comfort open/close was "
  "enabled or disabled",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- coding write; MCP-only with consent")

_f("after_wipe_logic", "Body/BCM (CAN Setup, byte 126)", "coding",
  "After-wipe (rear wiper delay) configuration",
  "Body -> CAN Setup -> Adjustments tab -> PROXI byte 126, bit 5",
  ["proxi_alignment_952 access path"], "which setting was written",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- coding write; MCP-only with consent")

_f("cornering_lights_enable", "Body/BCM (CAN Setup)", "coding",
  "Static bending/cornering lights activation",
  "Body -> CAN Setup -> Adjustments tab -> Cornering Lights option",
  ["proxi_alignment_952 access path", "headlight hardware supports it"],
  "whether the option was enabled",
  "https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80"
  " (2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- coding write; MCP-only with consent")

_f("tvm_bcm_etm_coding", "Body/TVM, BCM, ETM", "coding",
  "Torque Vectoring / BCM / ETM module coding (retrofit/variant coding)",
  "each module's own screen -> Adjustments/Coding tab, per module",
  ["module actually fitted", "VIN-matched coding values from "
   "TechAuthority for a retrofit"],
  "which module(s) were coded and the values written",
  "https://mhhauto.com/Thread-Giulia-Coding-TVM-BCM-ETM-Modules-Help "
  "(2026-10-14)", SINGLE_SOURCE,
  cuore_today="no -- coding write; MCP-only with consent",
  notes="thread is about a retrofit radar coding case -- treat any "
       "specific byte values there as that one car's, not a general spec")

_f("coil_actuator_test", "Engine/ECM (ignition)", "actuator",
  "Ignition coil actuator test",
  "Engine -> ECM -> Actuators tab (string 6001 \"Actuators\") -> "
  "ACTUATES THE COIL (string 6202)",
  ["engine off per MES's own prompt", "only one scan tool on the OBD port"],
  "which coil was commanded and whether it fired/clicked as expected",
  r"local install, C:\Program Files (x86)\MultiEcuScan\Lang\English.txt, "
  "string ids 6001/6202 (read 2026-10-14)", CONFIRMED, cable="A5",
  cuore_today="no -- write-side; MCP-only via obd2.run_actuator with "
             "consent, never over HTTP")

_f("idle_actuator_test", "Engine/ECM (throttle/idle)", "actuator",
  "Idle actuator test / throttle-idle learn",
  "Engine -> ECM -> Actuators tab -> ACTUATES IDLE ACTUATOR (string 6205); "
  "TIMING ACTUATOR ACTIVATION (6220) governs the commanded duration",
  ["engine running or KOEO per prompt", "throttle learn should follow per "
   "mechanic_tests.py's own throttle-learning-stage parameter"],
  "throttle learning stage reading before/after (this install's own FES "
  "logs record this parameter by name)",
  r"local install, C:\Program Files (x86)\MultiEcuScan\Lang\English.txt, "
  "string ids 6001/6205/6220 (read 2026-10-14) + this install's own "
  r"FESLog_2606071008_...txt (\"Throttle learning stage: Learned\")",
  CONFIRMED, cable="A5",
  cuore_today="no -- write-side; MCP-only with consent")

_f("key_rf_learning", "Body/BCM (RF Hub, immobiliser)", "adjustment",
  "Key / RF remote learning",
  "Body -> BCM -> Adjustments tab -> key learning procedure (per-prompt: "
  "DETECTING KEY, strings 6074/6076); \"ALL KEYS MUST BE LEARNED\" (6079) "
  "warns that unlearned keys are disabled by the procedure",
  ["every key the owner wants to keep working must be present and learned "
   "in the SAME session -- a key left out is disabled",
   "RF module fitted, or the remote-control function will not work per "
   "string 6084"],
  "which keys were learned and whether string 6084's RF-module warning "
  "fired",
  r"local install, C:\Program Files (x86)\MultiEcuScan\Lang\English.txt, "
  "string ids 6074/6076/6079/6084 (read 2026-10-14)", CONFIRMED,
  cuore_today="no -- write-side; MCP-only with consent",
  notes="highest-confidence row in this table -- read directly from the "
       "installed software's own string table, not a forum writeup")

# ===========================================================================
# Not applicable on this platform
# ===========================================================================

_f("dpf_regen", "Exhaust/DPF", "adjustment",
  "Forced DPF regeneration", "n/a on the 2.0T GME -- this is a gasoline "
  "engine with no diesel particulate filter; MES's DPF regen menu applies "
  "only to Giorgio-platform diesel variants (JTDM), not the 2.0T",
  [], "n/a",
  "platform fact: mes-log-mcp's own engine-family notes (GME = gasoline "
  "turbo, not diesel) -- not independently re-sourced for this pass",
  CONFIRMED, mes_support="n/a", cuore_today="n/a",
  notes="listed per the owner's explicit ask, marked n/a rather than "
       "omitted so the matrix shows it was considered")

# ===========================================================================
# Module roster (read side) -- named by the owner's task scope: IHS/CH
# comfort-bus modules reachable only with the A6 (or A5+adapter) cable
# ===========================================================================

_f("comfort_bus_module_roster", "IHS/CH (Magna Q4 transfer case, TRW "
  "steering lock, Bosch HALF camera, Bosch DASM radar, ESEM engine sound, "
  "TVM torque vectoring)", "read",
  "Comfort-bus module roster (IHS/CH, beyond CAN-C)",
  "main toolbar -> Scan vehicle with an A6 cable (or A5 + MES's IHS/CH "
  "adapter) reaches these; an A5-only CAN-C scan does not see them",
  ["A6 cable (or A5 + adapter)"], "which of these modules answered and "
  "their DTC/parameter state",
  "WebSearch results for \"multiecuscan.net Alfa Romeo Stelvio supported "
  "functions parameters actuators\" (2026-10-14), citing alfissimo.com's "
  "MES product listing", CORROBORATED, cable="A6",
  cuore_today="partial -- DTCM and DASM are registered on CAN-C and have "
             "answered there; two unnamed CAN-IHS nodes answered a VIN read "
             "and a code read; ABS on CAN-CH answered once and not since. "
             "HALF, ESEM, TVM and the others have not answered; none of it "
             "is compared with MES")


def all_functions() -> list[dict[str, Any]]:
    """Every function in catalogue order."""
    return [dict(FUNCTIONS[i]) for i in _ORDER]


def function(id_: str) -> Optional[dict[str, Any]]:
    """One function by id, or ``None`` if unknown."""
    f = FUNCTIONS.get(id_)
    return dict(f) if f is not None else None


def functions_for_module(module_substring: str) -> list[dict[str, Any]]:
    """Functions whose ``module`` contains ``module_substring``
    (case-insensitive)."""
    want = (module_substring or "").strip().lower()
    if not want:
        return []
    return [dict(FUNCTIONS[i]) for i in _ORDER if want in FUNCTIONS[i]["module"].lower()]


def functions_for_test(test_id: str) -> list[dict[str, Any]]:
    """Functions cross-referenced to one :mod:`mes.mechanic_tests` id."""
    return [dict(FUNCTIONS[i]) for i in _ORDER if FUNCTIONS[i]["test_id"] == test_id]


_STOPWORDS = frozenset({
    "a", "an", "the", "this", "that", "is", "of", "for", "and", "or", "to",
    "s", "on", "in", "with", "per",
})


def _tokens(text: str) -> frozenset[str]:
    import re
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    return frozenset(t for t in cleaned.split() if t and t not in _STOPWORDS)


def search(text: str) -> list[dict[str, Any]]:
    """Functions whose name matches ``text`` by token overlap, either
    direction: a short query like "service interval reset" matches the
    function name "Service interval / 'next service' reset" (the query's
    tokens are a subset of the name's), and a long job-step sentence
    containing a function's name matches too (the name's tokens are a
    subset of the sentence's). A single-token query never matches on its
    own (``len(hay_tokens) >= 2`` below) -- a bare word like "test" must
    not pull in every test-named function. Used by
    ``mes_handoff_bridge`` to decide whether a Tests-page row or a job
    step-6 checklist row gets a handoff card."""
    hay_tokens = _tokens(text)
    if not hay_tokens:
        return []
    out = []
    for i in _ORDER:
        f = FUNCTIONS[i]
        name_tokens = _tokens(f["name"])
        if not name_tokens:
            continue
        if name_tokens <= hay_tokens or (len(hay_tokens) >= 2 and hay_tokens <= name_tokens):
            out.append(dict(f))
    return out


__all__ = ["KINDS", "all_functions", "function", "functions_for_module",
          "functions_for_test", "search"]
