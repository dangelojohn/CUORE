"""Local web UI over the mes-log-mcp library -- no MCP round-trip needed.

Run this on the shop machine (or anywhere on the LAN) and open it from a
phone or tablet mounted near the car. It imports ``mes`` directly, so every
page reflects the CURRENT state of the log corpus -- unlike a generated
Artifact snapshot, there is nothing here to go stale.

    ..\.venv\Scripts\python.exe app.py
    -> http://<this machine's LAN IP>:5000  (find the IP with ipconfig)

Deliberately thin: every real decision (chronic classification, TSB
matching, fault-tree content, the evidence gate's criteria) lives in the
``mes`` package and is unit-tested there. This file only renders it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mes-log-mcp"))

from flask import Flask, redirect, render_template, request, url_for

from mes import faulttree, knowledge, verdict, workup as workup_mod
from mes.catalog import CATALOG
from mes.errors import MesError

app = Flask(__name__)


def _real_vehicles():
    """Vehicles worth showing: a real VIN and at least one non-simulated log."""
    return [v for v in CATALOG.vehicles()
            if v.get("real_logs", 0) > 0 and len(v.get("vin", "")) >= 11]


@app.route("/")
def index():
    return render_template("index.html", vehicles=_real_vehicles(),
                           stats=CATALOG.stats())


@app.route("/vehicle/<vin>")
def vehicle(vin: str):
    dossier = workup_mod.build(vin=vin)
    if "error" in dossier:
        return render_template("error.html", message=dossier["error"]), 404
    open_codes = [d.get("code", d.get("dtc", ""))
                  for d in dossier.get("current_picture", {})
                  .get("latest_session", {}).get("dtcs", [])]
    if not open_codes:
        lf = dossier.get("current_picture", {}).get(
            "last_session_with_findings", {})
        open_codes = [d.get("code", d.get("dtc", "")) for d in
                     lf.get("dtcs", [])]
    trees = faulttree.trees_for(open_codes) if open_codes else []
    return render_template("vehicle.html", vin=vin, d=dossier,
                           open_codes=[knowledge.base_code(c)
                                      for c in open_codes if c],
                           has_tree=bool(trees))


@app.route("/vehicle/<vin>/tree")
def tree(vin: str):
    codes = request.args.get("codes", "")
    if not codes:
        dossier = workup_mod.build(vin=vin)
        lf = dossier.get("current_picture", {}).get(
            "last_session_with_findings",
            dossier.get("current_picture", {}).get("latest_session", {}))
        codes = " ".join(d.get("code", d.get("dtc", ""))
                        for d in lf.get("dtcs", []))
    code_list = [c for c in codes.replace(",", " ").split() if c]
    result = faulttree.evaluate(code_list, vin=vin) if code_list else \
        {"error": "no codes to route", "available": [
            {"tree": t.key, "title": t.title, "applies_to": sorted(t.codes)}
            for t in faulttree.TREES]}
    return render_template("tree.html", vin=vin, codes=codes, result=result)


@app.route("/vehicle/<vin>/verdict", methods=["GET", "POST"])
def diagnosis_verdict(vin: str):
    result = None
    form = {"codes": "", "component": "", "mechanism": "",
            "disconfirming_test": ""}
    measurement_rows = [{"type": "actuator", "operation": ""}]

    if request.method == "POST":
        form["codes"] = request.form.get("codes", "")
        form["component"] = request.form.get("component", "")
        form["mechanism"] = request.form.get("mechanism", "")
        form["disconfirming_test"] = request.form.get(
            "disconfirming_test", "")

        rows = []
        types = request.form.getlist("m_type")
        for i, mtype in enumerate(types):
            row: dict = {"type": mtype}
            op = request.form.get(f"m_operation_{i}", "").strip()
            code = request.form.get(f"m_code_{i}", "").strip()
            name = request.form.get(f"m_name_{i}", "").strip()
            fname = request.form.get(f"m_file_{i}", "").strip()
            cond = request.form.get(f"m_condition_{i}", "").strip()
            desc = request.form.get(f"m_description_{i}", "").strip()
            if mtype == "actuator" and op:
                row["operation"] = op
            elif mtype == "freeze_frame" and code:
                row["code"] = code
            elif mtype == "parameter" and name:
                row["name"] = name
                if fname:
                    row["file"] = fname
            elif mtype == "recording_event" and fname and cond:
                row["file"] = fname
                row["condition"] = cond
            elif mtype == "manual" and desc:
                row["description"] = desc
            else:
                continue
            rows.append(row)
        measurement_rows = rows or measurement_rows

        result = verdict.assess(
            vin=vin, codes=form["codes"], component=form["component"],
            mechanism=form["mechanism"],
            measurements=json.dumps(rows) if rows else "",
            disconfirming_test=form["disconfirming_test"])

    return render_template("verdict.html", vin=vin, form=form,
                           result=result, measurement_rows=measurement_rows)


@app.route("/recordings")
def recordings():
    from mes import csvlog, paths
    return render_template("recordings.html",
                           recs=csvlog.list_recordings(),
                           roots=[str(r) for r in paths.csv_roots()])


@app.route("/recordings/<name>")
def recording_detail(name: str):
    from mes import csvlog
    try:
        rec = csvlog.load_named(name)
    except MesError as exc:
        return render_template("error.html", message=str(exc)), 404
    condition = request.args.get("condition", "")
    crossing = None
    crossing_error = None
    if condition:
        try:
            crossing = rec.crossings(condition)
        except MesError as exc:
            crossing_error = str(exc)
    return render_template("recording.html", name=name,
                           data=rec.to_dict(preview_rows=15),
                           condition=condition, crossing=crossing,
                           crossing_error=crossing_error)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
