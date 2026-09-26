"""Sample Avery label sheets for the Stelvio (for the user to verify layout)."""
import io, os, tempfile
os.environ.setdefault("CUORE_STATE_DIR", tempfile.mkdtemp())  # never touch real state
from cuore import bootstrap  # noqa
from cuore.services import labels_bridge as L
from pypdf import PdfReader, PdfWriter

VIN = "ZASFAKPN5J7B88115"
OUT = r"C:\Users\User\Desktop\Stelvio Sample Service Labels.pdf"
base = {"shop_name": "SAMPLE Stelvio", "date": "2026-09-15", "odometer_km": 142290,
        "oil_viscosity": "0W-30", "oil_spec": "MS-13340", "quantity_l": "5.2",
        "filter_part_no": "4892339", "technician": "JD",
        "next_due_km": 142290 + 12875, "next_due_date": "2027-09-15"}
pages = [
    L.render_pdf(vin=VIN, kind="oil_change", template_id="avery_5520", overrides=base, copies=30),
    L.render_pdf(vin=VIN, kind="reminder", template_id="avery_5520",
                 overrides={**base, "job": "Oil change"}, copies=30),
    L.render_pdf(vin=VIN, kind="torque_tag", template_id="avery_5520",
                 overrides={"torque_key": "drain_plug", "date": "2026-09-15", "technician": "JD"}, copies=30),
    L.render_pdf(vin=VIN, kind="oil_change", template_id="avery_6576", overrides=base, copies=32),
    L.render_test_grid("avery_5520"),
    L.render_test_grid("avery_6576"),
]
w = PdfWriter()
for b in pages:
    for p in PdfReader(io.BytesIO(b)).pages:
        w.add_page(p)
with open(OUT, "wb") as f:
    w.write(f)
print(OUT, len(w.pages))
