"""``GET /v/{vin}/fuses``: a find-the-fuse page for a busy workshop.

Order: search, heading, the call (every fuse / ground name links to its row), search results, "Go to" chips,
"For this job" cards (ranked, merged), "Which box?" picker + status chips + ONE car picture (Side / Top), one section per
box (where -> slot drawing -> fuse rows -> photos), grounds, then collapsed panels.

Data: :mod:`cuore.services.fuse_health` (lazy import). Reading the page never
contacts the car. Checks, added rows, added boxes and photos are plain POSTs
that redirect back with ``?msg=``. Photos live under the state dir
(``fuse_photos/<VIN>/<box id>/``), never in git.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from ..api.deps import require_token
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

STATUSES = ("green", "orange", "red", "grey")
STATUS_LABEL = {"green": "OK", "orange": "Suspect", "red": "Blown", "grey": "Not checked yet"}
STATUS_MARK = {"green": "✓", "orange": "!", "red": "✕", "grey": "?"}
CONF_WORDS = {"SOURCED": "from a source", "INFERRED": "worked out, not checked", "GENERAL": "general knowledge",
              "UNKNOWN": "not known"}
PHOTO_KINDS = ("Box open", "Cover label", "Location in the car", "Other")


def _svc():
    from ..services import fuse_health  # lazy
    return fuse_health


def _safe_redirect(url: str) -> bool:
    """Same-site relative path only (no //host, no backslash tricks, no CR/LF)."""
    return url.startswith("/") and not url.startswith("//") and not any(c in url for c in (chr(92), chr(13), chr(10)))


def _back(vin: str, msg: str, to: str = "") -> RedirectResponse:
    base = to if to and _safe_redirect(to) else f"/v/{vin}/fuses"
    path, _, frag = base.partition("#")
    sep = "&" if "?" in path else "?"
    return RedirectResponse(url=f"{path}{sep}msg={quote(msg)}" + (f"#{frag}" if frag else ""), status_code=303)


def _anchor(item_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(item_id))


def plain(text: Any) -> str:
    """Workshop words for jargon in data strings (PDC / PDM)."""
    t = str(text or "")
    t = re.sub(r"\s*\((?:rear )?PDC(?: / PDM)?\)", "", t)
    t = re.sub(r"\bPDC\b", "power distribution box", t)
    return re.sub(r"\bPDM\b", "power distribution module", t)


def ps(text: Any) -> str:
    """Plain words for a source string: no URLs, repo paths, file names or raw HTTP phrases in visible text."""
    t = plain(text)
    t = re.sub(r"https?://([^\s/)]+)[^\s)]*", r"\1", t)
    t = re.sub(r"\b((?:[a-z0-9-]+\.)+(?:com|info|net|org|ca))/[^\s),;']*", r"\1", t)
    t = re.sub(r"\bpage itself returned 403\b", "the page itself could not be opened", t)
    t = re.sub(r"\bpage returned 403\b", "the page could not be opened", t)
    t = re.sub(r"\b(?:cuore\s+)?(?:[A-Za-z]:)?[\w./\\-]*[\w-]+\.(?:md|json|jsonl|py|html|csv)\b", "CUORE's own notes", t)
    t = re.sub(r"\b(?:docs|mes-log-mcp|cuore)/[\w./-]+", "CUORE's own notes", t)
    t = re.sub(r"(CUORE's own notes)(\s+(?:section|element)\s+[\w-]+)?(\s+CUORE's own notes)+", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


RESULT_CAP = 10   # rows per search-result group before the 'Show all N' link


def photo_key(kind: str, type_text: str) -> str:
    """The component_image_keys.json key for a fuse / relay type as printed on the row; "" when not mapped."""
    t = re.sub(r"[^a-z]+", " ", str(type_text or "").lower()).strip()
    if kind == "relay":
        return "micro relay" if "micro" in t else "maxi relay" if "maxi" in t else ""
    if "fmx" in t or "j case" in t or "jcase" in t:
        return "j-case"
    for k in ("midi", "maxi", "mini"):
        if k in t.split():
            return k
    return ""


def _catalogue_photo(key: str, cache: dict[str, Any]) -> Any:
    if key not in cache:
        try:
            from ..services import component_images
            hits = component_images.images_for_key(key, limit=1, exclude_placeholders=True) if key else []
        except Exception:  # noqa: BLE001
            hits = []
        cache[key] = ({"url": hits[0]["photo_url"], "href": hits[0]["part_url"], "name": hits[0]["name"]} if hits else None)
    return cache[key]


def _item_name(i: dict[str, Any]) -> str:
    lab = str(i.get("label") or "")
    pos = str(i.get("position") or "")
    for pre in ("Fuse ", "Relay "):
        if lab.startswith(pre):
            lab = lab[len(pre):]
    if pos and lab.startswith(pos):
        lab = lab[len(pos):].strip()
    lab = lab.strip(" -:")
    if lab.startswith("(") and lab.endswith(")"):
        lab = lab[1:-1]
    return plain(lab or i.get("label") or "")


def _how_sure(b: dict[str, Any]) -> str:
    conf = b.get("location_confidence") or "UNKNOWN"
    src = str(b.get("source") or "").lower()
    if b.get("added_by_technician"):
        return "from a source named by the owner, not checked by CUORE"
    if "third-party" in src:
        return "from a third-party diagram, not checked on this car"
    if conf == "INFERRED":
        return "worked out from the sources, not checked on this car"
    return CONF_WORDS.get(conf, "not known")


def _worst(sts: list[str]) -> str:
    s = set(sts)
    return "red" if "red" in s else "orange" if "orange" in s else "green" if s == {"green"} else "grey"


def build_context(vin: str, data: dict[str, Any], status_f: str, box_f: str,
                  job_ids: Any = (), open_ids: Any = ()) -> dict[str, Any]:
    svc = _svc()
    boxes = list(data.get("boxes") or [])
    items = [dict(i) for i in data.get("items") or []]
    counts = {k: int((data.get("counts") or {}).get(k, 0)) for k in STATUSES}
    if not data.get("counts"):
        for i in items:
            counts[i.get("status") if i.get("status") in counts else "grey"] += 1
    cache: dict[str, Any] = {}
    for i in items:
        st = i.get("status") if i.get("status") in STATUS_LABEL else "grey"
        sp = i.get("spec") or {}
        i.update(status=st, status_word=STATUS_LABEL[st], anchor=_anchor(i["id"]), name=_item_name(i),
                 job=i["id"] in job_ids, is_open=i["id"] in open_ids,
                 missing=[w for w, have in (("rating", i.get("rating_a")), ("type", sp.get("type") or sp.get("relay_type")),
                                            ("colour", sp.get("colour")), ("voltage", sp.get("voltage_v"))) if not have],
                 photo=_catalogue_photo(photo_key(i.get("kind") or "", sp.get("type") or sp.get("relay_type") or ""), cache))
    secs: list[dict[str, Any]] = []
    for b in boxes:
        rows = [i for i in items if i.get("box") == b["id"]]
        st = _worst([r["status"] for r in rows])
        secs.append(_section(vin, svc, b, rows, st, status_f, job_ids=job_ids))
    nobox = [i for i in items if not i.get("box")]
    if nobox:
        secs.append(_section(vin, svc, {"id": "none", "label": "Box not stated by the source", "short": "No box stated",
                                        "source": "These rows come from a source that names the fuse or relay but not "
                                                  "which box it is in.", "location_confidence": "UNKNOWN",
                                        "full_list_sourced": False}, nobox, _worst([r["status"] for r in nobox]),
                             status_f, mapped=False, job_ids=job_ids))
    if box_f:
        secs = [x for x in secs if x["id"] == box_f]
    return {"secs": secs, "counts": counts, "total": len(items)}


def _section(vin: str, svc: Any, b: dict[str, Any], rows: list[dict[str, Any]], st: str, status_f: str,
             mapped: bool = True, job_ids: Any = ()) -> dict[str, Any]:
    from . import fuse_map_svg as fm
    photos, diagrams = [], []
    if b["id"] != "none":
        photos = svc.photos(vin, b["id"])
        try:
            diagrams = svc.box_diagrams(b)
        except Exception:  # noqa: BLE001
            diagrams = []
    slots, from_layout = fm.slot_svg(rows, plain(b.get("short") or b.get("label")), job_ids=set(job_ids))
    gap_words = [w for w, key in (("ratings", "rating_a"), ("colours", "colour"), ("voltages", "voltage_v"))
                 if any(not ((r.get("spec") or {}).get(key) if key != "rating_a" else r.get(key)) for r in rows)]
    shown = [r for r in rows if not status_f or r["status"] == status_f]
    n = len(rows)
    return {**b, "short": plain(b.get("short") or b.get("label")), "label_plain": plain(b.get("label")),
            "where_plain": plain(b.get("where") or ""), "pick_where": b.get("pick_where") or "", "source_plain": ps(b.get("source")), "status": st, "gap_words": gap_words,
            "has_job": any(r.get("job") for r in rows),
            "status_word": STATUS_LABEL[st], "count": n, "rows": shown, "how_sure": _how_sure(b),
            "list_word": "the full list is sourced" if b.get("full_list_sourced") else "the full list is not sourced yet",
            "photos": photos, "diagrams": diagrams, "slots": slots, "slots_from_layout": from_layout,
            "slot_note": fm.NOTE, "mapped": mapped,
            "side_word": {"left": "left side of the car", "right": "right side of the car (far side from the driver)"}
            .get(b.get("side") or "", "side not stated")}


def _directing(vin: str, dossier: dict[str, Any], data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(the call + job matches, the grounds). Both degrade to empty rather than failing the page."""
    from ..services import fuse_direct as fd
    try:
        grounds = fd.grounds(vin, REPO_ROOT)
    except Exception:  # noqa: BLE001
        grounds = []
    try:
        from ..services import electrical_bridge, mes_bridge
        codes = mes_bridge.open_codes_for(dossier)
        syms, ctext = fd.job_inputs(vin, codes, dossier)
        d = fd.direct(data.get("items") or [], data.get("boxes") or [], syms, codes, ctext, electrical_bridge.path_for_code)
    except Exception:  # noqa: BLE001
        d = {"call": "", "call_segs": [], "call_targets": [], "call_items": [], "call_box": "", "more": [], "groups": [],
             "matches": [], "ground_ids": [], "codes": []}
    return d, grounds


def ctx_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for i in data.get("items") or []:
        i = dict(i)
        i["status"] = i.get("status") if i.get("status") in STATUS_LABEL else "grey"
        out.append(i)
    return out


def _cards(vin: str, matches: list[dict[str, Any]], by_id: dict[str, Any]) -> list[dict[str, Any]]:
    """Ranked job cards: matches merged per (rank, box, circuit) so F47 + F48 become one card."""
    cards: dict[tuple, dict[str, Any]] = {}
    for m in matches:
        it = by_id.get(m["id"], m["item"])
        sp = it.get("spec") or {}
        circuit = _item_name(it)
        key = (m["rank"], m["box_id"], circuit)
        c = cards.setdefault(key, {"rank": m["rank"], "refs": [], "circuit": circuit, "box": m["box"], "where": m["where"],
                                   "box_id": m["box_id"], "kinds": [], "ratings": [], "types": [], "colours": [],
                                   "statuses": [], "sym": False, "codes": [], "paths": []})
        c["refs"].append({"ref": m["ref"], "anchor": _anchor(it["id"])})
        c["kinds"].append(it.get("kind") or "fuse")
        for lst, v in ((c["ratings"], it.get("rating_a")), (c["types"], sp.get("type") or ""),
                       (c["colours"], sp.get("colour") or "")):
            if v and v not in lst:
                lst.append(v)
        c["statuses"].append(it.get("status", "grey"))
        for w in m["name_whys"]:
            if w.startswith("matches the symptom"):
                c["sym"] = True
            else:
                mm = re.match(r"matches (\S+)", w)
                if mm and mm.group(1) not in c["codes"]:
                    c["codes"].append(mm.group(1))
        for code in m["path_codes"]:
            if code not in c["paths"]:
                c["paths"].append(code)
    out = []
    for c in cards.values():
        refs = [r["ref"] for r in c["refs"]]
        circ = c["circuit"]
        show_circ = circ and len(circ) <= 40 and not any(circ.lower() in r.lower() or r.lower() in circ.lower() for r in refs)
        basis = ""
        if c["sym"] or c["codes"]:
            basis = "Matches " + " and ".join((["the open symptom"] if c["sym"] else []) + c["codes"])
        n = len(c["paths"])
        out.append({**c, "title": " / ".join(refs) + (" " + circ if show_circ else ""),
                    "kind": "relay" if set(c["kinds"]) == {"relay"} else "fuse",
                    "status": _worst(c["statuses"]), "basis": basis,
                    "path_line": f"On the path for {n} code{'s' if n != 1 else ''}" if n else "",
                    "rating_txt": " / ".join(f"{x:g} A" for x in c["ratings"]),
                    "type_txt": " / ".join(c["types"]), "colour_txt": c["colours"][0] if len(c["colours"]) == 1 else ""})
    return out


def _components_ctx(vin: str, cat: str, area: str, q: str, item_ids: set, job_ids: set = frozenset()) -> dict[str, Any]:
    """The Components section: rows (enriched), category chips, car-view clusters, fuse-id -> components."""
    from ..services import components as cp
    from . import fuse_icons
    from ..services import fuse_direct as fd
    rows = cp.load()
    counts = {k: 0 for k in cp.CATS}
    for r in rows:
        counts[cp.cat_of(r)] += 1
    cat_f = cat.strip() if cat.strip() in cp.CATS else ""
    area_f = area.strip() if area.strip() in cp.AREA_WORDS else ""
    shown = [r for r in rows if (not cat_f or cp.cat_of(r) == cat_f) and (not area_f or r.get("area") == area_f)]
    photos: dict[str, Any] = {}
    out, by_fuse = [], {}
    for r in rows:
        c = cp.cat_of(r)
        links = r.get("links") or {}
        fids = [f for f in links.get("fuse_ids") or [] if f in item_ids]
        item = {"id": r["id"], "anchor": _anchor(r["id"]), "name": plain(r["name"]), "cat": c, "cat_label": cp.CATS[c][0],
                "icon": fuse_icons.icon(c, 28), "area": r.get("area"), "where": cp.area_text(r), "module": r.get("module"),
                "fuses": [{"id": f, "anchor": _anchor(f)} for f in fids],
                "sensors": [{"id": x, "label": x.replace("_", " "), "anchor": _anchor(x)} for x in links.get("sensor_ids") or []],
                "sources": cp.source_lines(r, ps)}
        for f in fids:
            by_fuse.setdefault(f, []).append(item)
        out.append(item)
    shown_ids = {r["id"] for r in shown}
    rows_out = [i for i in out if i["id"] in shown_ids]
    for i in rows_out:
        i["photo"] = cp.photo_for(i["name"], photos, exclude_placeholders=True)
    hit_ids = {r["id"] for r in cp.search(q, rows, fd.SYNONYMS)} if q else set()
    job_hit = {i["id"] for i in rows_out if job_ids and any(f["id"] in job_ids for f in i["fuses"])}
    groups = [{"cat": k, "label": cp.CATS[k][1], "icon": fuse_icons.icon(k, 28), "rows": [i for i in rows_out if i["cat"] == k]}
              for k in cp.CATS if any(i["cat"] == k for i in rows_out)]
    for g in groups:   # a group is open only when chosen (chip / map link) or when it holds a search or job match
        g["open"] = bool(cat_f == g["cat"] or area_f or any(i["id"] in hit_ids or i["id"] in job_hit for i in g["rows"]))
    # car clusters: sourced area only, per (area, category)
    cl: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        a = r.get("area")
        if a not in cp.AREA_VIEW:
            continue
        c = cp.cat_of(r)
        side = r.get("side") or ("left" if "_left_" in a else "right" if "_right_" in a else None)
        e = cl.setdefault((a, c), {"view_area": cp.AREA_VIEW[a], "cat": c, "label": cp.CATS[c][1], "count": 0, "side": side,
                                   "area_text": cp.AREA_WORDS.get(a, a),
                                   "href": f"/v/{vin}/fuses?cat={c}&area={a}#fuse-components"})
        e["count"] += 1
    chips = [{"cat": k, "label": cp.CATS[k][1], "icon": fuse_icons.icon(k, 24), "count": counts[k],
              "href": f"/v/{vin}/fuses?cat={k}#fuse-components", "on": cat_f == k} for k in cp.CATS if counts[k]]
    legend = [{"cat": k, "label": cp.CATS[k][0], "icon": fuse_icons.icon(k, 24)} for k in cp.CATS]
    matches = [{"kind": "component", "ref": plain(r["name"]), "text": cp.CATS[cp.cat_of(r)][0],
                "where": cp.area_text(r) or "location not sourced", "amps": "", "href": "#comp-" + _anchor(r["id"]),
                "icon": fuse_icons.icon(cp.cat_of(r), 24), "cat_label": cp.CATS[cp.cat_of(r)][0]}
               for r in rows if r["id"] in hit_ids] if q else []
    return dict(groups=groups, chips=chips, legend=legend, clusters=list(cl.values()), by_fuse=by_fuse, matches=matches,
                total=len(rows), shown=len(rows_out), cat_f=cat_f, area_f=area_f,
                area_word=cp.AREA_WORDS.get(area_f, ""), drawn=sum(e["count"] for e in cl.values()),
                sprite=fuse_icons.sprite(), icon=fuse_icons.icon)


def _page_ctx(vin: str, status: str, box: str, q: str, cat: str = "", area: str = "", show_all: bool = False) -> dict[str, Any]:
    from . import fuse_map_svg as fm
    from ..services import fuse_direct as fd
    dossier = _dossier(vin)
    error = None
    try:
        data = _svc().health(vin)
    except Exception as exc:  # noqa: BLE001 - render without the service
        data = {"vin": vin, "checked_at": None, "boxes": [], "items": [], "counts": {}, "unplaced": [], "gaps": []}
        error = f"Fuse health is not available yet: {exc}"
    status_f = status.strip().lower() if status.strip().lower() in STATUSES else ""
    box_ids = {b["id"] for b in data.get("boxes") or []}
    box_f = box.strip() if box.strip() in box_ids or box.strip() == "none" else ""
    direction, grounds = _directing(vin, dossier, data)
    job_ids = {m["id"] for m in direction["matches"] if m["rank"] < 2} | set(direction["call_items"])
    ctx = build_context(vin, data, status_f, box_f, job_ids=job_ids, open_ids=set(direction["call_items"]))
    jobs = {m["id"] for m in direction["matches"] if m["rank"] < 2} | set(direction["call_items"])
    try:
        comp = _components_ctx(vin, cat, area, q.strip()[:80], {i["id"] for i in data.get("items") or []}, jobs)
    except Exception:  # noqa: BLE001 - the page still renders without components
        comp = None
    if comp:
        for sec in ctx["secs"]:
            for row in sec["rows"]:
                row["also"] = comp["by_fuse"].get(row["id"], [])
    secs, counts, total = ctx["secs"], ctx["counts"], ctx["total"]
    by_id = {it["id"]: it for it in ctx_items(data)}
    for g in grounds:
        g["photo"] = _catalogue_photo("battery_negative_strap", {}) if g["id"] == "battery_neg_strap" else None
        g["source_txt"], g["outside_txt"] = ps(g.get("source")), ps(g.get("outside"))
    gmap = {g["id"]: g for g in grounds}
    job_grounds = [gmap[i] for i in direction["ground_ids"] if i in gmap]
    cards = _cards(vin, direction["matches"], by_id)
    top_cards = [c for c in cards if c["rank"] < 2] or [c for c in cards if c["rank"] == 2]
    also_cards = [c for c in cards if c not in top_cards]
    q = q.strip()[:80]
    results = fd.search(q, ctx_items(data), data.get("boxes") or [], grounds, status_f, box_f) if q else []
    comp_results = comp["matches"] if (q and comp and not status_f and not box_f) else []
    for r in results + comp_results:
        r["ref"], r["text"], r["where"] = plain(r["ref"]), plain(r["text"]), plain(r["where"])
    cap = None if show_all else RESULT_CAP
    parts_h = []
    for kinds, one, many in ((("fuse", "relay"), "fuse", "fuses"), (("ground",), "ground", "grounds"), (("box",), "box", "boxes")):
        n_k = sum(1 for r in results if r.get("kind") in kinds)
        if n_k:
            parts_h.append(f"{n_k} {one if n_k == 1 else many}")
    if comp_results:
        parts_h.append(f"{len(comp_results)} component{'' if len(comp_results) == 1 else 's'}")
    res_head = " · ".join(parts_h) + f" match ‘{q}’"
    all_href = f"/v/{vin}/fuses?" + urlencode({k: v for k, v in (("q", q), ("status", status_f), ("box", box_f), ("all", "1")) if v}) + "#fuse-results"

    def href(st: str = "") -> str:
        return f"/v/{vin}/fuses" + (f"?status={st}" if st else "") + "#fuse-chips"

    chip_href = {k: href("" if status_f == k else k) for k in STATUSES}
    boxed = [s for s in secs if s["id"] != "none"]
    nobox = next((s for s in secs if s["id"] == "none"), None)
    mapped = [s for s in boxed if s.get("mapped", True)]
    short = {"g003a": "G003A", "g003b": "G003B", "esim_ground": "ESIM gnd", "battery_neg_strap": "Batt. strap"}
    call_side = next((b.get("side") for b in data.get("boxes") or [] if b["id"] == direction["call_box"]), None)
    svg = fm.box_map([{"id": s["id"], "short": s["short"], "side": s.get("side"), "zone": s.get("zone"),
                       "area": s.get("area"), "status": s["status"], "status_word": s["status_word"],
                       "count": s["count"], "location_confidence": s.get("location_confidence")}
                      for s in mapped],
                     [{"id": g["id"], "name": g["name"], "short": short.get(g["id"], g["name"])} for g in grounds],
                     default_view="top" if call_side == "right" else "side",
                     comps=comp["clusters"] if comp else None) if mapped else ""
    try:
        parts = _svc().catalogue_parts()
    except Exception:  # noqa: BLE001
        parts = {}
    skip = ("full fuse list not sourced", "not on the drawing")
    gaps = [g for g in data.get("gaps") or [] if not any(k in g for k in skip)]
    gaps.insert(0, "No box has its full fuse list from a source yet; each box section says how many rows are listed.")
    if direction["call_segs"]:
        call_segs = direction["call_segs"]
    else:
        call_segs = [{"text": f"{total} fuses and relays, {len(data.get('boxes') or [])} boxes. Pick a box.", "href": ""}]
    why = {"match_lines": [{"refs": " / ".join(r["ref"] for r in c["refs"]), "via": m_via,
                            "lines": [plain(w) for w in lines]}
                           for c, m_via, lines in _why_rows(cards, direction["matches"])],
           "groups": [{"n": g["n"], "codes": ", ".join(g["codes"]), "names": ", ".join(g["names"])}
                      for g in direction["groups"]],
           "has_name": any(m["via"] == fd.BY_NAME for m in direction["matches"]),
           "has_path": any(m["via"] == fd.BY_PATH for m in direction["matches"]) or bool(direction["groups"])}
    return dict(vin=vin, bar=_vehicle_bar(vin, dossier), tab="fuses", svg=svg, call=direction["call"] or "".join(x["text"] for x in call_segs),
                call_segs=call_segs, go_chips=direction["call_targets"], why=why,
                cards=top_cards, also_cards=also_cards, job_grounds=job_grounds, grounds=grounds, q=q, results=results,
                results_shown=results[:cap], comp_results=comp_results, comp_shown=comp_results[:cap], res_head=res_head, all_href=all_href, no_match_hint=fd.SEARCH_HINT,
                secs=boxed, nobox=nobox, counts=counts, total=total, status_f=status_f, box_f=box_f, chip_href=chip_href,
                base=f"/v/{vin}/fuses", gaps=[plain(g) for g in gaps], status_label=STATUS_LABEL,
                status_mark=STATUS_MARK, parts=parts, colour_class=fm.colour_class, anchor=_anchor, error=error, plain=plain,
                ps=ps, checked_at=data.get("checked_at"), tested_label=_tested_label,
                ground_where_gap=any(not g.get("where_known") for g in grounds), comp=comp)


def _why_rows(cards: list[dict[str, Any]], matches: list[dict[str, Any]]):
    """(card, via, lines) for the Why disclosure: what linked each card, in full words."""
    by_ref = {m["ref"]: m for m in matches}
    for c in cards:
        m = by_ref.get(c["refs"][0]["ref"])
        if not m:
            continue
        if m["name_whys"]:   # path-only links are summarised once, grouped by code, in "groups"
            yield c, m["via"], list(m["name_whys"])


def _tested_label(kind: str) -> tuple[str, str]:
    return ("Tested OK", "Blown - replaced") if kind == "fuse" else ("Tested OK", "Faulty")


@router.get("/v/{vin}/fuses", response_class=HTMLResponse)
def fuses_page(request: Request, vin: str, status: str = "", box: str = "", msg: str = "", q: str = "",
               cat: str = "", area: str = "", all: str = "") -> HTMLResponse:
    response = _page(request, "fuses.html", msg=msg, **_page_ctx(vin, status, box, q, cat, area, all == "1"))
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/fuses/data", response_class=HTMLResponse)
def fuses_data_page(request: Request, vin: str, msg: str = "") -> HTMLResponse:
    """Owner data maintenance: the add / record / upload forms. Reached only from a footer link on the mechanic page."""
    dossier = _dossier(vin)
    try:
        data = _svc().health(vin)
    except Exception:  # noqa: BLE001
        data = {"boxes": [], "items": []}
    boxes = [{"id": b["id"], "short": plain(b.get("short") or b.get("label"))} for b in data.get("boxes") or []]
    items = [{"id": i["id"], "kind": i.get("kind"), "label": plain(i.get("label")), "position": i.get("position") or ""}
             for i in data.get("items") or []]
    response = _page(request, "fuses_data.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="fuses", base=f"/v/{vin}/fuses",
                     msg=msg, boxes=boxes, items=items, photo_kinds=PHOTO_KINDS,
                     area_choices=[("engine", "Engine bay"), ("interior", "Interior"), ("rear", "Rear"),
                                   ("luggage", "Luggage compartment")])
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/fuses/photo/{box}/{name}")
def fuses_photo(vin: str, box: str, name: str) -> Response:
    p = _svc().photo_path(vin, box, name)
    if not p:
        return Response(status_code=404)
    return FileResponse(p, headers={"Cache-Control": "max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.post("/v/{vin}/fuses/photo", response_class=HTMLResponse)
async def fuses_photo_add(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    box = f("box")
    to = f("redirect_to") or f"/v/{vin}/fuses#fuse-box-{_anchor(box)}"
    up = form.get("photo")
    if up is None or not hasattr(up, "read"):
        return _back(vin, "Photo not saved: choose a picture first", to)
    svc = _svc()
    data = await up.read(svc.MAX_PHOTO_BYTES + 1)
    kind = f("caption") if f("caption") in PHOTO_KINDS else ""
    try:
        svc.save_photo(vin, box, getattr(up, "filename", "") or "", data, by=f("by"), caption=kind)
    except ValueError as exc:
        return _back(vin, f"Photo not saved: {exc}", to)
    return _back(vin, "Photo saved", to)


@router.post("/v/{vin}/fuses/box", response_class=HTMLResponse)
async def fuses_box_add(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    try:
        rec = _svc().add_box(short=f("short"), label=f("label"), area=f("area"), side=f("side"), where=f("where"),
                             source=f("source"), by=f("by") or "technician")
    except ValueError as exc:
        return _back(vin, f"Box not added: {exc}", f("redirect_to"))
    return _back(vin, "Fuse box added (marked as added by a technician)", f"/v/{vin}/fuses#fuse-box-{_anchor(rec['id'])}")


@router.post("/v/{vin}/fuses/check", response_class=HTMLResponse)
async def fuses_check(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    to = f("redirect_to")
    note = f("note") or (f("blown_note") if f("result") == "blown" else "Tested OK" if f("result") == "ok" else "")
    try:
        _svc().add_check(vin, f("item"), f("result"), f("method") or "visual", value=f("value"), unit=f("unit"),
                         note=note, by=f("by") or "technician", limit=f("limit"))
    except ValueError as exc:
        return _back(vin, f"Check not saved: {exc}", to)
    return _back(vin, "Check recorded", to)


@router.post("/v/{vin}/fuses/spec", response_class=HTMLResponse)
async def fuses_spec(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    to = f("redirect_to")
    try:
        _svc().add_spec(f("item"), source=f("source"), by=f("by") or "technician",
                        **{k: f(k) for k in ("fuse_type", "voltage_v", "colour", "relay_type", "relay_number",
                                             "pin_layout", "orientation")})
    except ValueError as exc:
        return _back(vin, f"Details not saved: {exc}", to)
    return _back(vin, "Details saved", to)


@router.post("/v/{vin}/fuses/item", response_class=HTMLResponse)
async def fuses_item(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()

    def f(k: str) -> str:
        return str(form.get(k, "") or "").strip()

    mods = [m for m in f("feeds_modules").replace(";", ",").split(",") if m.strip()]
    try:
        _svc().add_item(kind=f("kind"), label=f("label"), source=f("source"), box=f("box"), position=f("position"),
                        rating_a=f("rating_a"), feeds_modules=mods, notes=f("notes"), by=f("by") or "technician",
                        **{k: f(k) for k in ("fuse_type", "voltage_v", "colour", "relay_type", "relay_number",
                                             "pin_layout", "orientation")})
    except ValueError as exc:
        return _back(vin, f"Not added: {exc}", f("redirect_to"))
    return _back(vin, "Fuse/relay added (marked as added by technician)", f("redirect_to"))
