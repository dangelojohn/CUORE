"""Smoke checks for the printable/PDF reports.

Same posture as ``check_api.py``: no mocks, the real MES corpus on this
machine is the fixture. Needs ``cuore.web.report_routes.router`` included
by ``cuore/app.py`` -- see that module's docstring for the include line.

Run:
    .venv/Scripts/python.exe cuore/tests/check_report.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- 17 logs, all real, chronic P0456

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


# --- HTML report ------------------------------------------------------------

resp = client.get(f"/v/{VIN}/report")
check("report page renders", resp.status_code == 200, str(resp.status_code))
if resp.status_code == 200:
    body = resp.text
    check("report page is HTML", "<html" in body.lower())
    check("as-of stamp present", "As of" in body and "data through" in body)
    check("verdict section present", 'id="verdict"' in body)
    check("print.css linked in base", "/static/print.css" in body)
    check("Report tab present", ">Report<" in body)


# --- vehicle PDF --------------------------------------------------------------

try:
    import pypdfium2 as pdfium
    HAVE_PDFIUM = True
except ImportError:
    HAVE_PDFIUM = False
    print("pypdfium2 not installed -- skipping PDF content checks", file=sys.stderr)


def _pdf_text(raw: bytes) -> str:
    doc = pdfium.PdfDocument(io.BytesIO(raw))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


pdf_resp = client.get(f"/v/{VIN}/report.pdf")
check("vehicle report.pdf responds 200", pdf_resp.status_code == 200, str(pdf_resp.status_code))
if pdf_resp.status_code == 200:
    check("vehicle report.pdf is a PDF", pdf_resp.content[:4] == b"%PDF")
    if HAVE_PDFIUM:
        doc = pdfium.PdfDocument(io.BytesIO(pdf_resp.content))
        check("vehicle report.pdf has >= 2 pages", len(doc) >= 2, str(len(doc)))
        text = _pdf_text(pdf_resp.content)
        check("vehicle report.pdf contains the VIN", VIN in text)

a4_resp = client.get(f"/v/{VIN}/report.pdf?size=a4")
check("vehicle report.pdf accepts ?size=a4", a4_resp.status_code == 200,
     str(a4_resp.status_code))


# --- single-code PDF -----------------------------------------------------------

code_resp = client.get(f"/v/{VIN}/code/P0455/report.pdf")
check("code report.pdf 200 for P0455", code_resp.status_code == 200,
     str(code_resp.status_code))
if code_resp.status_code == 200:
    check("code report.pdf is a PDF", code_resp.content[:4] == b"%PDF")
    if HAVE_PDFIUM:
        text = _pdf_text(code_resp.content)
        check("code report.pdf mentions P0455", "P0455" in text)

missing_resp = client.get(f"/v/{VIN}/code/P9999/report.pdf")
check("code report.pdf 404 for an unknown code", missing_resp.status_code == 404,
     str(missing_resp.status_code))


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
