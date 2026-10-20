# OBDb (Alfa-Romeo-Giulia, Chrysler-300, Maserati and siblings) (NOTES ONLY, nothing copied)

- URLs: https://github.com/OBDb/Alfa-Romeo-Giulia , https://github.com/OBDb/Chrysler-300 and sibling repos
- Licence: CC BY-SA 4.0 (attribution plus share-alike on anything derived). Not copied.

## Facts (our 2026-10-20 review)

- The Giulia and Tonale signal sets are empty. There is no Stelvio repo.
- Chrysler-300 data uses header / response-address pairs and services 0x21 and 0x22 only: no Mode 06, no 0x19, no EVAP/NVLD/ESIM signals. The Giulia tests cover only functional Mode 01 PIDs.
- Use for CUORE: none for P3/P4. The only structural idea (a signal set keyed by request header, response header and command) is something CUORE already does in its own tables.

## Why not copied

Share-alike would pull CUORE's own data under CC BY-SA, and there is nothing in it for our open problems.
