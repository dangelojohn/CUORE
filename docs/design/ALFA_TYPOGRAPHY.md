# Alfa typography for CUORE (research, 2026-10-29)

Status: interim. Official Alfa Romeo font files have not been supplied. Everything below is an open-licence stand-in plan. INFERENCE marks my deductions. "Not found" means I searched and could not confirm.

## 1. Alfa Romeo brand typefaces

| Role | Finding | Source | Licence |
|---|---|---|---|
| 2015 badge ring logotype | "Composed with the retouched ITC Blair font", chromed steel. Single source; I found no primary Alfa or Di Robilant document confirming it. Logopedia calls it "Custom". | https://www.museodelmarchioitaliano.it/en/alfa-romeo-2/ ; https://logos.fandom.com/wiki/Alfa_Romeo | ITC Blair is a commercial foundry font (ITC). Not verified here. |
| Institutional/corporate type (2015 guidelines) | Brand Identity Release 2.0, Oct 2015, has a section on the "Apex New" typeface and its family plus an alternative family. The PDF itself failed to fetch (over the 10 MB limit), so this comes from a search summary of its text, not a direct read. | https://www.arocaqld.com/downloads/logos/ar_brand_guidelines.pdf ; https://brandmarketingblog.com/articles/branding-how-to/brand-guide-type/ | Commercial. Designed by Chester Jenkins (with Rick Valicenti on the earlier Apex family), published by Village, later Constellation. A third-party site shows a Thirstype EULA (v2.4, 2005) giving seat-limited use and calling Apex a Village trademark: https://www.cufonfonts.com/font/apex-new . Check current terms with the foundry. |
| Current websites | A third-party "design system" page says Sequel, a proprietary geometric sans, weight 400 only, uppercase labels 11px with 1.5px tracking. It names Futura PT and Avenir Next as substitutes. It admits its extraction hit a market-selector page. Direct confirmation failed: alfaromeo.com returned HTTP 403 to my fetch, so no @font-face was seen. | https://www.shadcn.io/design/alfa-romeo/raw | "Sequel Sans" by OGJ Type Design (Oliver Jeschke, 2017) is a paid family (MyFonts lists $250 for the family): https://myfonts.com/collections/sequel-sans-font-ogj-type-design . INFERENCE: "Sequel" on the page may be this family, but I could not prove it. |

Note: a "free Alfa script" advertised on font blogs (Designbeep) appears to be fan-made, not corporate. Do not use it. https://designbeep.com/2025/12/26/alfa-romeo-font/

## 2. Cluster numerals

Press-photo judgement: not done. I could not view images in this session, so I will not claim a letterform description from a photo. Photo URL judged from: none.

What text sources say:
- 2023+ facelift has a 12.3 inch digital cluster with Evolved, Relax and Heritage layouts. Heritage imitates 1960s-70s Alfa gauges and has distinctive inverted numbers at the end of the speedometer. https://www.bmwblog.com/2022/11/01/alfa-romeo-giulia-facelift
- A font-ID for the 2017-2022 analogue numerals or the digital cluster: not found (forums, font-ID sites searched). The shadcn page only calls the cluster a data-readout look, which is not an identification.

INFERENCE (low confidence, unverified by photo): analogue Alfa gauge numerals are commonly described as upright, fairly condensed, geometric-grotesque with closed digits; treat as a design brief only. Ask the Alfa technical contact for the actual cluster font.

## 3. Open-licence look-alikes (Google Fonts, SIL OFL)

Directory contents confirmed by listing github.com/google/fonts/tree/main/ofl/<family>. Each directory contains an OFL.txt. Google Fonts pages state no file sizes in what I could read: size not stated for all. Fonts not shortlisted: Oswald, Big Shoulders Text, Titillium Web, Rajdhani, Orbitron, Audiowide, Montserrat, Josefin Sans, Barlow Semi Condensed were not evaluated in depth (INFERENCE: shortlist chosen from style knowledge, not side-by-side rendering; render before approving).

### (a) Numerals (gauges, live values)
1. Barlow Condensed. Closest for a DIN-like instrument feel with many weights. Page https://fonts.google.com/specimen/Barlow+Condensed . OFL.
   - Regular https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/BarlowCondensed-Regular.ttf
   - Bold https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/BarlowCondensed-Bold.ttf
2. Saira Condensed. Squared, techy, matches a racing cluster. Page https://fonts.google.com/specimen/Saira+Condensed . OFL.
   - Regular https://raw.githubusercontent.com/google/fonts/main/ofl/sairacondensed/SairaCondensed-Regular.ttf
   - Bold https://raw.githubusercontent.com/google/fonts/main/ofl/sairacondensed/SairaCondensed-Bold.ttf
3. Chakra Petch. Angular-cut corners, a modern digital-cluster look. Page https://fonts.google.com/specimen/Chakra+Petch . OFL.
   - Regular https://raw.githubusercontent.com/google/fonts/main/ofl/chakrapetch/ChakraPetch-Regular.ttf
   - Bold https://raw.githubusercontent.com/google/fonts/main/ofl/chakrapetch/ChakraPetch-Bold.ttf

Tabular figure support (tnum) is not verified for any of these; test in the browser before relying on it.

### (b) Display (headings, brand)
1. Jost. Futura-style geometric sans, closest to the Sequel/Futura PT direction. Page https://fonts.google.com/specimen/Jost . OFL. Variable TTF: https://raw.githubusercontent.com/google/fonts/main/ofl/jost/Jost%5Bwght%5D.ttf
2. Michroma. Wide, small-caps feel, nearest to the wide badge-ring lettering in spirit (the ring is reported as a serif face, so no open font matches it; INFERENCE). Page https://fonts.google.com/specimen/Michroma . OFL. Single weight: https://raw.githubusercontent.com/google/fonts/main/ofl/michroma/Michroma-Regular.ttf

### (c) Body
Keep the system stack. No clearly better OFL match found.

## 4. Proposed cuore.css tokens

```css
:root {
  --display:  "Jost", "Futura", "Century Gothic", system-ui, sans-serif;
  --numerals: "Barlow Condensed", "Arial Narrow", system-ui, sans-serif;
  /* --sans unchanged */
}
.num, .gauge, .live-value {
  font-family: var(--numerals);
  font-variant-numeric: tabular-nums lining-nums;
  font-feature-settings: "tnum" 1, "lnum" 1;
}
```

@font-face blocks, once files are approved and copied under /static/fonts/:

```css
@font-face { font-family: "Barlow Condensed"; font-weight: 400; font-display: swap;
  src: url("/static/fonts/BarlowCondensed-Regular.ttf") format("truetype"); }
@font-face { font-family: "Barlow Condensed"; font-weight: 700; font-display: swap;
  src: url("/static/fonts/BarlowCondensed-Bold.ttf") format("truetype"); }
@font-face { font-family: "Jost"; font-weight: 100 900; font-display: swap;
  src: url("/static/fonts/Jost[wght].ttf") format("truetype"); }
```

Keep the existing "no webfont" comment in mind: the fallbacks above keep the UI usable offline if a file fails to load. Rename the Jost file without brackets before shipping.

## 5. 33 Stradale

The 2023 car has a 3D "telescope" cluster (Alfa calls it "Cannocchiale") mixing analogue and digital elements, changing by Strada or Pista mode; the digital cockpit is by ART (ClusterX family); interior themes are Tributo and Alfa Corse. Typeface or lettering of the cluster or interior: not found. Sources: https://www.alfaromeo.com.au/models/special-series/33-stradale ; https://autotechinsight.spglobal.com/news/5278800/art-partners-with-alfa-romeo-for-high-tech-digital-cockpit-in-33-stradale

---

# Ferrari (data-marque="ferrari")

1. Brand type. The "Ferrari" wordmark lettering: not found (no source naming a typeface). A third-party, unofficial token page says the site uses "FerrariSans", a proprietary sans, medium weight, headings 500 to 700, with a secondary "Body-Font" for uppercase captions: https://open-design.ai/plugins/design-system-ferrari/ . Weak source; "Ferrari Pro" not found. Licensing: proprietary, supplied by Ferrari only.
2. Cluster numerals. Roma shares the SF90 Stradale's curved 16 inch all-digital cluster with a large tachometer (https://www.carscoops.com/2019/12/ferrari-fully-details-the-new-roma-612-hp-grand-tourer/). Numeral letterform, Purosangue cluster, font ID: not found. No photo judged (images not viewable here).
3. Look-alikes (INFERENCE, render before approving), both OFL:
   - Display: Saira, https://fonts.google.com/specimen/Saira , variable TTF https://raw.githubusercontent.com/google/fonts/main/ofl/saira/Saira%5Bwdth,wght%5D.ttf , size not stated.
   - Numerals: Titillium Web, https://fonts.google.com/specimen/Titillium+Web , Regular https://raw.githubusercontent.com/google/fonts/main/ofl/titilliumweb/TitilliumWeb-Regular.ttf , Bold https://raw.githubusercontent.com/google/fonts/main/ofl/titilliumweb/TitilliumWeb-Bold.ttf , size not stated.

# Maserati (data-marque="maserati")

1. Brand type. 2020 identity was designed in-house at Centro Stile, Turin (https://www.designweek.co.uk/issues/14-20-september-2020/maserati-new-logo/). Typeface: no primary source names one. Third-party sites call the wordmark custom lettering or compare it to Bembo (https://madegooddesigns.com/?p=12386 ), unconfirmed. Confirmed name: not found. Licensing: proprietary custom lettering (INFERENCE).
2. Cluster numerals. Grecale has a 12.3 inch digital cluster, graphics made in-house with Rightware Kanzi (https://www.businesswire.com/news/home/20220518005850/en). MC20 has a 10 inch cluster screen. Numeral letterform and font ID: not found. No photo judged.
3. Look-alikes (INFERENCE), both OFL:
   - Display: EB Garamond (Bembo-like old-style serif), https://fonts.google.com/specimen/EB+Garamond , variable TTF https://raw.githubusercontent.com/google/fonts/main/ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf , size not stated.
   - Numerals: Jost (see above), variable TTF https://raw.githubusercontent.com/google/fonts/main/ofl/jost/Jost%5Bwght%5D.ttf , size not stated.

# Marque token mapping

```css
:root[data-marque="alfa"]     { --display: "Jost", "Futura", system-ui, sans-serif;
                                --numerals: "Barlow Condensed", "Arial Narrow", system-ui, sans-serif; }
:root[data-marque="ferrari"]  { --display: "Saira", system-ui, sans-serif;
                                --numerals: "Titillium Web", system-ui, sans-serif; }
:root[data-marque="maserati"] { --display: "EB Garamond", Georgia, serif;
                                --numerals: "Jost", system-ui, sans-serif; }

@font-face { font-family: "Titillium Web"; font-weight: 400; font-display: swap;
  src: url("/static/fonts/TitilliumWeb-Regular.ttf") format("truetype"); }
@font-face { font-family: "Titillium Web"; font-weight: 700; font-display: swap;
  src: url("/static/fonts/TitilliumWeb-Bold.ttf") format("truetype"); }
@font-face { font-family: "Saira"; font-weight: 100 900; font-stretch: 50% 125%; font-display: swap;
  src: url("/static/fonts/Saira-VF.ttf") format("truetype"); }
@font-face { font-family: "EB Garamond"; font-weight: 400 800; font-display: swap;
  src: url("/static/fonts/EBGaramond-VF.ttf") format("truetype"); }
```
Jost and Barlow Condensed blocks are in section 4. Rename bracketed variable files (Saira, EBGaramond, Jost) when copying. Verify the font-stretch range against the font before shipping.
