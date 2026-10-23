# CUORE

*Cuore* is Italian for heart. CUORE is a diagnostic workbench for cars built on the Alfa Romeo Giorgio platform. The reference car is a 2018 Stelvio 2.0T. Alfa Romeo comes first; Maserati and Ferrari models are planned later, with marque-specific facts kept in data and configuration files rather than in code.

> **Diagnose on evidence. Prove the fix. Learn for the next car.**

## What it is, in plain words

A mechanic plugs a small adapter into the car's OBD port. CUORE reads the car (fault codes, live values, the engine computer's own test results), reads the logs that the MultiEcuScan (MES) tool has already written, and shows both in a web page on the shop PC, a tablet or a phone. It keeps one record per car: the complaint, the evidence, the hypotheses, the steps taken and whether the repair was actually proven.

CUORE advises and records. **The mechanic decides.** It never writes to the car from the web app, and it never presents a fault code, a forum post or a service bulletin as proof of a fault.

## Who it is for

- A mechanic who works on one brand and model family and wants each job to start where the last similar job finished.
- A car owner who wants an honest, dated, sourced story of the car instead of a list of cleared codes.
- Anyone building on the project: the code is organised so marque data (module addresses, bulletins, specifications) can be swapped without rewriting the logic.

## Three ways to use it

1. **Web app.** FastAPI, server-rendered pages plus a JSON API. Phone and tablet friendly. This is the main interface. See [[Getting Started|Getting-Started]].
2. **Claude Code.** Two MCP servers expose the same data conversationally. See [[MCP Servers and Claude|MCP-Servers-and-Claude]].
3. **Static report.** A point-in-time HTML or PDF summary of one car that can be printed or shared. It is not connected to the car.

## Status

As of 2026-10-22 the project is a working bench application for one reference car, with a live link to the car proven on three buses. It has about 105 test scripts for the web app and live layer, 31 for the MES library, and a long list of documented limits ([[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]]). The reference car's EVAP (fuel vapour) fault is still under diagnosis; see [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]. Later the same day every non-EVAP code on the car was reviewed ([[Code Reviews|Code-Reviews]]), outside GitHub material was filed with its licences ([[External References and Licences|External-References-and-Licences]]), and the live layer gained a listen-only chassis decoder and several bench-tested fixes that have **not yet been run on the car**. Only the Alfa Romeo Stelvio data set exists today; the port to other marques is a roadmap item ([[Roadmap]]). On 2026-10-22 the reference car's ESIM was replaced (owner-attested) and an export bundle for the AlfaCore shop platform was built and installed ([[AlfaCore Integration|AlfaCore-Integration]]); the EVAP proof run is still pending.

## Map of this wiki

**Start here**
- [[Getting Started|Getting-Started]]: install, start, first connection, health check.
- [[Hardware and Cables|Hardware-and-Cables]]: adapter, OBD pins, bypass cables, security gateway, one program per port.
- [[Adapter Cables|Adapter-Cables]]: the coloured A1-A6 / 3-pin / SGW cable catalogue (external reference), with cautions.
- [[Vehicle Networks|Vehicle-Networks]]: the three CAN buses, addressing modes, module table, awake and asleep signatures.

**How it works**
- [[Architecture]]: layers, programs, state directory.
- [[Features]]: every page and route group.
- [[Guided Full Scan|Guided-Full-Scan]]: the cable-swap wizard.
- [[Live Board|Live-Board]]: live values for a passenger to watch.
- [[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]: one job per visit.
- [[TSB Layer and Cross-Reference|TSB-Layer-and-Cross-Reference]]: bulletins, recalls and how they are scored.
- [[Evidence Model|Evidence-Model]]: what counts as a measurement and what does not.
- [[Safety Rules|Safety-Rules]]: read-only design and the rules behind it.
- [[Passive Chassis Decoding|Passive-Chassis-Decoding]]: the listen-only decoder for the chassis bus.
- [[External References and Licences|External-References-and-Licences]]: what was copied from public projects, what was only noted, and why.
- [[MES Integration|MES-Integration]]: working alongside MultiEcuScan.
- [[MCP Servers and Claude|MCP-Servers-and-Claude]]: the conversational surface.
- [[AlfaCore Integration|AlfaCore-Integration]]: the file bundle to the shop platform, export button, import module, live deployment, open pilot.

**The reference case**
- [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]: the full diagnostic story, readings kept apart from literature.
- [[ESIM Bench Test|ESIM-Bench-Test]]: how to test the suspect part out of the car.
- [[EVAP Interactive Tests|EVAP-Interactive-Tests]]: the passive purge-trim recording now; the ESIM switch probe (spec and software built, hardware not built); confirmed actuation and the dealer SLVT comparison planned.
- [[Code Reviews|Code-Reviews]]: every other code on the car, by system: readings, classification, resolution ladder, proof of fix.
- [[Network and Brake Findings|Network-and-Brake-Findings]]: the body-computer-centred code cluster, the brake event and the ranked tests.
- [[Wiring and Ground Faults|Wiring-and-Ground-Faults]]: failure-type map of every code by module, the load-step voltage test and the multimeter voltage-drop procedure.
- [[Recalls and Campaigns|Recalls-and-Campaigns]]: the recalls and notices that could apply, VIN checks first.
- [[Routine Maintenance: Accessory Belt|Routine-Maintenance-Accessory-Belt]]: sourced belt replacement procedure, interval, part numbers and what to record.
- [[Digital Rear-View Mirror|Digital-Rear-View-Mirror]]: planned accessory install; ADAS camera, power, airbag and liftgate cautions, job 98a6aad68d72.
- [[Infotainment and Camera Upgrades|Infotainment-and-Camera-Upgrades]]: four routes to add front, side, 360 and mirror cameras compared against the car's diagnostic state; evaluation, job c70f2f3e6932.

**Project**
- [[Testing]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]], [[Roadmap]], [[Glossary]], [[Data Captured|Data-Captured]], [[Project History|Project-History]].

## Project knowledge in the repository

Decisions, rules, roadmap, history and glossary are also kept as documents in the repository:
[DECISIONS](https://github.com/dangelojohn/CUORE/blob/main/docs/project/DECISIONS.md),
[RULES](https://github.com/dangelojohn/CUORE/blob/main/docs/project/RULES.md),
[ROADMAP](https://github.com/dangelojohn/CUORE/blob/main/docs/project/ROADMAP.md),
[HISTORY](https://github.com/dangelojohn/CUORE/blob/main/docs/project/HISTORY.md),
[GLOSSARY](https://github.com/dangelojohn/CUORE/blob/main/docs/project/GLOSSARY.md).
The repository front page is the [README](https://github.com/dangelojohn/CUORE/blob/main/README.md) and the statement of purpose is [CUORE.md](https://github.com/dangelojohn/CUORE/blob/main/CUORE.md).

## Core directive

- Every fact carries its date, its source and a confidence grade. Unknown is shown as unknown.
- A repair is verified only by proof from the car, not by the absence of codes.
- Every finished job can become a case, so the next car of the same model starts where the last one finished.
- CUORE advises and records. The mechanic decides.
