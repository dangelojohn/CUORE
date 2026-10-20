# Source: pylessard/python-can-isotp

- Repo: https://github.com/pylessard/python-can-isotp
- Commit: 5593c219f35e739554d743a98d3af68c9332da31 (HEAD), fetched 2026-10-20
- Licence: MIT, Copyright (c) 2017 Pier-Yves Lessard (`LICENSE` = upstream `LICENSE.txt`)
- `excerpts/protocol_params_and_flowcontrol.py`: `isotp/protocol.py` flow-control parsing (STmin encoding, reserved values treated as 0x7F) and the `Params` defaults (`stmin 0`, `blocksize 8`, `rx_flowcontrol_timeout 1000` ms, `rx_consecutive_frame_timeout 1000` ms). Reference for ISO-TP timers if CUORE ever runs with ATCAF0 and must send its own flow control.
