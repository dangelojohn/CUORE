# MES paddle-shift (NA vs Euro) coding on Giulia/Stelvio -- research pass

Date: 2026-10-14. Scope: read-only research (local MES install + public web).
No subagents, no OBD connection, no code edits other than this doc and the
companion data file.

## 1. Which module

**Body Control Module (BCM)**, not TCM and not ESM. MES groups the relevant
setting under its "Body" module tree, in the **CAN Setup** sub-section of
the PROXI/configuration dataset -- the same dataset block MES uses for
other body-config items (parking-sensor wiring, alarm country mode, cruise
light, etc.). The owner's hypothesis that it might be TCM (shift logic) or
ESM (gear-shift actuator) is not supported by any source found; every
source that names a module says Body/BCM.

## 2. MES menu path and exact function name

MES does not expose a single named "Euro paddle mode" function with its own
button. The path, per the community write-up and consistent with MES's own
generic PROXI mechanism (below), is:

1. Connect to the vehicle, select **Body** as the control module.
2. **Adjustments** screen (F7 in the generic flow) -> **CAN Setup**.
3. Locate **byte 156** of the CAN Setup/PROXI data block, bits 4-5.
4. Change the byte from the NA value to the EU value (bitwise: NA =
   `xx01xxxx`, EU = `xx00xxxx`; reported whole-byte values 0x50 -> 0x40).
5. Run **PROXI ALIGNMENT PROCEDURE** (the same named function the official
   User Guide shows -- see below) to push the edited config to the car.

MES's own User Guide (`C:\Program Files (x86)\MultiEcuScan\Multiecuscan
User Guide.pdf`, read locally, not web) documents the *mechanism* generically
using a Fiat Stilo cruise-control-light example: Adjustments screen -> change
the setting's value -> OK -> select **"PROXI ALIGNMENT PROCEDURE"** and press
F10 -> confirm Y -> after success, turn the key to OFF. That confirms the
button/function name ("PROXI ALIGNMENT PROCEDURE") and the generic flow as
vendor-documented; it does not mention paddle shift or byte 156 specifically.

## 3. Prerequisites

From the official generic procedure + the community post:

- Interface connected to the OBD port, car selected (make/model/version),
  **Connect** (F10) first; MES will report if PROXI alignment is already
  not needed (i.e. config already matches).
- No special engine-running requirement is stated anywhere found; the
  official example is done with the interface connected, module selected,
  no mention of engine on/off during the byte edit itself.
- **Before editing**: back up the current PROXI/config data (community
  advice -- "save this PROXI data to a text file for ease of restore if you
  happen to mess something up"). This is not in the official manual; it is
  the one community author's own practice, worth treating as a hard
  prerequisite given there is no documented DID to re-read the single byte
  in isolation.
- **After the edit**: run PROXI ALIGNMENT PROCEDURE, confirm Y, then turn
  the key to OFF per the official manual's closing step before judging the
  change live.
- Community source also flags that **adjacent bits in the same byte/area
  can affect other, unrelated settings** -- "pay close attention and only
  alter what you are attempting to alter as these settings can have dire
  consequences if changed unknowingly."

## 4. What it writes

A **configuration byte inside the BCM's CAN-Setup/PROXI dataset**, not a
RoutineControl actuator test. The write itself is MES's normal
adjustment-value write; **PROXI ALIGNMENT PROCEDURE** is the routine that
then re-synchronises the edited config across the relevant modules on the
car (this is the same procedure the official manual demonstrates for an
unrelated Fiat Stilo setting, so it is a general-purpose "push PROXI config"
routine, not something paddle-shift-specific).

No source gives an ISO 14229 DID number or raw UDS service/byte offset for
this -- "byte 156" is MES's own internal index into its PROXI dataset
representation, not a documented DID. **No DID is invented here.** Reading
or writing this programmatically (outside MES) would need that mapping
reverse-engineered first; it is not in `cuore/live/did_catalog.py` today.

## 5. Risks and reversibility

- Reversible in principle: restore the backed-up byte value and re-run
  PROXI ALIGNMENT PROCEDURE.
- Risk is concentrated in two places: (a) getting the bitwise edit wrong
  within byte 156 (bits 4-5 only; the rest of the byte must be preserved),
  and (b) the single documented source's own warning that this PROXI
  config area has effects beyond paddle behaviour if mishandled.
- No airbag/ABS/steering/immobiliser interaction is reported by any source,
  but BCM also carries alarm/immobiliser-adjacent config on this platform,
  so "it's just the body module" is not the same as "it's low-risk."

## 6. Source grading

- **giuliaforums.com**, thread "Added Neutral to paddle shifters! (EU
  settings)" (https://www.giuliaforums.com/threads/added-neutral-to-paddle-shifters-eu-settings.56872/),
  author **FizzGiGG**, **2024-04-05** -- gives byte 156, bits 4-5, NA/EU
  bit values, Body/BCM + CAN Setup location, PROXI alignment requirement,
  backup advice, and the "dire consequences" caution. This content is
  reproduced (same numbers, same wording) on **giuliatech.com**, thread
  "Multiecuscan (MES) - Popular Settings Compilation"
  (https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80),
  which is the page actually retrieved and quoted above (the giuliaforums.com
  original is now behind a paywall gateway and could not be fetched
  directly). **Grade: SINGLE-SOURCE** -- one originating author, repeated
  across forums, not independently corroborated by a second author or by
  MultiEcuScan's own documentation for this specific byte.
- **multiecuscan.net** official forum has a thread titled "Alfa Roimeo
  [sic] Stelvio 2.2 210 Paddle Shifter Enabling"
  (https://www.multiecuscan.net/forum/viewtopic.php?t=8494, found via
  search) confirming MES's own community discusses paddle-shift
  configuration for Stelvio by name. Its content could not be fetched
  (404 on that path, TLS-certificate mismatch on the alternate
  `forum.multiecuscan.net` host) within this pass's web-call budget, so its
  specifics are **not** used above and this remains an **open,
  unconfirmed lead**, not a corroborating citation.
- **MultiEcuScan User Guide** (local PDF, vendor-official) -- corroborates
  the *generic PROXI Alignment mechanism* (Adjustments -> edit value ->
  "PROXI ALIGNMENT PROCEDURE" -> confirm -> key OFF) but not the Stelvio
  paddle-shift byte itself. Treat as CORROBORATED for mechanism only.
- YouTube video "Alfa Romeo Giulia/Stelvio USA to Euro spec paddle shifting
  mod! General proxy alignment DIY free" (search result, not fetchable as
  text) is consistent by title with the above but was not viewed; not used
  as a citation.

**Overall grade for the specific byte-156 claim: SINGLE-SOURCE.** Do not
present it to the owner as vendor-confirmed.

## 7. CUORE recommendation

### (1) Read-side

CUORE **cannot currently read** the current paddle-shift setting. No DID has
been documented or reverse-engineered for byte 156 (or the BCM PROXI block
it lives in) by any source found, and it is not present in
`cuore/live/did_catalog.py`. Honest status: **needs DID definition** --
this would require either reverse-engineering the BCM's 0x22 DID space on
a real car, or MultiEcuScan publishing the mapping, neither of which exists
yet. Do not fabricate a DID to fill this gap.

### (2) The change stays an MES handoff card

This is a configuration write to a safety-adjacent module via a vendor
tool, with a single-source procedure and no documented DID -- it does not
belong in CUORE's write path regardless of module-blocklist status. The
handoff card:

- **Module**: Body (BCM).
- **Menu path**: Connect -> Body -> Adjustments (F7) -> CAN Setup -> byte
  156, bits 4-5.
- **Prerequisites**: back up current PROXI data to a text file first;
  confirm via MES's own "PROXI alignment not needed" check that you're
  reading current state before editing; change only bits 4-5, leave the
  rest of the byte untouched.
- **Record before/after**: log the exact byte value read before the edit
  and the value written, plus the backup file's name/location.
- **Proxi re-alignment step**: run **PROXI ALIGNMENT PROCEDURE** (F10),
  confirm Y, then key OFF per the official manual's closing step -- this is
  mandatory, not optional, for the edit to take effect.
- **Test-drive note**: confirm both-paddles-pull reaches Neutral and the
  right paddle returns to Drive (the EU behaviour being sought), and
  re-scan all modules for new DTCs after the change, since an adjacent-bit
  slip in the same byte can set unrelated faults.

Record this as a **coding event** in both places the task asked for:
- The **service ledger** (the `service_record` concept already present in
  `cuore/live/media.py`'s `TARGET_KINDS`) -- module, byte before/after,
  tool used (MES), date, backup file reference.
- **owner_events** (`cuore/live/owner_events.py`'s existing `event` record
  shape) -- an attested "module coded by whom" entry: `by: {role, name}`,
  category/kind naming the coding action, `fields` holding module + before
  + after + source citation, confidence `"reported"` like every other
  owner_events row. (Not implemented here -- `cuore/live/*` is out of
  scope for this pass -- but the existing record shapes already fit this
  use without new schema.)

### (3) Should CUORE ever get a "coding tier"? Honest view

**No-go for now**, and I'd stay cautious even later. Reasoning:

- `ACTUATION_BLOCKED_MODULES` in `cuore/live/safety.py` lists TCM, ESM,
  DASM and others because actuating or reconfiguring them wrong can release
  a park lock, disable steering assist, or worse, on a car that can't tell
  the difference between a test and reality. BCM is **not** on that list by
  name, and this research confirms the paddle-shift byte in fact lives in
  BCM, not TCM/ESM -- so a literal module-based gate would let this one
  through. That's the wrong outcome: the one documented source for this
  exact byte explicitly warns that neighbouring bits in the same area have
  "dire consequences if changed unknowingly," which is precisely the risk
  profile the blocklist exists to catch, just on a module the blocklist
  doesn't name. A coding tier needs a risk gate broader than "is this
  module on the actuation blocklist."
- There is no documented DID. CUORE would be writing blind to a vendor's
  internal byte index inferred from one forum post, with no independent
  confirmation -- that fails CUORE's own evidence bar before safety is even
  considered.
- If a coding tier is pursued at all, it would need, at minimum:
  1. **Explicit owner policy** opting into coding-class writes as a
     category separate from diagnostic reads/clears -- this is a different
     risk class and should require its own standing consent, not be folded
     into existing write-consent phrases.
  2. **MCP-only, consent-phrase-gated writes**, never HTTP, matching the
     existing pattern in `safety.py` for every other write path.
  3. **Mandatory backup read** of the full current configuration block
     before any write, stored immutably (not just a note that a human did
     it in MES).
  4. **Mandatory verification read-back** after the write, diffed against
     the expected target value before the event is logged as successful.
  5. **Full audit trail** in both the service ledger and owner_events --
     who, when, before, after, tool, and the source citation this write was
     based on.
  6. The byte/DID itself would need to move from SINGLE-SOURCE to
     CORROBORATED (independent reverse-engineering, not just a repost of
     the same forum claim) before CUORE should even read it, let alone
     write it.

**Go/no-go: NO-GO.** Keep this as a permanent MES-handoff workflow. Even
with all six requirements above eventually met, this specific function's
evidence base doesn't clear CUORE's own bar today, and the module-based
blocklist alone would have missed it -- worth flagging as a gap in
`ACTUATION_BLOCKED_MODULES`'s coverage if/when a coding tier is ever
designed, but that redesign is out of scope for this pass.
