# External References and Licences

On 2026-10-20 two reviews looked at public GitHub projects for Giorgio, Alfa Romeo and Maserati CAN data and for OBD and UDS tooling: [GITHUB_REVIEW_GIORGIO](https://github.com/dangelojohn/CUORE/blob/main/docs/research/GITHUB_REVIEW_GIORGIO.md) and [GITHUB_REVIEW_TOOLING](https://github.com/dangelojohn/CUORE/blob/main/docs/research/GITHUB_REVIEW_TOOLING.md). The results are kept in a reference area, [`external/`](https://github.com/dangelojohn/CUORE/tree/main/external), whose index is [external/README.md](https://github.com/dangelojohn/CUORE/blob/main/external/README.md). A third document, [EXTERNAL_IMPLEMENTATION_REVIEW](https://github.com/dangelojohn/CUORE/blob/main/docs/research/EXTERNAL_IMPLEMENTATION_REVIEW.md), turns the material into ten implementation points with file targets, risk, bench test and priority. This page explains the rules and what was kept.

## The lead-not-proof rule

**Facts from external sources are leads, never proof for a diagnosis.** A conclusion about the reference car cites CUORE's own readings from that car. Every external id, data identifier, scale or timing is "unverified on our car" until CUORE's own capture or read confirms it, and a signal is upgraded to "confirmed on this car" only after a recorded comparison. The reviews themselves were made partly through a small model summarising pages, so quotes are paraphrase-grade; anything not opened is marked UNVERIFIED. This is the same rule that keeps outside bulletins out of the evidence gate ([[Evidence Model|Evidence-Model]]).

## The four rules of the `external/` area

1. **Nothing in `external/` is imported by CUORE** until it has been reviewed. The only reviewed use today is the CAN database, which CUORE keeps as its own copy under `cuore/data/dbc/` with the licence notice beside it ([[Passive Chassis Decoding|Passive-Chassis-Decoding]]). The excerpts are not runnable and are not on any import path.
2. **Facts are leads** (above).
3. **Licence first.** Permissive licences (MIT, BSD, Apache-2.0): files are copied verbatim with the project's licence text (and notice file where one exists) and a `SOURCE.md` giving URL, commit, fetch date, paths and licence. Copyleft, non-commercial, share-alike or unlicensed projects: a `NOTES.md` only (URL, licence, the facts in CUORE's own words, and why nothing was copied). No code or data from those projects is stored anywhere in the tree.
4. **Upstream wins.** If a `SOURCE.md` and the upstream disagree, refetch rather than edit a copied file.

The reason for the licence rule is practical: CUORE may one day be distributed or sold, and non-commercial, share-alike or copyleft material cannot be merged into it. For a project with no licence at all, all rights are reserved by default, so it is read as a lead only. This is a reading of the licence fields, not legal advice.

## What was copied and what was notes only

| Project | Licence | Kept as | What it gave |
|---|---|---|---|
| commaai/opendbc | MIT | **Copied verbatim**: `fca_giorgio.dbc` (whole, 37 messages) and excerpts of its UDS and ISO-TP code | The CAN-CH message and signal names; drain-before-send; the pending-response loop (keep waiting, no resend); the Chrysler/FCA identity queries (`F132`, `F194`) and the reply offset of minus `0x280`; a parallel-query pattern |
| pylessard/python-udsoncan | MIT | Verbatim excerpts | Timing defaults (P2 1 s, P2* 5 s) and how a request waits, switches once to the longer timer on a pending reply, and empties the receive queue first |
| pylessard/python-can-isotp | MIT | Verbatim excerpt | Flow-control separation-time decoding; default parameters |
| tzebrowski/ObdMetrics | Apache-2.0 | Whole file with licence | Adapter error-reset and recovery command sequences |
| PowerBroker2/ELMduino | MIT | Verbatim excerpt | Flush the input before sending |
| electricimp/STN1110 | MIT | Verbatim excerpt | Reset and timeout-abort sequence |
| AriotaG/AlfaRaceX-Framework | Apache-2.0 | Verbatim data and licence | A small CAN id table and the bus bit-rate profile for a Stelvio (a different, diesel model year) |
| python-OBD, OBD.NET | GPL-2.0 | **Notes only** | Layout of Mode 06 records; ST command names. Copyleft, nothing copied |
| caringcaribou, stn1170-tools | GPL-3.0 | Notes only | Adapter reset checks; filter-clear names |
| ClaudeMarais dashboard projects | CC BY-NC 4.0 | Notes only | Module addresses and data identifiers for a 2019 Giulia petrol. Non-commercial, so not merged |
| BACCAble firmware | Unclear (no grant for its own code) | Notes only | Module addresses, ids by bus. Treated as all rights reserved; raw ids are facts about the car that CUORE can recapture itself |
| ELM327-emulator (Ircama) | CC BY-NC-SA 4.0 | Notes only | A fake adapter, explicitly **not** used (non-commercial, and it does not model the adapter's state) |
| OBDb | CC BY-SA 4.0 | Notes only | The Giulia signal set there is empty |
| giulia_ESCape | None stated | Notes only | Two broadcast ids |

Reviewed and judged not worth saving: a GranCabrio CAN project (an older Maserati architecture with no id overlap), a sim-racing cluster driver (ids sit in unopened archives), a LIN climate-panel repository (LIN, not CAN or UDS), and two repositories advertising cracked diagnostic software, which were never opened and are not recommended.

## Leads that matter (all unverified on our car)

These are the facts the reviews extracted, with the status CUORE gives them:

- **CAN-CH ids.** The Giorgio database names eight of the nine ids heard most often on the chassis bus (the ninth, `0x11C`, is carried as an unnamed message with a speed signal). CUORE decodes them listen-only ([[Passive Chassis Decoding|Passive-Chassis-Decoding]]).
- **Module addresses** in third-party code (instrument cluster `0x60`, keyless hub `0xC7`, engine `0x10`, transmission `0x18`, body `0x40`) **agree** with CUORE's own confirmed addresses. The one **conflict** is the brake module: a third-party firmware puts it at `0x28`, while CUORE's own identity read matched this car's identifier at `0x2A`. Settling it is a small read-only check on the implementation list ([[Vehicle Networks|Vehicle-Networks]]).
- **Data identifiers** for coolant temperature (`0x1003`) and battery voltage (`0x1004`) on a similar 2019 engine agree with CUORE's own freeze-frame layout; agreement is a hint only ([[Evidence Model|Evidence-Model]]).
- **Reply offset.** Chrysler/FCA firmware queries answer on request id minus `0x280`; nothing says this car's modules do. A hit is a lead; a miss is not proof of absence.
- **Keep-alive ids.** The camera is the listed sender of a `1E36001E` frame, so `0x1E` is the first candidate for the camera's address.
- **Still not found anywhere reviewed:** addresses for the steering, airbag, camera, parking, adaptive-light, climate and head-unit modules; the meaning of the keep-alive ids; any switch-state identifier for the leak-detection module; manufacturer routine identifiers; Mode 06 test meanings; Maserati data on this platform; meanings for several body-bus ids.

## What was built from it

Landed in the tree on 2026-10-20, bench-tested only, **nothing run on the car**: drain-before-send with a stale-reply audit, an opt-in adapter hard reset and flow-control restore, the alternative 11-bit addressing pass with an identity-DID probe, the passive chassis decoder, and the broadcast-id safety rule ([[Safety Rules|Safety-Rules]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]]).

Still open from the implementation review: a continuous (held) passive channel set and on-car validation of the decoder; a short quiet-period read after each reply; a test of whether a bare carriage return after a timeout repeats the previous request; stopping the re-send on a pending reply and aligning timers with the adapter wait; re-deriving the Mode 06 unit table from the standard rather than copying; a stateful fake adapter for the bench; the brake-address cross-check; keep-alive low bytes as ordered candidates for the 29-bit sweep. Nothing external covers the leak-detection module's internals, so that item adds no import and nobody should wait on one.

## Gaps that are not a licence matter

- GitHub code search needs authentication, so the adapter's own command reference was not fetched; adapter command spellings come from other projects' sources and are unverified on the reference adapter.
- The standards text (ISO 14229, SAE J1979) is not on GitHub and is paid; the Mode 06 unit table has to be re-derived from it.

Related: [[Vehicle Networks|Vehicle-Networks]], [[Hardware and Cables|Hardware-and-Cables]].
