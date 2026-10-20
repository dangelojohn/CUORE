# ELM327-emulator by Ircama (NOTES ONLY, nothing copied)

- URL: https://github.com/Ircama/ELM327-emulator (last push 2026-09-17)
- Licence: CC BY-NC-SA 4.0 (GitHub reports NOASSERTION). Non-commercial and share-alike: not copied.

## Facts (our 2026-10-20 review)

- It handles ATCAF, ATSH, ATCRA and ATWS. It recognises but does not act on STSLX, STPp, STCFCPA/STCAFCP, STPTO, STIP4 and ATFCSH/ATFCSD/ATFCSM. It does not mention STPX, STFAP or STMA.
- It does not model STN state, so it cannot reproduce CUORE's P1/P2 symptoms.
- Use for CUORE: none. CUORE's bench tests use their own scripted fake adapter (cuore/tests), which can be made stateful for filters and headers without borrowing this code.

## Why not copied

Non-commercial, share-alike licence.
