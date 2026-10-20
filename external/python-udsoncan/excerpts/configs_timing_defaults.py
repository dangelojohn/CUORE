# EXCERPT (verbatim, not runnable on its own)
# Source: pylessard/python-udsoncan @ 78e85f1b5dac968b6a2d478fce9c0cc5adba2b50, path udsoncan/configs.py, lines whole file (timing defaults: request_timeout 5, p2_timeout 1, p2_star_timeout 5, use_server_timing True)
# Licence: MIT, Copyright (c) 2017 Pier-Yves Lessard (see ../LICENSE)
# Fetched 2026-10-20. Not imported by CUORE; reference only.

from udsoncan.typing import ClientConfig
from udsoncan import latest_standard
from typing import cast

default_client_config: ClientConfig = cast(ClientConfig, {
    'exception_on_negative_response': True,
    'exception_on_invalid_response': True,
    'exception_on_unexpected_response': True,
    'security_algo': None,
    'security_algo_params': None,
    'tolerate_zero_padding': True,
    'ignore_all_zero_dtc': True,
    'dtc_snapshot_did_size': 2,		# Not specified in standard. 2 bytes matches other services format.
    'server_address_format': None,		# 8,16,24,32,40
    'server_memorysize_format': None,		# 8,16,24,32,40
    'data_identifiers': {},
    'input_output': {},
    'request_timeout': 5,
    'p2_timeout': 1,
    'p2_star_timeout': 5,
    'standard_version': latest_standard,  # 2006, 2013, 2020
    'use_server_timing': True,
    'extended_data_size': None,
    'nrc78_callback':None
})
