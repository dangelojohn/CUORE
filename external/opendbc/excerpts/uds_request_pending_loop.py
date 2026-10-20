# EXCERPT (verbatim, not runnable on its own: imports and helper types omitted)
# Source: commaai/opendbc @ 48c7f06c6f27c41e7169242acb03ef9775658deb, path opendbc/car/uds.py, lines 592-608 and 611-676 (functional addrs, rx addr rule, UdsClient._uds_request pending loop)
# Licence: MIT, Copyright (c) 2020 Comma.ai, Inc. (see ../LICENSE)
# Fetched 2026-10-20. Not imported by CUORE; reference only.

FUNCTIONAL_ADDRS = [0x7DF, 0x18DB33F1]


def get_rx_addr_for_tx_addr(tx_addr, rx_offset=0x8):
  if tx_addr in FUNCTIONAL_ADDRS:
    return None

  if tx_addr < 0xFFF8:
    # pseudo-standard 11 bit response addr (add 8) works for most manufacturers
    # allow override; some manufacturers use other offsets for non-OBD2 access
    return tx_addr + rx_offset

  if tx_addr > 0x10000000 and tx_addr < 0xFFFFFFFF:
    # standard 29 bit response addr (flip last two bytes)
    return (tx_addr & 0xFFFF0000) + (tx_addr << 8 & 0xFF00) + (tx_addr >> 8 & 0xFF)

  raise ValueError(f"invalid tx_addr: {tx_addr}")

class UdsClient:
  def __init__(self, panda, tx_addr: int, rx_addr: int | None = None, bus: int = 0, sub_addr: int | None = None, rx_sub_addr: int | None = None,
               timeout: float = 1, tx_timeout: float = 1, response_pending_timeout: float = 10):
    self.bus = bus
    self.tx_addr = tx_addr
    self.rx_addr = rx_addr if rx_addr is not None else get_rx_addr_for_tx_addr(tx_addr)
    self.sub_addr = sub_addr
    self.timeout = timeout
    can_send_with_timeout = partial(panda.can_send, timeout=int(tx_timeout*1000))
    self._can_client = CanClient(can_send_with_timeout, panda.can_recv, self.tx_addr, self.rx_addr, self.bus, self.sub_addr, rx_sub_addr)
    self.response_pending_timeout = response_pending_timeout

  # generic uds request
  def _uds_request(self, service_type: SERVICE_TYPE, subfunction: int | None = None, data: bytes | None = None) -> bytes:
    req = bytes([service_type])
    if subfunction is not None:
      req += bytes([subfunction])
    if data is not None:
      req += data

    # send request, wait for response
    isotp_msg = IsoTpMessage(self._can_client, timeout=self.timeout)
    isotp_msg.send(req)
    response_pending = False
    while True:
      timeout = self.response_pending_timeout if response_pending else self.timeout
      resp, _ = isotp_msg.recv(timeout)

      if resp is None:
        continue

      response_pending = False
      resp_sid = resp[0] if len(resp) > 0 else None

      # negative response
      if resp_sid == 0x7F:
        service_id = resp[1] if len(resp) > 1 else -1
        try:
          service_desc = SERVICE_TYPE(service_id).name
        except BaseException:
          service_desc = 'NON_STANDARD_SERVICE'
        error_code = resp[2] if len(resp) > 2 else -1
        try:
          error_desc = _negative_response_codes[error_code]
        except BaseException:
          error_desc = resp[3:].hex()
        # wait for another message if response pending
        if error_code == 0x78:
          response_pending = True
          carlog.debug("UDS-RX: response pending")
          continue
        raise NegativeResponseError(f'{service_desc} - {error_desc}', service_id, error_code)

      # positive response
      if service_type + 0x40 != resp_sid:
        resp_sid_hex = hex(resp_sid) if resp_sid is not None else None
        raise InvalidServiceIdError(f'invalid response service id: {resp_sid_hex}')

      if subfunction is not None:
        resp_sfn = resp[1] if len(resp) > 1 else None
        if subfunction != resp_sfn:
          resp_sfn_hex = hex(resp_sfn) if resp_sfn is not None else None
          raise InvalidSubFunctionError(f'invalid response subfunction: {resp_sfn_hex}')

      # return data (exclude service id and sub-function id)
      return resp[(1 if subfunction is None else 2):]
