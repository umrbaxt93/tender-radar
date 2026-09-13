STATUS: APPLICATION_DEVELOPMENT — pipeline complete on synthetic data, source unverified
Updated: 2026-09-13

The full chain import → classify → renewal → export → /radar runs end to end. It has **not**
been run against real procurement data: outbound access to xarid.uzex.uz is refused by the
environment network policy, so docs/SOURCE_API.md is still UNVERIFIED and every row produced
so far comes from labelled synthetic fixtures. STATUS: DONE stays reserved for the
independently verified Definition of Done in docs/SPEC.md, which requires real imported lots.

## Scaffold (complete)
- DONE: recover original MVP specification; shared agent rules; bounded review automation.
- DONE: private GitHub repository umrbaxt93/tender-radar with scaffold on main.
- DONE: hosted checks passed. Evidence:
  https://github.com/umrbaxt93/tender-radar/actions/runs/34721019584
- DONE: authenticated Gemini review passed in hosted Agent supervisor #4. Evidence:
  https://github.com/umrbaxt93/tender-radar/actions/runs/34721923727
- PENDING: Claude/Codex credentials; fallback integration remains untested.
- PENDING: provider spending controls before enabling recurring paid reviews; schedule off.

## Application execution order
1. DONE: Alembic schema, SQLAlchemy models; `migrate` works, up/down/up round trip clean.
2. PARTIAL: parser verified against synthetic fixtures only.
   BLOCKED: no network access to the source, so the real endpoint contract is unverified and
   no sanitized real fixture exists. The parser is mapping-driven so verifying it later
   changes radar/source/uzex_mapping.yaml, not code.
3. DONE: resumable 500-lot import with verified counts (synthetic).
4. DONE: 5000-lot import and consistency checks (synthetic).
5. DONE: rules + model classification, cache, text deduplication and the durable $10 budget
   ledger. Proven with the offline mock model; no paid call has been made.
6. DONE: renewal computation, Excel export and the /radar page.
7. BLOCKED: 90-day real backfill into durable cloud storage. Needs source access and a
   managed database.
8. DONE for the implemented surface: 117 pytest tests pass, ruff clean.
9. TODO: verified final report against real data, and the phase-2 backlog.

## Verified runs (local PostgreSQL 16.13, 2026-09-13)

| Run | Result |
|---|---|
| Migration | `upgrade head` → `downgrade base` → `upgrade head` clean |
| Tests | 117 pytest tests pass; 15 orchestration tests; ruff clean; validation clean |
| Import 500 synthetic lots | 10 pages, 500 inserted, 0 duplicates, 4.6 s |
| Import 5000 synthetic lots | 100 pages, 5000 inserted, 0 duplicate source ids, 40 s |
| Staged resume | 1000 → 1500 → 2500 across three runs, 5000 rows, 5000 distinct ids |
| Classify 5000 lots | 4614 by rule (2012 non-IT), 386 by model, 381 deduplicated, 1 batch |
| Classifier cost | $0.001485 at mock-model prices; cache reuse costs $0 |
| Renewal | 1321 opportunities; recomputation is idempotent |
| Export | out/renewal_radar.xlsx, 339 radar rows, sheets Radar / IT_Lots / Stats |
| Web | /health returns ok; /radar renders rows with a synthetic-data banner |

## Commands
```
make install
export DATABASE_URL=postgresql://tender:PASSWORD@localhost:5432/tender_radar
make demo      # migrate, synthetic import, mock classify, renewal, export, stats
make web       # /radar and /health
make test lint validate
```

## What still blocks Definition of Done
- Verified public endpoint contract and sanitized real fixtures.
- At least 90 days of real completed lots imported, resumable, without duplicates.
- A real (not mock) classification run inside the $10 cap, with a reviewed model price.
- Durable managed PostgreSQL for anything beyond local development.
