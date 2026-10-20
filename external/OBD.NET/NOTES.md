# OBD.NET (NOTES ONLY, nothing copied)

- URL: https://github.com/DarthAffe/OBD.NET (last push 2022-06-06)
- Licence: GPL-2.0. Not copied.

## Facts (leads, unverified on our car)

- It names the STN filter commands in one command class: add pass filter STFAP, add block filter STFAB, add flow-control filter STFAFC; clear commands STFCP (pass), STFCB (block), STFCFC (flow-control); monitor STM / STMA. These names match the ScanTool.net STN command family and are lead material for a P1 "clear every filter after a physical session" step.
- Whether each clear command exists and returns OK on our vLinker FS (STN1170 v4.3.2) is UNVERIFIED. CUORE's own bench found that STFAC also removes the firmware's default pass filters (see `cuore/live/transport.py`, `Session.untarget`), so any clear must be followed by a protocol re-select.
- It has no NO DATA handling and no timeouts, so nothing else is of use.

## Why not copied

GPL-2.0. The command names are facts of the adapter's documented command set; take them from the STN11xx/STN21xx command reference, not from this code.
