"""Smoke checks for mechanic feedback: a correction, a question, a
confirmation, input, or disagreement pinned to a fact cuore showed, and
later answerable.

CUORE_STATE_DIR is pointed at a fresh tempdir BEFORE anything cuore/mes is
imported, so this never writes to the real state directory. ``app.py`` is
owned by another agent and does not register ``cuore.api.feedback``, so this
test builds its own minimal FastAPI app around that router -- same pattern
``check_labels.py`` uses for ``labels_routes``.

Run:
    .venv/Scripts/python.exe cuore/tests/check_feedback.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-feedback-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: F401,E402
from cuore.config import load as load_settings  # noqa: E402
from cuore.services.errors import BridgeError  # noqa: E402
from cuore.api import feedback  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = load_settings()

    @app.exception_handler(BridgeError)
    async def _bridge_error(request: Request, exc: BridgeError):
        return JSONResponse(status_code=exc.status,
                            content={"error": type(exc).__name__, "detail": str(exc)})

    app.include_router(feedback.router, prefix="/api")
    return app


client = TestClient(build_app())


def target(item: str = "P0456") -> dict:
    return {"page": "dossier", "section": "dtcs", "item": item,
           "label": "P0456 Evaporative Emission System"}


# --- 1. add a question -> listed open --------------------------------------

r = client.post(f"/api/vehicles/{VIN}/feedback",
                json={"kind": "question", "target": target(),
                     "text": "was this cleared and re-set, or continuous?"})
check("add question responds 200", r.status_code == 200, str(r.status_code))
q = r.json()
check("question kind is question", q["kind"] == "question")
check("question starts open", q["status"] == "open", q["status"])
qid = q["id"]

listed = client.get(f"/api/vehicles/{VIN}/feedback?status=open").json()
check("question appears in open listing",
     any(f["id"] == qid for f in listed["feedback"]),
     str([f["id"] for f in listed["feedback"]]))

# --- 2. answer -> status answered with text ---------------------------------

ans = client.post(f"/api/feedback/{qid}/answer",
                  json={"text": "continuous since 2026-08, never cleared.", "by": "claude"})
check("answer responds 200", ans.status_code == 200, str(ans.status_code))
ans_body = ans.json()
check("status is answered", ans_body["status"] == "answered", ans_body["status"])
check("answer text stored", ans_body["answer"]["text"] ==
     "continuous since 2026-08, never cleared.", str(ans_body["answer"]))
check("answer author stored", ans_body["answer"]["by"] == "claude")

no_longer_open = client.get(f"/api/vehicles/{VIN}/feedback?status=open").json()
check("answered row no longer in open listing",
     not any(f["id"] == qid for f in no_longer_open["feedback"]))

# --- 3. invalid kind -> 400 --------------------------------------------------

bad = client.post(f"/api/vehicles/{VIN}/feedback",
                  json={"kind": "nonsense", "target": target(), "text": "x"})
check("invalid kind is 400", bad.status_code == 400, str(bad.status_code))

bad_status = client.post(f"/api/feedback/{qid}/status", json={"status": "nonsense"})
check("invalid status is 400", bad_status.status_code == 400, str(bad_status.status_code))

bad_id = client.post("/api/feedback/does-not-exist/answer", json={"text": "x"})
check("unknown id answer is 400", bad_id.status_code == 400, str(bad_id.status_code))

# --- 4/5. counts per target, confirm+correction on same target separate ----

confirm = client.post(f"/api/vehicles/{VIN}/feedback",
                      json={"kind": "confirm", "target": target("P0441"),
                           "text": "yes, this matches what I see."})
check("confirm add responds 200", confirm.status_code == 200, str(confirm.status_code))

correction = client.post(f"/api/vehicles/{VIN}/feedback",
                         json={"kind": "correction", "target": target("P0441"),
                              "text": "purge valve was already replaced, not pending."})
check("correction add responds 200", correction.status_code == 200, str(correction.status_code))

key = "dossier|dtcs|P0441"
counts_r = client.get(f"/api/vehicles/{VIN}/feedback/counts?targets={key},dossier|dtcs|P9999")
check("counts responds 200", counts_r.status_code == 200, str(counts_r.status_code))
tallies = counts_r.json()["counts"]
check("requested target present", key in tallies, str(list(tallies)))
check("unrelated target present with zero counts",
     tallies.get("dossier|dtcs|P9999") == {"open": 0, "answered": 0,
                                           "confirms": 0, "corrections": 0},
     str(tallies.get("dossier|dtcs|P9999")))
check("confirm counted once", tallies[key]["confirms"] == 1, str(tallies[key]))
check("correction counted once, separately", tallies[key]["corrections"] == 1, str(tallies[key]))
check("both are open", tallies[key]["open"] == 2, str(tallies[key]))


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(f"  FAIL: {f}")
sys.exit(1 if failures else 0)
