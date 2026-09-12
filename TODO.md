# TODO

## Cloud setup
- [x] Create private GitHub repository umrbaxt93/tender-radar.
- [x] Publish scaffold and verify Actions checks (#1, success).
- [x] Configure the Gemini secret and model in the agent-review environment.
- [ ] Set provider-side spending controls before any recurring paid review.
- [ ] Enable the scheduled review only after those controls exist. Currently off.

## Application — next steps
- [ ] Verify the public list/detail endpoint contract from a network that can reach
      xarid.uzex.uz, then fill docs/SOURCE_API.md and adjust radar/source/uzex_mapping.yaml.
      BLOCKED here by the environment network policy.
- [ ] Collect 5 verified IT and 5 verified non-IT lots as a labelled golden set.
- [ ] Rules classifier (radar/classify/rules.py + keywords.yaml) with Uzbek-Latin,
      Uzbek-Cyrillic and Russian keywords; `no` never reaches the AI.
- [ ] Gemini classifier with JSON schema, sha256 cache, ~20 lot batches, token logging and a
      reservation-before-call cost ledger. Prove the $10 stop with a mocked model first.
- [ ] Renewal computation with month-end clamping and explicit tests for missing dates.
- [ ] Excel export (Radar, IT_Lots, Stats) and the FastAPI /radar and /health endpoints.
- [ ] 500 then 5000 lot staged imports with verified counts.

## Phase 2
Bitrix24 lead/task creation for high scores with idempotent sync and a feedback loop back into
scoring, category to manager mapping, daily import and alerts, competitor and price
intelligence, durable cloud deployment. None of this is authorized in the current phase.
