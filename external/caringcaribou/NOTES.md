# caringcaribou (NOTES ONLY, nothing copied)

- URL: https://github.com/CaringCaribou/caringcaribou (last push 2026-06-12)
- Licence: GPL-3.0. Not copied.

## Facts (our 2026-10-20 review; leads, unverified on our car)

- Its UDS module uses short fixed timings: 10 ms between discovery probes, 0.2 s for a service probe, 20 ms for a sub-function probe, 0.2 s per DID in a DID dump, and a TesterPresent cadence of 0.5 s using sub-function 0x80 (suppress positive response) or 0x00.
- The DID dump keeps replies of 4 bytes or more whose echoed DID matches the request. Response-pending (0x78) is not handled there.
- Its service discovery probes every service id 0x00-0xFF, including write services. That is unsafe for CUORE's read-only rule and is not a technique we will use.
- Use for CUORE: only the idea of a 0.5 s TesterPresent cadence while a non-default session is deliberately held, tested on the bench against a scripted fake first. Our own values must come from our readings.

## Why not copied

GPL-3.0 (strong copyleft), and a security-research tool whose main feature (the service sweep) is outside CUORE's rules.
