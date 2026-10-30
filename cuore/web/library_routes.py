"""Library page: GET /library?q= -- every manufacturer document, searchable, with where its facts show."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import library
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

WHERE = [
    ("Codes", "test steps for each code", "test_steps, dtc_defs"),
    ("Electrical / Harnesses", "pinouts and connector views", "pinouts"),
    ("Sensors / Systems", "where a part is on the car", "locations"),
    ("Fuses", "fuse and relay maps", "fuse_maps"),
    ("Adjustments", "official procedures", "procedures, routines"),
    ("Configuration", "PROXI byte meanings", "proxi_map"),
    ("Parts", "removal and fitting, torque, tools, fluids, fitment", "part_fitment, torque, fluids"),
    ("TSB / Job / Arrive-ready / Warranty pack", "bulletins tied to the car and the code", "bulletins"),
    ("Facts", "specifications", "specs"),
]


@router.get("/library", response_class=HTMLResponse)
def library_page(request: Request, q: str = "") -> HTMLResponse:
    q = (q or "").strip()[:200]
    docs = library.search(q) if q else library.index()
    return _page(request, "library.html", q=q, docs=docs, summ=library.summary(), where=WHERE,
                 root=str(library.library_root()))
