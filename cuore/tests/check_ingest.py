"""Crawl-ingest endpoint: token + origin gate, PNA preflight, atomic save, listing.

In-process TestClient; temp state dir; no network, no COM3.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="cuore-check-ingest-"))
os.environ["CUORE_STATE_DIR"] = str(STATE)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

ORIGIN = "https://www.autodoc.co.uk"
TOKEN = "t0k3n-for-test"


def main() -> None:
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    (STATE / "ingest_token.txt").write_text(TOKEN + "\n", encoding="utf-8")
    (STATE / "ingest_origins.json").write_text(json.dumps([ORIGIN]), encoding="utf-8")
    c = TestClient(create_app())
    good = {"Origin": ORIGIN, "X-Cuore-Ingest": TOKEN, "Content-Type": "application/json"}
    url = "/api/ingest/autodoc/p1|x.2"

    r = c.options(url, headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                                "Access-Control-Request-Private-Network": "true",
                                "Access-Control-Request-Headers": "content-type,x-cuore-ingest"})
    h = r.headers
    assert r.status_code == 204, r.status_code
    assert h["access-control-allow-origin"] == ORIGIN
    assert "POST" in h["access-control-allow-methods"]
    assert "X-Cuore-Ingest" in h["access-control-allow-headers"]
    assert h["access-control-allow-private-network"] == "true"
    assert c.options(url, headers={"Origin": "https://evil.example"}).status_code == 403

    r = c.post(url, content=json.dumps({"a": 1}), headers=good)
    assert r.status_code == 200, r.text
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["access-control-allow-private-network"] == "true"
    f = STATE / "parts_catalog" / "sources" / "ingest" / "autodoc" / "p1~x.2.json"
    assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1}
    assert c.post(url, content=json.dumps({"a": 2}), headers=good).status_code == 200  # idempotent
    assert json.loads(f.read_text(encoding="utf-8")) == {"a": 2}
    assert not list(f.parent.glob(".ing-*"))

    body = "{}"
    assert c.post(url, content=body, headers={**good, "Origin": "https://evil.example"}).status_code == 403
    assert c.post(url, content=body, headers={**good, "X-Cuore-Ingest": "nope"}).status_code == 403
    nt = {k: v for k, v in good.items() if k != "X-Cuore-Ingest"}
    assert c.post(url, content=body, headers=nt).status_code == 403
    no_origin = {k: v for k, v in good.items() if k != "Origin"}
    assert c.post(url, content=body, headers=no_origin).status_code == 403

    for bad in ("a.", "a%20b", "CON", "x" * 121, ".hid"):
        assert c.post(f"/api/ingest/autodoc/{bad}", content=body, headers=good).status_code == 400, bad
    assert c.post("/api/ingest/bad%20src/k", content=body, headers=good).status_code == 400
    assert c.post(url, content="not json", headers=good).status_code == 400

    big = '{"x":"' + "a" * (2 * 1024 * 1024) + '"}'
    assert c.post(url, content=big, headers=good).status_code == 413

    r = c.get("/api/ingest/autodoc/keys", headers=good)
    assert r.status_code == 200 and r.json()["keys"] == ["p1|x.2"], r.text
    assert c.get("/api/ingest/autodoc/keys", headers={"Origin": ORIGIN}).status_code == 403
    assert c.get("/api/ingest/autodoc/keys").status_code == 403
    print("check_ingest: OK")


if __name__ == "__main__":
    main()
