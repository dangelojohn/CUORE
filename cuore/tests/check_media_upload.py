"""Checks for the mobile-upload robustness added to the mechanic evidence
media library: magic-byte content sniffing, the 25 MB HTTP-layer cap,
honest HEIC-without-a-decoder handling, EXIF orientation respected in the
thumbnail, and the enriched response shape (``url``/``thumb_url``/
``width``/``height``/``taken_at``/``has_gps``/``bytes``).

Same posture as ``check_media.py``: plain script, ``check()``, exit 1 on
failure, no pytest, no mocks -- except the state dir, which is a temp
directory so this never touches the real corpus.

Run:
    .venv/Scripts/python.exe cuore/tests/check_media_upload.py
"""

from __future__ import annotations

import io
import os
import struct
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-media-upload-")
os.environ["CUORE_STATE_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.api import media as media_api  # noqa: E402
from cuore.app import create_app  # noqa: E402

VIN = "TESTVIN0000000002"

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


def make_png() -> bytes:
    try:
        from PIL import Image
    except ImportError:
        # The raw 1x1 PNG signature + IHDR+IDAT+IEND, hand-built, so this
        # test doesn't hard-depend on Pillow for the PNG fixture itself.
        return (b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde"
                b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
                b"\x00\x00\x00\x00IEND\xaeB`\x82")
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def make_fake_heic() -> bytes:
    """A synthetic ``ftyp``/``heic`` box -- enough to sniff as HEIC, not
    enough to actually decode (simulates "no HEIF plugin on this install",
    which is this venv's real state: Pillow is present, pillow-heif is not)."""
    box = struct.pack(">I", 24) + b"ftyp" + b"heic" + b"\x00" * 16
    return box + b"not a real heic payload, just padding past the ftyp box"


PNG_BYTES = make_png()


# --- 1: PNG upload returns the enriched shape -------------------------------

resp = client.post(
    f"/api/vehicles/{VIN}/media",
    files=[("file", ("photo.png", PNG_BYTES, "image/png"))],
)
check("png upload responds 200", resp.status_code == 200, resp.text)
row = resp.json()["media"][0] if resp.status_code == 200 else {}
for field in ("id", "url", "thumb_url", "width", "height", "taken_at", "has_gps", "bytes"):
    check(f"png response has {field!r}", field in row, str(row))
check("png kind is photo", row.get("kind") == "photo", str(row.get("kind")))
check("png bytes matches payload size", row.get("bytes") == len(PNG_BYTES), str(row.get("bytes")))
check("png has_gps is False (no EXIF GPS)", row.get("has_gps") is False, str(row.get("has_gps")))
check("png url points at the file route", row.get("url") == f"/api/media/{row.get('id')}/file",
      str(row.get("url")))
check("png thumb_url points at the thumb route",
      row.get("thumb_url") == f"/api/media/{row.get('id')}/thumb", str(row.get("thumb_url")))

thumb_resp = client.get(row.get("thumb_url", ""))
check("png thumb_url resolves", thumb_resp.status_code == 200, thumb_resp.text)


# --- 2: oversized body gives 413 --------------------------------------------

oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (25 * 1024 * 1024 + 1)
big_resp = client.post(
    f"/api/vehicles/{VIN}/media",
    files=[("file", ("huge.png", oversized, "image/png"))],
)
check("oversized upload responds 413", big_resp.status_code == 413, big_resp.text)


# --- 3: wrong content-type header, real PNG bytes -> accepted (sniffed) ----

wrong_ct_resp = client.post(
    f"/api/vehicles/{VIN}/media",
    files=[("file", ("photo2.png", PNG_BYTES, "application/octet-stream"))],
)
check("wrong content-type but real PNG bytes responds 200",
      wrong_ct_resp.status_code == 200, wrong_ct_resp.text)
wrong_ct_row = wrong_ct_resp.json()["media"][0] if wrong_ct_resp.status_code == 200 else {}
check("sniffed mime overrides the client header",
      wrong_ct_row.get("mime") == "image/png", str(wrong_ct_row.get("mime")))
check("sniffed upload kind is photo", wrong_ct_row.get("kind") == "photo",
      str(wrong_ct_row.get("kind")))


# --- 4: HEIC magic bytes, no decoder -> stored, no 500, thumb_url null ------

heic_resp = client.post(
    f"/api/vehicles/{VIN}/media",
    files=[("file", ("IMG_0001.HEIC", make_fake_heic(), "application/octet-stream"))],
)
check("heic-without-decoder upload does not 500",
      heic_resp.status_code != 500, heic_resp.text)
check("heic-without-decoder upload responds 200", heic_resp.status_code == 200, heic_resp.text)
heic_row = heic_resp.json()["media"][0] if heic_resp.status_code == 200 else {}
check("heic sniffed as image/heic", heic_row.get("mime") == "image/heic", str(heic_row.get("mime")))
check("heic stored as kind photo", heic_row.get("kind") == "photo", str(heic_row.get("kind")))
check("heic thumb_url is honestly null (no decoder)", heic_row.get("thumb_url") is None,
      str(heic_row.get("thumb_url")))
check("heic width/height unknown rather than guessed",
      heic_row.get("width") is None and heic_row.get("height") is None,
      f"width={heic_row.get('width')!r} height={heic_row.get('height')!r}")


# --- 5: EXIF orientation 6 is respected in the thumbnail --------------------

try:
    from PIL import Image

    def make_rotated_jpeg() -> bytes:
        # Landscape source (wide); orientation 6 means the upright image is
        # actually portrait -- ImageOps.exif_transpose must swap w/h.
        img = Image.new("RGB", (80, 40), (200, 50, 50))
        exif = img.getexif()
        exif[0x0112] = 6  # Orientation
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif)
        return buf.getvalue()

    rot_resp = client.post(
        f"/api/vehicles/{VIN}/media",
        files=[("file", ("rotated.jpg", make_rotated_jpeg(), "image/jpeg"))],
    )
    check("rotated upload responds 200", rot_resp.status_code == 200, rot_resp.text)
    rot_row = rot_resp.json()["media"][0] if rot_resp.status_code == 200 else {}
    thumb_url = rot_row.get("thumb_url") or ""
    check("rotated upload has a thumbnail", bool(thumb_url), str(rot_row))
    if thumb_url:
        thumb_bytes = client.get(thumb_url).content
        with Image.open(io.BytesIO(thumb_bytes)) as thumb_img:
            tw, th = thumb_img.size
        check("exif orientation 6 rotates the thumbnail (portrait, not landscape)",
              th > tw, f"thumb size {tw}x{th}")
except ImportError:
    print("[note] Pillow not importable in this interpreter -- skipping the "
          "EXIF-orientation thumbnail check.")


print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    for f in failures:
        print(f"FAIL: {f}")
    sys.exit(1)
