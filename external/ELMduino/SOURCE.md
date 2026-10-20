# Source: PowerBroker2/ELMduino

- Repo: https://github.com/PowerBroker2/ELMduino
- Commit: e9d6b55fd63f4afd7789d0981861e9990cdfcd8e (master), fetched 2026-10-20 from raw.githubusercontent.com
- Licence: MIT, Copyright (c) 2020 PB2 (`LICENSE` = upstream `LICENSE.md`)

| Local file | Upstream path | Content |
|---|---|---|
| `excerpts/sendCommand_flush_before_send.cpp` | `src/ELMduino.cpp` 586-608, 2360-2399, 2402-2428 | `flushInputBuff()` (read and discard everything pending); `sendCommand()` which flushes before printing the command + CR; `sendCommand_Blocking()` with the timeout break |

Note for CUORE: `Session.cmd` already calls `reset_input_buffer()` before each write. The excerpt is kept as the reference for what "flush before send" means upstream (a read-and-discard loop, state reset), not as a gap to copy.
