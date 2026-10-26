# Review and findings, 2026-10-25

## Chrome review of the fuse page
- The interior fuse box was drawn on the wrong side of the car.
- The rear cluster of fuses piled up on top of each other.
- There was no call-out (leader line) tying a fuse to its position.
- Admin text appeared in the part of the page a mechanic reads.
- Tap targets were small.
- The deep link to a specific fuse was broken.
The agreed changes are in `fuse_page_spec.md`.

## Direction from the owner
CUORE is the source of truth. The mechanic does not enter data; the page must show what CUORE already knows.

## Harness diagram limits
The Mopar harness diagrams are exploded parts drawings. They give areas only: no pins, no wire colours, no connectors. They cannot support circuit-level paths on their own.

## Official manual access
The official owner's manual sites refused automated reading (HTTP 403: alfaromeousa.com, mopar.com and others; alfaromeo.ca 404; a Fiat service site 503). Only third-party fuse tables could be read (`fuse_tables_third_party.md`). Official manual extraction: pending.

## Open gaps
- Engine-bay fuse box list
- Rear power box list
- Relays
- Slot layouts (physical positions in each box)
- The overhang split is not published
