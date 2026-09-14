STATUS: APPLICATION_DEVELOPMENT — T1 verified on live source; ready for real import slice
Updated: 2026-09-14

The full chain runs end to end in one process: import → classify → renewal → export, plus a
`/radar` page, snapshot re-parsing and a deployment runbook.
T1 (source verification) is completed: `xarid.uzex.uz` public API is verified, sanitized fixtures
saved under `samples/uzex/`, `docs/SOURCE_API.md` filled, and `uzex_mapping.yaml` adjusted.
`ebirja.uz` was verified to require E-IMZO authentication, and is documented for operator file
export (T2).
All 140 pytest tests pass on local PostgreSQL 16 (0 skipped).

## Scaffold (complete)
- DONE: specification recovery, shared agent rules, bounded review automation.
- DONE: private GitHub repository with scaffold on main; hosted checks green.
  Evidence: https://github.com/umrbaxt93/tender-radar/actions/runs/34721019584
- DONE: authenticated Gemini review in hosted Agent supervisor #4.
  Evidence: https://github.com/umrbaxt93/tender-radar/actions/runs/34721923727
- PENDING: Claude/Codex credentials; fallback integration untested.
- PENDING: provider spending controls before any recurring paid review; schedule off.

## Application execution order
1. DONE: Alembic schema and models; migrations 0001 and 0002 round trip cleanly.
2. DONE: T1 Source contract verified against live public xarid.uzex.uz API (POST /Common/GetCompetitions, GET /Common/GetCompetition/{id}). Sanitized real fixtures saved under samples/uzex/. Mapping in radar/source/uzex_mapping.yaml adjusted. Parser tests pass on both synthetic and real samples. ebirja.uz confirmed login-only (requires E-IMZO); designated for file import.
3. DONE: resumable 500-lot import with verified counts (tested on synthetic fixtures).
4. DONE: 5000-lot import and consistency checks.
5. DONE: rules and model classification, cache, text deduplication, durable $10 ledger.
   Proven with the offline mock model; no paid call has been made.
6. DONE: renewal computation, Excel export, /radar page.
7. BLOCKED: 90-day real backfill into durable cloud storage. Needs source access and a
   managed database. The runbook for that host is written (docs/DEPLOYMENT.md, unexecuted).
8. DONE for the implemented surface: 140 pytest tests pass (0 skipped), ruff clean, validate clean.
9. TODO: verified final report against real data, and the phase-2 backlog.

## Launch readiness
- DONE: Dockerfile and a full-stack docker-compose (database, migrations, worker, web),
  validated with `docker compose config`. Never built here: no Docker daemon in this
  environment.
- DONE: scripts/bootstrap.sh, run end to end on this machine: virtualenv, .env, migrations,
  a synthetic cycle and stats.
- DONE: systemd units for the web and worker processes and an nginx example that keeps the
  app behind TLS and basic auth.
- DONE: the platform was run here as two long-lived processes, worker on an interval and web
  on 127.0.0.1:8000, with /health returning ok and /radar serving. The worker completed a
  second scheduled cycle on time, and SIGTERM while idle stopped it in one second without
  starting another cycle.
- BLOCKED: a real launch on a real host. No host, no verified source contract, and external
  deployment is outside what this phase authorizes.

## Beyond the original order
- DONE: `reparse` rebuilds every row from stored snapshots with checksum verification and no
  network access, which is what makes the raw_snapshot requirement useful.
- DONE: organization identity by STIR, then exact case-insensitive alias, then a strict
  trigram match that never merges organizations which already carry a STIR.
- DONE: coverage metrics (completion date, customer, amount, award, quantity) in `stats` and
  in the Excel Stats sheet, so a thin dataset cannot masquerade as a full one.
- DONE: `worker.py`, one process running one ordered cycle, optionally on an interval,
  finishing the cycle in flight when it receives a signal.

## Verified runs (local PostgreSQL 16.13, 2026-09-13)

| Run | Result |
|---|---|
| Migrations | upgrade → downgrade → upgrade across 0001 and 0002, clean |
| Tests | 137 pytest tests; 15 orchestration tests; ruff clean; validation clean |
| Import 500 synthetic lots | 10 pages, 500 inserted, 0 duplicates, 4.6 s |
| Import 5000 synthetic lots | 100 pages, 5000 inserted, 0 duplicate source ids, 40 s |
| Staged resume | 1000 → 1500 → 2500 across three runs, 5000 rows, 5000 distinct ids |
| Worker cycle at 5000 lots | 4614 rule, 386 model, 1321 renewals, 340 radar rows, one command |
| Classifier cost | $0.001485 at mock prices; cache reuse costs $0; budget stop verified |
| Reparse 5000 lots | 5000 rebuilt from snapshots, 0 checksum failures, no refetch |
| Coverage at 5000 lots | completion 100%, customer 100%, amount 100%, award 79.2% |
| Web | /health ok; /radar renders with a synthetic-data banner, light, dark and mobile |

## Commands
```
make install
export DATABASE_URL=postgresql://tender:PASSWORD@localhost:5432/tender_radar
make demo                                              # end to end, offline, free
make worker ARGS="--fixtures samples/synthetic --mock-ai"
make reparse                                           # rebuild from snapshots
make web test lint validate
```

## What still blocks Definition of Done
- A verified public endpoint contract and sanitized real fixtures.
- At least 90 days of real completed lots imported, resumable, without duplicates.
- One real classification run inside the $10 cap with a reviewed model price.
- A managed PostgreSQL host; docs/DEPLOYMENT.md has never been executed.
