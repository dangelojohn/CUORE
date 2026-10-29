# Stelvio 949 reference drawings

## getoutlines-2017-stelvio-front-side.png

- Source page: https://getoutlines.com/blueprints/22416/2017-alfa-romeo-stelvio-suv-blueprints
- File: https://getoutlines.com/blueprints/car/alfa-romeo/alfa-romeo-stelvio-2017-2.png (served as GIF 87a, 2027 x 662; converted to PNG here, pixels unchanged)
- Licence: Creative Commons Attribution 4.0 (CC BY 4.0), as stated on the page; attribution: "2017 Alfa Romeo Stelvio blueprint by getoutlines.com, CC BY 4.0".
- Fetched 2026-10-29 with the owner's approval ("download dimensional drawings of stelvio and giulia"). SHA-1 f33f784f6924f...
- Content: FRONT view (left) and SIDE view (right, nose to the left, the car's left side), title band at the bottom. No top or rear view and no printed dimension figures in the free file; the vendor's vector edition adds top and rear.
- Accuracy: the vendor states its blueprints are 95 to 99 percent accurate and not exact. CUORE pins the traced views to the official dimensions in cuore/data/vehicle_dimensions.json (wheelbase, overhangs, track, height) and reports the deviation in the trace notes.
- Use in CUORE: vectorised (potrace-style fill trace, exact line work) into cuore/web/sensor_profile_svg.py as the side view ink layer; the front view is kept for a later Front toggle.

## Not found (2026-10-29)

- A free, CC-licensed blueprint of the Giulia 952: none on getoutlines.com (the 952 is a paid custom order there) or Wikimedia Commons. Paid vectors exist at the-blueprints.com and getoutlines.com (docs/design/CAR_ART_SOURCES.md). Decision pending with the owner.
- Official Stellantis line art: request sent to the Alfa contact via the owner (same doc, section 2).

## commons-first-edition-rear-small.jpg (reference only)

- Source: https://commons.wikimedia.org/wiki/File:Alfa_Romeo_STELVIO_FIRST_EDITION_(ABA-94920)_rear.jpg (Tokumeigakarinoaoshima, CC BY-SA 4.0), 2518 x 1864, kept here downscaled to 1259 x 932. Fetched 2026-10-29 with the owner's approval.
- About 20 to 25 degrees off axis, so it is not a tracing base. It supplied the proportions of the tailgate features (glass, lamps, plate recess, exhaust tips, reflectors) for the constructed rear view; heights came from the side-view trace.
- No square-on rear photo and no top-down photo of the 949 exists on Commons (2026-10-29 search; tools/view_measurements.json and the search notes).

## Constructed views (tools/construct_views.py)

- Top view: x positions from the side-view trace, widths from the front-view trace and the official tracks; stroked line art, our own work.
- Rear view: the front-view envelope mirrored (the outer envelope is the same from both ends), feature heights from the side-view trace, feature widths from the reference photograph above; stroked line art, our own work.
