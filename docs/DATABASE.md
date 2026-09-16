# Database implementation contract

Schema source of truth: `radar/models.py`, applied by Alembic revision `0001` (see
`alembic/versions/`). The planned tables in docs/SPEC.md are implemented with two additions:

- `procedure` is unique on `(source, source_id)` rather than `source_id` alone, so synthetic
  and real rows cannot collide.
- `ai_cost_ledger` implements the durable cross-run cost ledger required by DECISIONS.md: a
  reservation row is written before an AI call and settled with actual token usage afterwards.

Indexes: `organization.stir` (unique), `procedure.completed_at`, `classification.category`,
`renewal_opportunity.contact_by_at`, and pg_trgm GIN indexes on `organization_alias.name_raw`
and, from migration `0002`, on `lower(name_raw)`, which is the expression alias matching
actually compares. Migration `0001` creates the `pg_trgm` extension, which requires a superuser
or a managed PostgreSQL that pre-enables it.

## Organization identity
STIR is the identity when present. Without one, an exact case-insensitive alias match is used,
and only then a trigram match above `ORG_MATCH_THRESHOLD` (default 0.92). Organizations that
already carry a STIR are never fuzzy-merged: keeping a duplicate is recoverable, merging two
real customers corrupts the purchase history the Radar is built on. Every distinct spelling is
kept in `organization_alias`.

Production needs durable cloud PostgreSQL 16, encrypted access and backups. CI's postgres
service is disposable test infrastructure only. Do not import a real historical dataset into
CI service storage.

Verified (2026-09-13, local PostgreSQL 16.13): `upgrade head` → `downgrade base` →
`upgrade head` across both revisions; unique source ids; idempotent upserts with no duplicate
organizations or lot items; raw snapshot checksum round trip; resume after a simulated crash
mid-page; idempotent renewal recomputation; and `reparse` rebuilding every row from snapshots
with no refetch and no new rows. A tampered snapshot is reported as a checksum failure and
skipped rather than reparsed.
