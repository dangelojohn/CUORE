# PROXI study for CUORE technicians

Date: 2026-10-29. Research only: no car contact, no tool runs. Raw outside material is kept outside the repo in C:\ProgramData\cuore\research\proxi_2026-10-29\ (Rule 13). Grading: CONFIRMED (local) means seen in this repo or on this car. A URL means an outside source; most were read only as search summaries, and the one primary document read in full is marked. INFERENCE means our reasoning. "Not found" means we looked and nothing was published.

## 1. What PROXI is

### The name and the idea

PROXI is the Fiat Chrysler (FCA, now Stellantis) name for the vehicle configuration block, also spelled "Proxy". The tools show it as "Proxi Configuration Alignment", "PROXI Alignment", "Proxy alignment" and "CAN Setup". A technician's one-line definition: a record of which options and equipment this exact car has, kept by the Body Control Module (BCM, the body computer), and copied to the other computers so they all agree.

Terms used below:
- Module or node: one computer on the car network.
- Configuration block: the stored list of option bits (market, equipment, battery type and so on).
- Alignment: the routine that makes every node's copy match the master.

### What the block holds, and who keeps a copy

One appcar-diagfca page says alignment "copies the current vehicle configuration from the BCM to all other modules" (https://appcar-diagfca.com/en/diy/proxi-configuration-alignment/). A second says the BCM stores the configuration and the other modules compare their own copies against it, and that a mismatch can set U-codes and disable features (https://www.automodulelab.com/es/blog/alineacion-proxi-chrysler-witech-remoto/). Both are secondary, shop-service sources. INFERENCE: the BCM is the master on these cars; we found no manufacturer text that says so in those words.

Contents named by public sources and by this repo: vehicle options and market behaviour (paddle behaviour, panic feature, key fob type), and the battery type (this repo, forum figures only). A full list of options: not found.

### When it is required

- After a module is reprogrammed. The FCA bulletin for this car's platform (read in full from NHTSA, Customer Satisfaction Notification W05, March 2020, https://static.nhtsa.gov/odi/tsbs/2020/MC-10175524-9999.pdf) tells the technician to flash the engine computer, then open the BCM, "Misc. Functions", and run "PROXI Alignment". It covers the 2017-2019 Giulia and 2018-2019 Stelvio.
- After a module is replaced. Examples named: BCM, radio, instrument cluster, RF hub (https://www.automodulelab.com/es/blog/alineacion-proxi-chrysler-witech-remoto/).
- After "Restore Vehicle Configuration" on a 2020 Giulia/Stelvio bulletin (search summary of https://static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf).
- After a configuration change, such as a market or battery setting (this repo; sources in section 5).
- Other FCA bulletins make it a repair step: Jeep Grand Cherokee WL droning noise names PROXI misalignment as the cause (search summary of https://static.nhtsa.gov/odi/tsbs/2025/MC-11014479-0001.pdf), and a 2026 Grand Cherokee battery-drain bulletin has an RF hub alignment (https://dot.report/bulletins/11028771, summary only).

### Names across brands

- Alfa Romeo Giulia and Stelvio (Giorgio platform): wiTECH shows "PROXI Alignment" under the BCM "Misc. Functions" tab in the W05 bulletin above.
- Jeep, Chrysler, Dodge, Ram: a 2016-era FCA US bulletin and recall place "PROXI Configuration Alignment" under the wiTECH "Vehicle Preparations" tab, run after reprogramming and VIN verification (search summaries of https://static.nhtsa.gov/odi/tsbs/2016/SB-10076538-2280.pdf and https://static.nhtsa.gov/odi/rcl/2016/RCRIT-16V529-3632.pdf).
- Newer Jeep WL: a per-module version, "PROXI Configuration Alignment for the ORC" (airbag controller), after unlocking it (summary of https://dot.report/manufacturer-communications/11005195).
- Fiat 500: MES forum threads titled "Bytes for Fiat 500 Proxy Alingment" show the same idea on the small Fiat cars (https://multiecuscan.net/forum/viewtopic.php?p=26732, title only; page not readable).
- "Configure vehicle" and "Vehicle configuration" as wiTECH menu text: not found. The names we found are "PROXI Alignment", "Proxi Configuration Alignment" and "Restore Vehicle Configuration".
- Platform differences (Giorgio, CUSW, Small Wide, Uconnect-era gateway): not found. INFERENCE: the idea is shared, but the block layout differs by platform and must not be copied between cars.

## 2. Data shape

- Where the block lives: this repo records that PROXI is a BCM data area and not a separate node (docs/design/CUORE_ADJUSTMENTS_PLAN.md Part 2, CONFIRMED local). The diagnostic identifier (DID, the 16-bit number a read request names), block length, and byte layout: not found in any public source. A forum search found no Giulia/Stelvio DID or length (multiecuscan.net forum search, summary only).
- Block length: this repo's reader treats 64 bytes as a likely length (cuore/live/proxi_read.py), but the paddle byte is reported as byte 156, so the real block must be at least 157 bytes. INFERENCE: the 64 is a guess to be replaced. Not found in any source.
- How tools index bytes: MES and AlfaOBD say "Byte N". Whether the count starts at 0 or 1: not found. CUORE's map (cuore/data/proxi_map_949.json) says so and decodes index N as block byte N.
- CAN Setup and PROXI are two names for the same thing. In MES the screen is "CAN Setup" and the routine is "PROXI ALIGNMENT PROCEDURE" (MES User Guide read locally, per docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md).
- Error messages name bytes. Forum posts show failed MES writes such as "Byte 64: 01->0E" on a Giulietta and "Byte 83: 08->00" on a Fiat 500 (search summary, multiecuscan.net forum). This shows that MES validates the new value per byte. It does not show the layout.
- Giorgio BCM versus older Fiat body computers: not found.
- Other byte claims, all single-source and for reference only: Stelvio US panic mode needs byte 70 plus 04 and byte 126 = 80, and byte 59 sets the key fob type (https://www.multiecuscan.net/forum/viewtopic.php?t=8375, summary only).

## 3. Codes and symptoms

- B10AA-4A "PROXI configuration control, incorrect component installed" is stored on this car's BCM by the 2026-10-23 MES scan, and absent from the 2026-10-25 scan (CUORE note f280e9fbd67f, CONFIRMED local). The PROXI write counter reads 1. A public definition of B10AA: not found.
- B2204 is described as "ECU configuration mismatch", set in any module when modules are out of alignment (search summary of https://www.go-parts.com/garage/obd-b2204; page blocked). The repo note ties B2204 and a flashing odometer to Jeep WL, citing the NHTSA bulletin MC-10212320 (docs/design/CUORE_ADJUSTMENTS_PLAN.md, not re-read here).
- U-codes: the module-replacement guide above gives lost-feature U-codes across the bus on a 2019 Ram 1500 (https://www.automodulelab.com/es/blog/alineacion-proxi-chrysler-witech-remoto/). A published FCA "U1xxx implausible configuration" family: not found. On this car BCM U1711 to U1716 are lost-communication codes tied to adapter reach, not configuration (docs/research/CONNECTIVITY_AND_SGW.md section 1, CONFIRMED local).
- Symptoms named by shop sources: flashing odometer, disabled features, wiper or remote-start misbehaviour (same automodulelab page; also appcar-diagfca page above).
- Limp mode: the repo records a transmission P1500 limp-in on a failed or partial configuration (docs/design/CUORE_ADJUSTMENTS_PLAN.md Part 2, CONFIRMED local). A manufacturer statement of this: not found.
- "Empty Proxi File": a Giulia owner saw this; replies blamed CAN noise or a replaced BCM whose configuration was never written (https://multiecuscan.net/forum/viewtopic.php?p=28261 and ?p=23739, summaries).
- DTCs remain active after alignment until the ignition is cycled, then show as stored and are cleared (2020 Giulia/Stelvio bulletin summary, https://static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf).

## 4. How the tools do it

- wiTECH (official, server-backed: it logs in to FCA with a dealer ID). The W05 bulletin states the whole path: wiTECH 2.0 website, MicroPod II interface, Topology screen, BCM, Misc. Functions, PROXI Alignment, then clear all DTCs (https://static.nhtsa.gov/odi/tsbs/2020/MC-10175524-9999.pdf). Its battery rule: a charger holding 13.2 to 13.5 V, checked on a separate accurate voltmeter, with the charger timer off, because other voltage "will cause an unsuccessful flash" (same PDF). Use of the same limits for alignment alone: INFERENCE.
- MES: "CAN Setup" shows the bytes, "PROXI ALIGNMENT PROCEDURE" pushes them. MES reads the node list and says "This vehicle is properly configured. PROXI Alignment is not needed!" or reports too many added or removed modules (MES language file, CONFIRMED local, CUORE_ADJUSTMENTS_PLAN.md).
- AlfaOBD: "Car Configuration Change" and "Proxy alignment". Owners report it working with a vLinker and grey adapter, and also failing partway on some modules (docs/project/ALFAOBD_GAP.md section 1c; thread titles only here: https://www.giuliaforums.com/threads/alfaobd-for-proxi-alignment.58085/).
- Appcar DiagFCA lists Giulia and Stelvio and shows a status table: "Proxi Required?", "Proxi OK?", "Write Proxi?". It requires a CAN-MS/IHS capable interface, tells the user to put the bus to sleep, and says to restore the original Proxi in the BCM if it fails (https://appcar-diagfca.com/en/diy/proxi-configuration-alignment/).
- Launch and Autel: not found.
- Secure Gateway (SGW, a firewall computer between the OBD port and the modules on 2018+ cars): a remote-service page says it is why a scanner may read but not clear codes, and that programming needs authorized access (https://www.automodulelab.com/es/blog/alineacion-proxi-chrysler-witech-remoto/). Local evidence on this car: MES completed ECU clears and actuator commands with no unlock step, so the gateway is not gating this car (docs/research/CONNECTIVITY_AND_SGW.md section 2, CONFIRMED local). That covers the ECM. It does not prove a BCM configuration write is allowed.
- Risks: a wrong block or wrong bit; partial alignment where one node refuses (negative responses, "Empty Proxi File"); supply voltage dropping mid-write; and Bluetooth adapters timing out, reported by one user on the MES forum (https://www.multiecuscan.net/forum/viewtopic.php?p=29086, per docs/project/ALFAOBD_GAP.md). Forum advice, anecdotal: let the car fully sleep before running, and re-running without sleep can return negative responses (search summary, 200forums and other threads).

## 5. Worked example: paddle shifter market setting

Owner statement (not verified by us): this Stelvio has North American paddle-shifter programming.

- What differs: per one forum author, in North American behaviour the paddles do not shift into Neutral. In European behaviour, [+] moves P or R to D, and [-] with [+] moves to N (docs/project/ALFAOBD_GAP.md section 3, from https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80, single source).
- Which bits: BCM, CAN Setup, byte 156, bits 4 and 5. Euro is xx00xxxx, North America is xx01xxxx; the reported whole-byte values are 0x50 for North America and 0x40 for Europe (docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md, from a giuliaforums.com post). That is one forum author. Another post says logic 0 enables EU control (https://www.giuliaforums.com/threads/alfaobd-and-multiscanecu-some-alfaobd-settings-i-was-surprised-by.55899/, summary). INFERENCE: byte numbering may differ by model year and trim.
- How a correct change would go: (1) read and save the full block; (2) record the current byte-156 value and confirm it matches the owner's statement; (3) change only bits 4 and 5 and keep the rest of the byte; (4) run the alignment with the battery supported; (5) cycle the ignition, let the car sleep; (6) read the block again on the BCM and confirm only the intended bits changed; (7) read each node's status and DTCs; (8) road-check the paddles; (9) record who, when and why.
- What CUORE needs from the manufacturer: the configuration identifier and block length for the 949, the byte and bit map with allowed values per market and model year, and the security level and procedure for writing and aligning. Without these CUORE will not write.

## 6. Teaching outline

### Safe PROXI work, ten steps

1. Write down the symptom and current DTCs, including B10AA and the PROXI write counter, before touching anything.
2. Confirm that alignment is truly needed. If MES says "not needed", stop.
3. Put a charger on the car. Use 13.2 to 13.5 V verified on a separate meter (per the FCA bulletin above) and turn off the charger timer.
4. Read and save the complete configuration block. No backup, no write.
5. Connect with an adapter that suits the bus. Prefer a wired adapter, because a Bluetooth one has timed out for owners.
6. Close every other program that talks to the adapter.
7. Change one named setting from a manufacturer document. Never from a forum alone.
8. Run alignment. Do not open doors or cycle the key unless the tool says so.
9. Let the car sleep, cycle the ignition, read the block back, check each node, then clear and re-read DTCs.
10. Road-check the feature and write down values before and after.

### Glossary

- PROXI: the vehicle configuration block and routine, also called Proxy or CAN Setup.
- Node: a computer on the car network.
- Alignment: copying the master configuration to all nodes.
- Configuration block: the stored option bytes.
- CAN Setup: the MES name for the PROXI byte screen.
- SGW: Secure Gateway, the firewall on 2018+ cars.
- wiTECH: the official FCA service tool.
- DID: data identifier, a 16-bit number used to read a stored value.
- Read-back: reading the value again after a write to prove it changed as intended.

## 7. What CUORE does today

- Read-only discovery of the BCM configuration block using the UDS read service only. No security access, write, routine or reset calls exist in cuore/live/proxi_read.py (CONFIRMED local).
- The owner accepts a candidate block with a reason. Only an accepted block is read and compared with earlier reads.
- Names from MES's CAN Setup screen can be recorded by hand. This was allowed on 2026-10-29 and is naming only.
- Adjustments cards for PROXI alignment, battery type and paddle behaviour are held until a manufacturer source exists. Forum figures in cuore/data/proxi_map_949.json are labelled single-source reference and are never written.

### Exact asks for the manufacturer

1. The identifier, length and read access level for the 949 BCM configuration block.
2. The byte and bit map with allowed values per market and model year, including byte 156 bits 4 and 5 and byte 63 battery bits, with the index base stated.
3. The alignment procedure: node list, order, security access and key source, expected responses, and abort conditions.
4. The supply voltage and sleep requirements for alignment.
5. The restore procedure from a saved block, and a statement on whether this car's gateway state affects BCM writes.
6. The definition of B10AA-4A and the steps to clear it.

Not found overall: the DID, block length and byte map; Giorgio versus older Fiat BCM differences; Launch and Autel documentation; wiTECH help text.
