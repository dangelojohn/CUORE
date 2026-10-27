# Serial-mirror capture: learning MES procedures without a second adapter

Status: PREPARED, NOT SET UP. Nothing has been installed, opened or run.
Code: `cuore/live/serial_mirror.py` (parser, pure), `cuore/live/serial_mirror_listen.py`
(read-only listener skeleton, refuses by default), `cuore/tests/check_serial_mirror.py`.
Related: `MES_LEARN_FIRST_SESSION.md` (the two-adapter route this replaces),
`cuore/live/procedure_capture.py` (review + gate), `CUORE_WRITE_CAPABILITY_PLAN.md`.

## What it is

MES talks to the adapter over COM3 in ELM327 text (STN1170 "vLinker FS", 115200 baud).
A PC-side mirror sits between them: MES opens a virtual port, the mirror forwards
everything to the real COM3 and copies every byte to two more virtual ports that
CUORE only reads. CUORE then sees MES's exact requests (ATSH / STP / STPX headers,
0x10 / 0x22 / 0x2F / 0x31 / 0x27 / 0x2E bytes) and the car's replies, as ELM text.
The parser rebuilds them into the same `{t, id, data}` frames `mes_learn` records,
so `procedure_capture.review` and `.gate` accept them unchanged.

Standing rule: CUORE never transmits through this path. The listener has no write
method, opens its ports with all flow control off, and stops if the driver queues
any TX byte. The mirror hub, not CUORE, is the only thing that touches COM3.

## What the parser handles

Echo on/off, `>` prompts, `SEARCHING...`, `NO DATA`, `BUS INIT`, ELM error lines,
0x78 responsePending (counted, not taken as the answer), the ATSH / ATCP / ATH /
ATE / ATS / ATCAF / ATSP / STP state, STPX `H:..., D:..., R:` sends, multi-frame
replies with headers on (PCI bytes, `18DAF118 10 0A ...` / `21 ...`) and with
headers off (`00E` then `0:` `1:` lines), with or without spaces. Anything else
goes to `unparsed` (with reason) and a count; nothing is dropped silently.
Only 29-bit `18DA<tt><ss>` requests become frames; 11-bit (STP 33 7E0/7E8) and
functional `18DB..` requests stay in `exchanges` and are counted as skipped.
Every 0x27 exchange is flagged (`flags.security_access`); the gate refuses it.

Limits: a serial mirror cannot see the bus bitrate or bus errors, so the capture's
`bitrate` is what the owner declares (500000 for CAN-C), not an observation.
A single mixed stream with no direction information is not supported.

## Setup (owner, numbered)

Outside facts below are labelled (OUTSIDE FACT). They come from general knowledge
of the free tools, were not checked here, and must be read against each tool's own
documentation before use. This document recommends no product beyond naming them.

1. Close MES. Note MES's current port (COM3). Unplug nothing from the car.
2. Install a virtual COM pair tool and a serial hub tool. (OUTSIDE FACT: com0com and
   hub4com are free, open-source, and are the tools this plan assumes; com0com
   installs a kernel driver, so read its signing and uninstall notes first. Any
   equivalent that provides virtual ports and one-to-many forwarding would do.)
3. Create three virtual pairs, each pair = one end for the hub, one end for a
   reader. Example names: `COM20`/`COM10` (MES side), `COM21`/`COM11` (copy of MES
   -> adapter), `COM22`/`COM12` (copy of adapter -> MES). Ends used by the hub:
   COM10, COM11, COM12. Ends used by programs: MES = COM20, CUORE = COM21 + COM22.
4. Hub routing (OUTSIDE FACT: hub4com takes `--route=<from>:<to,...>` options, one
   per direction, and a `--baud` option; confirm the syntax in its help). Intent:
   - bytes arriving from COM10 (MES) go to the real COM3 AND to COM11;
   - bytes arriving from COM3 (adapter) go to COM10 (MES) AND to COM12.
   Set 115200 8N1 on the real port, no flow control, everywhere.
5. Point MES at COM20 (its interface port setting). Leave CUORE's own adapter use of
   COM3 off while MES runs: one owner of COM3 at a time, the hub.
6. For a capture, set `CUORE_SERIAL_MIRROR_PORT=COM22` (adapter -> MES stream) and
   `CUORE_SERIAL_MIRROR_PORT_TX=COM21` (MES -> adapter stream) and start the
   listener with an explicit `out_dir`. It refuses if either is unset, the same,
   COM3, MES's own port, or listed in `CUORE_SERIAL_REAL_PORTS`.

## Validation order

1. Dry link check, no car actions: start the hub, open MES, connect, do nothing.
   MES must connect as fast as it did on COM3.
2. Mirror a plain MES parameter READ session (live data on the ECM). Compare, line
   by line, `exchanges` and the multi-frame replies against MES's own log/CSV for
   the same minute. Only when the DIDs, values and targets agree is the parser
   trusted.
3. Only then a commanded test (e.g. the ESIM vent test: engine/fuel prerequisites
   per `MES_LEARN_FIRST_SESSION.md`), with a battery maintainer on.
4. NEVER run the mirror during PROXI or battery writes (or any flash, coding or
   0x27/0x2E session). Those go straight to COM3, mirror stopped and MES repointed.

## Failure modes and how to recognise them

| Symptom | Likely cause | Action |
|---|---|---|
| MES reports timeout / "no response" it did not have on COM3 | hub adds latency or drops bytes | stop; rollback; do not capture |
| Burst of `NO DATA` / `?` / `BUFFER FULL` / `DATA ERROR` in the stats | two writers on COM3, wrong baud, or a buffer overrun in the hub | stop; check only the hub holds COM3 |
| `unparsed` count growing, text like binary noise | wrong baud on a virtual end | fix baud; discard capture |
| Replies with no requests (or the reverse) | one direction not routed | fix routing; discard |
| `incomplete_multiframe` flags | mirror stream cut mid reply | discard that exchange |
| Echo lines absent while requests present | ATE0 in use: fine, parser handles it | none |
| Listener raises "queued for TRANSMIT" | something wrote to a mirror port | stop; find the writer |

## Rollback

Close MES, stop the hub, set MES's interface port back to COM3, reconnect and read
one parameter. The virtual ports can stay installed and unused, or be removed with
the tool's own uninstaller. Nothing in the car was changed by the mirror.

## What the capture enables

`to_capture` frames -> `procedure_capture.review` (services, 0x27, writes) ->
dry run (`procedure_dry_run`) -> `gate` (allowlist, stop step, bus/bitrate, recorded
engine state and voltage, interlock) -> only then a first CUORE-run actuation under
the existing consent rules. Verified on synthetic fixtures: a 0x2F start with its
stop step reviews as replayable and passes the gate under engine-off conditions; a
0x27 seed/key exchange is captured, flagged and refused by review and gate.
Mirrored text carries no bus timing, so the dry run's timing comes from the
mirror timestamps (hub latency included) and should be read as approximate.
