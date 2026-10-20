# Source: electricimp/STN1110

- Repo: https://github.com/electricimp/STN1110
- Commit: e0ea82df89b01adae6ecade38d95ebf68d418c0d (HEAD), fetched 2026-10-20
- Licence: MIT, Copyright (c) 2015 Electric Imp (`LICENSE`)
- `excerpts/reset_and_timeout_abort.nut`: from `STN1110.class.nut`; `reset()` (ATZ then ATE0, version line read with or without echo) and `_handleTimeout()` (writes 0x04 to kill a hung command). Lead only for P1 recovery; not verified on an STN1170.
