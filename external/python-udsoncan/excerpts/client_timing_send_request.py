# EXCERPT (verbatim, not runnable on its own)
# Source: pylessard/python-udsoncan @ 78e85f1b5dac968b6a2d478fce9c0cc5adba2b50, path udsoncan/client.py, lines 27-37 (SessionTiming), 226-262 (change_session stores server P2/P2*), 2216-2347 (send_request: P2 then P2* on NRC 0x78)
# Licence: MIT, Copyright (c) 2017 Pier-Yves Lessard (see ../LICENSE)
# Fetched 2026-10-20. Not imported by CUORE; reference only.

class SessionTiming:
    """Container for server provided P2 & P2* timeouts."""

    p2_server_max: Optional[float]
    """P2 server max provided by the server. ``None`` if not provided yet """
    p2_star_server_max: Optional[float]
    """P2* server max provided by the server. ``None`` if not provided yet """

    def __init__(self, p2_server_max:Optional[float]=None, p2_star_server_max:Optional[float]=None) -> None:
        self.p2_server_max = p2_server_max
        self.p2_star_server_max = p2_star_server_max

    # ... (lines 226-262)
    def change_session(self, newsession: int) -> Optional[services.DiagnosticSessionControl.InterpretedResponse]:
        """ 
        Requests the server to change the diagnostic session with a :ref:`DiagnosticSessionControl<DiagnosticSessionControl>` service request

        :Effective configuration: ``exception_on_<type>_response``

        :param newsession: The session to try to switch. Values from :class:`DiagnosticSessionControl.Session <udsoncan.services.DiagnosticSessionControl.Session>` can be used.
        :type newsession: int 

        :return: The server response parsed by :meth:`DiagnosticSessionControl.interpret_response<udsoncan.services.DiagnosticSessionControl.interpret_response>`
        :rtype: :ref:`Response<Response>`
        """
        req = services.DiagnosticSessionControl.make_request(newsession)

        named_newsession = '%s (0x%02x)' % (services.DiagnosticSessionControl.Session.get_name(newsession), newsession)
        self.logger.info('%s - Switching session to %s' % (self.service_log_prefix(services.DiagnosticSessionControl), named_newsession))

        response = self.send_request(req)
        if response is None:
            return None

        response = services.DiagnosticSessionControl.interpret_response(response, standard_version=self.config['standard_version'])

        if newsession != response.service_data.session_echo:
            raise UnexpectedResponseException(response, "Response subfunction received from server (0x%02x) does not match the requested subfunction (0x%02x)" % (
                response.service_data.session_echo, newsession))

        if self.config['standard_version'] > 2006:
            assert response.service_data.p2_server_max is not None
            assert response.service_data.p2_star_server_max is not None
            if self.config['use_server_timing']:
                self.logger.info('%s - Received new timing parameters. P2=%.3fs and P2*=%.3fs.  Using these value from now on.' %
                                 (self.service_log_prefix(services.DiagnosticSessionControl), response.service_data.p2_server_max, response.service_data.p2_star_server_max))
                self.session_timing.p2_server_max = response.service_data.p2_server_max
                self.session_timing.p2_star_server_max = response.service_data.p2_star_server_max

        return response

    # ... (lines 2216-2347)
    def send_request(self, request: Request, timeout: int = -1) -> Optional[Response]:
        if request.service is None:
            raise ValueError("Request has no service")

        if timeout < 0:
            # Timeout not provided by user: defaults to Client request_timeout value
            overall_timeout = self.config['request_timeout']
            p2 = self.config['p2_timeout'] if self.session_timing.p2_server_max is None else self.session_timing.p2_server_max
            if overall_timeout is not None:
                single_request_timeout = min(overall_timeout, p2)
            else:
                single_request_timeout = p2
        else:
            overall_timeout = timeout
            single_request_timeout = timeout
        respect_overall_timeout = True
        if overall_timeout is None:
            respect_overall_timeout = False
        using_p2_star = False  # Will switch to true when Nrc 0x78 will be received the first time.

        self.conn.empty_rxqueue()
        self.logger.debug("Sending request to server")
        override_suppress_positive_response = False
        if self.suppress_positive_response.enabled == True and request.service.use_subfunction():
            payload = request.get_payload(suppress_positive_response=True)
            override_suppress_positive_response = True
        else:
            payload = request.get_payload()

        if self.payload_override.enabled:
            payload = self.payload_override.get_overrided_payload(payload)

        if self.suppress_positive_response.enabled and not request.service.use_subfunction():
            self.logger.warning('SuppressPositiveResponse cannot be used for service %s. Ignoring' % (request.service.get_name()))

        self.conn.send(payload)

        spr_used = request.suppress_positive_response or override_suppress_positive_response
        wait_nrc = self.suppress_positive_response.enabled and self.suppress_positive_response.wait_nrc

        if spr_used and not wait_nrc:
            return None

        done_receiving = False
        if respect_overall_timeout:
            overall_timeout_time = time.monotonic() + overall_timeout

        timed_out = False
        while not done_receiving and not timed_out:
            done_receiving = True
            self.logger.debug("Waiting for server response")

            if not respect_overall_timeout or (respect_overall_timeout and time.monotonic() + single_request_timeout < overall_timeout_time):
                timeout_type_used = 'single_request'
                timeout_value = single_request_timeout
            else:
                timeout_type_used = 'overall'
                timeout_value = max(overall_timeout_time - time.monotonic(), 0)

            try:
                recv_payload = self.conn.wait_frame(timeout=timeout_value, exception=True)
            except TimeoutException:
                timed_out = True
            except Exception as e:
                raise e

            if timed_out or recv_payload is None:
                if spr_used:
                    return None
                if timeout_type_used == 'single_request':
                    raise TimeoutException(single_request_timeout, 'P2* timeout' if using_p2_star else 'P2 timeout')
                elif timeout_type_used == 'overall':
                    raise TimeoutException(overall_timeout, 'Global request timeout')
                else:  # Shouldn't go here.
                    raise TimeoutException(timeout_value, 'Timeout')

            response = Response.from_payload(recv_payload)
            self.last_response = response
            self.logger.debug("Received response from server")

            if not response.valid:
                raise InvalidResponseException(response)

            assert response.service is not None
            assert response.code is not None

            if response.service.response_id() != request.service.response_id():
                msg = "Response gotten from server has a service ID different than the request service ID. Received=0x%02x, Expected=0x%02x" % (
                    response.service.response_id(), request.service.response_id())
                raise UnexpectedResponseException(response, msg)

            if not response.positive:
                try:
                    if not Response.Code.is_supported_by_standard(response.code, self.config['standard_version']):
                        self.logger.warning('Given response code "%s" (0x%02x) is not supported byt the UDS standard version that the clients s enforcing (%s)' % (
                            response.code_name,
                            response.code,
                            self.config['standard_version']))
                except ValueError:
                    self.logger.warning('Unkown response code "%s" (0x%02x)', response.code_name, response.code)

                if not request.service.is_supported_negative_response(response.code):
                    self.logger.warning('Given response code "%s" (0x%02x) is not a supported negative response code according to UDS standard.' % (
                        response.code_name, response.code))

                if response.code == Response.Code.RequestCorrectlyReceived_ResponsePending:
                    if self.config['nrc78_callback'] is not None:
                        self.config['nrc78_callback']()
                    
                    done_receiving = False
                    if not using_p2_star:
                        # Received a 0x78 NRC: timeout is now set to P2*
                        p2_star = self.config['p2_star_timeout'] if self.session_timing.p2_star_server_max is None else self.session_timing.p2_star_server_max
                        single_request_timeout = p2_star
                        using_p2_star = True
                        self.logger.debug("Server requested to wait with response code %s (0x%02x), single request timeout is now set to P2* (%.3f seconds)" %
                                          (response.code_name, response.code, single_request_timeout))
                else:
                    raise NegativeResponseException(response)

        assert response.service is not None
        self.logger.info('Received positive response for service %s (0x%02x) from server.' %
                         (response.service.get_name(), response.service.request_id()))

        response.original_request = request

        if spr_used:
            return None

        return response

    # ====  Authentication Service Client Functions
