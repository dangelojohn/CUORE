# Network-pattern readings, Stelvio ZASFAKPN5J7B88115 (2026-10-20)

Readings only. Sources: `data/captures/stelvio-2018/mes_logs/` (SCAN_*, FESLog_*; none flagged simulation; the SCAN format cannot prove provenance) and `data/captures/stelvio-2018/cuore_state/observations.jsonl` (222 rows), parsed with `mes-log-mcp/mes` (`scan`, `fes`, `dtc`). Every claim is tagged **[E]** evidence (file + time) or **[I]** inference.

Conventions: SCAN id = filename stamp YYMMDDHHMM (a save/start stamp, not exact scan time). `P` = present, `0` = module read, code absent, `nr` = module NOT read in that scan (not "absent"), `0*` = only one of two reporting modules read. Names as MES prints them: U1711/U1712 = "Brake system (NFR) erratic", U1713 = "Engine control (NCM) erratic", U1702-87 = "EPS (NGE) missing message", U1736 = ETM, U1765-86 = "Lost comm with RF Hub", B1040-64 = RFHUB "comm with BCM plausibility". **Code owners in the logs:** U1711/12/13, U1736-87, U1765-86 are stored in the BCM; U1736-86 and -87 also in the IPC; C1408/C1431/C1403/C141B/C141C and U1702-87 in the DASM; U0418-86 in the HALF; B1040-64 in the RFHUB. U1702-87 has never appeared in the EPS (EPS read once: U1960-83 only).

## 1. Per-scan matrix

Modules read: S-rows below are the 8-module scan (ECM, IPC, TCM, DTCM, ESM, BCM, RFHUB, DASM) except S2609042008, which read only ABS, EPS, NAB/ORC, AFLS, PAM, HALF.

| id | date time | U1711 | U1712 | U1713 | U1736-86 | U1736-87 | U1765-86 | P0440 | P0455 | P0456 |
|---|---|---|---|---|---|---|---|---|---|---|
| S2606070954 | 2026-06-07 09:54 | P | P | P | 0 | 0 | 0 | 0 | 0 | 0 |
| S2606071003 | 06-07 10:03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S2608271131 | 08-27 11:31 | P | P | P | 0 | 0 | 0 | 0 | 0 | 0 |
| S2608271136 | 08-27 11:36 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S2608271141 | 08-27 11:41 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S2609021445 | 09-02 14:45 | 0 | 0 | P | 0 | 0 | 0 | P | 0 | P |
| S2609041953 | 09-04 19:53 | P | P | P | 0 | 0 | 0 | P | 0 | 0 |
| S2609042008 | 09-04 20:08 | nr | nr | nr | nr | nr | nr | nr | nr | nr |
| S2609152048 | 09-15 20:48 | P | P | P | 0 | 0 | P | P | 0 | 0 |
| S2609251956 | 09-25 19:56 | P | P | P | 0 | 0 | 0 | P | P | P |
| S2609252027 | 09-25 20:27 | P | P | P | 0 | 0 | 0 | P | P | P |
| S2609281159 | 09-28 11:59 | 0 | 0 | P | 0 | 0 | 0 | P | 0 | 0 |
| S2609291046 | 09-29 10:46 | 0 | 0 | 0 | 0 | 0 | 0 | P | 0 | 0 |
| S2610041113 | 10-04 11:13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S2610041115 | 10-04 11:15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S2610080920 | 10-08 09:20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | P | P |
| S2610080926 | 10-08 09:26 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S2610140859 | 10-14 08:59 | 0 | 0 | P | P | P | P | P | P | 0 |
| S2610190039 | 10-19 00:39 | 0 | 0 | P | 0 | 0 | 0 | P | P | P |

| id | C1408 | C1431 | C1403 | C141C | C141B | U1702-87 | U0418 (HALF) | B1040 (RFHUB) | clears written in file (module:result) |
|---|---|---|---|---|---|---|---|---|---|
| S2606070954 | 0 | 0 | 0 | P | 0 | 0 | nr | 0 | BCM, DASM ok, then re-read (see below), BCM, DASM ok again |
| S2606071003 | 0 | 0 | 0 | 0 | 0 | 0 | nr | P | RFHUB, DASM ok (DASM held U1701-86) |
| S2608271131 | P | P | P | P | 0 | 0 | nr | P | IPC, DTCM, BCM, RFHUB, DASM ok |
| S2608271136 | 0 | 0 | 0 | 0 | 0 | 0 | nr | 0 | DTCM ok, re-read, DTCM ok again |
| S2608271141 | 0 | 0 | 0 | 0 | 0 | 0 | nr | 0 | none |
| S2609021445 | 0 | 0 | 0 | 0 | P | 0 | nr | 0 | none |
| S2609041953 | P | 0 | 0 | P | P | 0 | nr | 0 | ECM, DTCM, BCM ok; DASM FAILED (C1408-86, C141C-86 stayed) |
| S2609042008 | nr | nr | nr | nr | nr | nr | P | nr | none (HALF U0418-86; EPS U1960-83; AFLS U0428-86) |
| S2609152048 | 0 | 0 | 0 | P | 0 | 0 | nr | 0 | ECM, BCM, DASM ok |
| S2609251956 | 0 | 0 | 0 | P | P | 0 | nr | 0 | none |
| S2609252027 | 0 | 0 | 0 | P | P | 0 | nr | P | ECM, BCM, RFHUB, DASM ok |
| S2609281159 | 0 | 0 | 0 | 0 | P | 0 | nr | P | ECM, DTCM, BCM, RFHUB, DASM ok |
| S2609291046 | 0 | 0 | 0 | 0 | 0 | 0 | nr | 0 | ECM, BCM ok (BCM held only B1176-97) |
| S2610041113 | 0 | 0 | 0 | 0 | 0 | 0 | nr | 0 | none |
| S2610041115 | 0 | 0 | 0 | 0 | 0 | 0 | nr | 0 | none |
| S2610080920 | 0 | 0 | 0 | 0 | P | 0 | nr | P | first clear: ECM printed no result and codes stayed in re-read; then RFHUB, DASM ok |
| S2610080926 | 0 | 0 | 0 | 0 | 0 | 0 | nr | 0 | none |
| S2610140859 | 0 | 0 | 0 | 0 | P | 0 | nr | P | ECM, IPC, DTCM, BCM, RFHUB, DASM ok |
| S2610190039 | P | 0 | 0 | P | P | P | nr | 0 | ECM, DTCM, BCM, DASM ok (no re-read in file) |

[E] each row from the matching `SCAN_*.txt`. C1431-86 and C1403-86 appear only in S2608271131; U0418-86 and the EPS/NAB/AFLS/PAM reads only in S2609042008 (plus ABS via FES, below).

Other code sightings in the same scans [E]: U1716-2F "Electric steering erratic" (BCM, S2608271131 only), B1176-97 rear-left window (BCM, 08-27, 09-02, 09-04, 09-15, 09-25 x2, 09-28, 09-29, 10-14), U0100-87 ECM missing (DTCM, S2608271131, 08-27 11:36 re-read, 09-02, 09-04, 09-28, 10-14, 10-19), U0422-86 BCM invalid (DTCM, 10-19 only), U2054-87 BCM missing (RFHUB, 08-27, 10-14), B1029-64 and B102E-64 (IPC, 08-27), B10AA-4A PROXI "incorrect component" (BCM, 10-14), U1701-86 (DASM, 06-07 10:03).

Post-clear re-reads inside one file (the report listing printed after a CLEARING block) [E]: S2606070954 BCM U1711/12/13 and DASM C141C-86 still present after the first clear "SUCCESS"; S2608271136 DTCM U0100-87 still present; S2610080920 ECM P0455/P0456, RFHUB B1040-64, DASM C141B-97 still present. [I] the second listing is a re-read after the clear; MES does not label it.

### CUORE direct reads (observations.jsonl, UDS module DTC reads; status byte in brackets, 0x0F = failing now, 0x08 = stored/not failing)

| time | modules read | result |
|---|---|---|
| 2026-09-25 20:12:02 | ECM only (CAN ERROR on 20:11:52 and 20:12:05) | P0440, P0455, P0456 [0x4D] |
| 2026-10-13 20:24:25 | ECM, TCM, BCM, IPC, RFHUB (DTCM, ESM, DASM not read) | BCM U1713-2F [0x0F], U1765-86, U1736-87, B1176-97, B10AA-4A [0x08]; IPC U1736-86/-87 [0x0C]; RFHUB B1040-64 [0x08]; ECM P0440 [0xCD], P0455 [0x4D]; no U1711/U1712 |
| 2026-10-14 19:02:07 | same five | BCM clean; IPC, RFHUB, TCM clean; ECM P0440 [0x4D] only |
| 2026-10-15 00:12:43 | ABS on can_ch (grey_a6) | dtcs empty, but every identity field null; [I] treat as no real answer, not "clean" |
| 2026-10-19 00:23:42 and 00:30:25 | same five | BCM U1713-2F [0x0F] only; ECM P0440 [0xCD], P0455, P0456 [0x4D]; IPC, RFHUB, TCM clean |

Other single-module reads (FES): ECM only unless noted [E]. 2026-06-07 09:46 and 09:59 no faults; 08-27 10:57 P0455/P0440/P0456 (cleared); 08-27 11:19 none; 08-31 18:22 P0440 (cleared); 09-02 14:48 P0456/P0440 (cleared); 09-04 19:53 none; 09-25 19:56 P0455/P0440/P0456; 09-25 20:27 none; 10-04 11:16 none. ABS (FES): 09-04 20:01 C104B-92 and U1700-87 (cleared), 20:08 no faults x14 reads. All non-ECM, non-ABS modules never read by FES for these codes (BCM FES 06-07 09:55 is identity only).

## 2. Freeze frame / environment data

- SCAN logs contain no freeze frames, battery, odometer or counter data [E: grep of all 19 SCAN files].
- No FES freeze frame exists for any code in your list [E]. Nearest: ABS FES 2026-09-04 20:01:10, **U1700-87 "Body computer (BCM/NBC)"** (ABS saying the BCM message is missing, the reciprocal of U1711/12): battery **10.6 V**, startups counter **14280**, operating time 329228 min, speed 0, brake pedal off, hydraulic pressure 2.6 bar. Same file, C104B-92 (hydraulic leak): 12.1 V, startups 14356, 16 min of operating time before the read, speed 0, brake on.
- Startups counter is shared across modules [E: ECM 14357 at 19:53 vs ABS 14359 at 20:01; BCM and ECM both 13865 on 06-07]. ECM freeze frame for the first EVAP code stored at startups 14281 (odometer 140,471.2 km, 14.3 V). [I] so the U1700-87 / 10.6 V event was one start before that, odometer about 140,470 km, roughly 19 starts before the 2026-08-27 trio scan (startups 14299 at 10:57).
- CUORE `dtc_detail` for BCM U1713-2F: 2026-10-13 20:28:23 and 2026-10-19 00:25:39, status 0x0F both times (failing this cycle). Raw snapshot differs by: DID 1008 `03 BE 84` vs `03 C0 E2` (+606), DID 1009 `0E ... 38 F7` vs `11 ... 39 18`, DID 1004 byte `89` vs `91`. DID 1004 is the BCM battery-voltage DID in CUORE (formula A/10, unverified), so [I] 13.7 V and 14.5 V; 14.5 V matches the live BCM reading the same minute (0x91 at 00:23:42). [I] DID 1008 resembles operating-time minutes (ECM P0440 value 0x048DCD = 298,445 is consistent with ECM operating time 296,066 on 10-04). Decoding unverified; the "occurrence counter" byte is `60` for both BCM and ECM codes, so [I] it is not a counter.
- Voltage at other times [E]: ECM FES live 14.0 V at 2026-06-07 10:03 (trio present at 09:54, same ignition session, startups 13865); CUORE port voltage 14.0-14.5 V on 10-13, 10-14, 10-19; BCM DID 1004 0x90/0x91 (14.4/14.5 V) on 10-14 19:02, 10-19 00:23, 00:30, 00:33; IBS state of charge 71 % (ECM DID 19BD = 0x47, unverified formula) on 10-19 00:33:38. ECM EVAP freeze frames 13.5-14.3 V (2026), 12.0-13.6 V (2025).
- Ignition counter by time (ECM FES) [E]: 06-07 09:46-10:08 13865 (no cycling); 08-27 10:57 14299, 11:19 14303; 08-31 14321; 09-02 14:48 14345; 09-04 19:53 14357, 20:01 14359; 09-15 20:48 14415, 21:11 14417; 09-25 19:56 and 20:27 14473; 10-04 11:16 14532. About 5-7 starts per day. No counter exists after 10-04.

## 3. Correlations

**3a. Does the trio move together?**
- U1711 and U1712 always appear and disappear together: 6 of 6 scans in which either was present had both [E]. They are never present without U1713 [E].
- U1713 alone (without the pair): S2609021445, S2609281159, S2610140859, CUORE 10-13 20:24, S2610190039 and CUORE 10-19 [E]. So the three do NOT always move together; the pair is a subset of U1713 episodes.
- U1713 present in 10 of 18 eight-module scans; pair present in 6 of 18.
- Clears: in-file removal confirmed at 06-07 (second clear, S2606071003 BCM clean) and 08-27 (S2608271136 and S2608271141 clean). First clear on 06-07 did not hold in the re-read [E]. All other BCM clears were verified only by the next scan.

**3b. Return after BCM clears [E, intervals from scan stamps; starts from FES counter]**

| clear | next BCM read | what came back | elapsed (starts) |
|---|---|---|---|
| 06-07 ~09:56 | 06-07 10:03 | nothing | 7 min (0) |
| 08-27 ~11:31 | 11:41 clean; 09-02 14:45 | U1713 only (+B1176) | 6 d 3 h (about 42 starts) |
| 09-04 19:53 | 09-15 20:48 | full trio + U1765-86 | 11 d 1 h (58) |
| 09-15 20:48 | 09-25 19:56 | full trio | 10 d (56) |
| 09-25 20:27 | 09-28 11:59 | U1713 only | 2 d 15 h (not known) |
| 09-28 11:59 | 09-29 10:46 | U1713 not back (B1176 back) | 22 h 47 m |
| 09-29 10:46 | 10-04 11:13, 10-08 09:26 clean; 10-13 20:24 | U1713 + U1765-86, U1736-87, B10AA-4A, B1176 | clean at least 8 d 22 h; back between 10-08 09:26 and 10-13 20:24 (5 d 11 h window) |
| 10-14 08:59 | 10-14 19:02 clean; 10-19 00:23 | U1713 [0x0F] | clean 10 h; back within 4 d 5 h |

Return time is not constant: 2.6 d to over 8.9 d [E]. [I] Where the pair returned, 56-58 starts had elapsed; where it did not, the elapsed starts are unknown.

**3c. Battery voltage.** [E] Trio present at 14.0 V (06-07) and U1713 failing at 14.4-14.5 V (10-19), so a low supply is not needed for the code to be present at read time. The only low-voltage reading in the corpus is ABS U1700-87 at 10.6 V (startups 14280), which sits just before the 08-27 trio scan. [I] a low-voltage event can plausibly set BCM/ABS comm codes; no BCM freeze frame exists to test it.

**3d. Ignition-cycling sessions.** [E] Trio present in a session with no cycling (06-07, 09-25) and with cycling (08-27 +4 starts, 09-04 +2, 09-15 +2). [I] No pattern separates them; the BCM was never read with a counter beside it after 06-07.

**3e. Wrong-bitrate window 2026-10-14 23:58 to 2026-10-15 00:00.** [E] No DTC read of any module falls in the window (observations at 23:55:32 then 00:07:27, both adapter checks; first verified can_ch traffic 00:07:27). Last BCM read before: CUORE 10-14 19:02:07 (clean). Last DASM read before: S2610140859 (C141B only, then cleared). First reads after: CUORE 10-19 00:23:42 (BCM U1713 failing) and S2610190039 (DASM C1408-86, C141C-86, U1702-87 new). U1713 was also present on 10-13 (before the window), so the window did not create U1713. [I] The window cannot be confirmed or excluded as the cause of the DASM/DTCM codes first seen 10-19 (C1408, C141C, U1702-87, U0422-86): five days passed with no reads.

**3f. EVAP sets.** [E] Trio without EVAP codes: 06-07 (ECM FES 09:46 and 09:59 no faults). Trio with EVAP: 09-04, 09-15, 09-25 x2. U1713 alone with EVAP: 09-02, 09-28, 10-14, 10-19. EVAP without any BCM code: 09-29 (P0440), 10-08 (P0455/P0456). On 08-27 the EVAP codes were present at 10:57 (FES) and cleared before the 11:31 trio scan. [I] No dependence in either direction.

**3g. DASM/HALF group vs BCM group.**
- C141C-86 tracks the U1711/U1712 pair: present in 6 of 6 pair scans, and in 1 of 12 pair-absent scans (the exception is S2610190039, where U1713 is present) [E].
- DASM and BCM were cleared in the same sessions each time, so joint removal is confounded [E]. Joint return after clears: 09-15 to 09-25 (both returned), 09-04 to 09-15 (both; C141C never cleared on 09-04, see FAILED). Joint non-return: 08-27 to 09-02 and 09-25 to 09-28 (pair and C141C both absent, U1713 back alone).
- C141B-97 (camera) is independent: present in 8 scans with and without the pair, and alone on 10-08 when the BCM was clean [E].
- C1408-86: S2608271131, S2609041953, S2610190039 only; not pair-bound (absent at 06-07, 09-15, 09-25) [E]. C1403-86 and C1431-86: one scan only.
- HALF U0418-86 (ABS communication invalid) read once, 09-04 20:08, 15 min after pair and C141C were present [E]; no other HALF read, so no pattern.
- [I] Verdict: the DASM/HALF group is partly independent (C141B, C1408) and partly co-timed with the BCM pair (C141C).

## 4. Proven vs suggested

Proven [E]:
1. The BCM stores NCM (ECM) erratic U1713-2F in 10 of 18 eight-module scans, 06-07 to 10-19, and it is failing right now (status 0x0F, CUORE 10-13 20:28, 10-19 00:25, MES 10-19 00:39). BCM first read 2026-06-07, so onset is before that and unknown.
2. The BCM stores brake system (NFR) erratic U1711+U1712 in 6 scans, last 2026-09-25 20:27; not seen in any BCM read since (09-28 U1713 only; 09-29, 10-04, 10-08 clean; 10-13, 10-14, 10-19 U1713 only or clean).
3. ABS stored "BCM missing message" (U1700-87) at 10.6 V (startups 14280), seen 09-04 20:01, then cleared.
4. Other modules also log BCM-related faults: DTCM U0422-86 (10-19), RFHUB B1040-64 and U2054-87, IPC B102E-64 (08-27).
5. ECM's own list never holds a network code; DTCM holds "ECM missing" U0100-87 in 6 of 10 U1713 scans and 1 of 8 others (the 08-27 11:36 re-read).

Suggested [I]:
- "BCM flags both ABS-side and ECM-side messages as erratic since at least 2026-06-07." The word "rejects" is not in the data; the code means erratic.
- Common module: the **BCM** is the only module on both sides of the complaints (BCM reports on ABS and ECM; ABS, DTCM, RFHUB, IPC report on the BCM). Sender-vs-receiver cannot be split because complaints run in both directions. ABS/ESP is the common sender for U1711, U1712, C1408, C1431, U0418; ECM is common sender for U1713 and DTCM U0100-87; neither explains the other group.
- Network/gateway or BCM power/ground would produce this two-way pattern; a single dead sender would not. Not proven.

## 5. The three readings that discriminate most

1. **Reciprocity snapshot in one key-on session while U1713 is active:** full status bytes and freeze data for U1713/U1711/U1712 in the BCM and the mirror codes in ABS (U1700-87), ECM, DTCM (U0422-86, U0100-87), IPC (B102E-64), RFHUB (B1040-64, U2054-87). All sides complaining = BCM transmit, gateway or bus. Only the BCM complaining = BCM receive side. Only ABS/ECM complaining about the BCM = BCM sender. (ABS has not been read since 09-04 except one unanswered can_ch read.)
2. **Frame census of ABS (NFR), ECM (NCM) and BCM-originated frames at the OBD port on the verified-bitrate CAN-C**, engine running, several minutes: rate, jitter, and counter/CRC validity per ID. Healthy ABS/ECM frames at the port while the BCM still flags erratic = receiver (BCM) or its branch. Missing, jittery or bad-CRC frames = sender or bus. Frames absent on the BCM's segment but present elsewhere = gateway.
3. **BCM supply and bus electrical record across a start/stop cycle:** BCM DID 1004 and IBS values logged continuously through key-off, crank and run (the only low-voltage evidence is 10.6 V, 2026-09-04, one ABS freeze frame), plus CAN-H/CAN-L resistance and levels at the BCM connector with the key off. A voltage sag or termination fault at crank = supply or network; clean = module-internal.
