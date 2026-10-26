# Electrical component inventory (summary)

Data: `components_inventory.json` (145 rows). Verified to contain no part numbers (catalogue part numbers were deliberately omitted).

Sources per row: Mopar diagram ids (113 references), MES parameter names (77), CUORE element ids (22). A row can have several.

Counts by category: module 34, other 21, switch 15, sensor 15, actuator 13, solenoid valve 9, pump 6, horn/speaker 5, lamp 5, motor 5, connector 4, heater 4, ground 4, gauge/display 2, antenna 2, relay 1.

Areas seen: engine_bay, rear_left_wheel_well, underbody. Only 4 of 145 rows have an area, because Mopar diagrams carry no area field; area is set only when a CUORE element supplies a zone.

Gaps and caveats:
- 141 rows have no physical area.
- Washer pump, rear window heater and starter relay are known only from CUORE fuse labels.
- Merges by name equivalence: PAM = Park Assist Module, IPC = Instrument Panel Cluster, HVAC module = Mopar "Power Module" (weakest merge). Not merged because not proven the same: Passive Entry Module vs RFHUB, Power Transfer Unit Control Module vs DTCM, Collision Module vs DASM, Steering Column Module vs CSWM.
- ABS, BCM, TCM etc. (other than ECM and IPC) have zero parsed MES parameters, so no switches/actuators come from them.
- Generic fuses and relays are not itemised.
- Catalogue items are parts that exist in the catalogue, not proof the car is so equipped.
