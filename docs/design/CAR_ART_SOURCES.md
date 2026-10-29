# Car art and dimension sources for CUORE (research, 2026-10-29)

Status: interim. Nothing was downloaded. INFERENCE marks my deductions. "Not found" means I searched and could not confirm. Several official pages returned HTTP 403 or no spec text to my fetch tool, so the official-first order you asked for could not be met for the numbers: no Alfa Romeo or Stellantis page I could read states the Stelvio dimensions. The table below is therefore from third-party databases that publish the homologation figures, and must be checked against the official package the owner is requesting (section 2).

## 1. Dimensions, 2018 Stelvio 949 (2.0T, 280 hp, AWD)

| Item | Value | Source |
|---|---|---|
| Length | 4,687 mm | A, B |
| Width, mirrors excluded | 1,903 mm | A, B |
| Width, mirrors included | 2,163 mm | A only |
| Height | 1,671 mm (A, for the 2.0T AWD); 1,648 mm or 1,671 mm (B, "depending on configuration") | A, B |
| Wheelbase | 2,818 mm | A, B |
| Front overhang | 861 mm | A; also quoted from an autoevolution-hosted spec PDF in a search summary, the PDF itself was unreadable to me |
| Rear overhang | 1,008 mm | A; same note |
| Front track | 1,613 mm | A, B |
| Rear track | 1,653 mm | A, B |
| Ground clearance | 200 mm | A, B |
| Turning circle | 11.7 m | A, B |
| Tyres | A says 235/60 R18 on 8J x 18. B says 235/55 R19 on 8.0 in wide 19 inch alloys. 20 inch tyre size: not found. | A, B |
| Approach / departure angle | 21.7 / 18.3 degrees | B |

Sources:
- A: https://www.auto-data.net/en/alfa-romeo-stelvio-949-2.0-280hp-awd-automatic-28578 (third-party database, not Alfa)
- B: https://www.carexpert.co.nz/alfa-romeo/stelvio/2018/base/exterior-and-dimensions (third-party, cross-check)
- Candidate for an official-style sheet: https://www.autoevolution.com/pdf/news_attachements/alfa-romeo-releases-technical-specifications-for-the-european-stelvio-115661.pdf . A search summary gave the same wheelbase, track and overhangs. The PDF is compressed and I could not read it, and its issuer is unconfirmed.
- Official pages tried, no dimensions available to my fetch: https://www.alfaromeo.ca/en/stelvio and https://www.alfaromeo.ca/en/stelvio/specs (current 2025 model only). Press site https://www.media.stellantis.com returned HTTP 403.

Variation warning: another database lists a 2.2 diesel with tracks 1,627 / 1,674 mm (https://autotijd.be/en/dimensions/alfa-romeo/stelvio/22-turbo-210-hp-awd), so track depends on engine and wheels. Use the 2.0T figures for the reference car.

### Giulia 952 (2.0T AWD, 2018-2022), one row
Length 4,643 mm; width 1,860 mm (2,024 mm with mirrors); height 1,438 mm; wheelbase 2,820 mm; track 1,556 / 1,629 mm; turning circle 10.8 m; tyres 225/45 R18 front, 255/40 R18 rear. Overhangs and ground clearance: not found. Source: https://www.auto-data.net/en/alfa-romeo-giulia-952-2.0-turbo-280hp-awd-automatic-36545 . A second source for the Giulia: not found.

### INFERENCE: check against the current frame
The frame is 0.16 units per mm, with axles 451 units apart at x=199 and x=650.
- Wheelbase 2,818 mm x 0.16 = 450.9 units. This matches the frame.
- Overhangs: 861 mm = 138 units and 1,008 mm = 161 units. The body should span 61 to 811 units if the front is on the left (swap if the front is on the right). Overall length 4,687 mm = 750 units, which agrees (138 + 451 + 161).
- Height 1,671 mm = 267 units, so the roof is near y=61 with ground at y=328.
- Wheel centre height: a 235/60 R18 tyre has a radius of about 370 mm (18 x 25.4 / 2 + 0.60 x 235), which is 59 units. Ground y=328 minus 59 gives 269, matching the current wheel centre.
- Ground clearance 200 mm = 32 units, so the underbody line sits near y=296.
Compare these against the current drawing before trusting it.

## 2. Official line art and drawings

- Finding: I found no Stellantis or Alfa Romeo page that publishes dimensioned technical drawings (side, front, rear, top) for the Stelvio or Giulia. Not found does not mean they do not exist behind the accredited-media login.
- Stellantis global media site, legal notes: https://www.media.stellantis.com/em-en/page/legal-notes . I could not fetch the page myself (HTTP 403). A search summary of it says images are for reporting purposes by journalists, influencers and media employees, that commercial use and passing material to unauthorised third parties are excluded, and that texts, images, graphics and adaptations are covered by Stellantis copyright.
- Stellantis North America: https://embargoed.stellantisnorthamerica.com/page.do?file=legal . Per a search summary: accredited journalists may use materials "for editorial use only. Personal, commercial or any other use of the materials provided from this site is prohibited."
- Verdict: the press site is editorial only. An internal dealer tool is not editorial, so written permission is required. The manufacturer has now said it backs CUORE, so the right route is a direct request, not the press library.

What the owner should ask the Alfa contact for:
1. CAD-derived orthographic line art (side, front, rear, top) for Stelvio 949 and Giulia 952, as vector files (SVG, DXF or PDF), with the dimension values used.
2. Isometric or three-quarter renders, ideally line or clay style, with transparent background.
3. A written licence covering internal use in a dealer-technician tool, derivative drawings (CUORE redrawing from them), and the Alfa, Maserati and Ferrari expansion.
4. The official homologation dimension sheet for each model and wheel option, so the table in section 1 can be replaced with authoritative numbers.
5. Wheel and tyre options per trim (including 20 inch), since I could not find them.

## 3. Public dimensioned drawings

| Source | What it offers | Licence as found | Verdict |
|---|---|---|---|
| dimensions.com | I could not find an Alfa Romeo Stelvio or Giulia page. Tried /element/alfa-romeo-stelvio, /element/alfa-romeo-stelvio-2018, search and the Vehicles category: 404 or no Alfa entries. Terms page: 404 at the guessed URL. | Not found | Not found. Do not rely on it. |
| the-blueprints.com, free | 2017 Stelvio, PNG 428 x 315 px, credited to Dr Dan Saranga. https://www.the-blueprints.com/blueprints/cars/alfaromeo/82494/view/alfa_romeo_stelvio_2017/ | No licence text on the page; links to Terms of Use. Search results say free images are limited to 500 px without login. Terms page: not found. | No (too small, licence unclear) |
| the-blueprints.com, vector | Stelvio 2019-2022: https://www.the-blueprints.com/vectordrawings/show/19174/alfa_romeo_stelvio_ti . Stelvio 2022 on: https://www.the-blueprints.com/vectordrawings/show/24605/alfa_romeo_stelvio . Front, top, rear, side, AI/EPS/PDF/SVG/DWG/DXF, 1:25 scale, body/window/wheel layers. $25.00 each (13 credits). | Page states no licence; links to Terms of Use, which I could not read. | Only with purchase, after reading the Terms for commercial and internal use. The 2019-2022 file covers the facelift-era years, not necessarily 2018. |
| getoutlines.com, free raster | 2017 Stelvio, PNG 2027 x 662 px: https://getoutlines.com/blueprints/22416/2017-alfa-romeo-stelvio-suv-blueprints | Creative Commons CC BY 4.0, stated on the page | Usable as a tracing base with attribution, but see accuracy note. Page is more permissive than the others. |
| getoutlines.com, vector | Custom order, no price shown; ready vectors $19 to $33 elsewhere on the site: https://getoutlines.com/vector-drawings/5863/2016-alfa-romeo-stelvio-drawings | "Basic License" (terms not shown). Quote: "Our blueprints have an accuracy between 95 and 99%." and "We DO NOT offer exact blueprints. So you CANNOT use our blueprints for engineering, repair, and tuning purposes." | Only with purchase. The accuracy disclaimer is a problem for "internal scrutiny". |
| Wikimedia Commons | https://commons.wikimedia.org/wiki/Category:Alfa_Romeo_Stelvio has subcategories (2023 model, police, QV). The only SVG is a wordmark. No blueprint or orthographic drawings seen. Files carry individual licences. | Per file | No drawings found. Photos only. |

Trademark note (INFERENCE): drawings of the car also depict Alfa Romeo trade dress. That is another reason to get written permission from Alfa, not just a vendor licence.

## 4. 3D models for isometric views

Sketchfab: I could not retrieve a search listing (the page loads by script). A web search found no downloadable Stelvio or Giulia 949/952 model there, only a 1968 33 Stradale under CC BY-NC-SA ( https://sketchfab.com/3d-models/1968-alfa-romeo-33-stradale-b8694795cdc6497fb8937f66457505a9 ). Result: not found. Owner can check the Downloadable and Creative Commons filters by hand.

Paid marketplaces (neutral listing, no recommendation):

| Listing | Price | Size | Licence terms as shown | Notes |
|---|---|---|---|---|
| TurboSquid, Stelvio 2017, https://www.turbosquid.com/3d-models/alfa-romeo-stelvio-2017-1244958 | $129 | 829,238 polygons | Editorial uses only | Page itself returned 403; from search summary |
| TurboSquid, Stelvio 2020 low interior, https://www.turbosquid.com/3d-models/3d-realistic-alfa-romeo-stelvio-model-1549059 | $89 | 655,000 polygons | Editorial uses only | 2020 is a facelift-era body; check it matches the 949 |
| RenderHub, Swan3DStudios, 2018 Stelvio, https://www.renderhub.com/swan3dstudios/alfa-romeo-stelvio-2018 | $100 | 132,000 polygons listed, higher at smooth level 2 | Extended Use License (IP Restricted), "subject to an Editorial Use Only Restriction" | Formats 3DS, BLEND, C4D, FBX, LWO, MAX, MB, OBJ, SKP; published Nov 2018 |
| CGTrader, Stelvio 949 Q4 2017, https://cgtrader.com/3d-models/car/suv/alfa-romeo-stelvio-949-q4-2017-3529183e-c866-4368-8c68-acd0e9398865 | $10 | not stated | "Royalty Free No Ai License" per search summary; page fields unreadable to me | Price this low means accuracy needs checking |
| CGTrader, Stelvio Ti 2020, https://www.cgtrader.com/3d-models/car/suv/alfa-romeo-stelvio-ti-2020 | $129 | about 700,000 vertices | Editorial licence (no AI) | |
| Giulia, RenderHub, https://www.renderhub.com/exquisite/alfa-romeo-giulia | not read | not read | Extended licence with Editorial Use Only Restriction (search summary) | |
| Giulia 2016, 3dcadbrowser, https://3dcadbrowser.com/3d-model/alfa-romeo-giulia-2016 | not read | 750,280 polygons | Licence not stated in snippet | |

Hum3D: no Stelvio or Giulia listing surfaced; not found. Accuracy: I did not open any model, so I cannot vouch for fidelity of any of them. Stating a model is "accurate" would need a side-by-side with the official dimensions in section 1 (wheelbase, overhangs, height).

Licence point (INFERENCE): most Stelvio models are "editorial use only" because the car design belongs to Alfa. Whether a dealer-tool line render counts as editorial is unclear and a vendor cannot grant what Alfa owns. The clean fix is Alfa's own permission, or an Alfa-supplied CAD or mesh.

Tooling: Blender (open source, GPL) can import OBJ, FBX and others. Freestyle gives line renders and the Line Art modifier on Grease Pencil gives vector-style strokes. An orthographic camera gives true side, front, top; a camera at about 35 degrees elevation and 45 degrees azimuth with orthographic projection gives a true isometric look. Output to SVG needs the Freestyle SVG Exporter add-on (ships with Blender) or Grease Pencil SVG export. This is a reasonable path. Caveats (INFERENCE): a 800,000 polygon mesh renders slowly, hidden-line removal on interiors may need cleanup, and results must be checked against the official dimensions.

## 5. Recommended pipeline

1. Ask Alfa for the official package (section 2 list). This is the cleanest licence and the only source with certified accuracy.
2. Meanwhile, correct the current frame from the section 1 numbers (overhangs 861 / 1,008, tracks 1,613 / 1,653, height 1,671) and add dimension lines labelled with the values. Replace with official figures when received. Note the source and date on each dimension.
3. Tracing base, ranked by licence cleanliness: (a) Alfa-supplied line art; (b) getoutlines.com free CC BY 4.0 PNG, with attribution and its stated 95-99% accuracy, checked against section 1; (c) a purchased vector from the-blueprints.com or getoutlines.com, only after the owner reads their Terms; (d) not recommended for internal scrutiny: hand tracing from a photo.
4. Isometric: from an Alfa-supplied model if possible; otherwise a licensed marketplace model, with the owner reading the editorial-only wording first; then Blender Freestyle or Line Art output.
5. The owner must approve any download or purchase before it happens. Nothing has been fetched to disk or bought in this research.
