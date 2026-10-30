# Budget setup: running CUORE on a USB adapter

For mechanics moving from MultiEcuScan (MES). CUORE uses the same kind of USB adapter, on the same COM port.

## Reference adapter

The adapter CUORE was tested with is a vLinker FS USB: genuine STN1170 firmware v4.3.2, reports "ELM327 v2.3", COM3 at 115200 (CUORE session records). MES Interface 0 on the same machine points at the same COM3.

## 1. Install the driver

The adapter appears as a USB serial (FTDI-type) device. Install the driver the adapter's maker supplies, then unplug and replug the adapter.

## 2. Find the COM port

Open Device Manager, expand "Ports (COM & LPT)", and note the number shown for the adapter (for example COM3). If it shows with a yellow mark, the driver is not installed.

## 3. Tell CUORE the port

CUORE reads the port from the `CUORE_OBD_PORT` environment variable; if unset it uses the port MES is configured with. The Settings page (`/settings`) shows the port and where it came from. The Hardware page (`/hardware`) shows MES's configured interface next to CUORE's.

## 4. Share the adapter with MES

Only one program can hold the adapter. Close MES completely before CUORE uses it; CUORE refuses while MES is connected. Close CUORE's session before opening MES.

## 5. Check the adapter

Plug into the car, ignition on, open `/hardware` and press "Probe the adapter now". The table shows pass, limited, fail or not tested for each CUORE function, with the reason.

## 6. When the A5 and A6 cables are needed

The blue A5 (CAN-IHS) and grey A6 (CAN-CH) bypass cables are needed only to reach those two buses. Module reads on CAN-C through the OBD port do not need them. Declare the cable you fitted in CUORE (set_cable) so CUORE knows which buses it can reach.

## What "untested" means

Only the vLinker FS USB and the A5/A6 cables are tested, on one reference car. Any other adapter, including the OBDLink MX+ (Bluetooth) and generic ELM327 clones, is listed as untested: it may work, but there is no CUORE record. ELM clones have small buffers, so long module reads and listen-only recording may lose frames.
