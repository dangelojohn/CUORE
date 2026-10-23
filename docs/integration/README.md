# CUORE and AlfaCore integration: documents

CUORE is the diagnostic engine on the car-side PC (OBD adapter, no network link to AlfaCore). AlfaCore is the Odoo 19 CE service platform on the shop NAS. The two are connected by files moved by a person: a CUORE export bundle one way, an optional work order card the other way. Each document below was written from a reading of the code; none promises that a feature exists.

| File | Read it for | Status |
|---|---|---|
| [ALFACORE_MODEL_MAP.md](ALFACORE_MODEL_MAP.md) | What AlfaCore actually ships: models, fields, states, security groups, the five REST routes that exist, documented stubs, and where CUORE data has no home. Source: the AlfaCore repository at the date in its header. | Complete |
| [CUORE_SIDE_CONTRACTS.md](CUORE_SIDE_CONTRACTS.md) | What CUORE stores and exposes: state files, observation kinds and shapes, identity and key problems, jobs and hypotheses, evidence labels, TSB catalogue and cross-reference, safety invariants, HTTP API appendix. Its Part 2 (online sync design) is superseded by the spec below. | Complete |
| [ALFACORE_INTEGRATION_SPEC.md](ALFACORE_INTEGRATION_SPEC.md) | The decision document: goals, topology, security posture (owner decision), identity and idempotency, bundle and card formats, field-by-field mapping, the new `alfa_core_cuore` module with its import wizard, CUORE-side export work, pilot flow with acceptance criteria, safety invariants, licensing and privacy, open decisions, phased plan and first three tasks. | Draft 2 |
| [ALFACORE_LIVE_DEPLOYMENT.md](ALFACORE_LIVE_DEPLOYMENT.md) | The live AlfaCore deployment, the `alfa_core_cuore` install of 2026-10-22 (test, backup, install, gotcha), how to use the bundle flow end to end, and what is still open. | Recorded 2026-10-22 |

Suggested reading order: the spec first (sections 1 to 4), then the two source files when checking a mapping row (the spec cites them as `[MAP n]` and `[CUORE n.n]`).

Rules for everything in this folder: no credentials, addresses, hostnames or real VINs; customer data stays in deployed systems; fixtures use synthetic VINs only.
