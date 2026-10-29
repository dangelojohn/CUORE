# In-car CUORE app: feasibility memo

Date: 2026-10-29. Question from the manufacturer's technical contact: can CUORE be built as an app inside the Stelvio and Giulia (2018 to 2026) entertainment system, so an enthusiast connects to the car and the in-car CUORE connects to AlfaCore at the dealer?

Short answer: not as a head-unit app on any current car. A phone-first route is possible today. A head-unit app is only conceivable on a future Android-based platform, and only through a manufacturer partnership. Public sources are thin in places; gaps are stated as "not found in public sources".

## 1. Platform by model year

| Cars | What public sources say | Third-party app path |
|---|---|---|
| Giulia and Stelvio 2018 to 2022 | 8.8 inch touchscreen with Apple CarPlay and Android Auto (https://www.motoringresearch.com/car-news/alfa-romeo-giulia-stelvio-2019/). Supplier and operating system: not found in public sources. The names Uconnect 4C, Harman and QNX in the brief are not confirmed by the searches run. | None found. Phone projection only. |
| 2023 to 2025 facelift | Fully digital 12.3 inch cluster replaced the earlier semi-digital 7 inch unit (https://www.carkeys.co.uk/news/2023-alfa-romeo-giulia-and-stelvio-what-s-changed). Alfa USA lists CarPlay and Android Auto support (https://www.alfaromeousa.com/suvs/2023/stelvio). Whether CarPlay is wireless on these cars, and whether the head unit hardware changed: not found in public sources. | None found. |
| 2026 Stelvio on sale now (US) | Described as a carryover year with the 8.8 inch screen and 12.3 inch cluster, no major infotainment changes (https://www.carvana.com/buy/2026-alfa-romeo-stelvio/). INFERENCE: this is the existing platform, so no app path. | None found. |
| Next-generation Stelvio (not the car above) | Leaks and press say a redesigned model on Stellantis STLA Brain architecture with over-the-air updates and a bigger screen (https://www.carsguide.com.au/car-news/the-suv-to-save-this-car-brand-in-australia-next-generation-2026-alfa-romeo-stelvio-leaked). No official confirmation of operating system or screen size was found (https://www.autoexpress.co.uk/alfa-romeo/stelvio/369682/new-alfa-romeo-stelvio-will-come-both-petrol-and-ev-options). | Unknown. |
| Tonale (reference only) | Uconnect 5, which Stellantis describes as based on Android's automotive operating system (https://www.automotiveworld.com/news/whats-new-for-2024-uconnect-5-builds-upon-its-most-advanced-system-ever-with-new-connected-services-offerings/). | See section 2. |

The project owner's premise of an "all-new 2026 Stelvio" needs checking with the contact: the sources found show a carryover 2026 model and a next generation that is not officially detailed. The statement that the new car is Android Automotive based is INFERENCE only (Tonale precedent), not found in public sources for the Stelvio.

Generations with no third-party app path: every Giulia and Stelvio sold to date, INFERENCE from the absence of any developer program in public sources plus the confirmed use of phone projection only.

## 2. Developer program or app store

- Stellantis Uconnect 5 press material mentions partner content such as Fire TV for Auto, not an open store (same automotiveworld.com URL as above). A developer SDK, store policy or app review process for Uconnect: not found in public sources.
- Stellantis does run a data business, Mobilisights, that licenses connected-vehicle data (https://europe.autonews.com/automakers/stellantis-creates-new-data-services-business), and a developer portal for former PSA brands (Citroen, DS, Peugeot, Opel, Vauxhall) with a B2C web API that is available on request and needs end-user authorisation (https://developer.groupe-psa.io/webapi/b2c/quickstart/data-availability-scopes/). Alfa Romeo is not named there. Alfa Connect data access for outsiders: not found in public sources.
- Admission of a diagnostic app reading vehicle buses: not found in public sources. INFERENCE: it would be a bespoke partnership decision, not a self-service listing.

## 3. What the head unit can and cannot see

- The head unit is an infotainment computer, not the diagnostic gateway. INFERENCE: nothing found shows it exposing DTC reads, UDS requests or live PIDs to apps.
- Since 2018 FCA vehicles have a Secure Gateway Module on the OBD port. Actions that change systems, such as clearing codes, relearns and actuations, need authentication and a gateway unlock; reading codes and live data is not affected (https://www.repairerdrivennews.com/2020/01/20/cic-emerging-tech-head-explains-fca-sgw-says-other-oem-firewalls-coming/). FCA says it is not meant to block aftermarket servicing, and approved tools obtain credentials through AutoAuth, which needs a subscription (https://boschdiagnostics.com/ads-software/secure-gateway).
- Why an in-head-unit app cannot do what CUORE does: CUORE talks to many modules over the OBD port with an adapter, using CAN requests that the head unit does not offer to apps. INFERENCE: even on an Android-based unit, the app would sit behind the manufacturer's own interfaces, which are not published. Any write path would also be subject to the gateway, and the project rule is that writes come only from authoritative sources.

## 4. Routes, ranked

### (d) Dealer-side only. Exists today
Shop runs CUORE on the bench, exports a bundle, AlfaCore imports it (docs/integration/README.md and ALFACORE_LIVE_DEPLOYMENT.md). Effort: none. Dependency: none. Limit: customer must bring the car in.

### (a) Phone first. Realistic next step
Enthusiast owns a Bluetooth or Wi-Fi OBD adapter; CUORE's mobile page (docs/COMPANION_APP_SPEC.md tiers T1 to T3) runs on the phone. Effort: medium to high, because the spec says cloud accounts and a server-side Claude proxy only arrive at tier T3. Dependencies: adapter quality, reads only (the gateway gates writes), legal review noted in the spec.
In-car display: Apple CarPlay lists audio, video when parked, messaging, navigation and task apps such as EV charging, fueling and parking; diagnostics is not listed (https://developer.apple.com/carplay/). Android Auto requires an app to belong to a supported category, and its pages name navigation, point of interest, IoT, weather, media, communication and parked apps; diagnostics is not mentioned (https://developer.android.com/training/cars/apps). INFERENCE: expect phone screen only, not the car screen.

### (b) Manufacturer connected-vehicle data to a cloud CUORE
Needs Stellantis data access for Alfa Romeo, with owner consent. Effort: low code, high commercial. Dependency: a data agreement (Mobilisights or equivalent). What data the car actually uploads is not found in public sources; the PSA portal states vehicle data is not uploaded by default (developer.groupe-psa.io link above). INFERENCE: telemetry will not contain the module-level DTC detail CUORE needs.

### (c) OEM-partnered head-unit app
Only on an Android-based platform, only if the manufacturer agrees. Scope: show CUORE results and book the dealer; diagnostics stay on the phone, adapter or cloud. Effort: high. Dependency: a platform that exists in the Stelvio, which is not confirmed (section 1). Earliest realistic timing is the next-generation cars.

## 5. What "connect to AlfaCore" needs

- Identity: VIN plus owner consent. AlfaCore's existing customer scan API requires the caller to be an active owner of the vehicle and a device paired to that caller and vehicle, creates a new session on each POST and has no idempotency key (docs/integration/ALFACORE_INTEGRATION_SPEC.md, section 5.2).
- Sync API: the current design is offline file transfer, with no network link from CUORE to AlfaCore, no token or TLS client, by owner decision of 2026-10-22 (same spec, sections 1 and 3). Online sync (outbox, token, TLS) was designed earlier in docs/integration/CUORE_SIDE_CONTRACTS.md Part 2 and then superseded. An enthusiast-facing link would reverse that decision and need authentication work.
- Already in the repo: bundle export (cuore/services/bundle_export.py, cuore/api/export.py, cuore/web/static/export.js), bundle schema (docs/integration/cuore_bundle.schema.json), the `alfa_core_cuore` import module live since 2026-10-22, and an optional work order card going the other way. Idempotent import is specified.
- Privacy: VINs and diagnostic data are customer data (spec section 10). Applicable regimes, not researched here and flagged for counsel: PIPEDA in Canada, state laws such as California in the US, GDPR in the EU. Not found in public sources via this memo's searches; do not treat as legal advice.

## 6. Recommendation

Positioning note added 2026-10-29 by the project owner: CUORE is exclusive to Alfa Romeo, Maserati and Ferrari mechanics and technicians, and its purpose is to understand the customer's issue deeply and keep a technical interaction between the customer and the dealership. Any owner-facing or in-car piece is therefore a channel into the dealership's CUORE, not a consumer diagnostic product; routes (a) to (c) below are read in that light.

An in-head-unit CUORE app is not feasible on any Giulia or Stelvio sold so far, because the public record shows only phone projection and no developer program, and the gateway and bus access sit outside the head unit. Do not commit to it. Pursue route (a) as a phone-first, read-only owner app tied to AlfaCore by explicit owner consent, keep (d) as the proven base, and ask the manufacturer whether (b) and (c) are open to a partnership. Treat (c) as a conversation about the next-generation platform, not a build task.

## Questions for the manufacturer's contact

1. Which infotainment platform and operating system does the 2026 Stelvio run, and is a redesigned model with a different platform confirmed?
2. Is there a developer program, SDK or partner process for Alfa Romeo head-unit apps, and are diagnostic or workshop-booking apps admitted?
3. Can Alfa Romeo or Stellantis grant connected-vehicle API access (Alfa Connect, Mobilisights) with owner consent, and for which markets?
4. Which vehicle signals, if any, does the head unit expose to partner apps?
5. Is the Secure Gateway authentication available to a partner for owner-initiated reads, and under what terms?
6. Who owns data-protection responsibility for owner data flowing to a dealer?
