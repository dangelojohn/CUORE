# BACCAble-firmware (NOTES ONLY, nothing copied)

- URL: https://github.com/tr3ma-crew/BACCAble-firmware (last push 2025-10-05)
- Licence: unclear. LICENSE.md lists only third-party component licences (CANtact MIT, STM32 HAL BSD, ST USB library). The Alfa-specific message tables carry no stated licence and the README says "educational and research purposes". Treated as all rights reserved: no code and no tables copied. Raw ids and byte meanings are facts about the car that CUORE can re-capture itself.

## Facts to verify on our car by passive capture (leads, unverified)

- Bus naming: C1 = OBD pins 6/14 (our CAN-C), C2 = 12/13 (CAN-CH), BH = 3/11 (CAN-IHS, 125 kbps per a code comment).
- UDS pairing rule in the README: request 18DAAABB gets reply 18DABBAA.
- Module addresses seen in code: instrument cluster 0x60, ABS 0x28 (dyno-mode related), RF hub 0xC7. CUORE's own discovery on 2026-10-15 proved ABS at 0x2A on this car (22 F190 returned our VIN, F192/F194 matched Table A). 0x28 therefore conflicts with our evidence; see item 8 of docs/research/EXTERNAL_IMPLEMENTATION_REVIEW.md.
- Address 0xBA is a private convention of that firmware and is forbidden in CUORE (`RESERVED_TARGETS`, immobiliser hazard). Never probe it.
- CAN-IHS 0x3E8: current gear; byte 3 low nibble engaged gear, high nibble target gear indicator.
- Several CAN-C ids with comments (oil pressure/temperature 0x4B2, battery 0x41A/0x420, ACC state 0x73C, DPF 0x5AE which is probably diesel-only) are capture candidates only.
- Its write features (ESC/TC override, start-stop disable, dyno mode, immobiliser) are outside CUORE's read-only rule; only the state-read ideas matter.

## Why not copied

No licence grant for the project's own code or tables.
