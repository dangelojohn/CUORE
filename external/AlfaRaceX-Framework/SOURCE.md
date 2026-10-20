# Source: AriotaG/AlfaRaceX-Framework

- Repo: https://github.com/AriotaG/AlfaRaceX-Framework
- Commit: c7e6a11b2d96b43259b0de0e96ba427d56c6c257 (default branch HEAD), fetched 2026-10-20 from raw.githubusercontent.com
- Licence: Apache-2.0 (`LICENSE`, `NOTICE` both copied byte-for-byte; NOTICE text must travel with any redistribution). Files below are unmodified, so no change-marking applies.

| Local file | Upstream path | Content |
|---|---|---|
| `data/stelvio_my20_initial.json` | `database/can/stelvio_my20_initial.json` | the only CAN id table (0x2ED, 0x384, 0x46C, 0x4B2, 0x73C, 0x0FC, 0x0FB, 0x101, 0x226, 0x2EF, 0x3E8, 0x41A, ...) |
| `data/stelvio_my20_22_diesel_q4.json` | `database/vehicles/stelvio_my20_22_diesel_q4.json` | reference profile and bus bitrates (C1 500000, C2 500000, BH 125000) |

Caveats: reference car is a MY20 2.2 JTDm diesel Q4 (ours is a 2018 2.0T petrol); upstream README says hardware validation is pending and its ids agree with BACCAble, so it is a cross-check, not independent proof. Upstream's UDS database is empty by its own README.
