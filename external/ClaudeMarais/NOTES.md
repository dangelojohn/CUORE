# ClaudeMarais: AlfaRomeoGiulia_DashboardInfo_ESP32-S3 and Simple_OBD2_for_AlfaRomeoGiulia (NOTES ONLY)

- URLs: https://github.com/ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3 ; https://github.com/ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia
- Licence: CC BY-NC 4.0 (non-commercial; also incompatible with merging into MIT/Apache code). Not copied: CUORE may one day be distributed or sold.
- The author states the values work on a 2019 Giulia 2.0 petrol at 500 kbps.

## Facts (leads, "unverified on our car"; formulas were not read)

- Physical requests use 29-bit ids 0x18DA<module>F1; functional is 0x18DB33F1. Modules named: ECM 0x10, TCM 0x18, BCM 0x40. Replies come back as 0x18DAF1<module>.
- Service 0x22 DIDs on the ECM: boost pressure 0x195A, coolant temperature 0x1003, oil temperature 0x1302, exhaust gas temperature 0x18BA, atmospheric pressure 0x1956, battery voltage 0x1004. BCM: ignition key position 0x0131.
- Broadcast ids named: drive mode 0x384, gear 0x2EF, engine RPM 0x0FC, dashboard text 0x090.
- 0x1003 and 0x1004 agree with the ids in CUORE's own ECM freeze-frame layout work. That agreement is a hint only, not proof for any diagnosis.

## Why not copied

Non-commercial licence. CUORE already records these as sourced leads in `cuore/live/addressing.py` and `cuore/live/did_catalog.py`; any further use needs a CUORE reading of its own.
