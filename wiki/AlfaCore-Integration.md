# AlfaCore Integration

CUORE diagnoses the car; **AlfaCore** (an Odoo 19 service platform on the shop NAS) is the system of record for customers, vehicles, service orders, parts and invoices. The two are joined by **a file that a person carries**. There is no network link between them and no token: a bay works the same with the NAS up, down or absent. The decision document is [ALFACORE_INTEGRATION_SPEC.md](https://github.com/dangelojohn/CUORE/blob/main/docs/integration/ALFACORE_INTEGRATION_SPEC.md); the live record is [ALFACORE_LIVE_DEPLOYMENT.md](https://github.com/dangelojohn/CUORE/blob/main/docs/integration/ALFACORE_LIVE_DEPLOYMENT.md).

## Car side: the file bundle

- Format `cuore.bundle/1.0`, saved as `<state_dir>/exports/*.cuore.zip`.
- `services/bundle_export.py` builds it (`export_scan`, `export_job`); `services/bundle_schema.py` validates it (`validate_bundle`).
- Ids are `uuid5`, so the same data imported twice makes no duplicates.
- Contracts live in `docs/integration/`: the spec, `ALFACORE_MODEL_MAP.md`, `CUORE_SIDE_CONTRACTS.md` and `cuore_bundle.schema.json`.
- Built in CUORE commit `29b8c13`. It writes only its own export file; it never writes to the car.

## Export button and API

- The **Export for AlfaCore** button on a scan or job page saves the bundle on the PC. Nothing is sent over the network.
- `POST /api/export/scan/{id}?vin=...` and `POST /api/export/job/{id}?vin=...` build a bundle and return its file name, size, file list and warnings.
- `GET /api/export/download?path=...` streams a bundle, limited to `*.cuore.zip` inside the exports folder.

## AlfaCore side: the import module

Module `alfa_core_cuore`: model `alfa.cuore.bundle`, wizard `alfa.cuore.import.wizard`, validation in `lib/bundle_schema.py`, three Odoo tests. The bundle is treated as untrusted input: it is schema-validated, shown as a validation report and dry-run preview, and nothing is written until a person confirms. Branch `feature/alfa_core_cuore` (commits `1f7ac55` and `452c10d`), merged to main as `a7dce7b`.

## The flow

1. Diagnose in CUORE. 2. Press **Export for AlfaCore**. 3. Carry the zip on a USB stick or shared folder. 4. Run the import wizard against the service order. 5. Check the validation report and preview, then confirm. A second import of the same file must change nothing.

## Live deployment (2026-10-22)

- AlfaCore runs on a QNAP NAS as three containers (Odoo 19, Postgres, Caddy) behind an HTTP port and a self-signed HTTPS port. The QNAP runs a second Docker daemon, reached through its own socket; the default socket shows only old stopped containers.
- `alfa_core_cuore` was tested first on a throwaway database (3 tests pass), then installed on the live database after a backup. No restart was needed.
- Lesson: the Odoo 19 translation loader crashes an install if any `.po` entry lacks a `#. module:` comment.
- Addresses, logins and passwords are deliberately not recorded here.

## Open

- **Pilot:** one real service order by file (CUORE export, then AlfaCore import). Not done.
- Password rotation on the NAS (another set of containers' database passwords was visible in a process listing; rotation recommended).
- Optional Documents area in CUORE; the CUORE licence decision.

Related: [[Architecture]], [[Safety Rules|Safety-Rules]], [[Roadmap]], [[Project History|Project-History]].
