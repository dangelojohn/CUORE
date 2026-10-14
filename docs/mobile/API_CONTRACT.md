# CUORE mobile API contract

**For:** a native iPhone app (Swift or Flutter) that replaces the phone web page
`/m/{vin}` ("Tell CUORE").

**Status:** generated against the running schema, 2026-10-13. The web page at
`/m/{vin}` is the reference implementation and keeps no logic of its own --
every form it renders and every record it writes goes through exactly the
routes below, via `cuore.services.owner_events_bridge` / `cuore.live.media`.
A native app talks to the same routes and gets the same behaviour. Source:
`docs/handbook/06-roadmap.md` ("Mobile companion", decided 2026-10-13).

This file was produced by starting the app in-process
(`CUORE_STATE_DIR` pointed at a throwaway directory, `cuore.app.create_app()`)
and reading `app.openapi()`, then exercising each route with a `TestClient`
to capture real request/response shapes. `cuore/tests/check_api_contract.py`
re-reads `app.openapi()` on every run and fails if any path in the table
below has disappeared -- this document cannot silently go stale.

All examples use the Stelvio fixture VIN `ZASFAKPN5J7B88115`.

---

## Path table

Every path a native client needs, exactly as `app.openapi()` names it today.
`check_api_contract.py` parses this table and fails CI if a row's method+path
is no longer in the live schema.

| Method | Path | Summary |
|---|---|---|
| GET | /api/health | Liveness |
| GET | /api/capabilities | What this host can do |
| GET | /api/vehicle/{vin}/report | Identity and chronic faults |
| GET | /api/owner/{vin}/taxonomy | Category/kind table for the Tell CUORE form |
| GET | /api/owner/{vin}/events | This VIN's owner-reported events |
| POST | /api/owner/{vin}/events | Record one owner-reported event |
| DELETE | /api/owner/{vin}/events/{id} | Soft-delete one owner event |
| PATCH | /api/owner/{vin}/events/{id} | Edit one owner-reported event |
| GET | /api/owner/{vin}/messages | Questions for the owner, CUORE's and the mechanic's |
| POST | /api/owner/{vin}/messages/{id}/reply | Owner's (or mechanic's) reply to one message |
| GET | /api/owner/{vin}/correlations | Owner events near each code's first/returned occurrence |
| POST | /api/vehicles/{vin}/media | Upload one or more media files |
| GET | /api/vehicles/{vin}/media | Search this vehicle's media |
| GET | /api/media/{id}/file | The original media file |
| GET | /api/media/{id}/thumb | 320px thumbnail (or first frame, for video) |
| POST | /api/media/{id} | Edit caption, tags, target, symptom tags, or feels_like |
| POST | /api/media/{id}/hide | Hide a media item (soft delete) |
| GET | /api/vision/status | Which photo-reading provider is configured |
| POST | /api/vision/{vin}/read | Read one photo (odometer, fuel pump, oil bottle, part label, or receipt) |

`/api/vision/*` landed mid-write of this document (it did not exist at the
start of this pass; `cuore/services/vision_bridge.py` and `cuore/api/vision.py`
were built concurrently by another agent). See [Vision](#vision) below for
the real contract, captured from the live schema rather than the "pending"
placeholder this section originally held.

---

## Authentication

Every route above (except none -- all of them) carries
`Depends(require_token)` from `cuore/api/deps.py`. Today, on a bench LAN:

* If `CUORE_TOKEN` is unset, auth is a no-op -- anyone who can reach the host
  can read and write. This is only safe because the default bind is
  `127.0.0.1` (loopback-only; see `cuore/config.py`).
* If `CUORE_TOKEN` is set, every request must carry it as either the
  `X-Cuore-Token` header or a `?token=` query parameter. A missing or wrong
  token gets `401` with `WWW-Authenticate: Token`. Comparison is
  constant-time (`hmac.compare_digest`).
* There is no per-user identity, no OAuth, no session. One shared secret,
  one trust boundary: the shop LAN.

**What a native app must add before it ever leaves that LAN:**

1. Never ship with no token configured. Require `CUORE_TOKEN` to be set
   before the app will attempt a non-loopback connection, and store it in
   the iOS Keychain, not `UserDefaults`.
2. Treat the current design as LAN-only. There is no user authentication,
   no per-device revocation, and no TLS (`host`/`port` are plain HTTP) --
   do not expose this host to the public internet without first adding
   TLS termination and real per-device auth in front of it. A shared static
   token sent over LAN HTTP is adequate for "my shop, my devices"; it is not
   adequate for "my customer's phone, over the internet."
3. If remote (non-LAN) access is wanted, put it behind a VPN (e.g.
   WireGuard back to the shop LAN) rather than widening `CUORE_HOST` to
   `0.0.0.0` and exposing the token over the open internet.
4. Handle `401` by prompting for the token again, not by retrying silently.

---

## Vehicle identity

### `GET /api/vehicle/{vin}/report`

The identity call: who this car is and its chronic faults, from the MES log
corpus. This is what the mobile page's header/context would resolve the VIN
against -- the taxonomy, events and media endpoints below take a VIN as
given (usually from a QR code or manual entry) and never validate it against
this corpus themselves, so a native app should call this first to confirm
the VIN resolves to a real vehicle before showing a "Tell CUORE" session for
it.

**Params:** `vin` (path).

**Response 200** (abbreviated -- `chronic_dtcs[].occurrences` continues):

```json
{
  "vin": "ZASFAKPN5J7B88115",
  "vehicle": "",
  "ecu_seen": ["Body Computer Marelli (949)", "Continental ABS MK C1", "..."],
  "log_count": 39,
  "first_log": "2025-09-24 13:45:00",
  "last_log": "2026-10-08 09:26:00",
  "odometer_first_km": 114116.9,
  "odometer_last_km": 142289.9,
  "distinct_dtcs": 29,
  "chronic_dtcs": [
    {
      "dtc": "P0456-00",
      "descriptions": ["Evaporation system leak"],
      "modules": ["Engine / ECM", "..."],
      "vehicles": ["Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir"],
      "statuses_seen": ["stored", "cleared"],
      "sessions": 8,
      "first_seen": "2025-09-24 13:45:00",
      "last_seen": "2026-10-08 09:20:00",
      "occurrences": ["... one row per sighting ..."]
    }
  ]
}
```

**Errors:** `404` when the VIN resolves to no logs at all --

```json
{"error": "NotFound", "detail": "no logs match", "status": 404}
```

A native app should treat `404` here as "unknown vehicle, let the owner
re-enter/re-scan the VIN," not as a transient failure.

---

## `GET /api/health`

Liveness only -- no VIN, no auth-sensitive data beyond cache stats. Poll
this to show a connectivity indicator, and before trying anything else when
the app wakes from background.

**Response 200:**

```json
{
  "ok": true,
  "profile": "bench",
  "version": "0.1.0",
  "corpus_reachable": true,
  "cache": {"entries": 0, "capacity": 16}
}
```

No error codes beyond transport failure (host unreachable) -- this route
cannot itself fail once the process is up.

## `GET /api/capabilities`

The first call any client should make. A client never assumes which host
(bench PC vs. a future in-car node) it reached -- it renders against
whatever this document says the host can do. Fetch once per connection and
cache for the session.

**Response 200** (fields relevant to a mobile client):

```json
{
  "profile": "bench",
  "version": "0.1.0",
  "features": {"corpus": true, "workup": true, "live_obd": true, "...": "..."},
  "lan_exposed": false,
  "authenticated": false
}
```

`authenticated: true` means a token is configured on this host (not that
*this* request carried one) -- a native app can use it to decide whether to
prompt for a token at all.

---

## Owner events ("Tell CUORE")

HTTP face of `cuore.services.owner_events_bridge`; store is
`cuore.live.owner_events` (append-only JSONL under `CUORE_STATE_DIR`).

**Every record here is ATTESTED, never a car measurement** -- see
[Attested-record semantics](#attested-record-semantics).

### `GET /api/owner/{vin}/taxonomy`

The category -> kind -> field schema that drives the entire "Add" flow.
A native app should render its forms from this, not hard-code the
taxonomy -- categories and kinds are added over time (currently 9
categories: fluids, fuel, battery_electrical, tyres_wheels_brakes,
parts_repairs_elsewhere, environment_exposure, incidents, driving_pattern,
cleaning_maintenance).

**Params:** `vin` (path) -- accepted but not used to filter; the taxonomy
is global.

**Response 200** (one kind shown):

```json
{
  "categories": {
    "fluids": {
      "label": "Fluids",
      "kinds": {
        "engine_oil_change": {
          "label": "Engine oil change",
          "fields": {
            "brand": {"type": "text", "label": "Oil brand", "required": false, "remember": true},
            "viscosity": {"type": "text", "label": "Viscosity (e.g. 5W-30)", "required": false, "remember": true},
            "qty": {"type": "number", "label": "Quantity", "required": false, "unit": "L"},
            "filter_changed": {"type": "bool", "label": "Filter changed", "required": false}
          },
          "why_it_matters": "Oil interval and viscosity both matter for wear-related codes...",
          "systems": ["lubrication"],
          "relevance": {}
        }
      }
    }
  }
}
```

A field with `"remember": true` is a candidate for
[remembered values](#remembered-values-recents) -- see that section for the
gap a native app needs to fill.

### `GET /api/owner/{vin}/events`

**Params:** `vin` (path), `include_deleted` (query, bool, default `false`).

**Response 200:**

```json
{"vin": "ZASFAKPN5J7B88115", "events": []}
```

Each event now also carries `audit` (`[]` if never edited -- one entry per
edit applied via `PATCH .../events/{id}`, see below) and `edited_at` (the
most recent edit's own timestamp, or `null`).

### `POST /api/owner/{vin}/events`

**Params:** `vin` (path). **Body** (`OwnerEventRequest`):

```json
{
  "category": "fluids",
  "kind": "engine_oil_topup",
  "at": null,
  "by_role": "owner",
  "by_name": "",
  "fields": {"brand": "Mobil 1", "viscosity": "5W-30"},
  "note": "topped up 0.5L",
  "media_ids": [],
  "odometer_km": null
}
```

`category`/`kind` are required; everything else has a default. `by_role`
must be one of `owner | driver | mechanic`. `media_ids` links photos
already uploaded via the media endpoints (upload first, then reference the
returned `id`s here).

**Response 200:**

```json
{
  "op": "event",
  "id": "d7d1410725ab",
  "vin": "ZASFAKPN5J7B88115",
  "at": "2026-10-13T16:57:53",
  "recorded_at": "2026-10-13T16:57:53",
  "by": {"role": "owner", "name": ""},
  "category": "fluids",
  "kind": "engine_oil_topup",
  "fields": {"brand": "Mobil 1", "viscosity": "5W-30"},
  "note": "topped up 0.5L",
  "media_ids": [],
  "odometer_km": null,
  "confidence": "reported"
}
```

**Errors:**

* `422` -- `category`/`kind` missing entirely (FastAPI/Pydantic body
  validation, generic shape: `{"detail": [{"type": "missing", "loc": [...], ...}]}`).
* `400` -- `category`/`kind` present but not in the taxonomy, surfaced as a
  named `BadRequest`:

  ```json
  {"error": "BadRequest",
   "detail": "unknown kind 'oil_top_up' for category 'fluids'; use one of: engine_oil_change, engine_oil_topup, ...",
   "status": 400}
  ```

  A native app's form should prevent this entirely by always submitting a
  `kind` it got from `taxonomy`, but must still handle the 400 defensively
  (e.g. the taxonomy changed server-side between fetch and submit).

### `DELETE /api/owner/{vin}/events/{id}`

Soft-delete (sets a `delete` marker; `include_deleted=true` on the list call
still returns it). **Params:** `vin`, `id` (path). **Response 200:** the
same shape as `GET` with `op: "delete"`.

### `PATCH /api/owner/{vin}/events/{id}` (added 2026-10-13)

Edit an already-saved owner event -- a typo'd octane, a corrected litres
figure, a note added after the fact. The original append-only row is never
rewritten: this appends an `event_edit` amendment
(`cuore.live.owner_events`'s own op, folded on every read, same posture as
soft-delete) and the folded event keeps a full audit trail (`audit`: one
entry per edit -- `at`, `by`, `changes` -- plus a top-level `edited_at`) that
`GET /api/owner/{vin}/events` now returns on every event.

**Params:** `vin`, `id` (path). **Body** (all optional -- send only what
changed):

```json
{
  "fields": {"octane": "94"},
  "note": null,
  "odometer_km": null,
  "at": null,
  "by_role": "owner",
  "by_name": ""
}
```

`fields` keys are validated against the *event's own, fixed* kind's
taxonomy (the category/kind itself is not editable) -- an unknown key is a
`400`. `by_role`/`by_name` identify who made *this edit* (the audit
entry's `by`), separate from the original report's own `by`.

A changed field's `fields_meta` entry becomes `"typed"` -- it is a hand
edit now -- **unless the edit resubmits the exact same value the field
already had** ("keeps the photo value"), in which case its existing
provenance tag (`"photo"` or `"typed"`, or none) is left untouched.

**Response 200:** the updated, folded event (same shape as `POST`'s
response, plus `audit` and `edited_at`).

**Errors:**

* `404` -- unknown `id`, or an `id` that resolves to an already-deleted
  event (checked against this `vin`'s own events, so an id belonging to a
  *different* vin also 404s rather than leaking cross-vehicle existence):

  ```json
  {"error": "NotFound", "detail": "no owner event with id '...'", "status": 404}
  ```

* `400` -- a `fields` key that isn't one of this event's kind's real
  fields, a non-numeric `odometer_km`, a bad `at`, a note over
  `MAX_NOTE`, or a patch that changes nothing at all:

  ```json
  {"error": "BadRequest", "detail": "unknown field 'bogus' for kind 'fill_up'; use one of: station, octane, ...", "status": 400}
  ```

One kind is **not** editable through this route: `incidents/
noise_smell_vibration` is delegated to `mes.symptoms`, not stored in
`cuore.live.owner_events` at all (see [Owner events](#owner-events-tell-cuore)
above) -- its id always `404`s here. The web page itself (`/m/{vin}/history`)
hides its own Edit action for that one kind for the same reason.

### `GET /api/owner/{vin}/messages`

CUORE's own generated questions and the mechanic's, from the shared
`mes.feedback` inbox (page `"owner"`). This is the feed a native app's push
notifications (see [native-only features](#native-only-features)) should be
built on.

**Response 200** (truncated):

```json
{
  "vin": "ZASFAKPN5J7B88115",
  "messages": [
    {
      "id": "10e2be41b1d2",
      "vin": "ZASFAKPN5J7B88115",
      "at": "2026-10-13T16:57:39",
      "author": "cuore",
      "kind": "question",
      "target": {"page": "owner", "section": "B1029", "item": "elec_recent_work",
                "label": "B1029: Any battery work, jump start, or aftermarket electrical fitted recently (dashcam, lights, audio, tracker)?"},
      "text": "Any battery work, jump start, or aftermarket electrical fitted recently (dashcam, lights, audio, tracker)?",
      "media_ids": [],
      "status": "open",
      "answer": null,
      "applied_note": null
    }
  ]
}
```

There is no server-side push subscription endpoint today -- see
[native-only features](#native-only-features).

### `POST /api/owner/{vin}/messages/{id}/reply`

**Params:** `vin`, `id` (path). **Body:** `{"text": "...", "by": "owner"}`
(`text` required). **Response 200:** the updated message row
(`status: "answered"`, `answer` populated). **Errors:** `422` if `text`
missing; a web-page-level `400` ("a reply is required") is a web-route-only
check on `owner_routes.py` and does not apply to this JSON endpoint directly
-- the API itself relies on Pydantic's `422` for a missing `text`.

### `GET /api/owner/{vin}/correlations`

Owner-reported events within a 14-day window of a DTC's first/returned
occurrence. **Never implies causation** -- see
[attested-record semantics](#attested-record-semantics).

**Response 200:**

```json
{"vin": "ZASFAKPN5J7B88115", "window_days": 14, "correlations": []}
```

---

## Media

HTTP face of `cuore.live.media`. Files live under `<state>/media/<vin>/`;
one JSONL index row per file.

### `POST /api/vehicles/{vin}/media`

**Params:** `vin` (path). **Body:** `multipart/form-data` --

| Field | Type | Notes |
|---|---|---|
| `file` | file, repeatable | one or more files in one request |
| `caption` | text | optional |
| `tags` | text | comma-separated |
| `target_kind` | text | default `"vehicle"`; see `TARGET_KINDS` below |
| `target_id` | text | e.g. a DTC code, a note id |
| `odometer_km` | number | optional |
| `author` | text | optional |
| `symptom_tags` | text | comma-separated, audio clips |
| `feels_like` | text | free text, audio clips |

`target_kind` is one of `vehicle | code | step | service_record | symptom |
note | timeline`.

**Response 200:**

```json
{
  "count": 1,
  "media": [{
    "id": "1e2a100119b240739f540146008e5588",
    "vin": "ZASFAKPN5J7B88115",
    "kind": "photo",
    "filename": "test.jpg",
    "mime": "image/jpeg",
    "size": 8,
    "sha256": "a48e678ec19bde5b8f33567c04f9e3e2a6a9747a0dd67c5a857833aa212917fc",
    "captured_at": "2026-10-13T16:57:40",
    "uploaded_at": "2026-10-13T16:57:40",
    "author": "",
    "caption": "test odometer",
    "tags": [],
    "target_kind": "vehicle",
    "target_id": "",
    "odometer_km": null,
    "hidden": false,
    "symptom_tags": [],
    "feels_like": "",
    "duration_s": null
  }]
}
```

**Errors:** `400` for an unsupported mime type --
`{"detail": "unsupported mime type: 'text/plain'"}` -- or a file over the
size limit (see [image upload limits](#image-upload-limits-and-heic)).

### `GET /api/vehicles/{vin}/media`

**Params:** `vin` (path); `q`, `kind`, `tag`, `target_kind`, `target_id`,
`since`, `until`, `symptom_tag` (all query, all optional). **Response 200:**
`{"count": int, "media": [...]}`, same row shape as upload.

### `GET /api/media/{id}/file`

The original file, served inline (`Content-Disposition: inline`) with the
stored mime type. **Errors:** `404` -- `{"detail": "no media with id '...'"}`.

### `GET /api/media/{id}/thumb`

320px JPEG thumbnail (first frame for video, a drawn waveform poster for
audio). **Errors:** `404` if the id is unknown, or if no thumbnail exists
for that item.

### `POST /api/media/{id}`

Edit caption/tags/target/symptom tags/`feels_like`. **Note for API
implementers (quirk worth knowing):** these are plain FastAPI function
parameters, not a Pydantic body model, so FastAPI binds them as **query
parameters**, not a JSON body -- `POST /api/media/{id}?caption=...&tags=a,b`.
A native client must send them on the query string, not as a JSON body.

**Params:** `id` (path); `caption`, `tags`, `target_kind`, `target_id`,
`symptom_tags`, `feels_like` (all query, optional). **Response 200:** the
updated media row. **Errors:** `404` unknown id; `400` `BadMedia` (e.g. bad
`target_kind`).

### `POST /api/media/{id}/hide`

Soft-delete. **Params:** `id` (path). **Response 200:** the updated row
(`hidden: true`).

---

## Vision

`/api/vision/*` is live. HTTP face of `cuore.services.vision_bridge`
("pluggable 'read this photo' service for the mobile 'Tell CUORE' page"),
matching the roadmap note in `docs/handbook/06-roadmap.md` ("Mobile
companion", 2026-10-13): *"a photo of the odometer, oil bottle or pump
proposing the fields for the human to confirm (pluggable vision provider,
off by default because CUORE runs offline; the Claude provider is an
explicit opt-in that sends the photo to Anthropic)."*

**Every value this returns is a suggestion, never a measurement, never
written automatically.** This module never calls `POST
/api/owner/{vin}/events` itself -- it only reads a photo already in hand
(upload it separately via the media API if it should also be kept as
evidence) and proposes field values for a human to confirm in the add-event
form.

### `GET /api/vision/status`

Which provider is configured, and whether it can actually be used *right
now* -- never whether the last read succeeded.

**Response 200** (default, no provider configured):

```json
{"provider": "none", "available": false, "model": null}
```

Three possible `provider` values: `"none"` (the default -- CUORE runs
offline by rule; `available` is always `false`), `"claude"` (`available`
reflects whether `ANTHROPIC_API_KEY` is set server-side -- the photo is
then sent to Anthropic's Messages API over the open internet, an explicit
opt-in the owner turns on via `CUORE_VISION_PROVIDER=claude`, never the
default), `"tesseract"` (a documented hook; always `available: false`
today -- no OCR binary is wired up).

### `POST /api/vision/{vin}/read`

**Params:** `vin` (path, accepted but not used to scope the read).
**Body:** `multipart/form-data` -- `file` (the photo, required) and `hint`
(form field, required, one of `odometer | fuel_pump | oil_bottle |
part_label | receipt | other`).

**Response 200**, provider `"none"` (today's default -- this is what a
native app gets until an owner opts in to a provider):

```json
{
  "provider": "none",
  "available": false,
  "fields": {},
  "suggested_kind": null,
  "note": "Automatic reading is not set up on this CUORE. Fill in by hand."
}
```

With `CUORE_VISION_PROVIDER=claude` configured and a successful read, the
shape (per-hint field set, from `vision_bridge._FIELD_SPECS`) is:

```json
{
  "provider": "claude",
  "available": true,
  "fields": {
    "odometer_km": {"value": 142290, "confidence": 0.9, "unit": "km"}
  },
  "suggested_kind": null,
  "note": "Suggested from the photo -- confirm or correct every field before saving; this is not a car measurement."
}
```

Per-hint field names and `suggested_kind` (the taxonomy `category/kind` the
native app should pre-select, or `null` when there is no single matching
one):

| hint | fields | suggested_kind |
|---|---|---|
| `odometer` | `odometer_km` (number, km) | `null` -- goes on the event's own `odometer_km`, not a `fields` entry |
| `fuel_pump` | `litres`, `price`, `octane`, `station` | `fuel/fill_up` |
| `oil_bottle` | `brand`, `viscosity`, `qty` | `fluids/engine_oil_change` |
| `part_label` | `part`, `part_no`, `brand` | `parts_repairs_elsewhere/part_fitted_elsewhere` |
| `receipt` | `station`, `litres`, `price`, `at` | `fuel/fill_up` |
| `other` | provider's best effort, unshaped | `null` |

Each field value is `{"value": <reading or null>, "confidence": 0.0-1.0,
"unit": <ours, never the model's, or null>}` -- a native app should treat
`value: null` or low `confidence` as "show the field empty, let the human
type it," never auto-accept.

**Errors:** `400` for an unrecognised `hint` --

```json
{"detail": "hint must be one of odometer, fuel_pump, oil_bottle, part_label, receipt, other, got 'bogus'"}
```

A failed Claude call (network/HTTP error, or a non-JSON reply) is **not**
an HTTP error -- it still returns `200` with `available: false` (or
`available: true, fields: {}` for an unparseable reply) and a human-
readable `note`. A native app must branch on `available`/`fields`, not on
HTTP status, to detect "nothing to suggest."

### `fields_meta` provenance (wired 2026-10-13)

`POST /api/owner/{vin}/events` accepts an optional `fields_meta:
{<field key>: "photo" | "typed"}` alongside `fields`. The store
(`cuore.live.owner_events.add()`), the bridge and the JSON API all carry it,
validated against the kind's field keys, and `GET .../events` returns it on
each event. A native app that pre-fills a field from `POST
/api/vision/{vin}/read` stamps that key `"photo"` when the human saves; the
value is still an attested record at `confidence: "reported"` -- the marker
only remembers how the value got into the box.

---

## Attested-record semantics

Every write in this contract -- owner events, media, replies -- carries
`confidence: "reported"` (owner events) or is otherwise a human-filed
record, never a car measurement:

* `cuore.live.owner_events`: *"Every row says who said it, when, at
  confidence 'reported' -- a human claim, kept separate from, and never
  promoted into, `mes.verdict`'s evidence gate."*
* `cuore.live.media`: *"Media are attested evidence of what a technician
  saw, not a measurement the car reported... nothing here should be
  mistaken for one."*
* `cuore.services.owner_events_bridge.correlate`: correlation results are
  worded "owner-reported, possible link" -- **never** that a reported event
  *caused* a code. A native app's UI copy must preserve this distinction
  (e.g. do not render "Caused by: recent fill-up"; render "Reported around
  the same time: recent fill-up").
* A field proposed by a `POST /api/vision/{vin}/read` call (above) is
  likewise never committed as fact on its own -- it is a draft a human
  confirms, same as anything typed by hand. Once accepted, the intent is
  for the saved event to stamp `fields_meta[key] = "photo"` on that field
  (`cuore.live.owner_events`'s own provenance convention) -- **informational
  only**: a photo-read field is stored at the exact same `confidence:
  "reported"` as a typed one, `fields_meta` just remembers *how* the value
  got into the box. The JSON API accepts `fields_meta` on `POST
  /api/owner/{vin}/events` (see above), so a native app sets it directly.

The one existing pictogram/footer line every `/m/{vin}` page renders and
that a native app should preserve in spirit:

> "Everything recorded here is an ATTESTED report -- who said it, when --
> at confidence 'reported'. It is never a car measurement and never counts
> as evidence on its own."

---

## Remembered values (recents)

The web page's "Add" form pre-fills fields marked `"remember": true` in the
taxonomy (e.g. oil brand, viscosity, filter brand/part no, fuel station,
battery brand) with values typed before, this car's own history first, then
the rest of the garage's -- via `cuore.live.owner_events.recent_values(vin,
kind, field, limit=6)`.

**This is not exposed as its own `/api` route today.** It is called
directly inside `cuore/web/owner_routes.py`'s `add_form` handler, which
renders server-side HTML -- there is no JSON endpoint a native app can hit
to get the same list. A native client building its own "Add" screen either:

1. Reconstructs the same most-recent-first, de-duplicated logic client-side
   from `GET /api/owner/{vin}/events` (read this VIN's events, and if the
   feature is wanted "for the rest of the garage" too, a second vehicle's
   events), or
2. Waits for (or requests) a dedicated `GET /api/owner/{vin}/recent/{kind}/{field}`
   route that wraps `recent_values` directly.

Until then, treat "remembered values" as a **gap**, not a shipped contract
-- do not assume a route exists that isn't in the [path table](#path-table).

---

## Idempotency

**None of the write routes above are idempotent**, and none accept an
idempotency key:

* `POST /api/owner/{vin}/events` assigns a fresh 12-hex-char id
  (`uuid4().hex[:12]`, see `cuore/live/owner_events.py`) on every call. A
  retried request after a dropped response creates a **second** event.
* `POST /api/vehicles/{vin}/media` likewise mints a new id per call, even
  for byte-identical files (the `sha256` field lets a client detect this
  after the fact, but nothing on the server deduplicates before writing).
* `POST /api/owner/{vin}/messages/{id}/reply` is closer to idempotent in
  effect (replying twice just appends/overwrites the answer on the same
  message id) but is not guarded against a double-submit race.

**What a native app must do about this itself:** disable the submit control
immediately on tap, and treat a network timeout as "unknown outcome,"
surfacing a retry the person must explicitly choose -- not an automatic
retry -- since an automatic retry on a successful-but-unacknowledged POST
will file a duplicate attested record. Client-side de-dup by comparing
`(vin, category, kind, fields, note, at-within-a-few-seconds)` against the
most recent entry in `GET /api/owner/{vin}/events` after a reconnect is a
reasonable mitigation, but is a client-side workaround, not a server
guarantee.

---

## Image upload limits and HEIC note

From `cuore/live/media.py`:

* **500 MB per file** (`MAX_SIZE = 500 * 1024 * 1024`). A file over this
  raises `BadMedia`, surfaced as a `400`. There is no documented limit on
  total request size or on the number of files in one multipart upload
  beyond that per-file cap.
* **Allowed mime types** (`ALLOWED_MIMES`):

  | mime | kind | stored extension |
  |---|---|---|
  | `image/jpeg` | photo | `.jpg` |
  | `image/png` | photo | `.png` |
  | `image/webp` | photo | `.webp` |
  | `image/heic` | photo | `.heic` |
  | `application/pdf` | scan | `.pdf` |
  | `video/mp4` | video | `.mp4` |
  | `video/webm` | video | `.webm` |
  | `video/quicktime` | video | `.mov` |
  | `audio/mpeg` | audio | `.mp3` |
  | `audio/mp4` | audio | `.m4a` |
  | `audio/wav`, `audio/x-wav` | audio | `.wav` |
  | `audio/ogg` | audio | `.ogg` |
  | `audio/webm` | audio | `.webm` |
  | `audio/aac` | audio | `.aac` |

  Anything else -> `400 unsupported mime type`.

* **HEIC note:** `image/heic` is **already a first-class, directly accepted
  format** (`ALLOWED_MIMES["image/heic"] -> ("photo", "heic")`). A native
  iOS app that captures photos with `PHPickerViewController`/`UIImagePickerController`
  in its native HEIC output does **not** need to transcode to JPEG before
  upload -- send the HEIC bytes with `Content-Type: image/heic` as-is.
  (Thumbnailing is EXIF-rotation-aware for photos generally; nothing in the
  media module special-cases HEIC thumbnailing beyond that, so verify a
  HEIC thumbnail renders correctly once this is exercised against a real
  device capture, not just the synthetic bytes this document's own checks
  use.)

---

## Native-only features

Capabilities that belong on the native app, not the web page, per
`docs/handbook/06-roadmap.md`: *"Features that need the phone itself
(Location Services for the station, background capture, a 'pull up to the
pump' shortcut, push for messages) belong to the native app; nothing in the
web surface should block that, so all logic stays server-side behind the
API and the page keeps no state of its own."*

1. **Location Services -> station field.** The `fuel` category's kinds
   carry a `station` text field (`"remember": true`). A native app can
   resolve the device's current location (reverse-geocode or a known-POI
   lookup) and pre-fill `station` in the `POST /api/owner/{vin}/events`
   body -- the server has no geolocation capability of its own and never
   will (LAN-only, offline-first design), so this is purely a client-side
   enrichment of an existing field, not a new endpoint.
2. **Camera capture -> `/api/vision` read.** `POST /api/vision/{vin}/read`
   (see [Vision](#vision)) is live: a native app's camera capture button is
   the natural trigger -- snap a photo of the odometer/pump/oil bottle,
   call the vision endpoint with a `hint`, show the proposed fields for
   confirmation, then save via `POST /api/owner/{vin}/events` (optionally
   also keeping the photo as evidence via `POST
   /api/vehicles/{vin}/media`). The web page has no camera API to call from
   a browser form in the same way, so this is a genuinely native-only
   interaction even though the underlying write path is identical. Remember
   the provider is `"none"` (unavailable) until the owner explicitly
   configures `CUORE_VISION_PROVIDER` server-side -- design the capture
   flow so "nothing was read, fill in by hand" is a normal, expected
   outcome, not an error state.
3. **Push for `/api/owner` messages.** `GET /api/owner/{vin}/messages`
   returns CUORE's and the mechanic's open questions, but there is no
   server-side push subscription (no APNs device-token registration route
   exists in this contract). A native app wanting push notifications for
   new messages must either poll this endpoint periodically or -- if this
   is wanted -- a new route to register a device token would need to be
   added server-side first; it is not part of today's contract and should
   not be assumed.
