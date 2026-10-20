# EXCERPT (verbatim, not runnable on its own)
# Source: pylessard/python-can-isotp @ 5593c219f35e739554d743a98d3af68c9332da31, path isotp/protocol.py, lines 150-175 (flow-control STmin decode, craft_flow_control_data), 334-362 (Params defaults)
# Licence: MIT, Copyright (c) 2017 Pier-Yves Lessard (see ../LICENSE)
# Fetched 2026-10-20. Reference only.


            self.flow_status = int(msg_data[0]) & 0xF
            if self.flow_status >= 3:
                raise ValueError('Unknown flow status')

            self.blocksize = int(msg_data[1])
            stmin_temp = int(msg_data[2])

            if stmin_temp >= 0 and stmin_temp <= 0x7F:
                self.stmin_sec = stmin_temp / 1000
            elif stmin_temp >= 0xf1 and stmin_temp <= 0xF9:
                self.stmin_sec = (stmin_temp - 0xF0) / 10000

            if self.stmin_sec is None:
                # ISO-15765-2 requires reserved values to be treated as 0x7F.
                stmin_temp = 0x7F
                self.stmin_sec = stmin_temp / 1000
            self.stmin = stmin_temp

        else:
            raise ValueError("Unsupported PDU type: %s" % self.type)

    @classmethod
    def craft_flow_control_data(cls, flow_status: int, blocksize: int, stmin: int) -> bytes:
        return bytes([(0x30 | (flow_status) & 0xF), blocksize & 0xFF, stmin & 0xFF])


        # ... (lines 334-362)
        tx_padding: Optional[int]
        wftmax: int
        tx_data_length: int
        tx_data_min_length: Optional[int]
        max_frame_size: int
        can_fd: bool
        bitrate_switch: bool
        default_target_address_type: isotp.TargetAddressType
        rate_limit_max_bitrate: int
        rate_limit_window_size: float
        rate_limit_enable: bool
        listen_mode: bool
        blocking_send: bool
        logger_name: str
        wait_func: Callable[[float], None]

        def __init__(self) -> None:
            self.stmin = 0
            self.blocksize = 8
            self.override_receiver_stmin = None
            self.rx_flowcontrol_timeout = 1000
            self.rx_consecutive_frame_timeout = 1000
            self.tx_padding = None
            self.wftmax = 0
            self.tx_data_length = 8
            self.tx_data_min_length = None
            self.max_frame_size = 4095
            self.can_fd = False
            self.bitrate_switch = False
