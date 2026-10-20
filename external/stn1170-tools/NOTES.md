# stn1170-tools (NOTES ONLY, nothing copied)

- URL: https://github.com/bigunclemax/stn1170-tools (last push 2022-03-10)
- Licence: GPL-3.0. Not copied.

## Facts (our 2026-10-20 review; leads, unverified on our car)

- Its device probe sends ATWS and treats a reply containing the ELM327 version string as proof the adapter really restarted.
- It sends a bare CR or `?` to resync the prompt, reads STI for identity, and uses STDI, STIX, STMFR, STSN for info. Baud commands STBR, STWBR, STBRT exist. Protocol select is STP53/STP33 on STN versus ATSPB/ATSP6 on ELM. It never uses ATZ.
- Use for CUORE (P1 lead): after a reset, check the reply text so the log shows whether the adapter really went through a reset instead of assuming it did. Unverified on our STN1170.

## Why not copied

GPL-3.0 terms. The command names are in the vendor command reference.
