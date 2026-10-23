"""Validator for CUORE export bundles (``*.cuore.zip``, schema ``cuore.bundle/1.0``).

Pure Python, standard library only, and deliberately free of any other CUORE
import so the future AlfaCore (Odoo) import wizard can vendor this one file
with ``docs/integration/cuore_bundle.schema.json``.

Treat a bundle as untrusted input (spec section 6.4): this module reads the
zip but never extracts it to disk, executes nothing, and enforces size and
path limits before parsing anything.

It implements only the JSON Schema keywords the schema file uses: ``type``,
``required``, ``properties``, ``items``, ``enum``, ``const``, ``pattern``,
``minimum``, ``minItems`` and local ``$ref`` (``#/$defs/...``). Unknown keys
in the data are tolerated (kept, never an error).

    errors = validate_bundle(path)      # [] when the bundle is sound
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Optional, Union

SCHEMA_ID = "cuore.bundle/1.0"
SUPPORTED_SCHEMAS = (SCHEMA_ID,)

#: Zip safety limits (spec 6.4 rule 1).
MAX_MEMBERS = 64
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024

#: Members that carry data but are not described by an ``x-parts`` entry.
RAW_MEMBERS = ("observations.jsonl",)

DEFAULT_SCHEMA_PATH = (Path(__file__).resolve().parents[2] / "docs" / "integration"
                       / "cuore_bundle.schema.json")


def load_schema(path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    return json.loads(Path(path or DEFAULT_SCHEMA_PATH).read_text(encoding="utf-8"))


# --- the JSON Schema subset ------------------------------------------------------

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate(instance: Any, schema: dict[str, Any], root: Optional[dict[str, Any]] = None,
             path: str = "$") -> list[str]:
    """Errors (``path: message``) of ``instance`` against ``schema``; ``[]`` = valid."""
    root = root if root is not None else schema
    errs: list[str] = []
    if "$ref" in schema:
        errs += validate(instance, _resolve(schema["$ref"], root), root, path)
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES[x](instance) for x in types):
            return errs + [f"{path}: expected {'/'.join(types)}, got {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        errs.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errs.append(f"{path}: {instance!r} not one of {schema['enum']}")
    if isinstance(instance, str) and "pattern" in schema \
            and not re.search(schema["pattern"], instance):
        errs.append(f"{path}: {instance!r} does not match {schema['pattern']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool) \
            and "minimum" in schema and instance < schema["minimum"]:
        errs.append(f"{path}: {instance} is below {schema['minimum']}")
    if isinstance(instance, dict):
        for key in schema.get("required") or []:
            if key not in instance:
                errs.append(f"{path}: missing required key {key!r}")
        for key, sub in (schema.get("properties") or {}).items():
            if key in instance:
                errs += validate(instance[key], sub, root, f"{path}.{key}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errs.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "items" in schema:
            for i, item in enumerate(instance):
                errs += validate(item, schema["items"], root, f"{path}[{i}]")
    return errs


# --- the bundle ------------------------------------------------------------------

def validate_manifest(manifest: Any, schema: Optional[dict[str, Any]] = None) -> list[str]:
    schema = schema or load_schema()
    errs = validate(manifest, schema)
    if isinstance(manifest, dict) and manifest.get("schema") not in SUPPORTED_SCHEMAS:
        errs.append(f"$.schema: {manifest.get('schema')!r} is not supported "
                    f"(this reader supports {list(SUPPORTED_SCHEMAS)})")
    return errs


def validate_part(name: str, data: Any, schema: Optional[dict[str, Any]] = None) -> list[str]:
    schema = schema or load_schema()
    part = (schema.get("x-parts") or {}).get(name)
    if part is None:
        return []
    return validate(data, part, schema, name)


def _safe_member_name(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts \
        and "\\" not in name and ":" not in name


def validate_bundle(source: Union[str, Path, bytes],
                    schema: Optional[dict[str, Any]] = None) -> list[str]:
    """Everything a reader must check before trusting a bundle: zip safety,
    manifest against the schema, every listed file present with a matching
    SHA-256 and size, no unlisted files, every part against its schema, and
    the one VIN of the bundle matching the vehicle section."""
    import io
    schema = schema or load_schema()
    errs: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(source) if isinstance(source, bytes) else str(source))
    except (zipfile.BadZipFile, OSError) as exc:
        return [f"not a readable zip: {exc}"]
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            return [f"too many members ({len(infos)} > {MAX_MEMBERS})"]
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            return ["archive expands beyond the size cap"]
        names: dict[str, zipfile.ZipInfo] = {}
        for i in infos:
            if not _safe_member_name(i.filename):
                errs.append(f"unsafe member name {i.filename!r}")
            elif i.file_size > MAX_MEMBER_BYTES:
                errs.append(f"{i.filename}: larger than the member cap")
            elif (i.external_attr >> 16) & 0o170000 == 0o120000:
                errs.append(f"{i.filename}: symlink")
            names[i.filename] = i
        if errs:
            return errs
        if "manifest.json" not in names:
            return ["manifest.json is missing"]
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return [f"manifest.json is not valid JSON: {exc}"]
        errs += validate_manifest(manifest, schema)
        if errs:
            return errs
        listed = {f["path"]: f for f in manifest["files"]}
        for path, f in listed.items():
            if path not in names:
                errs.append(f"{path}: listed in the manifest but not in the zip")
                continue
            raw = zf.read(path)
            if len(raw) != f["bytes"]:
                errs.append(f"{path}: {len(raw)} bytes, manifest says {f['bytes']}")
            if hashlib.sha256(raw).hexdigest() != f["sha256"]:
                errs.append(f"{path}: sha256 mismatch")
            if path in (schema.get("x-parts") or {}):
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    errs.append(f"{path}: not valid JSON: {exc}")
                    continue
                errs += validate_part(path, data, schema)
            elif path in RAW_MEMBERS:
                for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
                    try:
                        json.loads(line)
                    except ValueError:
                        errs.append(f"{path}: line {n} is not valid JSON")
                        break
            else:
                errs.append(f"{path}: not a known part of {SCHEMA_ID}")
        for n in names:
            if n != "manifest.json" and n not in listed:
                errs.append(f"{n}: in the zip but not listed in the manifest")
        for part in ("scan.json", "job.json"):
            if part in listed:
                vin = (json.loads(zf.read(part).decode("utf-8")).get("vin")
                       or (json.loads(zf.read(part).decode("utf-8")).get("job") or {}).get("vin"))
                if vin and vin != manifest["vehicle"]["vin"]:
                    errs.append(f"{part}: VIN differs from the manifest's vehicle (a bundle never mixes vehicles)")
    return errs


__all__ = ["SCHEMA_ID", "validate", "validate_bundle", "validate_manifest", "validate_part",
           "load_schema"]
