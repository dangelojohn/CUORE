"""Checks for the mechanic evidence media library.

Same posture as ``check_actuate.py``: plain script, ``check()``, exit 1 on
failure, no pytest, no mocks -- except the state dir, which is a temp
directory so this never touches the real corpus.

``cuore.app.create_app`` does not include the media router yet (that wiring
belongs to app.py, which this change does not touch), so this test includes
it itself when it is missing.

Run:
    .venv/Scripts/python.exe cuore/tests/check_media.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-media-")
os.environ["CUORE_STATE_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from cuore.api import media as media_api  # noqa: E402
from cuore.app import create_app  # noqa: E402
from cuore.live import media as media_store  # noqa: E402

VIN = "TESTVIN0000000001"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


app = create_app()
if not any(getattr(r, "path", "") == "/api/vehicles/{vin}/media" for r in app.routes):
    app.include_router(media_api.router, prefix="/api")
client = TestClient(app)


def make_jpeg(exif_dt: str = "2024:05:17 10:30:00") -> bytes:
    img = Image.new("RGB", (64, 64), (120, 200, 50))
    exif = img.getexif()
    if exif_dt:
        exif[36867] = exif_dt
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


# --- upload with EXIF date, thumbnail, dedupe -----------------------------

jpeg_bytes = make_jpeg()
resp = client.post(
    f"/api/vehicles/{VIN}/media",
    files=[("file", ("evap_valve.jpg", jpeg_bytes, "image/jpeg"))],
    data={"caption": "EVAP purge valve, visible crack", "tags": "evap,leak",
          "target_kind": "code", "target_id": "P0456", "author": "tech"},
)
check("upload responds 200", resp.status_code == 200, resp.text)
body = resp.json()
row = body["media"][0] if resp.status_code == 200 else {}
check("captured_at from EXIF", row.get("captured_at") == "2024-05-17T10:30:00",
      str(row.get("captured_at")))
check("kind is photo", row.get("kind") == "photo", str(row.get("kind")))
media_id = row.get("id", "")

thumb_resp = client.get(f"/api/media/{media_id}/thumb")
check("thumbnail exists", thumb_resp.status_code == 200, thumb_resp.text)
check("thumbnail is a jpeg", thumb_resp.headers.get("content-type", "").startswith("image/"),
      thumb_resp.headers.get("content-type", ""))

dup_resp = client.post(
    f"/api/vehicles/{VIN}/media",
    files=[("file", ("evap_valve_again.jpg", jpeg_bytes, "image/jpeg"))],
    data={"target_kind": "vehicle"},
)
check("duplicate upload responds 200", dup_resp.status_code == 200, dup_resp.text)
dup_row = dup_resp.json()["media"][0] if dup_resp.status_code == 200 else {}
check("duplicate upload returns the same id", dup_row.get("id") == media_id,
      f"got {dup_row.get('id')!r} want {media_id!r}")


# --- bad mime rejected -------------------------------------------------------

bad_resp = client.post(
    f"/api/vehicles/{VIN}/media",
    files=[("file", ("notes.txt", b"not a real media file", "text/plain"))],
)
check("bad mime responds 400", bad_resp.status_code == 400, bad_resp.text)


# --- search by tag, by target; hidden excluded ------------------------------

by_tag = client.get(f"/api/vehicles/{VIN}/media", params={"tag": "leak"})
check("search by tag responds 200", by_tag.status_code == 200, by_tag.text)
check("search by tag finds it",
      media_id in {m["id"] for m in by_tag.json().get("media", [])})

by_target = client.get(f"/api/vehicles/{VIN}/media",
                       params={"target_kind": "code", "target_id": "P0456"})
check("search by target finds it",
      media_id in {m["id"] for m in by_target.json().get("media", [])})

hide_resp = client.post(f"/api/media/{media_id}/hide")
check("hide responds 200", hide_resp.status_code == 200, hide_resp.text)

after_hide = client.get(f"/api/vehicles/{VIN}/media")
check("hidden item excluded from search",
      media_id not in {m["id"] for m in after_hide.json().get("media", [])})


# --- export zip: recovery -----------------------------------------------

# A fresh, non-hidden item so the export has something to carry.
export_src = make_jpeg("2024-06-01 09:00:00")
client.post(f"/api/vehicles/{VIN}/media",
           files=[("file", ("export_me.jpg", export_src, "image/jpeg"))])

export_resp = client.get(f"/api/vehicles/{VIN}/media/export.zip")
check("export responds 200", export_resp.status_code == 200, export_resp.text)
try:
    zf = zipfile.ZipFile(io.BytesIO(export_resp.content))
    names = zf.namelist()
    index = json.loads(zf.read("index.json"))
except Exception as e:
    names, index = [], []
    check("export zip parses", False, str(e))
check("export zip contains index.json", "index.json" in names, str(names))
check("export index excludes the hidden item",
      media_id not in {r.get("id") for r in index})
check("export zip contains a file under files/",
      any(n.startswith("files/") for n in names), str(names))


print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    for f in failures:
        print(f"FAIL: {f}")
    sys.exit(1)
