# AlfaCore live deployment and the `alfa_core_cuore` install

Status: recorded 2026-10-22. Source: the owner's session of 2026-10-21/22. This file records what was done and how to use it; it promises nothing beyond that. The bundle design is in [ALFACORE_INTEGRATION_SPEC.md](ALFACORE_INTEGRATION_SPEC.md).

Rules kept here: no passwords or tokens, and no LAN address (the folder rule in [README.md](README.md)). The host's address is in the owner's notes. Logins on the live database are named below; their passwords are not and cannot be read back.

## 1. The live deployment

| Item | Value |
|---|---|
| Host | OdooIQ QNAP TS-x51, QTS 5.2.9 |
| URLs | HTTP on port **9080**; HTTPS on port **9443** (self-signed certificate) |
| Front end | container `alfacore-caddy`, proxying to `odoo:8069` |
| Containers | `alfacore-odoo` (image `odoo-alfacore:19`, Odoo 19.0-20260504), `alfacore-postgres` (database `alfacore`), `alfacore-caddy`; network `alfacore-net` |
| Docker daemon | QNAP runs a **second** daemon: use `docker -H unix:///var/run/system-docker.sock`. The default socket shows only old, stopped containers. |
| Data | Vol 1 (Vol_System, CACHEDEV3), `/share/Container/odoo/{addons,config,odoo-data,logs}` |
| `odoo.conf` | `dbfilter` `^alfacore$`, 3 workers, `list_db` False |
| Neighbours | The QNAP also hosts Forgejo (repo `qnap/alfacore`) and about 7 other Odoo instances behind the same Caddy (ports 9444 to 9452). |

State before the CUORE install: 16 `alfa_*` modules installed; `alfa_core_loaner_sign` uninstalled; `alfa_tsb` present in the addons folder but not registered (it needs Apps > Update Apps List).

Logins on the live database: `admin` (uid 2, active, last sign-in 2026-06-09) and `demo` (uid 5, never signed in). Passwords are hashed. A reset script was prepared and **not run**; it waits for the owner's explicit OK.

## 2. The `alfa_core_cuore` module

AlfaCore side of the file bundle:

| Part | Name |
|---|---|
| Module | `alfa_core_cuore` |
| Model | `alfa.cuore.bundle` |
| Import wizard | `alfa.cuore.import.wizard` |
| Validation | `lib/bundle_schema.py` |
| Tests | 3 Odoo tests |

Git: branch `feature/alfa_core_cuore`, commits `1f7ac55` (feature) and `452c10d` (.po fix), merged to `main` as `a7dce7b`.

### How it was installed (2026-10-22)

1. Tested on a **throwaway database**: a one-off `odoo-alfacore:19` container on `alfacore-net`, the live `odoo.conf` mounted read-only, the branch addons in `/share/Container/alfacore-cuore-test`, run with `-d alfacore_cuore_test --test-enable --stop-after-init --workers=0`. The 3 tests passed. Then the test database was dropped (retry if sessions linger) and the folder removed.
2. **Backup first:** `OdooIQ-Backups/alfacore_before_cuore_20261022-210645.dump`.
3. Copied the module into `/share/Container/odoo/addons`.
4. Installed on the live database `alfacore` with a one-off `odoo-alfacore:19` container on `alfacore-net`: `-i alfa_core_cuore --stop-after-init`.
5. **No restart was needed:** registry signalling reloaded the workers.

Gotcha: the Odoo 19 translation loader needs a `#. module: <name>` comment on **every** `.po` entry, or the install crashes (`odoo/tools/translate.py`, about line 854). The `.po` fix commit `452c10d` is that.

## 3. Using the bundle flow end to end

No network link, no tokens: a person carries a file. Nothing in CUORE contacts AlfaCore.

**On the car-side PC (CUORE)**
1. Connect and run the diagnosis as usual (guided scan, job, hypotheses). Never clear codes for the export's sake.
2. On the scan or job page press **Export for AlfaCore**. This calls `POST /api/export/scan/{scan_id}?vin=...` or `POST /api/export/job/{job_id}?vin=...`; the API needs the usual CUORE token. The reply gives the file name, size, listed files and any warnings.
3. The bundle (`cuore.bundle/1.0`) is written to `<state_dir>/exports/*.cuore.zip`. `GET /api/export/download?path=...` serves it, limited to that folder and to `*.cuore.zip`.
4. Ids are `uuid5`, so importing the same data twice is safe. Exporting twice gives distinct bundle ids that import without duplicates.

**Carry** the zip on a USB stick or shared folder. Delete the removable copy after import (spec section 10).

**In AlfaCore (alfa_core_cuore)**
5. Run the **import wizard** (`alfa.cuore.import.wizard`) with the service order and the zip. The bundle is untrusted input: it is schema-validated (`lib/bundle_schema.py`), shown as a validation report and dry-run preview, and nothing is written until the person confirms (spec 6.3, 6.4).
6. A second import of the same file must say "already imported" and change nothing.
7. Check the result against the acceptance criteria in the spec, section 8 (steps 4 and 5).

## 4. Open

- **Pilot:** one real service order, by file (CUORE export, then AlfaCore import). Not done yet.
- Password rotation on the QNAP: other Odoo containers' database passwords were visible in a `ps` listing on the shared host (values not recorded here). Rotation is recommended.
- The `admin` and `demo` password reset is prepared and waits for the owner's OK.
- Optional Documents area in CUORE; the CUORE licence decision (spec section 10).
