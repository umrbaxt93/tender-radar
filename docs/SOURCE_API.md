# Source API contract

STATUS: UNVERIFIED — no request to xarid.uzex.uz has been made or reproduced.

Outbound access to xarid.uzex.uz was blocked by the development environment's network policy
(HTTP CONNECT refused, 2026-09-12), so neither the list nor the detail endpoint could be
confirmed. No endpoint, lot identifier, pagination rule or sample response in this repository
is real. `radar/source/uzex_mapping.yaml` documents the *assumed* JSON shape and is the single
place to change once sanitized real responses exist.

Before any live import, record here: public origin, list/detail endpoint, HTTP method,
sanitized headers, query/body, pagination, status semantics, date/currency/amount formats, lot
and customer identifiers, availability of awards, rate-limit evidence and fixture provenance.
Strip Authorization, Cookie, token parameters and personal data before committing anything.
Stop at login, E-IMZO, 403 or CAPTCHA; bypassing them is out of scope permanently.

## Implemented client behaviour (radar/source/client.py)
- One request per 3 s plus 0–1 s jitter, single worker, `User-Agent` carries `CONTACT_EMAIL`.
- 429 and 5xx: backoff 10 → 20 → 40 → 80 → 160 s.
- Five consecutive failures raise `SourcePaused`; the importer commits its cursor and exits
  instead of sleeping 30 minutes.
- 401/403, any redirect, or a non-JSON login/CAPTCHA body raises `SourceBlocked` and stops
  collection. No bypass path exists in the code.
- `UZEX_LIST_URL` / `UZEX_DETAIL_URL` are unset by default, so a live import cannot start by
  accident.

## Synthetic fixtures
`samples/synthetic/` holds generated fixtures (`scripts/gen_synthetic_fixtures.py`). Every file
carries `"synthetic": true`, every lot id starts with `SYN-`, every customer name contains
`(SYNTHETIC)`. Rows imported from fixtures are stored with `procedure.source = 'synthetic'`,
never `'uzex'`, so synthetic and real data can never be confused in the database.
