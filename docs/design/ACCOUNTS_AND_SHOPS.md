# Accounts, roles and shop separation (design)

Status: accounts and roles are built (`cuore/services/accounts.py`, `/accounts`).
Shop separation of data is design only; no existing data is migrated.

## What exists now
- `<state_dir>/accounts.json`: users (username, display_name, role, shop_id, shop_kind,
  scrypt hash + salt, created_at, disabled) and `accounts_enabled`.
- Mode is on only when the switch is true AND an enabled admin exists; otherwise the
  shared token behaves exactly as before. The shared token (header or token cookie)
  stays the machine/MCP path with full access, in either mode.
- Roles: `admin` (everything, resets passwords), `shop_lead` (manages technicians of
  own shop, accepts PROXI/procedure candidates), `technician` (everything else).
- Records written by a logged-in user (note, feedback and media authors) carry the
  username instead of the free-text author.

## Per-shop (would carry `shop_id`)
Everything a shop generates about its own customers and cars:
- vehicles/dossiers keyed by VIN, jobs, job actions/evidence/hypotheses, notes,
  feedback, media, scan archives, recordings, symptoms, dealer results, tool inventory;
- procedure acceptances (an acceptance is a shop-lead decision; the record already has
  `by`, add `shop_id`);
- learned/accepted PROXI, DID and responder mappings (start per-shop; promote to global
  only through an explicit admin "publish" step).

Mechanism: each new record gets `shop_id` from the logged-in user (`request.state.user`)
or the configured default shop for token/machine writes. Reads filter by the user's
`shop_id`; admin and the machine token see all shops. Storage stays one state dir, one
file tree, with `shop_id` as a field (and a per-shop subfolder for large artefacts such
as media and recordings). Migration later: stamp existing records with the default
shop id in a one-off, reversible script run by the owner.

A VIN touched by two shops stays two separate records; no cross-shop merge.

## Global (shared, read-only to shops)
Procedures and their sources, TSB and bulletin data, the parts catalogue, DTC
descriptions, wiring/electrical reference, fault trees, brand/marque data, the
tool knowledge base, experience links. These ship with CUORE releases (the update
channel), not per shop. Shop edits to global content go through feedback to the
maintainer, not in place.

## Dealer vs independent
`shop_kind` is metadata for now (which bulletins and dealer-result screens to show).
It does not change permissions.

## Open decisions
- Whether a shop_lead may promote a learned mapping to global (proposed: no, admin only).
- Per-shop token for each shop's MCP servers (proposed: yes, one token per shop id,
  stored beside accounts.json) so machine writes get a shop_id too.
- Password reset by email is out of scope; reset is admin or CLI only.
