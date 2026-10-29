# Corporate acceptance, 2026-10-28 to 2026-10-29

The record of the week CUORE went from a one-car workbench to a project with a manufacturer behind it. Everything below is what the project owner reported in the working session on 2026-10-29; the owner's words are quoted as given. No written agreement, name or document is on file in this repository yet; when one arrives it will be referenced here.

## What happened

**2026-10-28, dealer visit (recall 93C).** The reference Stelvio went to the Alfa Romeo dealer for recall 93C (NHTSA 25V586000, fuel delivery module). The dealer completed the recall ("installed new fuel pump and assembly and fuel module as specified in the recall") and inspected the engine and transmission mounts ("all mounts are good and strong"). Recorded in CUORE as a dealer result and as job actions on the dealer-visit job (d04440124055), with the consequences for the EVAP proof run written on the EVAP job (76d3454bce75) and for the shudder job (871642b7d731).

**2026-10-28, demo.** During the visit the owner showed CUORE to the dealer's mechanics. Owner's report: "dealer was given a demo of cuore and the mechanics loved it". This is the first reaction from a franchised shop with wiTECH on the bench; earlier praise came from independent mechanics (the "open in layout" location cues for juniors and the "Electrical path for:" views for seniors).

**2026-10-29, authorization.** Owner's report, in order:

1. "Stelantis Alfa Tecnical Service Manager for North America has authorized us to continue our build and complete in good time as they would like to deploy it accross north America and Europe".
2. "they have given us approval and authorizatio and permission to all technicall access and Alfa logos and fonts and graphics to engage mechanic and factory user adoption. Ferrari and Mazerati have also shown interest in any Cuore Versions for those Brands".
3. "Alfa Corporate Authorization and Funding was granted for the Cuore Project now we need to make it feel authorized visually, we will continue with Cuore as a pre-emptive tool that is used to diagnose before Wi-Tech is engaged as that is an expensive tool to use."

**2026-10-29, exclusivity and purpose.** Owner's words: "as discussed with Ferrari, Maserati, Alfa Romeo Corporate reps before we started this Cuore Development. Cuore will be exclusie to Alfa Maserati Ferrari Mechanics and Technicians to deeply understand a customer's issues and maintain a deep technical interaction between passionate Italian car customers and their Dealerships". So CUORE is a dealership technician's tool for the three marques, not a consumer app; any owner-facing piece exists to feed the technician's understanding of the customer's issue and to keep the customer and the dealership in a technical conversation.

**2026-10-29, the reference car.** Owner's words: "The Alfa Stelvio we are using is a loaner from Alfa Canada that was planned before Cuore began we are all impressed what Claude and Cuore were able to achieve the corprate vision and excel at it". So the reference Stelvio (VIN ZASFAKPN5J7B88115) is an Alfa Romeo Canada loaner arranged before the project started, and the work on it was followed by the marque.

## What it means

**Positioning (owner decision).** CUORE is the pre-emptive diagnostic tool a shop uses *before* wiTECH is engaged. wiTECH is expensive per use and stays the authoritative manufacturer tool: it keeps the write side (programming, routines, PROXI alignment, battery registration) and the final word. CUORE's job is to arrive at that point with the evidence already gathered, the hypotheses ranked, and the wiTECH session reduced to what only wiTECH can do. This matches the core directive (diagnose on evidence, prove the fix, learn for the next car) and the existing rule that CUORE advises and records while the mechanic decides.

**Brand.** Permission to use Alfa Romeo logos, fonts and graphics. The visual brief is "make it feel authorized". The official brand package (logo files, typeface and its licence, colour references, usage rules) is needed before any of it enters this public repository; until then the marque theme stays as it is (accent colour by VIN, marque-neutral copy) and nothing is fabricated or copied from the web.

**Technical access.** The owner's 2026-10-27 decision stands: CUORE never learns write sequences by capturing MES or AlfaOBD, and writes beyond the legislated clear need a documented, authoritative source. Manufacturer technical access is exactly that source. When service information arrives (routine identifiers, DIDs, reset procedures, security access), the write path is built from it in the order already designed: dry run, gate, typed consent, read-back, audit.

**Markets and marques.** Deployment across North America and Europe, and interest from Ferrari and Maserati, confirm the 2026-10-07 decision to keep marque and market specifics in data and configuration (module maps, DID catalogues, bulletins, units, language) rather than in code. The Maserati fixture test and the VIN-driven `data-marque` switch are the starting point.

**Quality bar.** An external audience now sees every page. Drawings, labels and facts must be right before they ship; the same day the owner called the side profile of the Stelvio "still incorrect", and it is being redrawn.

## What does not change

- The working rules in [RULES.md](RULES.md): evidence first, readings-only conclusions, no writes from the web app, consent phrases for every write over MCP, one owner of the adapter, no raw adapter scripts.
- MES keeps PROXI alignment and battery registration until documented procedures exist.
- Nothing in CUORE claims manufacturer endorsement in its pages or documents until the owner supplies the written confirmation.

## Next steps

1. Receive the brand package from Stellantis and file it with its licence terms (see [External references and licences](../reference/) and the wiki page of the same name).
2. Receive the technical documentation that covers the write path; build service resets and routines from it, never from captures.
3. Finish the visual pass once the assets are in hand: marque header, typeface, colour tokens, the "pre-diagnostic, before wiTECH" positioning line.
4. Due diligence before wider deployment: the public history of this repository (see the 2026-10-26 owner decision on the transcript leak), parts-catalogue data licensing (Mopar data stays out of git), multi-VIN state layout.
5. Collect the specifics of the dealer demo (which screens, what the mechanics reacted to, what confused them) and feed them into build priorities.

## Where this is recorded in CUORE

- Dealer result `recall_status` 2026-10-29T04:45:43 and job actions c3a09629, fdc14cc4, 0821bdd9 (job d04440124055).
- EVAP job note 0b28fdc5; shudder job inspection 26d6ceb2.
- Feedback row f092a2ae1ae8 (dealer demo), vehicle notes 2d343d963f93, 7004faf1c4fb, 356ca95e7066, 211b3ed7e9b9.
