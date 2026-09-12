STATUS: SCAFFOLD_READY
Updated: 2026-09-13

## Scaffold
- DONE: recover original MVP specification.
- DONE: prepare shared agent rules, infrastructure and bounded review automation.
- DONE: create private GitHub repository umrbaxt93/tender-radar.
- DONE: publish all scaffold files and GitHub Actions workflows to main.
- DONE: hosted Scaffold checks #1 passed (15 orchestration tests, scaffold validation, PostgreSQL SELECT 1); duration 24s.
  Evidence: https://github.com/umrbaxt93/tender-radar/actions/runs/34721019584 (tested commit ce3fe3ae196676249629a433a9c60f072f6c77de).
- PENDING: provider environment secrets, chosen model IDs and spending controls.
- PENDING: authenticated provider smoke run; schedule disabled until verified.

## Application execution order — not started
1. TODO: Alembic schema/models and working up/migrate.
2. TODO: obtain sanitized public list/detail fixtures and verify parser.
3. TODO: resumable 500-lot import with verified counts.
4. TODO: 5000-lot import and consistency checks.
5. TODO: rules + Gemini classification, cache and durable $10 budget ledger.
6. TODO: renewal calculation, Excel export and /radar.
7. TODO: 90-day backfill into durable cloud storage.
8. TODO: full application tests and ruff.
9. TODO: verified final report and phase-2 backlog.

STATUS: DONE is reserved for independently verified application acceptance criteria.
