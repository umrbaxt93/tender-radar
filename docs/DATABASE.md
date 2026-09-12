# Database implementation contract

Schema source of truth: `radar/models.py`, applied by Alembic revision `0001` (see
`alembic/versions/`). The planned tables in docs/SPEC.md are implemented with two additions:

- `procedure` is unique on `(source, source_id)` rather than `source_id` alone, so synthetic
  and real rows cannot collide.
- `ai_cost_ledger` implements the durable cross-run cost ledger required by DECISIONS.md: a
  reservation row is written before an AI call and settled with actual token usage afterwards.

Indexes: `organization.stir` (unique), `procedure.completed_at`, `classification.category`,
`renewal_opportunity.contact_by_at`, and a pg_trgm GIN index on `organization_alias.name_raw`.
The migration creates the `pg_trgm` extension, which requires a superuser or a managed
PostgreSQL that pre-enables it.

Production needs durable cloud PostgreSQL 16, encrypted access and backups. CI's postgres
service is disposable test infrastructure only. Do not import a real historical dataset into
CI service storage.

Verified so far (2026-09-12, local PostgreSQL 16.13): `alembic upgrade head` → `downgrade base`
→ `upgrade head` round trip, unique source ids, idempotent upserts with no duplicate
organizations or lot items, raw snapshot checksum round trip, and resume after a simulated
crash mid-page. Renewal recomputation and transaction boundaries for classification are not
implemented yet.
