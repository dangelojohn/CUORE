"""Smoke checks for the CSV recording pipeline.

No real MES CSV has ever been exported on this install, so these fixtures are
built from the documented sample in MES_INTEGRATION_SURFACE.md: UTF-16LE with
BOM, quoted text, names row then units row, Time first, TAG last. A second
fixture deliberately deviates (semicolon separator, comma decimals, UTF-8,
no BOM) to prove the sniffing holds when a locale build differs.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIX = Path(tempfile.mkdtemp(prefix="mes_csv_fixtures_"))
os.environ["MES_CSV_DIR"] = str(FIX)

import server  # noqa: E402  (env must be set before tools run)
from mes import csvlog, paths  # noqa: E402
from mes.errors import MesError  # noqa: E402

failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# --- fixture 1: documented format. Tab, UTF-16LE BOM, quoted header ---------
# 0.5 s cadence, a 5 s dropout after t=6.0, an RPM excursion above 3000
# between 4.0 and 5.0, a DTC tag at 5.0, and an enum column throughout.
rows = []
t = 0.0
for i in range(20):
    rpm = 3500.0 if 4.0 <= t <= 5.0 else 1200.0 + i
    press = 350.0 - i
    clutch = "Released" if i % 2 == 0 else "Pressed"
    tag = "P0456 Evaporation system leak (small)" if t == 5.0 else ""
    rows.append(f'{t:.2f}\t{rpm:.4f}\t{press:.4f}\t"{clutch}"\t"{tag}"')
    t += 5.0 if t == 6.0 else 0.5  # one big gap
f1 = FIX / "rec_tab.csv"
content = ('"Time"\t"Engine speed"\t"Fuel pressure"\t"Clutch pedal"\t"TAG"\n'
           '"sec"\t"rpm"\t"bar"\t" "\t" "\n' + "\n".join(rows))
f1.write_bytes(b"\xff\xfe" + content.encode("utf-16-le"))

# --- fixture 2: locale deviant. Semicolon, comma decimals, UTF-8, ragged ----
f2 = FIX / "rec_semi.csv"
f2.write_text(
    '"Time";"Battery voltage";"TAG"\n'
    '"sec";"V";" "\n'
    '0,00;14,1;""\n'
    '0,50;13,9;""\n'
    '1,00;11,2;"sag"\n'
    '1,50;14,0\n'          # ragged: missing TAG cell
    '2,00;14,2;""\n',
    encoding="utf-8")

# --- containment ------------------------------------------------------------
print("=== containment ===")
for bad in [r"..\..\Windows\win.ini", r"C:\Windows\system.ini",
            r"../rec_tab.csv", "notes.txt"]:
    try:
        paths.resolve_csv(bad)
        check(f"blocked {bad!r}", False, "resolved!")
    except MesError:
        check(f"blocked {bad!r}", True)

# --- parsing: documented format --------------------------------------------
print("=== fixture 1: documented tab/UTF-16LE format ===")
rec = csvlog.load_csv(f1)
check("encoding utf-16-le", rec.encoding.startswith("utf-16"), rec.encoding)
check("separator tab", rec.separator == "\t")
check("3 parameter columns (Time/TAG excluded)", len(rec.columns) == 3,
      [c.name for c in rec.columns])
check("units canonicalised", rec.columns[0].unit == "rpm"
      and rec.columns[1].unit == "bar")
check("20 samples", len(rec.times) == 20, len(rec.times))
timing = rec.timing()
check("dropout detected", len(timing.get("dropouts", [])) == 1,
      timing.get("dropouts"))
check("rate measured", 0 < timing.get("rate_hz", 0) < 3, timing.get("rate_hz"))
check("DTC tag extracted", any(t.dtcs == ["P0456"] for t in rec.tags),
      [t.to_dict() for t in rec.tags])

s = rec.series("engine speed")
stats = s.stats()
check("series numeric, not static", stats["samples"] == 20
      and not stats["static"], stats)
enum = rec.series("Clutch pedal").stats()
check("enum column yields states", "distinct_states" in enum
      and set(enum["distinct_states"]) == {"Released", "Pressed"}, enum)

x = rec.crossings("Engine speed > 3000")
check("one excursion interval, not many hits",
      x["count"] == 1 and x["intervals"][0]["samples"] == 3
      and x["intervals"][0]["extreme"] == 3500.0, x)

snap = rec.snapshot(5.0)
check("snapshot at tag time", snap["sample_s"] == 5.0
      and snap["values"]["Engine speed"].startswith("3500"), snap)

try:
    rec.find_column("e")
    check("ambiguous ref rejected", False)
except MesError as exc:
    check("ambiguous ref rejected", "ambiguous" in str(exc))

# --- parsing: locale deviant ------------------------------------------------
print("=== fixture 2: semicolon / comma-decimal deviant ===")
rec2 = csvlog.load_csv(f2)
check("separator sniffed ;", rec2.separator == ";")
check("comma decimals parsed", rec2.times == [0.0, 0.5, 1.0, 1.5, 2.0],
      rec2.times)
check("ragged row counted and kept", rec2.ragged_rows == 1
      and len(rec2.times) == 5)
check("non-DTC tag kept as event", [t.text for t in rec2.tags] == ["sag"])
low = rec2.crossings("Battery voltage < 12")
check("voltage sag found", low["count"] == 1
      and low["intervals"][0]["extreme"] == 11.2, low)

# --- server tools -----------------------------------------------------------
print("=== server tools ===")
inv = json.loads(server.list_recordings())
check("list_recordings sees both", inv["count"] == 2, inv)
rd = json.loads(server.read_recording("rec_tab.csv", preview_rows=2))
check("read_recording previews", len(rd.get("preview", [])) == 2)
check("dtcs surfaced at top level", rd["dtcs_in_tags"] == ["P0456"])
ev = json.loads(server.recording_events("rec_tab.csv",
                                        condition="Fuel pressure < 340"))
check("recording_events threshold", ev["threshold"]["count"] == 1, ev)
sn = json.loads(server.recording_snapshot("rec_tab.csv", at_seconds=4.8))
check("recording_snapshot nearest sample", sn["sample_s"] == 5.0, sn)
ser = json.loads(server.recording_series("rec_tab.csv", "Battery"))
check("bad column is an error with hints", "error" in ser, ser)
bad = json.loads(server.read_recording(r"..\evil.csv"))
check("server blocks traversal", "error" in bad)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("all checks passed")
