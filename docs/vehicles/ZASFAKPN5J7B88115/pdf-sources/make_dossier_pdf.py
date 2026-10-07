"""One-page Dossier sheet for the 2018 Stelvio 2.0T, built from the live mes workup (verdict-first layout)."""
import re
import sys
from datetime import date

sys.path.insert(0, r"C:\Users\User\mcp-servers\mes-log-mcp")
from mes import workup  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
OUT = r"C:\Users\User\Desktop\Stelvio Dossier (1 page).pdf"
TODAY = date(2026, 10, 7)

INK, MUTED, ACCENT = colors.HexColor("#1b2227"), colors.HexColor("#5b6770"), colors.HexColor("#9e1b21")
RULE, SHADE = colors.HexColor("#c9d1d6"), colors.HexColor("#f1f4f6")
RED, AMBER, GREEN, GREY = (colors.HexColor("#f4dedf"), colors.HexColor("#f5e8cd"),
                           colors.HexColor("#dcefe1"), colors.HexColor("#e2e6e9"))
ss = getSampleStyleSheet()
b = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=6.9, leading=8.4, textColor=INK)
bb = ParagraphStyle("bb", parent=b, fontName="Helvetica-Bold")
h = ParagraphStyle("h", parent=b, fontName="Helvetica-Bold", fontSize=8.6, leading=10.5, textColor=ACCENT,
                   spaceBefore=3, spaceAfter=2)
sm = ParagraphStyle("sm", parent=b, fontSize=6.4, leading=7.8, textColor=MUTED)
big = ParagraphStyle("big", parent=b, fontName="Helvetica-Bold", fontSize=9.5, leading=11.5)
title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK)


def P(t, s=b):
    return Paragraph(t, s)


def esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def desc_of(r):
    return r.get("description") or ", ".join(r.get("descriptions") or []) or ""


def short_date(ts):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(ts or ""))
    if not m:
        return "-"
    d = date(int(m[1]), int(m[2]), int(m[3]))
    s = f"{d.day} {d.strftime('%b')}"
    return s if d.year == TODAY.year else s + f" '{str(d.year)[2:]}"


GRID = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), SHADE),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.3), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3)]


def table(rows, widths, extra=()):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle(GRID + list(extra)))
    return t


d = workup.build(vin=VIN)
cp = d["current_picture"]
ca = cp.get("clear_assessment") or {}
cleared_at = (ca.get("cleared_at") or "")[:10]
lswf = cp.get("last_session_with_findings") or {}

# --- verdict (computed the same way as cuore's dossier: cleared, nothing since proves either way) ---
returned = ca.get("codes_returned_in_session") or ca.get("codes_that_would_not_clear")
if returned:
    state, bg = "ACTIVE FAULTS", RED
elif cleared_at:
    state, bg = "UNVERIFIED REPAIR", AMBER
else:
    state, bg = "NO DATA", GREY
fam_codes = [c for c in ("P0455", "P0440", "P0456")]
summary = (f"EVAP leak ({'/'.join(fam_codes)}) cleared {short_date(cleared_at)}; monitors have not re-run. "
           f"Not proof of repair.") if state == "UNVERIFIED REPAIR" else ca.get("verdict", "")
verdict = Table([[P(f"<b>{state}</b>", big), P(summary, big)],
                 [P(f"Latest: engine session {short_date(cp['latest_session']['timestamp'])} read clean; all-systems "
                    f"scan {short_date(cp['latest_scan']['timestamp'])} no faults. Both after the clear on "
                    f"{short_date(cleared_at)} ({esc(ca.get('source'))}). Last session with findings: "
                    f"{short_date(lswf.get('timestamp'))}, {', '.join(x['dtc'] for x in lswf.get('dtcs', []))}.", sm), ""],
                 [P("<b>Actions:</b> Verify repair (read readiness with the car connected)  |  EVAP fault tree  |  "
                    "Evidence gate.  Next: drive until the EVAP monitor re-runs (fuel 15-85 %, cold starts, several "
                    "drives), then read readiness or re-scan. A returning code is the answer; silence right after a "
                    "clear is not."), ""]],
                colWidths=[1.45 * inch, 6.05 * inch])
verdict.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("SPAN", (0, 1), (-1, 1)), ("SPAN", (0, 2), (-1, 2)),
                             ("LINEBEFORE", (0, 0), (0, -1), 4, ACCENT if bg is RED else colors.HexColor("#c07a1c")),
                             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))

# --- open work: family checklists ---
EVAP_STEPS = [("Inspect the recirculation-line quick-connect", "S2125000002"),
              ("Purge / vent valve actuation, key on engine off", "MES actuators"),
              ("Hose routing check", "9100325"),
              ("Canister and ESIM check", "9100471"),
              ("Smoke test to localise", "done 3x: sealed"),
              ("Small-leak verification: wiTECH SLVT or Mode $06", "18-048-23")]
NET_STEPS = [("Supply side first: BCM feeds, fuse F82", "S1808000005"),
             ("Connectors and grounds XY201, G003A/B", "S2008000032"),
             ("Terminals", "S1708000262")]
fams = {f["family"]: f for f in d["tsb_matches"]["family_findings"]}


def work_card(title_txt, codes, steps):
    rows = [[P(f"<b>{title_txt}</b>  <font color='#5b6770'>{' '.join(codes)}</font>", bb), ""]]
    for i, (txt, ref) in enumerate(steps, start=1):
        rows.append([P(f"[ ] {i}. {esc(txt)}"), P(esc(ref), sm)])
    t = Table(rows, colWidths=[2.95 * inch, 0.75 * inch])
    t.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), SHADE),
                           ("BOX", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]))
    return t


net_codes = fams.get("network", {}).get("codes", [])
open_work = Table([[work_card("EVAP: one system fault", fams.get("EVAP", {}).get("codes", fam_codes), EVAP_STEPS),
                    work_card("Network: one power / bus event", net_codes[:6] + (["+%d" % (len(net_codes) - 6)] if len(net_codes) > 6 else []), NET_STEPS)]],
                  colWidths=[3.75 * inch, 3.75 * inch])
open_work.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))

# --- codes table with status ---
SYSTEM = {"P": "Engine", "C": "Chassis", "B": "Body", "U": "Network"}
sessions_after_clear = 0  # both 04 Oct logs read clean, so no code was seen after the clear


def status_of(r):
    last = (r.get("last_seen") or "")[:10]
    if cleared_at and last > cleared_at:
        return "ACTIVE", RED
    if r["dtc"].split("-")[0] in fam_codes or (cleared_at and last >= cleared_at[:7]):
        return "CLEARED, UNVERIFIED", AMBER
    return "STALE", GREY


crow = [[P(x, bb) for x in ("Code", "Description", "Sys", "Status", "xN", "Last seen", "km span")]]
extra = []
chronic = sorted(d["history"]["chronic"], key=lambda r: (r["dtc"][0] != "P", -r["sessions"]))
for r in chronic:
    st, bgc = status_of(r)
    crow.append([P(f"<b>{r['dtc']}</b>"), P(esc(desc_of(r))[:60]), P(SYSTEM.get(r["dtc"][0], "")),
                 P(st), P(str(r["sessions"])), P(short_date(r["last_seen"])),
                 P(f"{int(r['distance_span_km']):,}" if r.get("distance_span_km") else "-")])
    extra.append(("BACKGROUND", (3, len(crow) - 1), (3, len(crow) - 1), bgc))
codes_t = table(crow, [0.7 * inch, 3.2 * inch, 0.55 * inch, 1.3 * inch, 0.3 * inch, 0.75 * inch, 0.7 * inch], extra)
once = d["history"]["seen_once"]
once_line = P("<b>Seen once (%d, stale):</b> " % len(once) + ", ".join(
    f"{r['dtc']} ({short_date(r['last_seen'])})" for r in once), sm)

# --- attempted, grouped, failures first ---
# the workup gives one row per occurrence (operation/outcome/timestamp); group by (operation, outcome)
# to get count/first/last ourselves -- the raw records carry no such aggregate fields.
_att_groups = {}
for a in d["already_attempted"]:
    key = (a["operation"], a["outcome"])
    g = _att_groups.setdefault(key, {"operation": a["operation"], "outcome": a["outcome"], "ts": []})
    g["ts"].append(a["timestamp"])
att_grouped = []
for g in _att_groups.values():
    att_grouped.append({"operation": g["operation"], "outcome": g["outcome"], "count": len(g["ts"]),
                         "first": min(g["ts"]), "last": max(g["ts"])})
att = sorted(att_grouped, key=lambda a: (a["outcome"] != "FAILED TO EXECUTE", -a["count"]))
arow = [[P(x, bb) for x in ("Operation", "Outcome", "xN", "First", "Last")]]
aextra = []
for a in att:
    arow.append([P(esc(a["operation"])), P(a["outcome"].title()), P(str(a["count"])), P(short_date(a["first"])),
                 P(short_date(a["last"]))])
    if a["outcome"] == "FAILED TO EXECUTE":
        aextra.append(("BACKGROUND", (1, len(arow) - 1), (1, len(arow) - 1), AMBER))
att_t = table(arow, [1.6 * inch, 0.95 * inch, 0.3 * inch, 0.55 * inch, 0.55 * inch], aextra)

# --- freeze frames with the fuel-window flag ---
frow = [[P(x, bb) for x in ("Code", "Fuel", "Eng temp", "Speed / rpm", "Set")]]
fextra = []
odo_now = d["identity"]["odometer_last_km"]
for code, fr in cp["freeze_frames"].items():
    fuel = float(str(fr.get("Fuel level", "0")).split()[0])
    flag = " <b>above 85 %: monitor could not run</b>" if fuel > 85 else (" below 15 %" if fuel < 15 else "")
    odo = float(str(fr.get("Odometer", "0")).split()[0])
    frow.append([P(f"<b>{code}</b>"), P(f"{fuel:.0f} %{flag}"), P(esc(fr.get("Engine temperature"))),
                 P(f"{esc(fr.get('Vehicle speed'))} / {esc(fr.get('Engine speed'))}"),
                 P(f"{int(odo_now - odo):,} km ago" if odo else "-")])
    if fuel > 85 or fuel < 15:
        fextra.append(("BACKGROUND", (1, len(frow) - 1), (1, len(frow) - 1), AMBER))
ff_t = table(frow, [0.65 * inch, 1.5 * inch, 0.55 * inch, 0.85 * inch, 0.4 * inch], fextra)

# --- bulletins deduplicated ---
bul = {}
for code, lst in d["tsb_matches"]["per_code"].items():
    for x in lst:
        bul.setdefault(x["bulletin"], {"title": x["title"], "codes": []})["codes"].append(code)
brow = [[P(x, bb) for x in ("Bulletin", "What it says", "Codes")]]
for bid, x in sorted(bul.items(), key=lambda kv: -len(kv[1]["codes"])):
    brow.append([P(f"<b>{bid}</b>"), P(esc(x["title"])), P(" ".join(sorted(set(x["codes"]))))])
bul_t = table(brow, [1.0 * inch, 2.2 * inch, 0.75 * inch])

# --- blind spots as actions ---
blind = [[P(x, bb) for x in ("Question", "Action")]]
for bsp in d["blind_spots"]:
    blind.append([P(esc(bsp["question"])), P(esc(bsp["closes_it"]))])
blind_t = table(blind, [1.75 * inch, 2.2 * inch])

right = [P("Already attempted", h), att_t, P("MES actuator tests on the IAW 10JA need key-on engine-off: "
                                              "'Engine running' is an interlock, not a fault.", sm),
         P("Freeze frames", h), ff_t, P("The EVAP monitor only runs with fuel between 15 and 85 %.", sm)]
left = [P("Bulletins", h), bul_t, P("Blind spots: what the logs cannot answer", h), blind_t]
lower = Table([[left, right]], colWidths=[4.05 * inch, 3.45 * inch])
lower.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))

ident = d["identity"]
story = [P("Dossier - 2018 Alfa Romeo Stelvio 2.0T", title),
         P(f"VIN {VIN}  |  {ident['odometer_first_km']:,.0f} to {ident['odometer_last_km']:,.0f} km  |  "
           f"{ident['log_count']} logs {short_date(ident['first_log'])} to {short_date(ident['last_log'])}  |  "
           f"{len(ident['ecu_seen'])} ECUs  |  as of {TODAY.isoformat()}  |  {esc(d['provenance_note'])}", sm),
         Spacer(1, 4), verdict, Spacer(1, 4),
         P("Open work (tick as you go; the cuore dossier keeps the shared tick state)", h), open_work, Spacer(1, 2),
         P("Chronic codes (%d) with status" % len(chronic), h), codes_t, once_line, Spacer(1, 2), lower]


def foot(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(0.5 * inch, 0.35 * inch, f"cuore dossier: /v/{VIN}  |  status colours: red active, amber cleared but "
                 "unverified, grey stale  |  clearing is not fixing")
    c.restoreState()


SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.42 * inch,
                  bottomMargin=0.5 * inch, title="Stelvio Dossier").build(story, onFirstPage=foot, onLaterPages=foot)
print(OUT)
