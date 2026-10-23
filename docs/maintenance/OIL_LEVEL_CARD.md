# Oil level card (2018 Stelvio 2.0T)

An "Oil level" card on the vehicle dashboard (`/v/{vin}/dashboard#oil-level`): a horizontal bar with MIN and MAX ticks, litres and US quarts in the sump, % of capacity, % between MIN and MAX, the last reading (date, odometer, method) and the last five readings. Over-full (above MAX) and below-MIN are flagged in red text.

## Entering a reading
Readings are owner events (category `fluids`, kind `oil_level`, confidence "reported"), so there are three ways in, all writing the same row:

- the form on the card itself;
- the phone: Tell CUORE, Fluids, Engine oil level (`/m/{vin}/add/fluids/oil_level`);
- the API: `GET` / `POST /api/vehicles/{vin}/oil-level` with `date`, `odometer_km`, `method`, `dipstick_position_pct`, `litres`, `note`.

`method` is `dipstick` (needs `dipstick_position_pct`: 0 = MIN mark, 100 = MAX mark; may be below 0 or above 100), `measured_fill` (litres poured in after a drain) or `drain_volume` (litres that came out; the "before" value at an oil change). The last two need `litres`.

## Model (`mes-log-mcp/mes/oil_level.py`)
- Capacity with filter 5.2 L (5.5 qt), from `mes.service_specs.OIL_SPEC["capacity_with_filter_qt"]` (AMSOIL engine-code lookup, SINGLE-SOURCE; see `STELVIO_20T_SERVICE_SPECS.md`). Oil 0W-30, MS-13340.
- MIN-to-MAX span: **ASSUMED 1.0 L. Measure once: fill from MIN to MAX and record the volume**, then set `CUORE_OIL_DIPSTICK_RANGE_L`.
- `sump_l = capacity - (1 - position_pct/100) * span`; `% of capacity = sump_l / capacity * 100`; `% between MIN and MAX = position_pct`. MAX is taken as a full fill. Example: 70 % gives 4.9 L / 5.2 qt, 94 % of capacity.
- For measured fill and drain volume the litres are the sump quantity and the dipstick position is derived back from them.

## Oil-change job 6d55b2e32b2a (planned 2026-10-23)
A job note says: record the drained volume as a `drain_volume` reading; it is the before-change quantity on the card, and a dipstick or measured fill after refilling is the after value.

Readings are owner-reported, never car measurements. Check: `.venv/Scripts/python.exe cuore/tests/check_oil_level.py`.
