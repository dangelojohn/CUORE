# external/: third-party material kept for reference

Fetched 2026-10-20 from the projects named in docs/research/GITHUB_REVIEW_GIORGIO.md and docs/research/GITHUB_REVIEW_TOOLING.md. Implementation plan that uses it: docs/research/EXTERNAL_IMPLEMENTATION_REVIEW.md.

## Rules

1. Nothing in `external/` is imported by CUORE until it has been reviewed. The only reviewed use today is the DBC, which CUORE keeps as its own copy at `cuore/data/dbc/` with the MIT notice beside it. Excerpts here are not runnable and are not on any import path.
2. Facts from external sources are leads, never proof for a diagnosis. Project rule: conclusions cite CUORE's own readings from this car. Every external id, DID, scale or timing is marked "unverified on our car" until our own capture or read confirms it.
3. Licence first. Permissive licences (MIT, BSD, Apache-2.0): files copied verbatim with the project's LICENSE (and NOTICE where one exists) and a SOURCE.md giving URL, commit, fetch date, paths, licence. Copyleft, non-commercial, share-alike or unlicensed projects: NOTES.md only (URL, licence, facts in our own words, why nothing was copied). No code or data from those projects is stored anywhere in this tree.
4. If a SOURCE.md and the upstream disagree, upstream wins; refetch rather than edit a copied file.

## Index

| Folder | Project | Licence | Saved | Copied or notes only |
|---|---|---|---|---|
| `opendbc/` | commaai/opendbc | MIT | `fca_giorgio.dbc` (whole), IsoTpMessage/CanClient drain code, UdsClient pending loop, FCA F132/F194 + RX offset, parallel query | copied (verbatim) |
| `python-udsoncan/` | pylessard/python-udsoncan | MIT | timing defaults (`configs.py`), `send_request` P2/P2* logic, `SessionTiming` | copied (verbatim excerpts) |
| `python-can-isotp/` | pylessard/python-can-isotp | MIT | flow-control STmin decode, `Params` defaults | copied (verbatim excerpt) |
| `ObdMetrics/` | tzebrowski/ObdMetrics | Apache-2.0 | `DefaultCommandGroup.java` (CAN_ERROR_RESET and recovery sequences), LICENSE | copied (whole file) |
| `ELMduino/` | PowerBroker2/ELMduino | MIT | flush-before-send excerpt | copied (verbatim excerpt) |
| `STN1110/` | electricimp/STN1110 | MIT | reset and timeout-abort excerpt | copied (verbatim excerpt) |
| `AlfaRaceX-Framework/` | AriotaG/AlfaRaceX-Framework | Apache-2.0 | CAN id table, vehicle bitrate profile, LICENSE, NOTICE | copied (verbatim JSON) |
| `python-OBD/` | brendan-w/python-OBD | GPL-2.0 | NOTES.md | notes only |
| `OBD.NET/` | DarthAffe/OBD.NET | GPL-2.0 | NOTES.md | notes only |
| `caringcaribou/` | CaringCaribou/caringcaribou | GPL-3.0 | NOTES.md | notes only |
| `stn1170-tools/` | bigunclemax/stn1170-tools | GPL-3.0 | NOTES.md | notes only |
| `ClaudeMarais/` | ClaudeMarais/AlfaRomeoGiulia_* | CC BY-NC 4.0 | NOTES.md | notes only |
| `BACCAble/` | tr3ma-crew/BACCAble-firmware | unclear (no grant for its own code) | NOTES.md | notes only |
| `ELM327-emulator-Ircama/` | Ircama/ELM327-emulator | CC BY-NC-SA 4.0 | NOTES.md | notes only |
| `OBDb/` | OBDb/* | CC BY-SA 4.0 | NOTES.md | notes only |
| `giulia_ESCape/` | beaups/giulia_ESCape | none stated | NOTES.md | notes only |

Reviewed and judged not worth saving (see the two research reviews): grancabrio-can (other platform), Alfa-Romeo-Giulia-SimRacing (ids in unopened zip files), ufnalski LIN repo (LIN, not CAN or UDS), cracked AlfaOBD repos (never opened).

## Gaps that are not a licence matter

- GitHub code search needs authentication, so the STN command reference (ScanTool.net) was not fetched; ST command spellings used in notes come from other projects' sources and are unverified on our adapter (vLinker FS, STN1170 v4.3.2).
- ISO 14229 / SAE J1979 text is not on GitHub. The Mode 06 unit-and-scaling table has to be re-derived from the standard (see item 6 of the implementation review).
