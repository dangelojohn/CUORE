# giulia_ESCape (NOTES ONLY, nothing copied)

- URL: https://github.com/beaups/giulia_ESCape (last push 2022-10-13)
- Licence: none stated, so all rights reserved by default. Not copied.

## Facts (lead, unverified on our car)

- An Arduino sketch for a 2018 Giulia Quadrifoglio on CAN-CH at 500 kbps lists id 0x384 (drive-mode and stalk-button frame) and 0x1FC (suspension control, receive-only) as seen on that bus. Both are unnamed in opendbc.
- The project's own purpose is writing TC/ESC state, which CUORE does not do. Its README says it is untested on Stelvio and on cars with the Secure Gateway.
