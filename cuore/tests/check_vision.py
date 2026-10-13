"""Smoke checks for "read this photo" (POST /api/vision/{vin}/read) and its
status endpoint: ``cuore/services/vision_bridge.py`` + ``cuore/api/vision.py``.

CUORE_STATE_DIR is pointed at a fresh tempdir BEFORE anything cuore/mes is
imported, same posture as every other ``check_*.py`` here. The default
("none") provider path, hint validation, and the status endpoint are
checked against the real app (``cuore.app.create_app``, same pattern
``check_screens.py`` uses). The ``claude`` provider path never calls the
real network: ``urllib.request.urlopen`` inside ``vision_bridge`` is
monkeypatched to return a canned Anthropic Messages API body, under a fake
``ANTHROPIC_API_KEY`` set and restored around just those checks.

Run:
    .venv/Scripts/python.exe cuore/tests/check_vision.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-vision-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("CUORE_VISION_PROVIDER", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.config import Settings  # noqa: E402
from cuore.services import vision_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
IMAGE_BYTES = b"\xff\xd8\xff\xe0not-a-real-jpeg-but-bytes-are-all-this-needs"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def upload(client: TestClient, hint: str) -> "object":
    return client.post(f"/api/vision/{VIN}/read",
                       files={"file": ("photo.jpg", IMAGE_BYTES, "image/jpeg")},
                       data={"hint": hint})


def assert_contract_shape(body: dict) -> None:
    check("response has exactly the contract's top-level keys",
         set(body) == {"provider", "available", "fields", "suggested_kind", "note"},
         str(sorted(body)))
    for name, field in body.get("fields", {}).items():
        check(f"field {name!r} has exactly value/confidence/unit",
             set(field) == {"value", "confidence", "unit"}, str(field))


# --- 1. default provider ("none"): available false, exact note, status matches

default_client = TestClient(create_app())

r = upload(default_client, "odometer")
check("default provider read responds 200", r.status_code == 200, str(r.status_code))
body = r.json()
assert_contract_shape(body)
check("default provider is none", body["provider"] == "none", body["provider"])
check("default provider is unavailable", body["available"] is False)
check("default provider fields empty", body["fields"] == {}, str(body["fields"]))
check("default provider suggested_kind is null", body["suggested_kind"] is None)
check("default provider note is the exact fill-in-by-hand sentence",
     body["note"] == "Automatic reading is not set up on this CUORE. Fill in by hand.",
     body["note"])

status_r = default_client.get("/api/vision/status")
check("status responds 200", status_r.status_code == 200, str(status_r.status_code))
status_body = status_r.json()
check("status reflects default provider/availability/model",
     status_body == {"provider": "none", "available": False, "model": None},
     str(status_body))


# --- 2. hint validation -----------------------------------------------------

bad_hint_r = upload(default_client, "banana")
check("an unknown hint is rejected with 400", bad_hint_r.status_code == 400,
     str(bad_hint_r.status_code))

for hint in vision_bridge.HINTS:
    ok_r = upload(default_client, hint)
    check(f"hint {hint!r} is accepted (200)", ok_r.status_code == 200, str(ok_r.status_code))


# --- 3. claude provider, monkeypatched network -----------------------------

claude_client = TestClient(create_app(Settings(vision_provider="claude")))


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _canned_opener(payload_text: str):
    def _opener(req, timeout=None):  # noqa: ANN001 -- matches urlopen's call shape
        raw = json.dumps({"content": [{"type": "text", "text": payload_text}]}).encode("utf-8")
        return _FakeResponse(raw)
    return _opener


_real_urlopen = vision_bridge.urllib.request.urlopen
os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-tests-only"

try:
    # 3a. odometer -- canned reply has odometer_km with a confidence
    vision_bridge.urllib.request.urlopen = _canned_opener(
        json.dumps({"odometer_km": {"value": 184213, "confidence": 0.95}}))
    odo_r = upload(claude_client, "odometer")
    check("claude odometer read responds 200", odo_r.status_code == 200, str(odo_r.status_code))
    odo_body = odo_r.json()
    assert_contract_shape(odo_body)
    check("claude odometer provider is claude", odo_body["provider"] == "claude")
    check("claude odometer is available", odo_body["available"] is True)
    check("claude odometer value parsed",
         odo_body["fields"]["odometer_km"]["value"] == 184213, str(odo_body["fields"]))
    check("claude odometer confidence parsed",
         odo_body["fields"]["odometer_km"]["confidence"] == 0.95, str(odo_body["fields"]))
    check("claude odometer unit is km",
         odo_body["fields"]["odometer_km"]["unit"] == "km", str(odo_body["fields"]))
    check("claude odometer suggested_kind is null (not a kind field)",
         odo_body["suggested_kind"] is None, str(odo_body["suggested_kind"]))

    # 3b. fuel_pump -- canned reply covers all four fields, one deliberately null
    vision_bridge.urllib.request.urlopen = _canned_opener(json.dumps({
        "litres": {"value": 32.14, "confidence": 0.9},
        "price": {"value": 61.50, "confidence": 0.85},
        "octane": {"value": "91", "confidence": 0.7},
        "station": {"value": None, "confidence": 0.0},
    }))
    fuel_r = upload(claude_client, "fuel_pump")
    check("claude fuel_pump read responds 200", fuel_r.status_code == 200, str(fuel_r.status_code))
    fuel_body = fuel_r.json()
    assert_contract_shape(fuel_body)
    check("claude fuel_pump litres parsed",
         fuel_body["fields"]["litres"]["value"] == 32.14, str(fuel_body["fields"]))
    check("claude fuel_pump price parsed",
         fuel_body["fields"]["price"]["value"] == 61.50, str(fuel_body["fields"]))
    check("claude fuel_pump octane parsed as string",
         fuel_body["fields"]["octane"]["value"] == "91", str(fuel_body["fields"]))
    check("claude fuel_pump station stayed null (model said so)",
         fuel_body["fields"]["station"]["value"] is None, str(fuel_body["fields"]))
    check("claude fuel_pump litres unit is L",
         fuel_body["fields"]["litres"]["unit"] == "L", str(fuel_body["fields"]))
    check("claude fuel_pump suggested_kind is fuel/fill_up",
         fuel_body["suggested_kind"] == "fuel/fill_up", str(fuel_body["suggested_kind"]))

    # 3c. invalid JSON from the model -- available stays true, fields empty,
    #     note explains rather than raising
    vision_bridge.urllib.request.urlopen = _canned_opener(
        "sorry, I can't make out the dial clearly enough to give you numbers.")
    bad_json_r = upload(claude_client, "odometer")
    check("claude invalid-JSON read responds 200", bad_json_r.status_code == 200,
         str(bad_json_r.status_code))
    bad_json_body = bad_json_r.json()
    assert_contract_shape(bad_json_body)
    check("claude invalid-JSON stays available (the call itself succeeded)",
         bad_json_body["available"] is True, str(bad_json_body))
    check("claude invalid-JSON fields are empty",
         bad_json_body["fields"] == {}, str(bad_json_body["fields"]))
    check("claude invalid-JSON note explains rather than silently losing data",
         "JSON" in bad_json_body["note"], bad_json_body["note"])

    # 3d. network error -- available false, error class named in note
    def _raising_opener(req, timeout=None):  # noqa: ANN001
        raise ConnectionRefusedError("no route to host (test)")
    vision_bridge.urllib.request.urlopen = _raising_opener
    net_err_r = upload(claude_client, "odometer")
    check("claude network-error read responds 200", net_err_r.status_code == 200,
         str(net_err_r.status_code))
    net_err_body = net_err_r.json()
    assert_contract_shape(net_err_body)
    check("claude network error is unavailable", net_err_body["available"] is False)
    check("claude network error names the exception class in the note",
         "ConnectionRefusedError" in net_err_body["note"], net_err_body["note"])

    # 3e. status with the fake key set reports available, with the model id
    claude_status_r = claude_client.get("/api/vision/status")
    claude_status_body = claude_status_r.json()
    check("claude status is available with a key set",
         claude_status_body == {"provider": "claude", "available": True,
                                "model": "claude-sonnet-5"},
         str(claude_status_body))
finally:
    vision_bridge.urllib.request.urlopen = _real_urlopen
    os.environ.pop("ANTHROPIC_API_KEY", None)


# --- 4. claude provider configured but no API key: unavailable, not a crash

no_key_client = TestClient(create_app(Settings(vision_provider="claude")))
no_key_r = upload(no_key_client, "odometer")
check("claude with no key responds 200", no_key_r.status_code == 200, str(no_key_r.status_code))
no_key_body = no_key_r.json()
check("claude with no key is unavailable", no_key_body["available"] is False)
check("claude with no key mentions the missing key",
     "ANTHROPIC_API_KEY" in no_key_body["note"], no_key_body["note"])

no_key_status = no_key_client.get("/api/vision/status").json()
check("claude status with no key is unavailable but still names the model",
     no_key_status == {"provider": "claude", "available": False, "model": "claude-sonnet-5"},
     str(no_key_status))


# --- 5. tesseract: documented stub, always unavailable ----------------------

tess_client = TestClient(create_app(Settings(vision_provider="tesseract")))
tess_r = upload(tess_client, "part_label")
check("tesseract read responds 200", tess_r.status_code == 200, str(tess_r.status_code))
tess_body = tess_r.json()
check("tesseract is unavailable", tess_body["available"] is False)
check("tesseract note says not installed",
     tess_body["note"] == "Tesseract not installed", tess_body["note"])

tess_status = tess_client.get("/api/vision/status").json()
check("tesseract status is unavailable with no model",
     tess_status == {"provider": "tesseract", "available": False, "model": None},
     str(tess_status))


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(f"  FAIL: {f}")
sys.exit(1 if failures else 0)
