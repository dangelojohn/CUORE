# CUORE project record

This folder is the short, durable record of how the CUORE project is run: why it exists, the rules it works by, the decisions taken, what is still open, what happened when, and the vocabulary used.

CUORE is a diagnostic assistant for a mechanic who specialises in one brand and model (Alfa Romeo Stelvio and Giulia now; Maserati and Ferrari later). It helps diagnose the car on evidence (scan logs, live reads, inspections, photos, sounds, driver and mechanic input), proves the repair, and makes the next car of the same model with the same fault start from what this one taught. The mechanic decides. CUORE advises and records, with sources, dates and confidence.

## Files

| File | Contents |
|---|---|
| [RULES.md](RULES.md) | The working rules, each with its reason. Read before changing behaviour. |
| [DECISIONS.md](DECISIONS.md) | Dated architecture and product decisions, with the reason and the commit where known. |
| [ROADMAP.md](ROADMAP.md) | Open items: planned work, open tool faults, next on-car tests. |
| [HISTORY.md](HISTORY.md) | Changelog grouped by month, from git history and session records. |
| [CORPORATE_ACCEPTANCE_2026-10-29.md](CORPORATE_ACCEPTANCE_2026-10-29.md) | The dealer demo, the manufacturer authorization and funding as reported by the owner, the positioning before wiTECH, what changes and what does not. |
| [MES_PARITY_PLAN.md](MES_PARITY_PLAN.md) | What closes the gap so CUORE is the mechanic's first tool: the ask list for the manufacturer, the read-only car session, the designed write path, the parity board, the exit criterion for MES. |
| [GLOSSARY.md](GLOSSARY.md) | Terms and abbreviations (bus names, adapter commands, UDS services, bulletins, tools). |

## Core directive (check every feature against it)

Before building anything, ask: does this serve diagnosing, proving the repair, or learning for the next car? If not, do not build it. Kept: Job workspace in diagnostic order, flow bar, evidence, hypothesis ledger, proof of repair, cases. Minimal only: Start (VIN and complaint), tools (which tool at this step, is it available, what was used), release (verified or not, record, next car). Not built: boards, throughput, blocking gates, inventory management.

## Where the detail lives

- Product overview and feature tour: `../../README.md`, `../../CUORE.md`, `../FEATURES.md`, `../ARCHITECTURE.md`
- Handbook (decisions, methods, knowledge tables, first live session): `../handbook/`
- Research and reviews: `../research/` (diagnosis write-ups, mechanic reviews, MES capability gaps, bus topology, connectivity)
- Session records: `../sessions/`
- Reference data (specs, known-good values, bulletin catalogue): `../reference/`

## Conventions

- Dates are absolute (YYYY-MM-DD). Commit hashes are short git hashes.
- "The reference car" is the 2018 Alfa Romeo Stelvio 2.0 Turbo used for development and the first worked diagnosis (an EVAP fault). Its identifying details are deliberately not recorded here.
- Facts that came from outside literature are labelled as such and are never presented as proof (see RULES.md, rule 2).
