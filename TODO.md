# TODO

## Blocked on source access
- [ ] Verify the public list/detail endpoint contract from a network that can reach
      xarid.uzex.uz, fill docs/SOURCE_API.md, adjust radar/source/uzex_mapping.yaml.
- [ ] Commit sanitized real fixtures and replace the synthetic golden set in
      samples/synthetic/known_lots.md with 5 verified IT and 5 verified non-IT lots.
- [ ] Import 90 days of real completed lots, then re-measure rule coverage, AI spend and the
      coverage percentages reported by `stats`.
- [ ] Re-check the renewal lifecycle table against what real purchase intervals show.

## Blocked on credentials or cost approval
- [ ] Add the chosen Gemini model price to radar/classify/pricing.yaml from the official
      pricing page, with the date it was checked.
- [ ] Run one small paid batch and compare real spend against the ledger.
- [ ] Provider-side spending controls before enabling any recurring paid job.

## Blocked on a host
- [ ] Build the image and run `docker compose up -d --build` on a real machine. The compose
      file validates but has never been built: no Docker daemon here.
- [ ] Execute docs/DEPLOYMENT.md end to end on the target host, then correct it from what
      actually happened.
- [ ] Put the reverse proxy and an access control in front of the web process before it is
      reachable from anywhere but localhost. The application has no authentication.
- [ ] Nightly pg_dump off the host, and a tested restore.

## Open code work
- [ ] Parent organization relationships, so a ministry and its subordinate bodies can be read
      as one customer where that is the right view.
- [ ] Product normalization to brand, model and licence term, which price analysis depends on.
- [ ] Supplier side analysis once award data proves rich enough to support it.

## Phase 2
Bitrix24 lead and task creation for high scores with idempotent sync and a feedback loop back
into scoring, category to manager mapping, daily import and alerts, competitor and price
intelligence. None of this is authorized in the current phase.
