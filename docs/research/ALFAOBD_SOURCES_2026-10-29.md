# AlfaOBD research log, 2026-10-29
Kept outside the public repo (vendor material, forum summaries). Study: docs/project/ALFAOBD_GAP.md (copy here).

## Files here
- AlfaOBD_Help.pdf: vendor Windows help manual, fetched from https://www.alfaobd.com/AlfaOBD_Help.pdf (19 pages, generic; names no Giulia, Stelvio, PROXI or paddle function).
- AlfaOBD_Help.extracted.txt: text extracted from it.

## Pages read (summaries from the fetch tool, not verbatim)
- https://www.alfaobd.com/ : features (live data, ECU ID, DTC read/clear with freeze frame, active diagnostics, service/oil/DPF/ABS bleed/air suspension/transmission calibration, key and RF remote on some models, configuration and Proxy alignment); adapters (OBDLink MX+, EX, LX, CX, ELM327 1.3+, OBDKey, Kiwi 3, J2534); Giulia/Stelvio need grey adapter, MX+/EX and vLinker MS need no blue; 2018+ hardware SGW bypass with pins 12 and 13 (range-wide statement); Windows, Android, Mac via Windows; not iOS.
- http://www.alfaobd.com/supported_cars.html : Giulia 2015+, Stelvio 2016+, "OBDLink MX+ / EX + grey adapter"; no function lists.
- https://www.alfaobd.com/download.html : paid per-platform licences, free demo, no VIN lock; PC 2.5.7.0 and Android 2.4.4.0 added 2020-24 models (Aug 2025).
- https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80 : MES settings table: paddle byte 156 bits 4-5 (EU xx00xxxx, US xx01xxxx, PROXI alignment needed); battery byte 63 bits 0-3; cornering lights byte 149; race mode byte 88; ACC+; window comfort byte 58 bit 1; after-wipe byte 126 bit 5; TPMS pressures (RFHub, no alignment); seat belt chime (cluster, no alignment). DRL, door lock, Start/Stop, mirrors not covered.

## Search-summary only (pages paywalled via tollbit, not read)
- https://www.giuliaforums.com/threads/diy-add-paddle-shifters.44122/ : one owner coded EU paddles on a 2017 QV with AlfaOBD on Android via Body computer, Car Configuration Change, search "paddle".
- https://www.giuliaforums.com/threads/alfaobd-and-multiscanecu-some-alfaobd-settings-i-was-surprised-by.55899/ : logic 0 enables EU paddle control; compass display mentioned.
- https://www.giuliaforums.com/threads/alfaobd-for-proxi-alignment.58085/ : PROXI alignment worked on Android with vLinker MC+ and grey adapter; another owner had AlfaOBD fail partway on some modules.
- https://www.giuliaforums.com/threads/what-are-proxi-parameters-for-agm-battery-on-giulia-2-2.65519/ : battery type set to AGM H8 in AlfaOBD, then aligned in MES.
- https://www.stelvioforum.com/threads/neutral-with-the-paddles.18171/ : EU neutral works on Stelvio as on Giulia (forum claim).
- https://www.multiecuscan.net/forum/viewtopic.php?p=29086 : PROXI alignment timed out on a Bluetooth vLinker MS (one user).
- https://shop.imlss.com/item_view/item/601163 : key programming on Giulia 2018+/Stelvio 2019-23 with SGW bypass cable (vendor listing).

## Owner statements this session
- Alfa corporate supplied a purchased AlfaOBD licence on a tablet with an OBDLink MX+; grey and other adapters available; not yet connected to CUORE.
- 2018 Stelvio needs no SGW bypass (owner: confirmed with MES and AlfaOBD use); local evidence in docs/research/CONNECTIVITY_AND_SGW.md section 2.
- Rule: CUORE never learns a write by capturing AlfaOBD or MES.
