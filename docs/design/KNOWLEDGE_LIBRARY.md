# Knowledge library (design, 2026-10-30)

Purpose: when the owner downloads manufacturer service information (TechAuthority, North America; stellantisiop.com, Europe), corporate's answers, or wiTECH recordings, CUORE keeps the originals, extracts small sourced facts, and shows each fact on the page where the mechanic's question arises, with a source line.

## Three layers

1. **Originals** `<state_dir>/library/<source>/<YYYY-MM-DD>/` -- downloaded PDFs/pages unchanged, plus one SOURCES record per file (`<file>.source.json`).
2. **Extracted facts** `<state_dir>/knowledge/<platform>/<kind>.json` -- platform e.g. `949`, `952`. One JSON list per kind.
3. **CUORE working data** (procedures, tsb_catalogue, proxi map, parts) updated from layer 2 with `source_kind: "manufacturer"`.

`state_dir` is `cuore/live/config.py state_dir()` (default `C:\ProgramData\cuore`, override `CUORE_STATE_DIR`).

## Folder layout

```
<state_dir>/
  library/techauthority/2026-11-02/AC-Pump-R-and-R.pdf
                                   AC-Pump-R-and-R.pdf.source.json
  library/stellantisiop/2026-11-05/...
  knowledge/949/test_steps.json  specs.json  pinouts.json  fuse_maps.json  locations.json
                 procedures.json part_fitment.json torque.json fluids.json proxi_map.json bulletins.json
                 module_dids.json routines.json dtc_defs.json dbc.json      (corporate data)
```
Folders are created only when a document is registered. A missing library is an empty index.

## SOURCES record

```json
{
  "doc_id": "3f9a1c0b7d22",
  "file": "AC-Pump-R-and-R.pdf",
  "title": "A/C compressor, removal and installation",
  "doc_no": "08-0012",
  "source": "techauthority",
  "url": "https://techauthority.example/doc/08-0012",
  "licence": "Subscription service information; internal shop use only",
  "retrieved": "2026-11-02",
  "sha256": "<64 hex>",
  "bytes": 482113
}
```
`doc_id` is the first 12 hex of the SHA-256. Re-registering the same file updates the record (blank fields keep their old values).

## Fact provenance

Every fact carries its provenance; a fact's `source_doc_id` is the SOURCES `doc_id` or `doc_no`.

```json
{
  "dtc": "P0171",
  "step": 3,
  "text": "Measure fuel pressure at the rail; specification 3.8 bar at idle.",
  "source_doc_id": "08-0012",
  "section": "4.2",
  "page": 17,
  "retrieved": "2026-11-02",
  "extracted_by": "owner-manual-entry | script:<name>@<version>",
  "confidence": "verbatim | paraphrased | inferred"
}
```
Template line: `Source: techauthority, A/C compressor, removal and installation 08-0012 §4.2, retrieved 2026-11-02` (`library.source_line(fact)`, also `services/provenance.py`).

## Precedence

`manufacturer` > `mes_display` > `forum`. A manufacturer fact replaces the lower-ranked value on the page; the lower value remains visible as "also reported" only when it disagrees.

## Where it shows

| Page | Shows | Fact kind |
|---|---|---|
| Codes | test steps per DTC; definitions | test_steps, dtc_defs |
| Electrical / Harnesses | pinouts | pinouts |
| Sensors / Systems | locations | locations |
| Fuses | fuse maps | fuse_maps |
| Adjustments | procedures | procedures, routines |
| Configuration | PROXI meanings | proxi_map |
| Parts | R&R, torque, tools, fluids, fitment | part_fitment, torque, fluids |
| TSB / Job / Arrive-ready / Warranty pack | bulletins | bulletins |
| Facts | specifications | specs |
| Modules / Live | DIDs; CAN signals | module_dids, dbc |

`/library` lists every document (search by title, document number, code, part) with "used on these pages" links, built from the same kind-to-page map (`KIND_PAGES` in `services/library.py`).

## Privacy and licensing

Originals and facts live only under `state_dir`: never in git, never republished, never uploaded. Anywhere CUORE shows a fact it cites title + document number + retrieval date, and shows only the short extract needed for the job, not the document.

## Corporate data

UDS specifications, ODX/CDD and DBC files arrive as layer-1 originals, registered like any document. Extraction produces layer-2 kinds: `module_dids` (per module DID id, name, length, scaling), `routines` (routine ids, preconditions, results), `dtc_defs` (code, text, set conditions), `dbc` (message/signal definitions). Writes still require a documented manufacturer procedure; these kinds inform reads and display only until the owner authorizes otherwise.

## CLI

```
python -m cuore.library register <file> --source techauthority --title "..." --doc-no 08-0012 --url https://...
python -m cuore.library index
```
`register` copies nothing: the file must already sit under `library/<source>/<date>/`.
