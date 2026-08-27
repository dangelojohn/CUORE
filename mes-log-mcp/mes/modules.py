"""Canonical ECU/module registry for FCA (Alfa Romeo / Fiat / Lancia / Jeep / Chrysler).

Why this exists
---------------
MES prints the same physical ECU under many different strings. ``BCM`` alone
appears as ``Body / BCM (Body Computer Module)``, ``Body / BCM (Body Control
Module)``, ``Body Computer Node (BCM/NBC)``, ``Body computer (BCM)`` and more,
across SCAN headings, PROXI node rosters, and DTC description text. Without
normalisation one ECU fragments into half a dozen "modules" and any per-module
history is wrong.

Three rules the corpus forced:

* **The abbreviation is the stable key**, not the printed heading. MES's group
  and long-name strings both change between database revisions.
* **Compound abbreviations are alias sets, not compound identities.**
  ``TCM/NCA/NCR`` is one module with three regional names, so every token
  registers as an alias of one canonical code.
* **MES's own group is not a usable domain.** It files the transfer case under
  ``Gearbox``, the radar and TPMS under ``Other``, and the RF hub under
  ``Body``. Display grouping therefore comes from :attr:`ModuleInfo.domain`
  here, never from the log's category field.

Provenance is tracked per entry. ``corpus`` means the string was observed in
this shop's own logs; ``mes-lang`` means it came from MES's shipped
``Lang\\English.dat`` string table; ``confirmed`` means vendor documentation.
Entries whose presence on the Giorgio platform is a guess say so rather than
asserting it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Domain(str, Enum):
    """Display grouping. Deliberately independent of MES's own category."""

    POWERTRAIN = "powertrain"
    ELECTRIFICATION = "electrification"
    CHASSIS = "chassis"
    SAFETY = "safety"
    BODY = "body"
    LIGHTING = "lighting"
    CLIMATE = "climate"
    INFOTAINMENT = "infotainment"
    NETWORK = "network"
    PSEUDO = "pseudo"
    UNKNOWN = "unknown"


class Tier(str, Enum):
    """How much a fault in this module matters. Drives report sort order."""

    CRITICAL = "critical"        # drivability or safety
    IMPORTANT = "important"      # emissions, transmission, ADAS, chassis aids
    INFORMATIONAL = "informational"

    @property
    def rank(self) -> int:
        return {Tier.CRITICAL: 0, Tier.IMPORTANT: 1,
                Tier.INFORMATIONAL: 2}[self]


#: Confidence that a module is present on the Giorgio platform (Giulia/Stelvio).
GIORGIO_YES = "yes"
GIORGIO_NO = "no"
GIORGIO_LIKELY = "likely"
GIORGIO_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ModuleInfo:
    code: str
    name: str
    description: str
    domain: Domain
    tier: Tier
    giorgio: str = GIORGIO_UNKNOWN
    aliases: tuple[str, ...] = ()
    source: str = "mes-lang"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "domain": self.domain.value,
            "tier": self.tier.value,
            "on_giorgio": self.giorgio,
            "source": self.source,
        }
        if self.aliases:
            d["aliases"] = list(self.aliases)
        if self.note:
            d["note"] = self.note
        return d


def _m(code, name, desc, domain, tier, giorgio=GIORGIO_UNKNOWN,
       aliases=(), source="mes-lang", note="") -> ModuleInfo:
    return ModuleInfo(code, name, desc, domain, tier, giorgio,
                      tuple(aliases), source, note)


# --- Powertrain -----------------------------------------------------------

_POWERTRAIN = [
    _m("ECM", "Engine Control Module",
       "Fuel, ignition, boost, throttle and emissions monitors. Master "
       "powertrain node; owns the EVAP monitors and their freeze frames.",
       Domain.POWERTRAIN, Tier.CRITICAL, GIORGIO_YES,
       ("NCM", "ECU", "PCM"), "corpus"),
    _m("TCM", "Automatic Transmission Control Module",
       "Shift scheduling, clutch and torque-converter control, adaptives.",
       Domain.POWERTRAIN, Tier.CRITICAL, GIORGIO_YES,
       ("NCA", "NCR"), "corpus", "Giorgio uses ZF 8HP50/75"),
    _m("ESM", "Gearbox Selector Module",
       "Reads the shift-by-wire lever or rotary selector and reports gear "
       "intent to the TCM.",
       Domain.POWERTRAIN, Tier.CRITICAL, GIORGIO_YES,
       ("GSM", "NSC"), "corpus"),
    _m("DTCM", "Drive Train Control Module",
       "Transfer case / AWD torque split front to rear. On Stelvio this is "
       "the Magna Q4 transfer case.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_YES, (), "corpus"),
    _m("TVM", "Torque Vectoring Module",
       "Rear-axle torque-vectoring differential control.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_YES, (), "corpus"),
    _m("ELSDM", "Electronic Limited Slip Differential Module",
       "e-LSD clutch pack control.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_LIKELY, (), "mes-lang",
       "likely Quadrifoglio only"),
    _m("RDM", "Rear Drive Module", "Rear-axle drive unit control.",
       Domain.POWERTRAIN, Tier.IMPORTANT),
    _m("CCM", "Coupling Control Module", "AWD coupling actuator control.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_NO),
    _m("NSM", "Engine Signals Node",
       "Distributes engine signals onto the body network.",
       Domain.POWERTRAIN, Tier.IMPORTANT),
    _m("SDU", "Gas Injector Module",
       "LPG/CNG bi-fuel injection; a second ECU alongside the ECM.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_NO),
    _m("SCRM", "Selective Catalytic Reduction Module",
       "AdBlue/urea dosing on diesel engines.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_YES, (), "confirmed",
       "2.2 diesel only"),
    _m("ESEM", "Engine Sound Enhancement Module",
       "Synthesised engine note through the audio system; also active noise "
       "cancellation.",
       Domain.POWERTRAIN, Tier.INFORMATIONAL, GIORGIO_YES, ("ANC",), "corpus",
       "MES ships a typo, 'enhacement' - match both spellings"),
    _m("AAML", "Active Aerodynamic Module Left", "Active front splitter, left.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_YES, (), "confirmed",
       "2.9 V6 Quadrifoglio only"),
    _m("AAMR", "Active Aerodynamic Module Right",
       "Active front splitter, right.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_YES, (), "confirmed",
       "2.9 V6 Quadrifoglio only"),
    _m("HCSS", "Heated Cold Start System",
       "Diesel intake or coolant preheat.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_NO),
    _m("FPCM", "Fuel Pump Control Module", "In-tank fuel pump driver.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_UNKNOWN, (), "mes-lang",
       "see recall 25V586 / Mopar 93C for 2018-2019 Stelvio FDM"),
    _m("GPCM", "Glow Plug Control Module", "Diesel glow plug control.",
       Domain.POWERTRAIN, Tier.IMPORTANT, GIORGIO_LIKELY, (), "mes-lang",
       "2.2 diesel"),
]

# --- Electrification ------------------------------------------------------

_ELECTRIFICATION = [
    _m("HCP", "Hybrid Control Processor",
       "Supervisory hybrid strategy: torque blend, engine start/stop.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO, ("MHEV",), "corpus"),
    _m("MCP", "Motor Control Processor",
       "Traction-motor inverter and torque control.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO),
    _m("BPCM", "Battery Pack Control Module",
       "HV pack state of charge and health, cell balancing, contactors.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO, (), "corpus"),
    _m("PIM", "Power Inverter Module", "DC to AC for the traction motor.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO, ("IPM",)),
    _m("EVCU", "Electric Vehicle Control Unit", "Vehicle-level EV supervisor.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO),
    _m("OBCM", "Onboard Battery Charger Module", "AC charging control.",
       Domain.ELECTRIFICATION, Tier.IMPORTANT, GIORGIO_NO),
    _m("IDCM", "Integrated Dual Charge Module",
       "Combined onboard charger and DC/DC converter.",
       Domain.ELECTRIFICATION, Tier.IMPORTANT, GIORGIO_NO),
    _m("BSG", "Belt Starter Generator",
       "48 V mild-hybrid motor-generator.",
       Domain.ELECTRIFICATION, Tier.IMPORTANT, GIORGIO_NO),
    _m("RBC", "Regenerative Brakes Controller",
       "Blends friction and regenerative braking.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO),
    _m("DBSM", "Dual Battery Switch Module",
       "12 V dual-battery switching for stop-start.",
       Domain.ELECTRIFICATION, Tier.IMPORTANT),
    _m("EAC", "Electric Air Compressor",
       "Electric A/C compressor on hybrids.",
       Domain.ELECTRIFICATION, Tier.IMPORTANT, GIORGIO_NO),
    _m("QVPM", "Quiet Vehicle Pedestrian Module",
       "Low-speed pedestrian warning sound (AVAS).",
       Domain.ELECTRIFICATION, Tier.INFORMATIONAL, GIORGIO_NO),
    _m("DCDC", "DC/DC Converter", "High voltage to 12 V supply.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO),
    _m("HGM", "Hybrid Gateway Module", "Isolates the HV powertrain CAN.",
       Domain.ELECTRIFICATION, Tier.CRITICAL, GIORGIO_NO),
]

# --- Chassis --------------------------------------------------------------

_CHASSIS = [
    _m("ABS", "Brake System Module",
       "ABS, ESP/ESC and traction control. Wheel-speed sensing; brake-by-wire "
       "on the Continental MK C1 used by Giorgio.",
       Domain.CHASSIS, Tier.CRITICAL, GIORGIO_YES,
       ("BSM", "NFR", "ESP", "ESC"), "corpus"),
    _m("NBA", "Assisted Braking Node", "Brake booster / assisted braking.",
       Domain.CHASSIS, Tier.CRITICAL),
    _m("EPB", "Electronic Parking Brake",
       "Electric caliper actuators and auto-hold.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_YES, ("NPB",), "corpus"),
    _m("EPS", "Electric Power Steering",
       "Steering assist torque; also hosts the steering-angle sensor on "
       "Giorgio.",
       Domain.CHASSIS, Tier.CRITICAL, GIORGIO_YES, ("NGE",), "corpus"),
    _m("NAS", "Steering Angle Sensor Node",
       "Absolute steering angle for ESP and ADAS.",
       Domain.CHASSIS, Tier.CRITICAL, GIORGIO_NO, (), "mes-lang",
       "integrated into EPS/NGE on Giorgio"),
    _m("NYL", "Side Acceleration / Yaw Node",
       "Yaw-rate and lateral-g sensor cluster.",
       Domain.CHASSIS, Tier.CRITICAL, GIORGIO_NO, (), "mes-lang",
       "integrated into ABS on Giorgio"),
    _m("NBS", "Steering Lock Node", "Electric steering-column lock (ESL).",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_YES, (), "corpus"),
    _m("SCCM", "Steering Column Control Module",
       "Column stalks, column adjustment, steering wheel control hub.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_YES, ("SCM",), "corpus",
       "MES has no SCM node entry; SCM appears only inside DTC text"),
    _m("NVO", "Steering Wheel Controls Node", "Steering wheel button matrix.",
       Domain.CHASSIS, Tier.INFORMATIONAL),
    _m("NMA", "Air Suspension Node", "Air-spring ride height and levelling.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_NO, ("ASM",)),
    _m("NCS", "Suspension Control Node", "General suspension controller.",
       Domain.CHASSIS, Tier.IMPORTANT),
    _m("DCM", "Controlled Suspension Node",
       "Adaptive damping / frequency-selective damper control.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_LIKELY),
    _m("ADCM", "Active Damping Control Module", "Active damper control.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_LIKELY),
    _m("NRC", "Roll Control Node", "Active anti-roll control.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_NO),
    _m("CDCM", "Chassis Domain Control Module",
       "Domain controller aggregating chassis functions.",
       Domain.CHASSIS, Tier.CRITICAL),
    _m("DSCM", "Drive Style Control Module",
       "Alfa DNA drive-mode selector.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_LIKELY),
    _m("TPMS", "Tire Pressure Monitoring System",
       "Direct TPMS receiver and sensor IDs.",
       Domain.CHASSIS, Tier.IMPORTANT, GIORGIO_NO, ("TPM",), "confirmed",
       "not a separate addressable module on Giulia/Stelvio; present on 500L"),
    _m("VDCM", "Vehicle Dynamics Control Module",
       "Vehicle-dynamics supervisor.",
       Domain.CHASSIS, Tier.CRITICAL),
]

# --- Safety and ADAS ------------------------------------------------------

_SAFETY = [
    _m("ORC", "Occupant Restraint Controller",
       "Crash sensing, airbag and pretensioner deployment, crash log.",
       Domain.SAFETY, Tier.CRITICAL, GIORGIO_YES, ("NAB", "SRS"), "corpus"),
    _m("OCM", "Occupant Classification Module",
       "Seat-track and weight sensing; decides passenger airbag enable.",
       Domain.SAFETY, Tier.CRITICAL, GIORGIO_LIKELY),
    _m("SIS", "Side Impact Satellite Sensor",
       "Remote side-impact accelerometers reporting to the ORC.",
       Domain.SAFETY, Tier.CRITICAL, GIORGIO_LIKELY),
    _m("EPPM", "Electronic Pedestrian Protection Module",
       "Active hood / pedestrian impact mitigation.",
       Domain.SAFETY, Tier.IMPORTANT),
    _m("DASM", "Driver Assistant System Module",
       "Front radar (Bosch MRR): adaptive cruise, forward collision warning, "
       "autonomous emergency braking.",
       Domain.SAFETY, Tier.IMPORTANT, GIORGIO_YES, (), "corpus"),
    _m("HALF", "Haptical Lane Feedback Module",
       "Forward camera (Bosch): lane keeping, traffic sign recognition, lane "
       "departure. Linked to DASM by a private CAN.",
       Domain.SAFETY, Tier.IMPORTANT, GIORGIO_YES, (), "corpus"),
    _m("NAC", "Adaptive Cruise Control Node",
       "Standalone ACC controller on older platforms.",
       Domain.SAFETY, Tier.IMPORTANT, GIORGIO_NO, (), "mes-lang",
       "superseded by DASM on Giorgio"),
    _m("FVCM", "Front View Camera Module", "Forward camera module.",
       Domain.SAFETY, Tier.IMPORTANT),
    _m("CVPM", "Central Vision Processing Module",
       "Multi-camera fusion / surround view.",
       Domain.SAFETY, Tier.IMPORTANT),
    _m("LBSS", "Left Blind Spot Sensor",
       "Rear corner radar: blind spot monitoring, rear cross-traffic alert.",
       Domain.SAFETY, Tier.IMPORTANT, GIORGIO_YES, (), "confirmed"),
    _m("RBSS", "Right Blind Spot Sensor",
       "Rear corner radar: blind spot monitoring, rear cross-traffic alert.",
       Domain.SAFETY, Tier.IMPORTANT, GIORGIO_YES, (), "confirmed"),
    _m("CMM", "Collision Mitigation Module", "AEB supervisor.",
       Domain.SAFETY, Tier.IMPORTANT),
    _m("PAM", "Parking Assist Module", "Ultrasonic parking sensors.",
       Domain.SAFETY, Tier.INFORMATIONAL, GIORGIO_YES, ("NSP",), "corpus"),
    _m("SPM", "Semi-automatic Parking Module", "Self-park steering control.",
       Domain.SAFETY, Tier.INFORMATIONAL),
    _m("VPAM", "Video Parking Aid Module", "Reversing camera.",
       Domain.SAFETY, Tier.INFORMATIONAL),
    _m("OMM", "Overweight Monitoring Module", "Payload monitoring.",
       Domain.SAFETY, Tier.INFORMATIONAL, GIORGIO_NO),
    _m("UAM", "Ultrasound / Tilt Sensor Module",
       "Alarm volumetric and tow-away sensing.",
       Domain.SAFETY, Tier.INFORMATIONAL, GIORGIO_LIKELY),
    _m("ASU", "Alarm Siren Control Unit", "Self-powered alarm siren.",
       Domain.SAFETY, Tier.INFORMATIONAL, GIORGIO_LIKELY),
    _m("ITM", "Intrusion Transceiver Module", "Intrusion detection.",
       Domain.SAFETY, Tier.INFORMATIONAL),
]

# --- Body -----------------------------------------------------------------

_BODY = [
    _m("BCM", "Body Computer Module",
       "Central body controller AND the B-CAN to C-CAN gateway: lighting, "
       "wipers, locks, windows, immobiliser, PROXI master. Faults here "
       "cascade across every other module.",
       Domain.BODY, Tier.CRITICAL, GIORGIO_YES, ("NBC",), "corpus",
       "Giorgio = Marelli 949 (Stelvio) / 952 (Giulia); 500L = 330. "
       "MES prints both 'Body Computer Module' and 'Body Control Module' "
       "for the same ECU - key on ISO code, not the heading."),
    _m("RFHUB", "Radio Frequency Hub Module",
       "RF keyfob, passive entry, TPMS RF receive.",
       Domain.BODY, Tier.IMPORTANT, GIORGIO_YES, ("RFHM", "RFH"), "corpus"),
    _m("WIN", "Wireless Ignition Node",
       "Start button and ignition authorisation.",
       Domain.BODY, Tier.CRITICAL),
    _m("NPE", "Passive Entry Node", "Keyless entry antennas.",
       Domain.BODY, Tier.IMPORTANT, GIORGIO_LIKELY),
    _m("NTR", "Transponder Reader Node", "Immobiliser coil and reader.",
       Domain.BODY, Tier.IMPORTANT, GIORGIO_LIKELY),
    _m("NPG", "Driver Door Module",
       "Window, mirror, lock and switch pack in the driver door.",
       Domain.BODY, Tier.INFORMATIONAL, GIORGIO_YES, ("DDM",), "corpus"),
    _m("NPP", "Passenger Door Module",
       "Window, mirror, lock and switch pack, passenger side.",
       Domain.BODY, Tier.INFORMATIONAL, GIORGIO_LIKELY, ("PDM",)),
    _m("RLDM", "Rear Left Door Module", "Rear left door controller.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("RRDM", "Rear Right Door Module", "Rear right door controller.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("LSMD", "Driver Latch Smart Module", "Driver e-latch door hardware.",
       Domain.BODY, Tier.IMPORTANT),
    _m("LSMP", "Passenger Latch Smart Module",
       "Passenger e-latch door hardware.",
       Domain.BODY, Tier.IMPORTANT),
    _m("DMCM", "Driver Mirror Control Module",
       "Power fold, memory and auto-dimming, driver side.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("PMCM", "Passenger Mirror Control Module",
       "Power fold, memory and auto-dimming, passenger side.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("NVB", "Boot / Trunk Node", "Tailgate release and latch.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("PLGM", "Power Lift Gate Module", "Powered tailgate (BROSE).",
       Domain.BODY, Tier.INFORMATIONAL, GIORGIO_YES, (), "confirmed",
       "Stelvio yes, Giulia no"),
    _m("RCU", "Roof Control Unit", "Sunroof and overhead console.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("NIM", "Ceiling Node", "Overhead console and interior lighting.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("ALU", "Ambient Lighting Module", "Interior mood lighting.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("IBS", "Intelligent Battery Sensor",
       "12 V battery state of charge and health, mounted on the negative "
       "post. Drives stop-start and load shedding; a failing battery or IBS "
       "is a classic cause of multi-module communication faults.",
       Domain.BODY, Tier.IMPORTANT, GIORGIO_LIKELY),
    _m("VTM", "Vehicle Tracking Module", "Anti-theft tracker.",
       Domain.BODY, Tier.INFORMATIONAL),
    _m("TTM", "Trailer Tow Module", "Trailer lighting and stability.",
       Domain.BODY, Tier.INFORMATIONAL, GIORGIO_LIKELY),
]

# --- Lighting -------------------------------------------------------------

_LIGHTING = [
    _m("AFLS", "Self-Adaptive Headlamps",
       "Cornering and matrix beam steering (AFS).",
       Domain.LIGHTING, Tier.IMPORTANT, GIORGIO_YES, ("NFA",), "corpus"),
    _m("AHLM", "Auto Headlamp Levelling Module",
       "Beam levelling from ride-height sensors.",
       Domain.LIGHTING, Tier.IMPORTANT, GIORGIO_LIKELY),
    _m("AHBM", "Auto High Beam Module", "Automatic high-beam switching.",
       Domain.LIGHTING, Tier.INFORMATIONAL, GIORGIO_LIKELY),
    _m("RLS", "Rain-Light Sensor",
       "Auto wipers, auto lights, windscreen fogging detection.",
       Domain.LIGHTING, Tier.INFORMATIONAL, GIORGIO_LIKELY, ("HRLS",)),
    _m("XEN", "Xenon Headlamp Ballast", "HID ballast and igniter control.",
       Domain.LIGHTING, Tier.IMPORTANT, GIORGIO_NO, (), "confirmed",
       "older Alfas"),
]

# --- Climate and comfort --------------------------------------------------

_CLIMATE = [
    _m("HVAC", "Climate Control Node",
       "Blend doors, blower, compressor request, cabin sensors.",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_YES, ("NCL",), "corpus"),
    _m("RLCM", "Rear Left Climate Control", "Rear-zone climate, left.",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_NO),
    _m("RRCM", "Rear Right Climate Control", "Rear-zone climate, right.",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_NO),
    _m("AHCP", "Auxiliary Heater Control Module",
       "Diesel or electric auxiliary heater.",
       Domain.CLIMATE, Tier.INFORMATIONAL),
    _m("CRS", "Supplementary Heater Control Unit",
       "PTC or Webasto supplementary heat.",
       Domain.CLIMATE, Tier.INFORMATIONAL),
    _m("CSWM", "Comfort Seat and Wheel Module",
       "Heated and ventilated seats plus heated steering wheel (Bitron).",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_YES, (), "confirmed"),
    _m("CRSM", "Comfort Rear Seat Module", "Heated rear seats (Bitron).",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_YES, (), "confirmed"),
    _m("NAG", "Driver Seat Node", "Power driver seat and memory position.",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_LIKELY),
    _m("NAP", "Passenger Seat Node", "Power passenger seat.",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_LIKELY),
    _m("HMSM", "Heated Memory Seat Module", "Combined seat heat and memory.",
       Domain.CLIMATE, Tier.INFORMATIONAL),
    _m("WCPM", "Wireless Charge Pad Module", "Qi phone charger.",
       Domain.CLIMATE, Tier.INFORMATIONAL, GIORGIO_LIKELY),
]

# --- Infotainment and telematics ------------------------------------------

_INFOTAINMENT = [
    _m("IPC", "Instrument Panel Cluster",
       "Gauges, warning lamps, odometer, driver information display. The "
       "odometer here is the VIN-lock reference.",
       Domain.INFOTAINMENT, Tier.IMPORTANT, GIORGIO_YES, ("NQS",), "corpus"),
    _m("ETM", "Entertainment Telematic Module",
       "Uconnect head unit: radio, navigation, media, phone.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_YES, (), "corpus"),
    _m("CTM", "Convergence Telematic Node",
       "Older-generation combined telematics and infotainment node.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_NO,
       ("NCV", "NIT", "L3"), "corpus",
       "ABBREVIATION COLLISION: MES also uses CTM for 'Additional Heater "
       "Node'. Disambiguate by MES group - Dashboard/Other means telematics, "
       "Climate control means heater."),
    _m("NRR", "Receiver Radio", "Base radio head unit.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_NO, (), "corpus"),
    _m("RMN", "Radio Navigator with Maps", "Navigation-equipped head unit.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL),
    _m("EMCM", "Entertainment Multimedia Control Module",
       "Multimedia controller.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL),
    _m("ICS", "Integrated Center Stack", "Centre-stack HMI.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL),
    _m("AMP", "Amplifier Node",
       "External audio power amplifier and DSP (Ask / Beats / Harman).",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_YES, (), "confirmed"),
    _m("MMCM", "Multimedia Control Module",
       "Rotary knob / joystick / touchpad HMI controller on the console.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_YES, (), "confirmed"),
    _m("SRM", "Satellite Receiver Module", "SiriusXM satellite tuner.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_LIKELY, ("SDARS",)),
    _m("CDM", "Compact Disk Module", "CD/DVD changer.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_NO),
    _m("DSM", "Display Screen Module", "Standalone display.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL),
    _m("TBM", "Telematic Box Module", "Connected-services modem.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL, GIORGIO_LIKELY),
    _m("ECSB", "Emergency Call System",
       "Automatic crash call (eCall).",
       Domain.INFOTAINMENT, Tier.IMPORTANT, GIORGIO_LIKELY, (), "mes-lang",
       "EU market; safety-relevant despite the infotainment grouping"),
    _m("TMM", "Traffic Message Module", "TMC traffic receiver.",
       Domain.INFOTAINMENT, Tier.INFORMATIONAL),
]

# --- Network / gateway ----------------------------------------------------

_NETWORK = [
    _m("SGW", "Security Gateway Module",
       "Gates write and actuation access on 2018+ FCA vehicles unless the "
       "tool is authenticated or bypassed.",
       Domain.NETWORK, Tier.CRITICAL, GIORGIO_YES, (), "confirmed",
       "Vendor lists Giulia/Stelvio as SGW-equipped, but this shop's own "
       "2018 Stelvio cleared codes successfully on five modules across four "
       "sessions - so it is not gating that car. Mechanism unresolved."),
    _m("CGW", "Central Gateway", "CAN domain router on newer architectures.",
       Domain.NETWORK, Tier.CRITICAL),
]

# --- MES pseudo-modules ---------------------------------------------------

_PSEUDO = [
    _m("SERVICE-RESET", "Service Interval Reset",
       "MES procedure page, not an ECU. Writes to IPC/BCM.",
       Domain.PSEUDO, Tier.INFORMATIONAL, GIORGIO_YES, (), "corpus"),
    _m("PROXI", "CAN Setup / PROXI Alignment Procedure",
       "MES network configuration tool, not an ECU. Its output is the node "
       "roster, not DTCs.",
       Domain.PSEUDO, Tier.IMPORTANT, GIORGIO_YES, (), "corpus",
       "The string contains ' / ' and will collide with a "
       "'<Group> / <ABBREV>' heading regex if applied to FES line 4."),
    _m("CAN-INFO", "CAN Info",
       "MES free-tier network identification page.",
       Domain.PSEUDO, Tier.INFORMATIONAL, GIORGIO_UNKNOWN, (), "confirmed"),
    _m("CAN-MONITOR", "CAN Monitor / Vehicle Settings",
       "MES body-configuration editor.",
       Domain.PSEUDO, Tier.INFORMATIONAL, GIORGIO_UNKNOWN, (), "confirmed"),
]


REGISTRY: dict[str, ModuleInfo] = {}
for _group in (_POWERTRAIN, _ELECTRIFICATION, _CHASSIS, _SAFETY, _BODY,
               _LIGHTING, _CLIMATE, _INFOTAINMENT, _NETWORK, _PSEUDO):
    for _info in _group:
        REGISTRY[_info.code] = _info

#: alias token -> canonical code. Built from the registry, then extended with
#: the free-text variants MES actually prints.
ALIASES: dict[str, str] = {}
for _code, _info in REGISTRY.items():
    ALIASES[_code.upper()] = _code
    for _a in _info.aliases:
        ALIASES[_a.upper()] = _code

#: MES's own group labels (Lang/English.txt keys 1101-1111). Retained for
#: reference only -- see the module docstring for why they are not used as the
#: display domain.
MES_GROUPS = ("Engine", "ABS", "Airbag", "Electric Steering", "Gearbox",
              "Dashboard", "Body", "Service", "Headlights", "Climate control",
              "Other")

#: MES placeholder when an ECU answers but its ISO code is not in MES's
#: database. Not a module name.
UNKNOWN_ECU_SENTINEL = "UNKNOWN/UNSUPPORTED"


def normalize_abbrev(abbrev: str) -> str | None:
    """Resolve an MES abbreviation (possibly a compound alias set) to a code.

    ``TCM/NCA/NCR`` resolves to ``TCM``: the compound is an alias set naming
    one module in three markets, not a compound identity. Tokens are tried in
    order so the canonical name wins when several are registered.
    """
    if not abbrev:
        return None
    cleaned = abbrev.strip().upper()
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    for token in (t.strip() for t in cleaned.split("/")):
        if token in ALIASES:
            return ALIASES[token]
    return None


def lookup(abbrev: str) -> ModuleInfo | None:
    """Look up module metadata from any MES abbreviation form."""
    code = normalize_abbrev(abbrev)
    return REGISTRY.get(code) if code else None


def describe(abbrev: str, *, category: str = "") -> dict[str, Any]:
    """Metadata for a module, with an explicit unknown rather than a guess.

    ``category`` resolves the one genuine abbreviation collision in MES's
    vocabulary: ``CTM`` is both the Convergence Telematic Node and the
    Additional Heater Node.
    """
    cleaned = (abbrev or "").strip()
    if cleaned.upper() == "CTM" and category.strip().lower() == "climate control":
        return {
            "code": "CTM-HEATER",
            "name": "Additional Heater Node",
            "description": "Auxiliary or parking heater.",
            "domain": Domain.CLIMATE.value,
            "tier": Tier.INFORMATIONAL.value,
            "on_giorgio": GIORGIO_NO,
            "source": "mes-lang",
            "note": "Disambiguated from the telematics CTM by MES group.",
        }

    info = lookup(cleaned)
    if info:
        return info.to_dict()
    return {
        "code": cleaned.upper() or "UNKNOWN",
        "name": cleaned or "unknown",
        "description": "not in the module registry",
        "domain": Domain.UNKNOWN.value,
        "tier": Tier.IMPORTANT.value,
        "on_giorgio": GIORGIO_UNKNOWN,
        "source": "none",
        "note": "unrecognised module abbreviation - reported as-is rather "
                "than guessed at",
    }


def sort_key(abbrev: str) -> tuple[int, str]:
    """Report ordering: most clinically significant modules first."""
    info = lookup(abbrev)
    if info is None:
        return (Tier.IMPORTANT.rank, (abbrev or "").upper())
    return (info.tier.rank, info.code)


def by_domain() -> dict[str, list[ModuleInfo]]:
    out: dict[str, list[ModuleInfo]] = {}
    for info in REGISTRY.values():
        out.setdefault(info.domain.value, []).append(info)
    for group in out.values():
        group.sort(key=lambda i: (i.tier.rank, i.code))
    return out


def registry_stats() -> dict[str, Any]:
    return {
        "modules": len(REGISTRY),
        "aliases": len(ALIASES),
        "by_domain": {d: len(v) for d, v in sorted(by_domain().items())},
        "by_tier": {
            t.value: sum(1 for i in REGISTRY.values() if i.tier is t)
            for t in Tier
        },
        "on_giorgio": sum(1 for i in REGISTRY.values()
                          if i.giorgio == GIORGIO_YES),
        "corpus_confirmed": sum(1 for i in REGISTRY.values()
                                if i.source == "corpus"),
    }
