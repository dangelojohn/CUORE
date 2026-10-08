"""Mechanic evidence media library: photos, scans, borescope clips.

Files live at ``<state>/media/<vin>/<id>.<ext>``, a thumbnail for each at
``<state>/media/<vin>/thumbs/<id>.jpg`` (320px, EXIF-rotated for photos; for
video the first frame via ``ffmpeg`` when it is on PATH, else a generic
poster), and one append-friendly index row per file at
``<state>/media/index.jsonl``.

Same posture as ``cuore.live.store`` and ``cuore.live.checklists``: plain
JSON/JSONL beside the lock file, guarded by a lock, read-modify-write. Unlike
those stores this one also owns binary files on disk, so every mutating
function keeps the index and the files it describes in step -- a crash
between writing a file and appending its index row would otherwise leave an
orphan, which is why the file is written first and the index row appended
only once it is known to be on disk.

Media are attested evidence of what a technician saw, not a measurement the
car reported: this module never writes to ``cuore.live.store``'s
observations log, and nothing here should be mistaken for one.
"""

from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import shutil
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import state_dir

_LOCK = threading.Lock()

MAX_SIZE = 500 * 1024 * 1024  # 500 MB

# mime -> (kind, extension)
ALLOWED_MIMES: dict[str, tuple[str, str]] = {
    "image/jpeg": ("photo", "jpg"),
    "image/png": ("photo", "png"),
    "image/webp": ("photo", "webp"),
    "image/heic": ("photo", "heic"),
    "application/pdf": ("scan", "pdf"),
    "video/mp4": ("video", "mp4"),
    "video/webm": ("video", "webm"),
    "video/quicktime": ("video", "mov"),
}

TARGET_KINDS = {"vehicle", "code", "step", "service_record", "symptom", "note",
                "timeline"}

THUMB_SIZE = 320


class BadMedia(ValueError):
    """Rejected before anything was written: bad mime or too large."""


class UnknownMedia(KeyError):
    """No index row for this id."""


# --- paths ------------------------------------------------------------------

def _root() -> Path:
    return state_dir() / "media"


def index_path() -> Path:
    return _root() / "index.jsonl"


def vin_dir(vin: str) -> Path:
    return _root() / vin


def thumbs_dir(vin: str) -> Path:
    return vin_dir(vin) / "thumbs"


def _file_path(vin: str, id_: str, ext: str) -> Path:
    return vin_dir(vin) / f"{id_}.{ext}"


def _thumb_path(vin: str, id_: str) -> Path:
    return thumbs_dir(vin) / f"{id_}.jpg"


# --- index --------------------------------------------------------------

def _read_rows() -> list[dict[str, Any]]:
    p = index_path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _append_row(row: dict[str, Any]) -> None:
    index_path().parent.mkdir(parents=True, exist_ok=True)
    with index_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _rewrite_rows(rows: list[dict[str, Any]]) -> None:
    index_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path().with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")
    tmp.replace(index_path())


def _latest_by_id() -> dict[str, dict[str, Any]]:
    """Last row per id wins -- later appends (update/hide) are amendments."""
    out: dict[str, dict[str, Any]] = {}
    for row in _read_rows():
        rid = row.get("id")
        if rid:
            out[rid] = row
    return out


# --- EXIF helpers -------------------------------------------------------

def _exif_captured_at(img: Any) -> str | None:
    try:
        exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    # 0x9003 DateTimeOriginal lives in the Exif IFD, not the base tag dict.
    try:
        from PIL import ExifTags
        exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
    except Exception:
        exif_ifd = {}
    raw = exif_ifd.get(36867) or exif.get(36867) or exif.get(306)
    if not raw:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def _make_photo_thumb(src: Path, dest: Path) -> bool:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return False
    try:
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((THUMB_SIZE, THUMB_SIZE))
            dest.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest, "JPEG", quality=85)
        return True
    except Exception:
        return False


def _make_video_thumb(src: Path, dest: Path) -> bool:
    """First frame via ffmpeg when it's on PATH, else a generic poster."""
    if shutil.which("ffmpeg"):
        import subprocess
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1",
                 "-vf", f"scale='min({THUMB_SIZE},iw)':-2", str(dest)],
                capture_output=True, timeout=30)
            if result.returncode == 0 and dest.exists():
                return True
        except Exception:
            pass
    return _generic_poster(dest)


def _generic_poster(dest: Path) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), (40, 40, 40))
        draw = ImageDraw.Draw(img)
        # A plain triangle "play" glyph -- no font dependency.
        cx, cy, s = THUMB_SIZE // 2, THUMB_SIZE // 2, THUMB_SIZE // 6
        draw.polygon([(cx - s, cy - s), (cx - s, cy + s), (cx + s, cy)],
                     fill=(200, 200, 200))
        img.save(dest, "JPEG", quality=80)
        return True
    except Exception:
        return False


def _build_thumb(vin: str, id_: str, kind: str, file_path: Path) -> None:
    dest = _thumb_path(vin, id_)
    if kind == "photo":
        if _make_photo_thumb(file_path, dest):
            return
    elif kind == "video":
        if _make_video_thumb(file_path, dest):
            return
    # scans/documents (PDF) and anything thumbnail generation failed on:
    # no thumbnail is written; callers treat a missing thumb as "none".


# --- core API -------------------------------------------------------------

def add(vin: str, file_bytes: bytes, filename: str, mime: str, *,
        caption: str = "", tags: list[str] | None = None,
        target_kind: str = "vehicle", target_id: str = "",
        odometer_km: float | None = None, author: str = "",
        captured_at: str = "") -> dict[str, Any]:
    """Store one media file for ``vin``. Returns its index row.

    A duplicate (same sha256, same VIN) returns the existing row untouched --
    no new file, no new index entry.
    """
    if mime not in ALLOWED_MIMES:
        raise BadMedia(f"unsupported mime type: {mime!r}")
    if len(file_bytes) > MAX_SIZE:
        raise BadMedia(f"file too large: {len(file_bytes)} bytes (max {MAX_SIZE})")
    if len(file_bytes) == 0:
        raise BadMedia("empty file")
    if target_kind not in TARGET_KINDS:
        raise BadMedia(f"unknown target_kind: {target_kind!r}")

    kind, ext = ALLOWED_MIMES[mime]
    digest = hashlib.sha256(file_bytes).hexdigest()

    with _LOCK:
        for row in _latest_by_id().values():
            if row.get("vin") == vin and row.get("sha256") == digest and not row.get("hidden"):
                return row

        id_ = uuid.uuid4().hex
        vin_dir(vin).mkdir(parents=True, exist_ok=True)
        fpath = _file_path(vin, id_, ext)
        fpath.write_bytes(file_bytes)

        resolved_captured_at = captured_at
        if not resolved_captured_at and kind == "photo":
            try:
                from PIL import Image
                with Image.open(io.BytesIO(file_bytes)) as img:
                    resolved_captured_at = _exif_captured_at(img) or ""
            except Exception:
                resolved_captured_at = ""

        now = datetime.now().isoformat(timespec="seconds")
        row = {
            "id": id_,
            "vin": vin,
            "kind": kind,
            "filename": filename,
            "mime": mime,
            "size": len(file_bytes),
            "sha256": digest,
            "captured_at": resolved_captured_at or now,
            "uploaded_at": now,
            "author": author or "",
            "caption": caption or "",
            "tags": list(tags or []),
            "target_kind": target_kind,
            "target_id": target_id or "",
            "odometer_km": odometer_km,
            "hidden": False,
        }
        _append_row(row)

    _build_thumb(vin, id_, kind, fpath)
    return row


def get(id_: str) -> dict[str, Any]:
    row = _latest_by_id().get(id_)
    if row is None:
        raise UnknownMedia(id_)
    return row


def path(id_: str) -> Path:
    row = get(id_)
    _, ext = ALLOWED_MIMES[row["mime"]]
    return _file_path(row["vin"], id_, ext)


def thumb_path(id_: str) -> Path | None:
    row = get(id_)
    p = _thumb_path(row["vin"], id_)
    return p if p.exists() else None


def update(id_: str, *, caption: str | None = None, tags: list[str] | None = None,
           target_kind: str | None = None, target_id: str | None = None) -> dict[str, Any]:
    with _LOCK:
        rows = _read_rows()
        row = None
        for r in rows:
            if r.get("id") == id_:
                row = r
        if row is None:
            raise UnknownMedia(id_)
        new_row = dict(row)
        if caption is not None:
            new_row["caption"] = caption
        if tags is not None:
            new_row["tags"] = list(tags)
        if target_kind is not None:
            if target_kind not in TARGET_KINDS:
                raise BadMedia(f"unknown target_kind: {target_kind!r}")
            new_row["target_kind"] = target_kind
        if target_id is not None:
            new_row["target_id"] = target_id
        _append_row(new_row)
        return new_row


def hide(id_: str) -> dict[str, Any]:
    with _LOCK:
        rows = _read_rows()
        row = None
        for r in rows:
            if r.get("id") == id_:
                row = r
        if row is None:
            raise UnknownMedia(id_)
        new_row = dict(row)
        new_row["hidden"] = True
        _append_row(new_row)
        return new_row


def search(vin: str, q: str = "", kind: str = "", tag: str = "",
           target_kind: str = "", target_id: str = "", since: str = "",
           until: str = "") -> list[dict[str, Any]]:
    """Rows for ``vin``, newest ``captured_at`` first, hidden excluded.

    ``q`` matches caption, tags, filename, and target id, case-insensitive.
    """
    needle = q.strip().lower()
    out: list[dict[str, Any]] = []
    for row in _latest_by_id().values():
        if row.get("vin") != vin or row.get("hidden"):
            continue
        if kind and row.get("kind") != kind:
            continue
        if tag and tag not in (row.get("tags") or []):
            continue
        if target_kind and row.get("target_kind") != target_kind:
            continue
        if target_id and row.get("target_id") != target_id:
            continue
        ts = str(row.get("captured_at") or "")
        if since and ts < since:
            continue
        if until and ts > until:
            continue
        if needle:
            haystack = " ".join([
                str(row.get("caption") or ""),
                " ".join(row.get("tags") or []),
                str(row.get("filename") or ""),
                str(row.get("target_id") or ""),
            ]).lower()
            if needle not in haystack:
                continue
        out.append(row)
    out.sort(key=lambda r: str(r.get("captured_at") or ""), reverse=True)
    return out


def export_zip(vin: str) -> Path:
    """Build ``<state>/media/<vin>/export.zip`` with every non-hidden file
    plus ``index.json`` (the rows themselves) for recovery. Returns its path."""
    rows = [r for r in _latest_by_id().values() if r.get("vin") == vin and not r.get("hidden")]
    rows.sort(key=lambda r: str(r.get("captured_at") or ""))
    out_path = vin_dir(vin) / "export.zip"
    vin_dir(vin).mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.json", json.dumps(rows, indent=2, default=str))
        for row in rows:
            _, ext = ALLOWED_MIMES[row["mime"]]
            fpath = _file_path(vin, row["id"], ext)
            if fpath.exists():
                zf.write(fpath, f"files/{row['id']}.{ext}")
    return out_path


__all__ = ["BadMedia", "UnknownMedia", "ALLOWED_MIMES", "TARGET_KINDS", "MAX_SIZE",
           "index_path", "vin_dir", "thumbs_dir", "add", "get", "path", "thumb_path",
           "update", "hide", "search", "export_zip"]
