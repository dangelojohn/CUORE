# EXCERPT (verbatim, not runnable on its own: imports and helper types omitted)
# Source: commaai/opendbc @ 48c7f06c6f27c41e7169242acb03ef9775658deb, path opendbc/car/uds.py, lines 418-590 (IsoTpMessage: send() drains first; flow control frame)
# Licence: MIT, Copyright (c) 2020 Comma.ai, Inc. (see ../LICENSE)
# Fetched 2026-10-20. Not imported by CUORE; reference only.

class IsoTpMessage:
  def __init__(self, can_client: CanClient, timeout: float = 1, single_frame_mode: bool = False, separation_time: float = 0):
    self._can_client = can_client
    self.timeout = timeout
    self.single_frame_mode = single_frame_mode
    self.max_len = 8 if self._can_client.sub_addr is None else 7

    # <= 127, separation time in milliseconds
    # 0xF1 to 0xF9 UF, 100 to 900 microseconds
    if 1e-4 <= separation_time <= 9e-4:
      offset = int(round(separation_time, 4) * 1e4) - 1
      separation_time = 0xF1 + offset
    elif 0 <= separation_time <= 0.127:
      separation_time = round(separation_time * 1000)
    else:
      raise Exception("Separation time not in range")

    self.flow_control_msg = bytes([
      0x30,  # flow control
      0x01 if self.single_frame_mode else 0x00,  # block size
      separation_time,
    ]).ljust(self.max_len, b"\x00")

  def send(self, dat: bytes, setup_only: bool = False) -> None:
    # throw away any stale data
    self._can_client.recv(drain=True)

    self.tx_dat = dat
    self.tx_len = len(dat)
    self.tx_idx = 0
    self.tx_done = False

    self.rx_dat = b""
    self.rx_len = 0
    self.rx_idx = 0
    self.rx_done = False

    if not setup_only:
      carlog.debug(f"ISO-TP: REQUEST - {hex(self._can_client.tx_addr)} 0x{bytes.hex(self.tx_dat)}")
    self._tx_first_frame(setup_only=setup_only)

  def _tx_first_frame(self, setup_only: bool = False) -> None:
    if self.tx_len < self.max_len:
      # single frame (send all bytes)
      if not setup_only:
        carlog.debug(f"ISO-TP: TX - single frame - {hex(self._can_client.tx_addr)}")
      msg = (bytes([self.tx_len]) + self.tx_dat).ljust(self.max_len, b"\x00")
      self.tx_done = True
    else:
      # first frame (send first 6 bytes)
      if not setup_only:
        carlog.debug(f"ISO-TP: TX - first frame - {hex(self._can_client.tx_addr)}")
      msg = (struct.pack("!H", 0x1000 | self.tx_len) + self.tx_dat[:self.max_len - 2]).ljust(self.max_len - 2, b"\x00")
    if not setup_only:
      self._can_client.send([msg])

  def recv(self, timeout=None) -> tuple[bytes | None, bool]:
    if timeout is None:
      timeout = self.timeout

    start_time = time.monotonic()
    rx_in_progress = False
    try:
      while True:
        for msg in self._can_client.recv():
          frame_type = self._isotp_rx_next(msg)
          start_time = time.monotonic()
          # Anything that signifies we're building a response
          rx_in_progress = frame_type in (ISOTP_FRAME_TYPE.FIRST, ISOTP_FRAME_TYPE.CONSECUTIVE)
          if self.tx_done and self.rx_done:
            return self.rx_dat, False
        # no timeout indicates non-blocking
        if timeout == 0:
          return None, rx_in_progress
        if time.monotonic() - start_time > timeout:
          raise MessageTimeoutError("timeout waiting for response")
    finally:
      if self.rx_dat:
        carlog.debug(f"ISO-TP: RESPONSE - {hex(self._can_client.rx_addr)} 0x{bytes.hex(self.rx_dat)}")

  def _isotp_rx_next(self, rx_data: bytes) -> ISOTP_FRAME_TYPE:
    # TODO: Handle CAN frame data optimization, which is allowed with some frame types
    # # ISO 15765-2 specifies an eight byte CAN frame for ISO-TP communication
    # assert len(rx_data) == self.max_len, f"isotp - rx: invalid CAN frame length: {len(rx_data)}"

    if rx_data[0] >> 4 == ISOTP_FRAME_TYPE.SINGLE:
      assert self.rx_dat == b"" or self.rx_done, "isotp - rx: single frame with active frame"

      # "if the first byte is 0x00, then it's a CAN-FD SF, and the second byte specifies the size of the data."
      # - https://en.wikipedia.org/wiki/CAN_FD
      if rx_data[0] & 0x0F == 0 and len(rx_data) > 8:
        self.rx_len = rx_data[1]
        offset = 2
        # TODO: update self.max_len for CAN FD
        max_len = 62 if self._can_client.sub_addr is None else 61
        assert self.rx_len <= max_len, f"isotp - rx: invalid single frame length: {self.rx_len}"
      else:
        self.rx_len = rx_data[0] & 0x0F
        offset = 1
        assert self.rx_len < self.max_len, f"isotp - rx: invalid single frame length: {self.rx_len}"

      self.rx_dat = rx_data[offset:offset + self.rx_len]
      self.rx_idx = 0
      self.rx_done = True
      carlog.debug(f"ISO-TP: RX - single frame - {hex(self._can_client.rx_addr)} idx={self.rx_idx} done={self.rx_done}")
      return ISOTP_FRAME_TYPE.SINGLE

    elif rx_data[0] >> 4 == ISOTP_FRAME_TYPE.FIRST:
      # TODO: support CAN FD first frames
      # Once a first frame is received, further frames must be consecutive
      assert self.rx_dat == b"" or self.rx_done, "isotp - rx: first frame with active frame"
      self.rx_len = ((rx_data[0] & 0x0F) << 8) + rx_data[1]
      assert self.rx_len >= self.max_len, f"isotp - rx: invalid first frame length: {self.rx_len}"
      assert len(rx_data) == self.max_len, f"isotp - rx: invalid CAN frame length: {len(rx_data)}"
      self.rx_dat = rx_data[2:]
      self.rx_idx = 0
      self.rx_done = False
      carlog.debug(f"ISO-TP: RX - first frame - {hex(self._can_client.rx_addr)} idx={self.rx_idx} done={self.rx_done}")
      carlog.debug(f"ISO-TP: TX - flow control continue - {hex(self._can_client.tx_addr)}")
      # send flow control message
      self._can_client.send([self.flow_control_msg])
      return ISOTP_FRAME_TYPE.FIRST

    elif rx_data[0] >> 4 == ISOTP_FRAME_TYPE.CONSECUTIVE:
      assert not self.rx_done, "isotp - rx: consecutive frame with no active frame"
      self.rx_idx += 1
      assert self.rx_idx & 0xF == rx_data[0] & 0xF, "isotp - rx: invalid consecutive frame index"
      rx_size = self.rx_len - len(self.rx_dat)
      self.rx_dat += rx_data[1:1 + rx_size]
      if self.rx_len == len(self.rx_dat):
        self.rx_done = True
      elif self.single_frame_mode:
        # notify ECU to send next frame
        self._can_client.send([self.flow_control_msg])
      carlog.debug(f"ISO-TP: RX - consecutive frame - {hex(self._can_client.rx_addr)} idx={self.rx_idx} done={self.rx_done}")
      return ISOTP_FRAME_TYPE.CONSECUTIVE

    elif rx_data[0] >> 4 == ISOTP_FRAME_TYPE.FLOW:
      assert not self.tx_done, "isotp - rx: flow control with no active frame"
      assert rx_data[0] != 0x32, "isotp - rx: flow-control overflow/abort"
      assert rx_data[0] == 0x30 or rx_data[0] == 0x31, "isotp - rx: flow-control transfer state indicator invalid"
      if rx_data[0] == 0x30:
        carlog.debug(f"ISO-TP: RX - flow control continue - {hex(self._can_client.tx_addr)}")
        delay_ts = rx_data[2] & 0x7F
        # scale is 1 milliseconds if first bit == 0, 100 micro seconds if first bit == 1
        delay_div = 1000. if rx_data[2] & 0x80 == 0 else 10000.
        delay_sec = delay_ts / delay_div

        # first frame = 6 bytes, each consecutive frame = 7 bytes
        num_bytes = self.max_len - 1
        start = self.max_len - 2 + self.tx_idx * num_bytes
        count = rx_data[1]
        end = start + count * num_bytes if count > 0 else self.tx_len
        tx_msgs = []
        for i in range(start, end, num_bytes):
          self.tx_idx += 1
          # consecutive tx messages
          msg = (bytes([0x20 | (self.tx_idx & 0xF)]) + self.tx_dat[i:i + num_bytes]).ljust(self.max_len, b"\x00")
          tx_msgs.append(msg)
        # send consecutive tx messages
        self._can_client.send(tx_msgs, delay=delay_sec)
        if end >= self.tx_len:
          self.tx_done = True
        carlog.debug(f"ISO-TP: TX - consecutive frame - {hex(self._can_client.tx_addr)} idx={self.tx_idx} done={self.tx_done}")
      elif rx_data[0] == 0x31:
        # wait (do nothing until next flow control message)
        carlog.debug(f"ISO-TP: TX - flow control wait - {hex(self._can_client.tx_addr)}")
      return ISOTP_FRAME_TYPE.FLOW

    # 4-15 - reserved
    else:
      raise Exception(f"isotp - rx: invalid frame type: {rx_data[0] >> 4}")

