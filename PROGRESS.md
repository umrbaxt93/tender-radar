STATUS: APPLICATION_DEVELOPMENT — stage 1 partially complete
Updated: 2026-09-12

No real procurement data has been imported. Every row currently produceable comes from
labelled synthetic fixtures. STATUS: DONE stays reserved for the independently verified
application Definition of Done in docs/SPEC.md.

## Scaffold (complete)
- DONE: recover original MVP specification.
- DONE: shared agent rules, infrastructure and bounded review automation.
- DONE: private GitHub repository umrbaxt93/tender-radar with scaffold on main.
- DONE: hosted Scaffold checks #1 passed (15 orchestration tests, validation, PostgreSQL).
  Evidence: https://github.com/umrbaxt93/tender-radar/actions/runs/34721019584
- DONE: authenticated Gemini review passed in hosted Agent supervisor #4, 2026-09-13.
  Evidence: https://github.com/umrbaxt93/tender-radar/actions/runs/34721923727
- PENDING: Claude/Codex credentials; fallback integration remains untested.
- PENDING: provider spending controls before enabling recurring paid reviews; schedule off.

## Application execution order
1. PARTIAL: Alembic schema, SQLAlchemy models, parser, resumable importer and CLI.
   Verified locally on PostgreSQL 16.13 (2026-09-12):
   - `alembic upgrade head` / `downgrade base` / `upgrade head` round trip clean.
   - 12 pytest tests pass; `ruff check radar tests scripts` clean.
   - `python -m radar import --fixtures samples/synthetic` imported 12 synthetic lots,
     13 raw snapshots, 12 organizations; re-running inserts nothing; forced refresh updates
     12 rows and creates no duplicate procedures, organizations, lot items or snapshots.
   - Simulated crash mid-page rolls the page back, leaves the cursor at the last committed
     page, and a resume run completes the import.
   Not done in this stage: classify, renewal, export and web CLI subcommands have no
   implementation modules yet, so `make classify renewal export web` exit 2 by design.
2. TODO: obtain sanitized public list/detail fixtures and verify the parser against them.
   BLOCKED: outbound access to xarid.uzex.uz is refused by the environment network policy,
   so the endpoint contract in docs/SOURCE_API.md is still UNVERIFIED.
3. TODO: resumable 500-lot import with verified counts (synthetic first, then real).
4. TODO: 5000-lot import and consistency checks.
5. TODO: rules + Gemini classification, cache and durable $10 budget ledger
   (`ai_cost_ledger` table exists; the classifier does not).
6. TODO: renewal calculation, Excel export and /radar.
7. TODO: 90-day backfill into durable cloud storage.
8. TODO: full application tests and ruff across the finished feature set.
9. TODO: verified final report and phase-2 backlog.

## Verified commands
```
make install
make migrate                 # DATABASE_URL required
make import-synthetic        # labelled synthetic fixtures only
make stats
make test                    # TEST_DATABASE_URL required, else database tests skip
make lint
make validate                # offline repository checks
```
