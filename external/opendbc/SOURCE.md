# Source: commaai/opendbc

- Repo: https://github.com/commaai/opendbc
- Commit: 48c7f06c6f27c41e7169242acb03ef9775658deb (master, 2026-10-17), fetched 2026-10-20 from raw.githubusercontent.com
- Licence: MIT, Copyright (c) 2020, Comma.ai, Inc. Full text in `LICENSE` (fetched from the same commit). The notice must travel with any copied material.

| Local file | Upstream path | Content |
|---|---|---|
| `fca_giorgio.dbc` | `opendbc/dbc/fca_giorgio.dbc` | whole file, byte-for-byte (37 messages). Added upstream in PR #1250 (a894cc9, 2024-09-18). |
| `excerpts/uds_canclient_drain.py` | `opendbc/car/uds.py` lines 337-416 | `CanClient`: `recv(drain=True)` throws away buffered frames; `send` drains every 10 frames |
| `excerpts/uds_isotp_message.py` | `opendbc/car/uds.py` lines 418-590 | `IsoTpMessage`: `send()` begins with `recv(drain=True)`; flow-control frame bytes; FC status handling |
| `excerpts/uds_request_pending_loop.py` | `opendbc/car/uds.py` lines 592-608, 611-676 | functional addresses, `get_rx_addr_for_tx_addr`, `UdsClient._uds_request` (0x78 pending handling: keep waiting, longer timeout, no resend) |
| `excerpts/chrysler_fw_query_rx_offset.py` | `opendbc/car/chrysler/values.py` lines 131-156 | FCA `F132` / `F194` identity requests and `CHRYSLER_RX_OFFSET = -0x280` |
| `excerpts/isotp_parallel_query.py` | `opendbc/car/isotp_parallel_query.py` whole file | functional request once, then listen on each physical address with `setup_only=True` |

Excerpts carry a header comment (source path, lines, licence) added by CUORE; the code lines themselves are unmodified.

Caveats: the DBC does not state which bus it was captured on (the ids match CAN-CH). Many scales are marked "TBD" / "estimated" upstream. Per CUORE project rule, everything here is a lead; conclusions must cite CUORE's own readings.
