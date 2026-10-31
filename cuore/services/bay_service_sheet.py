"""Bay Service Sheet: the card under the wiper blade, and the read-only page its QR opens.

Pure view-model from CUORE's own stores, rebuilt on every call (no cache), so a reprint is never stale.
Nothing is invented: a missing value is "" and prints as a blank line to write on. No customer name,
phone or address is read here, and the QR holds only a URL (no token, no secret). No adapter, no network.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime
from typing import Any, Optional

MAX_WORK = 4
MAX_TEXT = 90
# Notes and working thoughts stay off a card that sits on a windshield.
ACTION_WORDS = {"test": "Test", "inspection": "Inspection", "repair": "Repair", "part": "Part", "clear": "Codes cleared"}
OUTCOME_WORDS = {"not_fixed": "Not fixed", "deferred": "Deferred"}


def _s(x: Any) -> str:
    return str(x or "").strip()


def lan_ip() -> str:
    """This machine's LAN address, or "" when none is usable. Sends no packet (UDP connect only)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    return "" if (a.is_loopback or a.is_link_local or a.is_unspecified) else ip


def card_url(vin: str, settings: Any) -> dict[str, str]:
    """{url, problem}: the phone page URL, or why there is none. Never 127.0.0.1 / localhost."""
    base = _s(getattr(settings, "public_base_url", "")).rstrip("/")
    if base:  # the one place the QR's address is set; the path below never changes
        if not base.lower().startswith("http") or any(x in base.lower() for x in ("127.0.0.1", "localhost", "[::1]")):
            return {"url": "", "problem": "The public base address is not usable from a phone (it must be http(s) and "
                                          "not this PC's loopback). Fix CUORE_PUBLIC_BASE_URL and print again."}
        return {"url": f"{base}/v/{vin}/bay-card", "problem": ""}
    if not getattr(settings, "lan_exposed", False):
        return {"url": "", "problem": "CUORE is set to answer on this PC only, so a phone cannot open a code. "
                                      "Start it on the shop network (host 0.0.0.0) and print again."}
    ip = lan_ip()
    if not ip:
        return {"url": "", "problem": "No shop-network address was found on this PC, so no code is printed. "
                                      "Connect to the shop network and print again."}
    return {"url": f"http://{ip}:{settings.port}/v/{vin}/bay-card", "problem": ""}


def _job(vin: str) -> Optional[dict[str, Any]]:
    try:
        from mes import jobs
        j = jobs.current(vin)
        if j is None:
            allj = jobs.load(vin)
            j = allj[-1] if allj else None
        return j
    except Exception:  # noqa: BLE001
        return None


def status_word(job: Optional[dict], verdict: Optional[dict]) -> str:
    """One word, from the job store's own statuses. "Fixed" only when closed as fixed AND the proof says clean."""
    if not job:
        return ""
    st, out = _s(job.get("status")), _s(job.get("outcome"))
    if st == "closed":
        if out == "fixed":
            return "Fixed" if _s((verdict or {}).get("state")) == "VERIFIED_CLEAN" else "Verifying"
        return OUTCOME_WORDS.get(out, "Closed")
    return {"open": "Open", "verifying": "Verifying"}.get(st, st.capitalize())


def _clip(t: str) -> str:
    t = " ".join(re.sub(r"\s*\([^)]*(?:Log_|/|\|\.txt|\.csv)[^)]*\)", "", _s(t)).split())  # no file names
    return t if len(t) <= MAX_TEXT else t[:MAX_TEXT - 1].rstrip() + "..."


def latest_work(vin: str, limit: int = MAX_WORK) -> list[dict[str, str]]:
    """Newest job actions and recorded services for this car, newest first: [{at, date, kind, text}]."""
    rows: list[dict[str, str]] = []
    try:
        from mes import jobs
        for j in jobs.load(vin):
            for a in j.get("actions") or []:
                if _s(a.get("kind")) in ACTION_WORDS:
                    rows.append({"at": _s(a.get("at")), "kind": ACTION_WORDS[_s(a.get("kind"))], "text": _clip(a.get("text"))})
    except Exception:  # noqa: BLE001
        pass
    try:
        from mes import service
        from . import service_bridge
        for r in service.load(vin):
            d = r.get("data") or {}
            items = []
            for it in d.get("items") or []:
                try:
                    lab = service_bridge.maintenance_label(it.get("item_key"))
                except Exception:  # noqa: BLE001
                    lab = _s(it.get("item_key"))
                items.append(f"{lab} {_s(it.get('action'))}".strip())
            text = "; ".join(items) or _s(r.get("kind")).replace("_", " ")
            rows.append({"at": _s(r.get("at")) or _s(d.get("date")), "kind": "Service", "text": _clip(text)})
    except Exception:  # noqa: BLE001
        pass
    rows.sort(key=lambda r: r["at"], reverse=True)
    out = rows[:limit]
    for r in out:
        r["date"] = r["at"][:10]
    return out


def build(vin: str, *, bar: Optional[dict] = None, verdict: Optional[dict] = None, marque_name: str = "",
          now: Optional[datetime] = None) -> dict[str, Any]:
    vin = _s(vin).upper()
    bar = bar or {}
    job = _job(vin)
    name = _s(bar.get("name"))
    if name == "(unnamed vehicle)":
        name = ""
    odo = bar.get("odo_last")
    now = now or datetime.now()
    return {
        "vin": vin, "vin8": vin[-8:], "name": name, "marque": marque_name,
        "odo": odo if isinstance(odo, (int, float)) else None,
        "reason": _s((job or {}).get("complaint")),
        "date_in": _s((job or {}).get("opened_at"))[:10],
        "tech": _s((job or {}).get("technician")),
        "status": status_word(job, verdict),
        "work": latest_work(vin),
        "updated": now.strftime("%Y-%m-%d %H:%M"),
    }


def qr_svg(url: str) -> str:
    """The URL as an inline SVG QR code, error correction H, quiet zone 4 modules, black on white."""
    from reportlab.graphics.barcode import qrencoder
    q = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.H)
    q.addData(url)
    q.make()
    n, quiet = q.getModuleCount(), 4
    path = "".join(f"M{c + quiet} {r + quiet}h1v1h-1z" for r in range(n) for c in range(n) if q.isDark(r, c))
    size = n + 2 * quiet
    return (f'<svg class="qr" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" '
            f'aria-label="QR code for this car\'s details" shape-rendering="crispEdges">'
            f'<rect width="{size}" height="{size}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
