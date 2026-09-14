# MES CSV Recording Format

**Status: PROVISIONAL.** Unlike `FES_LOG_FORMAT.md` and `SCAN_LOG_FORMAT.md`,
which were reverse-engineered from an 88-file corpus, **no CSV has ever been
recorded on this install**. Everything here comes from read-only inspection of
MES 5.4.0.0 (UI string table IDs 5001–5041, Settings registry values) and the
vendor's documented sample. Confidence is marked per item.

**On the first real export: diff it against this document and update anything
marked `UNCONFIRMED`.** The parser (`mes/csvlog.py`) was built to the spec
below and validated on synthetic fixtures (`tests/check_csv.py`).

---

## How a recording is produced (the workflow that has never been run here)

1. Connect to a module, open the **Graph** tab.
2. Add parameters — up to **4 graphs × 10 parameters** (string IDs 5001–5041);
   `Rate` sets the sampling rate.
3. Optionally enable **Monitor DTCs** (string 4010) — *"writes DTCs into the
   CSV during recording"*.
4. **CSV Start** … drive/test … **CSV Stop** (or Export).
5. The file lands in Settings → **Export Folder**. On this install that is `.`
   — i.e. `C:\Program Files (x86)\Multiecuscan`, same as the logs.
   Changing it needs the MES Settings dialog (the `HKLM\SOFTWARE\Multiecuscan`
   key gives `BUILTIN\Users` only `ReadKey`).
6. Manual CSV export works in **every licence tier including FREE**.

If the export folder is moved, point the parser at it with `MES_CSV_DIR`
(or `MES_CSV_DIRS`, `os.pathsep`-separated).

---

## File format

| Item | Value | Confidence |
|---|---|---|
| Encoding | UTF-16LE with BOM | `CONFIRMED` (vendor sample) — parser falls back to UTF-8/cp1252 anyway |
| Separator | per Settings `CSV Separator`; **Tab** on this install | `CONFIRMED` (registry) — parser sniffs Tab/`;`/`,` per file |
| Quoting | text fields double-quoted | `CONFIRMED` (sample) |
| Row 1 | parameter names | `CONFIRMED` (sample) |
| Row 2 | units | `CONFIRMED` (sample) |
| Column 1 | `Time`, seconds from recording start | `CONFIRMED` (sample) |
| Last column | `TAG` | `CONFIRMED` (sample) |
| Decimal separator | `.` in the sample; comma plausible on other locales | `UNCONFIRMED` — parser accepts both |
| Filename convention | **UNKNOWN** — no example exists | `UNCONFIRMED` — parser accepts any bare `*.csv` in the roots; session time falls back to file mtime |
| Absolute timestamps | none visible in the sample; `Time` is relative | `UNCONFIRMED` |
| DTC rendering under "Monitor DTCs" | assumed to appear in `TAG` | `UNCONFIRMED` — parser surfaces every non-empty TAG as an event and extracts `[PBCU]xxxx` tokens |
| Enum parameters ("Released"…) in cells | plausible (the .txt format has them) | `UNCONFIRMED` — parser types cells individually |

Vendor sample:

```
"Time"  "Engine speed"  "Fuel pressure"  "TAG"
"sec"   "rpm"           "bar"            " "
0.00    1215.0000       366.3000         ""
```

---

## Why this pipeline exists

The `.txt` FES session log has **no per-sample timestamps at all** — order is
file order, rate unrecoverable (`parameter_series` says so on every call).
The CSV is the only MES output with real timing, which enables what the
mcp tools now expose:

| Tool | What it answers |
|---|---|
| `list_recordings` | what recordings exist, parameters, duration, measured rate |
| `read_recording` | columns, timing (rate, median interval, **dropouts**), TAG/DTC events |
| `recording_series` | one parameter with physically meaningful statistics |
| `recording_events` | TAG/DTC events; threshold queries like `"Fuel pressure < 250"` returned as **excursion intervals** (enter/exit/duration/extreme), not per-sample hits |
| `recording_snapshot` | post-hoc freeze frame: every value at the sample nearest time *t* |

Dropout detection flags any inter-sample gap over 3× the median interval —
an adapter or ECU-link stall; values bracketing a gap are not adjacent in
time and must not be read as a trend.

---

## Security

CSV names resolve through `mes.paths.resolve_csv`: bare filename only, must
end `.csv`, resolved real path must sit inside a configured root — the same
containment contract as `resolve_log`, regression-tested in
`tests/check_csv.py`.
