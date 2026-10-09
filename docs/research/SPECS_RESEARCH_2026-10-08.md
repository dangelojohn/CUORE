# Specs research pass -- 2026-10-08

Target: fill UNKNOWN rows in `mes-log-mcp/mes/mechanic_tests.py` (and
`known_good.py`/`service_specs.py` where a value belongs there instead) for
the 2018 Alfa Romeo Stelvio 2.0T GME (engine 55273835 family, Giorgio
platform; Giulia 2.0T shares the engine). Same house rule as every other
sourced file in this repo: never invent a number. Grading: CONFIRMED
(FCA/Alfa/Mopar/TechAuthority doc or owner's manual) / CORROBORATED (two
independent reputable sources agree) / SINGLE-SOURCE (one named source) /
UNKNOWN (nothing credible -- left as prose pointing at the service manual).

No paywalled/bot-gated FCA TechAuthority document was read for this pass.
Both `giuliaforums.com`, `stelvioforum.com` and `alfabb.com` thread fetches
redirected to a `tollbit.<site>` bot-gate during this pass (same obstacle
`known_good.py`'s and `service_specs.py`'s own research passes already
recorded) -- not resolved, so those threads are **not** treated as read;
only the search engine's own result-snippet summaries of them were
available, and per this project's own prior precedent (see
`known_good.py` engine_rpm/coolant_temp notes) a bot-gated-summary is not
promoted to a source citation.

## Result summary

| Value sought | Found? | Grade | Change made |
|---|---|---|---|
| Cooling-system cap / system test pressure | No usable figure | UNKNOWN (unchanged) | none |
| Low-side fuel rail pressure, idle/load | No usable figure | UNKNOWN (unchanged) | none |
| DI high-side fuel rail pressure, idle/load | No usable figure | UNKNOWN (unchanged) | none |
| Oil pressure, hot idle | No usable figure | UNKNOWN (unchanged) | none |
| Oil pressure, 2000-3000 rpm | No usable figure | UNKNOWN (unchanged) | none |
| EVAP purge valve duty | No usable figure | UNKNOWN (unchanged) | none |
| EVAP vapour pressure limits | No usable figure | UNKNOWN (unchanged) | none |
| Ignition coil bolt torque | No usable figure | UNKNOWN (unchanged) | none |
| Spark plug torque | Already sourced | CORROBORATED (pre-existing) | none needed |
| Spark plug gap / part number | Already sourced | CORROBORATED (pre-existing) | none needed |
| Battery / charging voltages | Already sourced | CORROBORATED (pre-existing) | none needed |
| Compression / leak-down absolute expectation | No usable figure | UNKNOWN (unchanged) | none |
| CAN bus resistance | Confirmed generic standard corroborates existing figure | SINGLE-SOURCE -> **CORROBORATED** | `mechanic_tests.py` `can_bus_resistance_test` |

Only one row changed confidence level. Everything else searched for this
pass stays UNKNOWN -- not because no number exists anywhere, but because no
number was found this pass that clears this project's own bar (a named,
checkable, non-bot-gated source, or two of them agreeing).

## Detail, value by value

### Cooling-system cap / system test pressure

Searched: `"Stelvio Giulia radiator cap pressure rating bar psi"`,
`"Alfa Romeo Stelvio Giulia radiator cap Mopar part number pressure rating
bar RockAuto"`.

One eBay aftermarket-cap listing claims "1.1 Bar / 13 PSI" and lists
fitment across the Stelvio **and** Giulia Quadrifoglio **and** Giulia
Sprint -- different engines/years on one generic "fits" listing, which is
exactly the kind of unreliable, non-vehicle-specific aftermarket fitment
claim this project's sourcing bar is meant to exclude (c.f.
`known_good.py`'s TPMS note rejecting a similarly-styled aggregator
figure). The genuine Mopar OEM radiator cap part number (4596198, and a
separate `52028974AA` catalog number) was found, but neither Mopar listing
page states a bar/psi rating. No service-manual or TechAuthority figure
reached. **Left UNKNOWN** in `mechanic_tests.py` (`radiator_cap_test`,
`cooling_system_pressure_test`) -- no code change.

Source checked (rejected): https://www.ebay.com/itm/394565643254 (accessed
2026-10-08) -- rejected as unreliable multi-fitment aftermarket listing,
not adopted.

### Fuel pressure, low side and DI high side (idle and under load)

Searched: `"Alfa Romeo Giulia Stelvio 2.0 GME fuel rail pressure bar spec
high side direct injection"`; attempted fetch of
`giuliaforums.com/threads/anyone-know-what-the-stock-fuel-pressure-is-on-the-2-0.52288/`
(bot-gated, not read) and
`go-parts.com/garage/obd-p0087-alfa-romeo-giulia-2017-2018` (HTTP 403, not
read).

A search-engine summary claims a DI rail pressure "topping out at about
3,000 PSI (~207 bar)" and a lift-pump pressure of "about 30-40 PSI", but
this is the search engine's own paraphrase of unidentified underlying
pages, not a page this pass actually read -- no URL could be attributed to
either number, so it fails this project's citation bar outright (an
unsourced number is indistinguishable from an invented one). **Left
UNKNOWN** in `mechanic_tests.py` (`fuel_pressure_test`, both the low-side
and high-side rows) -- no code change.

### Oil pressure, hot idle and 2000-3000 rpm

Searched: `"Alfa Romeo 2.0 Multiair turbo oil pressure spec psi bar idle"`;
attempted fetch of
`giuliaforums.com/threads/warm-oil-pressure-at-idle-for-2-0t.45802/`
(bot-gated, not read).

Same problem as fuel pressure: a search-engine summary cites "33 psi at
idle and 68 psi at 5,000 rpm" attributed only to an unnamed forum post
inside a thread this pass could not actually open, mixed in with unrelated
generic/older-Alfa-model oil pressure folklore (156, Spider, 164 -- not
this engine) from the same result set. No attributable, checkable source.
**Left UNKNOWN** in `mechanic_tests.py` (`oil_pressure_test`) -- no code
change.

### EVAP purge valve duty and vapour pressure limits

Already covered in `known_good.py` (`commanded_evap_purge`,
`evap_vapor_pressure`, `evap_vapor_pressure_abs`) from the 2026-09-26
research pass, with an explicit note that this platform exposes no
readable EVAP UDS DID and that no OEM/corroborated figure exists anywhere
in that pass. This pass's searches turned up nothing new (no FCA
TechAuthority document reached, no additional independent source for a
duty-cycle or vapour-pressure number). `purge_vent_actuation` in
`mechanic_tests.py` is a pass/fail actuation check, not a numeric spec, so
it is unaffected either way. **Left UNKNOWN** -- no code change.

### Ignition coil bolt torque

Searched: `"Giulia 2.0 ignition coil bolt torque Nm"`, `"Alfa Romeo Giulia
Stelvio 'coil' bolt torque Nm alfaowner OR alfabb"`.

No thread, listing, or document naming a coil-bolt torque figure for this
engine was found in either pass -- results returned wheel-bolt and
spark-plug torque threads (already sourced elsewhere) and coil-bolt specs
for unrelated makes (Toyota/Nissan). `service_specs.py`'s
`TORQUES["coil_pack_bolt"]` already correctly states "No sourced torque
value found." and stays UNKNOWN -- no code change.

### Spark plug torque / gap / part number

Already sourced and not UNKNOWN: `service_specs.py` `TORQUES["spark_plug"]`
is CORROBORATED (19-20 Nm, two figures from
https://www.giuliaforums.com/threads/inconsistent-spark-plug-torque-specs-2-0l.64916/
treated as agreeing within rounding); part number and gap are in
`maintenance_specs.py` (`NGK 90219 (ILZKR7G7G) / Mopar 68292346AA`,
CORROBORATED, with the gap figure's own source disagreement already
flagged in that module's notes). Nothing to add.

### Battery and charging voltages

Already sourced and not UNKNOWN: `known_good.py` `battery_voltage`
(CORROBORATED, 13.5-14.7 V running / ~12.2-12.8 V resting, generic
lead-acid reference) and `mechanic_tests.py`
`charging_voltage_ripple_test` (CORROBORATED, same 13.5-14.7 V band, same
source). Nothing to add.

### Compression / leak-down absolute expectation

Searched: `"Alfa Romeo Giulia Stelvio 2.0 compression test psi spec
cranking compression"`.

A search-engine summary cites per-cylinder compression numbers for
cylinders "1 through 6" -- that is a V6 (Quadrifoglio), not this car's
inline-4 2.0T, so it is the wrong engine and was discarded outright, not
treated as even single-source evidence. A theoretical psi figure computed
from the engine's compression ratio (10.0:1) and atmospheric pressure was
also offered by the search summary, but a calculated number is not a
measured spec and this project's own house rule treats a computed
stand-in as exactly the kind of guess it forbids. **Left UNKNOWN** in
`mechanic_tests.py` (`compression_test` absolute-compression row) -- no
code change. (The existing 10% cylinder-to-cylinder variation row in the
same test, and in `relative_compression_test`/`cylinder_leak_down_test`,
is unaffected -- that was already sourced as an industry-practice rule of
thumb, not from this pass.)

### CAN bus resistance

Searched: `"FCA Stellantis CAN bus termination resistance 60 ohm
specification diagnostic"`.

No FCA/Stellantis-specific document was found (none expected -- CAN bus
termination is a physical-layer standard, not an OEM-specific figure).
What the search did turn up is multiple independent, reputable
technical-reference sources (apextechnation.com, industrialmonitordirect.com,
gridconnect.com, canbusdebugger.com; accessed 2026-10-08) all stating the
same underlying physics: ISO 11898 (the CAN physical-layer standard this
platform's bus implements, like virtually every modern OBD-II vehicle)
specifies two 120-ohm termination resistors, one at each end of the bus,
which measure as **60 ohm in parallel** between CAN-H and CAN-L (OBD
connector pins 6 and 14) with the key off and the bus otherwise
undisturbed -- exactly the figure already in `mechanic_tests.py` as an
`INDUSTRY_PRACTICE`/`SINGLE_SOURCE` row. This is a second, independent,
named, non-bot-gated source agreeing with the existing one -- the
`CORROBORATED` bar this project defines (two independent reputable sources
agreeing), not a Stelvio-specific CONFIRMED figure (no manufacturer
document was read), but stronger than the single `INDUSTRY_PRACTICE`
label it had.

**Change made**: `mechanic_tests.py` `can_bus_resistance_test`'s
`"CAN-H to CAN-L resistance, key off"` pass-criteria row is upgraded from
`SINGLE_SOURCE` to `CORROBORATED`; the source string now cites both the
original industry-practice framing and the ISO 11898 standard basis, and
`fail_means` is left unchanged (the figure itself, 60 ohm, is unchanged --
only the confidence grade and citation improved).

Sources (accessed 2026-10-08):
- https://apextechnation.com/articles/can-bus-diagnostics
- https://industrialmonitordirect.com/blogs/knowledgebase/can-bus-network-termination-resistor-specifications-practical-implementation-and-troubleshooting
- https://www.gridconnect.com/blogs/news/how-to-diagnose-a-controller-area-network-can
- https://www.canbusdebugger.com/articles/can-bus-termination

## Why so little changed

This pass's searches repeatedly ran into the same two walls the prior
`known_good.py`/`service_specs.py` passes already documented: (1) the
Alfa/Giulia/Stelvio owner-forum threads most likely to carry a real-world
number are bot-gated (`tollbit.<site>` redirects) and were not resolved,
so this pass -- like the ones before it -- could only see a search
engine's own paraphrase of them, which this project's existing precedent
(see `known_good.py` notes on `engine_rpm`/`engine_coolant_temp`) already
treats as not a citable read; and (2) no FCA/Stellantis TechAuthority
document is reachable without a paid/dealer login. Where a search summary
offered a number with no attributable source, or attributed to the wrong
engine (a V6 compression result bleeding into a 2.0T four-cylinder
search), it was discarded rather than adopted, per the "never invent a
number" rule -- an unsourced or misattributed number is worse than an
honest UNKNOWN.
