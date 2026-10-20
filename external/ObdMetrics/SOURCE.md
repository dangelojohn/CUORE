# Source: tzebrowski/ObdMetrics

- Repo: https://github.com/tzebrowski/ObdMetrics
- Branch / commit: v11.x @ bf9ca5b97b8eb04a772bde4e70391d0212e2e251, fetched 2026-10-20 from raw.githubusercontent.com
- Licence: Apache-2.0 (`LICENSE`, byte-for-byte). The upstream tree has no NOTICE file at this commit (fetch returned 404). The file keeps its own Apache licence header; it is unmodified, so no change-marking is needed.

| Local file | Upstream path | Content |
|---|---|---|
| `excerpts/DefaultCommandGroup.java` | `src/main/java/org/obd/metrics/command/group/DefaultCommandGroup.java` (whole file, 59 lines) | `INIT`, `CAN_ERROR_RESET` (delay 200 ms, ATWS, delay 500 ms), `RECOVERY_AFTER_STOPPED` (delay 500 ms, bare CR, ATE0, ATCS), `SNIFFING` (ATZ, ATE0, ATL0, ATH1, ATCAF0) |

Open question carried from the tooling review: where upstream triggers `CAN_ERROR_RESET` was not found. The sequence is a lead for CUORE problem P1; whether the delays or the command matters is untested on our adapter.
