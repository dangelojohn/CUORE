# Source: pylessard/python-udsoncan

- Repo: https://github.com/pylessard/python-udsoncan
- Commit: 78e85f1b5dac968b6a2d478fce9c0cc5adba2b50 (master, 2026-09-21), fetched 2026-10-20 from raw.githubusercontent.com
- Licence: MIT, Copyright (c) 2017 Pier-Yves Lessard. `LICENSE` is upstream `LICENSE.txt`.

| Local file | Upstream path | Content |
|---|---|---|
| `excerpts/configs_timing_defaults.py` | `udsoncan/configs.py` whole | default client config: `request_timeout 5`, `p2_timeout 1`, `p2_star_timeout 5`, `use_server_timing True`, `tolerate_zero_padding True` |
| `excerpts/client_timing_send_request.py` | `udsoncan/client.py` 27-37, 226-262, 2216-2347 | `SessionTiming`; `change_session` capturing server P2/P2* from the 0x10 reply; `send_request` (empties RX queue first, waits P2, switches once to P2* on NRC 0x78, distinguishes P2 / P2* / global timeout) |

Upstream `tester_present()` (client.py ~389) sends one request and has no keepalive thread; CUORE would own any keepalive.
Facts here are reference only; conclusions about our car cite CUORE's own readings.
