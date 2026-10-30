"""Check the knowledge library: register, index, facts, search, cited_on, source_line, /library page.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_library.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-library-")
os.environ["CUORE_STATE_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.library import main as cli_main  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import library, provenance  # noqa: E402
from cuore.web import library_routes  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
TOKEN = "machine-token-123"
failures: list[str] = []
checks = 0
TMP = Path(_TMP).resolve()


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def snapshot() -> set[str]:
    return {str(p) for p in TMP.rglob("*")}


Path(_TMP, "web_token.txt").write_text(TOKEN, encoding="utf-8")
app = create_app()
app.include_router(library_routes.router)  # until app.py registers it
client = TestClient(app, follow_redirects=False, raise_server_exceptions=False,
                    headers={"X-Cuore-Token": TOKEN})

# --- 1. empty ----------------------------------------------------------------------------------
check("empty index", library.index() == [])
check("empty search", library.search("P0171") == [])
check("empty facts", library.facts("949", "specs") == [])
check("empty cited_on", library.cited_on("nope") == [])
check("empty summary", library.summary()["documents"] == 0)
check("no folders made by reading", not (TMP / "library").exists() and not (TMP / "knowledge").exists())
r = client.get("/library")
check("empty page 200", r.status_code == 200, str(r.status_code))
check("empty message", "No manufacturer documents yet" in r.text and "TechAuthority" in r.text)
check("where table", "Where things show" in r.text and "Fuses" in r.text)

# --- 2. register two fake docs -----------------------------------------------------------------
d1 = TMP / "library" / "techauthority" / "2026-11-02"
d2 = TMP / "library" / "stellantisiop" / "2026-11-05"
d1.mkdir(parents=True)
d2.mkdir(parents=True)
f1 = d1 / "evap-test.pdf"
f2 = d2 / "fuse-box.pdf"
f1.write_bytes(b"fake evap pdf")
f2.write_bytes(b"fake fuse pdf")
import hashlib  # noqa: E402

rec1 = library.register(f1, "TechAuthority", "EVAP leak test", "18-030-17", "https://ta.example/1", "internal use")
rec2 = library.register(f2, "stellantisiop", "Fuse box layout", "FB-949", "https://iop.example/2", "internal use")
check("sha256 recorded", rec1["sha256"] == hashlib.sha256(b"fake evap pdf").hexdigest())
check("sidecar on disk", json.loads((d1 / "evap-test.pdf.source.json").read_text())["doc_no"] == "18-030-17")
check("original untouched", f1.read_bytes() == b"fake evap pdf")
check("retrieved from folder date", rec1["retrieved"] == "2026-11-02" and rec2["retrieved"] == "2026-11-05")
try:
    outside = TMP / "stray.pdf"
    outside.write_bytes(b"x")
    library.register(outside, "x", "x")
    check("outside file refused", False)
except ValueError:
    check("outside file refused", True)
check("no sidecar for refused", not (TMP / "stray.pdf.source.json").exists())

# --- 3. facts ------------------------------------------------------------------------------------
kdir = TMP / "knowledge" / "949"
kdir.mkdir(parents=True)
(kdir / "test_steps.json").write_text(json.dumps([
    {"dtc": "P0456", "step": 1, "text": "Smoke test the purge line", "source_doc_id": "18-030-17",
     "section": "3.1", "page": 4, "retrieved": "2026-11-02", "extracted_by": "owner", "confidence": "verbatim"}]))
(kdir / "fuse_maps.json").write_text(json.dumps({"facts": [
    {"fuse": "F12", "amps": 15, "circuit": "ECM", "source_doc_id": rec2["doc_id"], "section": "2",
     "retrieved": "2026-11-05", "extracted_by": "owner", "confidence": "verbatim"},
    {"fuse": "F13", "amps": 10, "source_doc_id": "FB-949", "retrieved": "2026-11-05"}]}))
(kdir / "specs.json").write_text(json.dumps([{"name": "orphan", "source_doc_id": "unknown-doc"}]))

idx = library.index()
check("two documents", len(idx) == 2)
by = {d["doc_no"]: d for d in idx}
check("fact counts", by["18-030-17"]["n_facts"] == 1 and by["FB-949"]["n_facts"] == 2)
check("newest first", idx[0]["doc_no"] == "FB-949")
check("facts loaded", len(library.facts("949", "fuse_maps")) == 2 and library.facts("949", "test_steps")[0]["dtc"] == "P0456")
check("facts hide internals", all(not k.startswith("_") for k in library.facts("949", "fuse_maps")[0]))
check("facts other platform empty", library.facts("952", "fuse_maps") == [])
check("search by doc no", [d["doc_no"] for d in library.search("18-030-17")] == ["18-030-17"])
check("search by DTC", [d["doc_no"] for d in library.search("p0456")] == ["18-030-17"])
check("search by part/circuit", [d["doc_no"] for d in library.search("ecm")] == ["FB-949"])
check("search by title", len(library.search("fuse box")) == 1)
check("search miss", library.search("zzz") == [])
check("cited_on test_steps -> Codes", [p[0] for p in library.cited_on(rec1["doc_id"])] == ["Codes"])
check("cited_on by doc no -> Fuses", [p[0] for p in library.cited_on("FB-949")] == ["Fuses"])
check("orphan fact cites nothing", library.cited_on("unknown-doc") == [])
s = library.summary()
check("summary", s == {"documents": 2, "sources": 2, "facts_in_use": 3, "last_added": "2026-11-05"}, str(s))

# --- 4. source_line -----------------------------------------------------------------------------
fact = library.facts("949", "test_steps")[0]
check("source_line format", library.source_line(fact) ==
      "Source: techauthority, EVAP leak test 18-030-17 \u00a73.1, retrieved 2026-11-02", library.source_line(fact))
check("provenance alias", provenance.source_line(fact) == library.source_line(fact))
check("source_line sparse", library.source_line({"source_doc_id": "zz"}).startswith("Source: unknown source, zz"))

# --- 5. page, CLI --------------------------------------------------------------------------------
r = client.get("/library")
check("page counts", "2 documents from 2 sources; 3 facts in use on CUORE pages; last added 2026-11-05" in r.text)
check("page lists docs", "EVAP leak test" in r.text and "Fuse box layout" in r.text and 'href="/vehicles"' in r.text)
r = client.get("/library?q=P0456")
check("page search", "EVAP leak test" in r.text and "Fuse box layout" not in r.text)
check("page search miss", "Nothing in the library matches" in client.get("/library?q=nothing").text)
check("page has no script", "<script" not in client.get("/library").text.split("</style>", 1)[1].split("Where things show")[0])
check("CLI index", cli_main(["index"]) == 0)
f3 = d1 / "third.pdf"
f3.write_bytes(b"three")
check("CLI register", cli_main(["register", str(f3), "--source", "techauthority", "--title", "Third", "--doc-no", "T-3"]) == 0
      and (d1 / "third.pdf.source.json").is_file())
check("CLI refuses outside", cli_main(["register", str(TMP / "stray.pdf"), "--source", "x", "--title", "x"]) == 2)

# --- 6. containment ------------------------------------------------------------------------------
real = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"), "cuore", "library")
check("real state dir not used", str(library.library_root()).startswith(str(TMP)))
check("library root is under temp", library.library_root().resolve() == TMP / "library")
repo = Path(__file__).resolve().parents[2]
check("nothing in repo", not (repo / "library").exists() and not (repo / "knowledge").exists()
      and not (repo / "cuore" / "library").exists())

print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
