# TODO

## Blocked on source access
- [ ] Verify the public list/detail endpoint contract from a network that can reach
      xarid.uzex.uz, fill docs/SOURCE_API.md, adjust radar/source/uzex_mapping.yaml.
- [ ] Commit sanitized real fixtures and replace the synthetic golden set in
      samples/synthetic/known_lots.md with 5 verified IT and 5 verified non-IT lots.
- [ ] Import 90 days of real completed lots, then re-measure rule coverage and AI spend.

## Blocked on credentials or cost approval
- [ ] Add the chosen Gemini model price to radar/classify/pricing.yaml from the official
      pricing page, with the date it was checked.
- [ ] Run one small paid classification batch and compare real spend against the ledger.
- [ ] Provider-side spending controls before enabling any recurring paid job.

## Next in code
- [ ] Re-parse command that rebuilds classifications from raw_snapshot without re-fetching.
- [ ] Organization deduplication beyond STIR: parent organizations and pg_trgm alias matching.
- [ ] Coverage metrics: share of lots with an award, with quantity, and unparseable rows.
- [ ] Durable managed PostgreSQL, backups and a deployment runbook.

## Phase 2
Bitrix24 lead and task creation for high scores with idempotent sync and a feedback loop back
into scoring, category to manager mapping, daily import and alerts, competitor and price
intelligence. None of this is authorized in the current phase.
