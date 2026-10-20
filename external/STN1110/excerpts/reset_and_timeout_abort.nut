// EXCERPT (verbatim, not runnable on its own)
// Source: electricimp/STN1110 @ e0ea82df89b01adae6ecade38d95ebf68d418c0d, path STN1110.class.nut, lines 12-22 (constants), 48-62 (reset), 223-232 (_handleTimeout)
// Licence: MIT, Copyright (c) 2015 Electric Imp (see ../LICENSE)
// Fetched 2026-10-20. Reference only. Whether 0x04 aborts a command on an STN1170 is UNVERIFIED.

    _NEWLINE_CHAR = 0x0D; // '\r' char
    _PROMPT_CHAR = 0x3E; // '>' char
    _END_OF_PACKET = "\r\r>";
    _COMMAND_RESET = "ATZ";
    _COMMAND_DISABLE_ECHO = "ATE0";
    _COMMAND_SET_BAUD_RATE = "STBR";
    _COMMAND_SUCCESS_REPLY = "OK";
    _END_OF_TRANSMISSION = 0x04;
    _PID_REPLY_MODE_OFFSET = 0x40; // PID responses have the mode offset by 0x40 from the request

    _uart = null; // UART the STN1110 is connected to
    // ...
    // Resets the STN1110 and blocks until the STN1110 is ready to accept commands or times out
    function reset() {
        // write reset command
        _uart.write(_COMMAND_RESET + _NEWLINE);
        try {
            // handle inconsistency in output between hard and soft reset
            local echoOrVersion = _readLineSync();
            if(echoOrVersion == _COMMAND_RESET) {
                _elmVersion = _readLineSync(); // it was an echo, read the next line for version
            } else {
                _elmVersion = echoOrVersion; // no echo, it's the version
            }
            _uart.write(_COMMAND_DISABLE_ECHO + _NEWLINE); // disable echo
            _readLineSync(); // read echo of disable echo command
            local response;
    // ...
    // command timeout handler 
    function _handleTimeout() {
        if(_activeCommand != null && "callback" in _activeCommand && _activeCommand.callback != null) {
            _activeCommand.callback({"err": "command '" + _activeCommand.command + "' timed out"}); // callback with error
        }
        _uart.write(_END_OF_TRANSMISSION); // send EOT char to kill command
        // execute next command
        _clearActiveCommand();
        _executeNextInQueue();
    }
