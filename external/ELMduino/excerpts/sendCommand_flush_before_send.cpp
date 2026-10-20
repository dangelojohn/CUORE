// EXCERPT (verbatim, not compilable on its own)
// Source: PowerBroker2/ELMduino @ e9d6b55fd63f4afd7789d0981861e9990cdfcd8e, path src/ELMduino.cpp, lines 586-608, 2360-2399, 2402-2428
// Licence: MIT, Copyright (c) 2020 PB2 (see ../LICENSE)
// Fetched 2026-10-20. Not imported by CUORE; reference only.

/*
 void ELM327::flushInputBuff()

 Description:
 ------------
  * Flushes input serial buffer

 Inputs:
 -------
  * void

 Return:
 -------
  * void
*/
void ELM327::flushInputBuff()
{
    if (debugMode)
        Serial.println(F("Clearing input serial buffer"));

    while (elm_port->available())
        elm_port->read();
}

/*
 void ELM327::sendCommand(const char *cmd)

 Description:
 ------------
  * Sends a command/query for Non-Blocking PID queries

 Inputs:
 -------
  * const char *cmd - Command/query to send to ELM327

 Return:
 -------
  * void
*/
void ELM327::sendCommand(const char *cmd)
{
    // clear payload buffer
    memset(payload, '\0', PAYLOAD_LEN + 1);

    // reset input serial buffer and number of received bytes
    recBytes = 0;
    flushInputBuff();
    connected = false;

    // Reset the receive state ready to start receiving a response message
    nb_rx_state = ELM_GETTING_MSG;

    if (debugMode)
    {
        Serial.print(F("Sending the following command/query: "));
        Serial.println(cmd);
    }

    elm_port->print(cmd);
    elm_port->print('\r');

    // prime the timeout timer
    previousTime = millis();
    currentTime = previousTime;

/*
 obd_rx_states ELM327::sendCommand_Blocking(const char* cmd)

 Description:
 ------------
    * Sends a command/query and waits for a respoonse (blocking function)
    Sometimes it's desirable to use a blocking command, e.g when sending an AT command.
    This function removes the need for the caller to set up a loop waiting for the command to finish.
    Caller is free to parse the payload string if they need to use the response.

 Inputs:
 -------
  * const char *cmd - Command/query to send to ELM327

 Return:
 -------
  * int8_t - the ELM_XXX status of getting the OBD response
*/
int8_t ELM327::sendCommand_Blocking(const char *cmd)
{
    sendCommand(cmd);
    uint32_t startTime = millis();
    while (get_response() == ELM_GETTING_MSG) {
        if (millis() - startTime > timeout_ms) break;
    }
    return nb_rx_state;
}
