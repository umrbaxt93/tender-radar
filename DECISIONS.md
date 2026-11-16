# Decisions

2026-09-13 | Latest user instruction overrides the historical local setup: GitLab private repository and cloud CI; no local tool installation, local cron or local database startup.
2026-09-13 | Preserve the attachment's original MVP spec verbatim, with a clearly separated cloud amendment. Current phase is scaffold/automation only.
2026-09-13 | CI agents review supplied text and return artifacts only. No application implementation, GitLab write token, automatic commit, MR, merge or deployment in the agent job. Future implementation requires a separate task and reviewed workflow change.
2026-09-13 | One pass Gemini → Claude → Codex; skip unconfigured providers; stop after first success. Maximum 180 seconds per provider and 15 minutes per job, no job auto-retry. Missing/invalid output counts as failure; text mentioning quotas in a successful report does not.
2026-09-13 | CLI versions pinned from official npm registry: Gemini 0.59.0, Claude Code 2.1.270, Codex 0.154.0. Node 22 cloud tooling satisfies Claude's current >=22 requirement. Application Python remains 3.12.
2026-09-13 | No model ID or price is guessed. Set an available economical model for each configured provider. Timeouts and Claude's $0.25 per-run guard are not an aggregate dollar guarantee; provider-side controls are required before scheduled spending.
2026-09-13 | GitLab secrets are protected masked/hidden FILE variables scoped to agent-review. They are passed as values only to the relevant child CLI. No .env is created or committed. No account auth cache is copied from the user's machine.
2026-09-13 | Source fixtures were not present in the attachment. Keep their absence explicit; do not invent lot IDs/endpoints/real rows. Acquire public sanitized fixtures in the later implementation phase.
2026-09-13 | Resolve rate-limit ambiguity conservatively: jitter is 3–4 seconds, never 2 seconds. 403/CAPTCHA stops collection; after exhausted backoff persist cursor and exit rather than sleeping 30 minutes inside a paid CI job.
2026-09-13 | Calendar month addition must clamp month-end dates. Score time buckets are exclusive; the original weights top out at 75. Preserve weights and report the true 0–75 reachable range rather than silently normalizing to 100. Renewal-window selection and missing dates need explicit tests in the future implementation task.
2026-09-13 | The classifier's $10 cap is separate from agent development spend. A durable cross-run cost ledger must reserve estimated cost before calls. Runtime model listing alone does not provide prices; use reviewed model/pricing configuration.
2026-09-13 | Create a GitLab-native two-hour schedule inactive until smoke verification and provider controls exist. No desktop heartbeat or machine cron. A completion flag in PROGRESS.md stops provider calls. A cache avoids unchanged scheduled reviews when available, but is not a billing control.
2026-09-13 | Telegram is deferred: no bot credentials or destination were supplied; no Telegram delivery is claimed. Use GitLab pipeline/artifact status now.

2026-09-13 | User switched destination to GitHub. Earlier GitLab decisions are historical and superseded for this repository by docs/CLOUD_WORKFLOW.md. Private repository created as umrbaxt93/tender-radar.
2026-09-13 | GitHub adapter uses Gemini/Claude CLI then official openai/codex-action for Codex. No GitLab secrets, token or runner required. GitHub Actions secrets are scoped to agent-review; schedule gated by ENABLE_AGENT_SCHEDULE, initially off. GitHub adapter does not use the historical cache deduplication.

2026-09-13 | Browser bulk upload completed staging but commit returned HTTP failure; repository remained empty. Switched to GitHub file editor to establish main before retrying grouped uploads.

2026-09-13 | Recovery succeeded: initialized main using GitHub file editor, then committed grouped uploads. Hosted Scaffold checks #1 passed in 24s; no provider credentials or scheduled spending enabled. Node20 action-runtime deprecation produced a non-fatal warning (runner forced Node24); consider updating pinned action versions in a later maintenance change.

## Cloud authentication diagnostic — 2026-09-13
Two hosted Gemini CLI attempts exited before producing a review. Fixed-category diagnostics were inconclusive, so the next diagnostic emits a bounded stderr excerpt with the exact provider secret removed before logging; no additional provider credentials are inherited. Schedule remains disabled until a successful review.

The diagnostic identified Gemini CLI workspace trust rejection before authentication. Pass --skip-trust only for the newly created empty temporary working directory, while retaining fresh HOME and wildcard deny-tool policy. Removed temporary raw diagnostic logging after identifying the cause.

Validation: 15 orchestration tests passed; hosted Agent supervisor #4 passed using Gemini after the trust fix. Gemini produced an unverified review artifact. Application source and scheduled paid execution remain outside this completed scaffold step.

## Application development phase — 2026-09-12
2026-09-12 | User authorized APPLICATION_DEVELOPMENT on branch claude/tender-radar-mvp-5pp4mn.
Agent rule files updated from SCAFFOLD_ONLY. Merging to main, external deployment, paid
schedules and CI write access remain prohibited.
2026-09-12 | The cloud supervisor now reads prompts/CLOUD_REVIEW_PROMPT.md, a review-only
prompt kept separate from the development rules, so widening development authorization can
never widen what the hosted review job may do. ci/validate.py asserts that separation.
2026-09-12 | Outbound access to xarid.uzex.uz is refused by the environment network policy
(HTTP CONNECT 403). No endpoint, lot id or response was invented. Development proceeds on
generated fixtures under samples/synthetic, labelled synthetic in file content, ids, customer
names and in the stored `procedure.source` value.
2026-09-12 | `procedure` is unique on (source, source_id) instead of source_id alone so that
synthetic development rows can never be mistaken for, or collide with, real imported rows.
2026-09-12 | The source contract lives in radar/source/uzex_mapping.yaml, a data file, so that
verifying the real endpoint changes one mapping rather than parser code. UZEX_LIST_URL and
UZEX_DETAIL_URL default to empty, making an accidental live import impossible.
2026-09-12 | Importer transaction boundary is one list page: list snapshot, all detail
snapshots, upserts and the cursor advance commit together. A crash rolls back the whole page,
so the cursor never points past partially written data.
2026-09-12 | Python 3.12 is provided by a local uv virtualenv (.venv) because the system
interpreter is 3.11. PostgreSQL 16 runs as a local cluster since the container has no Docker
daemon; docker-compose.yml stays the documented path for other machines.

## Classification, renewal and presentation — 2026-09-13
2026-09-13 | Model prices are never guessed. radar/classify/pricing.yaml holds reviewed
figures and ships with no real model priced; a paid run refuses to start unless the model is
priced there or GEMINI_INPUT_USD_PER_MTOK / GEMINI_OUTPUT_USD_PER_MTOK are set. The offline
mock model is priced so tests exercise the same ledger path as a paid run.
2026-09-13 | Cost control order: rules decide first, identical lot text is deduplicated within
a run, ai_cache answers repeats across runs, then batches of 20 go to the model. On the 5000
lot synthetic set this cut the model from 386 lots to 5 distinct texts in one batch.
2026-09-13 | The ledger reserves estimated cost and commits before the call, so a crash during
a call cannot hide spend. A call that returns nothing usable is marked failed and not charged.
2026-09-13 | The rules layer may abstain but must never decide the wrong way. Keywords that
borrow IT words for non-IT goods (a computer desk) are listed under not_it so they cannot be
counted as IT. tests/test_rules.py enforces both directions against samples/synthetic/
known_lots.md, which is a labelled synthetic golden set standing in for the real 5 IT + 5
non-IT lots that were never supplied.
2026-09-13 | Renewal window: a row stays on the Radar while the expected renewal is still
ahead and the contact date is at most radar_contact_window_days away. A contact date that has
already passed while the renewal is still ahead scores in the most urgent bucket rather than
scoring nothing.
2026-09-13 | Score weights are kept exactly as specified and reach 75, not 100. The page and
the docs state the true range instead of silently rescaling.
2026-09-13 | Hardware categories are excluded from the Radar unless the lot itself was
classified is_subscription, and a term detected in the lot text overrides the category
lifecycle because the lot text is better evidence than a table.
2026-09-13 | Synthetic provenance is carried end to end: fixture content, lot ids, customer
names, procedure.source, the Excel warning row and the /radar banner. Reports must never
present these rows as real procurement results.

## Reparse, organization identity and the worker — 2026-09-13
2026-09-13 | `reparse` rebuilds rows from stored snapshots and verifies each checksum first. A
snapshot that fails its checksum is reported and skipped, never reparsed, because silently
importing corrupted bytes is worse than a visible gap. This is what makes the raw_snapshot
requirement in docs/SPEC.md pay off: a parser or mapping fix never means re-fetching.
2026-09-13 | Organization identity order: STIR, then an exact case-insensitive alias match,
then a trigram match above ORG_MATCH_THRESHOLD (0.92). Organizations that already carry a STIR
are excluded from fuzzy matching entirely. A duplicate customer is recoverable; a wrong merge
destroys the purchase history the Radar is built on. Migration 0002 indexes lower(name_raw) so
the matching query can use an index.
2026-09-13 | Spellings differing only in case are one alias. Genuinely different spellings are
all kept, since they are the raw material for later matching.
2026-09-13 | Coverage percentages are published next to results in `stats` and the Excel Stats
sheet. Without them a Radar built on lots that lack amounts or completion dates looks complete
and means nothing.
2026-09-13 | worker.py runs one ordered cycle in one process with no broker, per docs/SPEC.md.
A failed import or a hit budget stop ends the cycle instead of publishing a Radar from
half-imported data. SIGTERM finishes the cycle in flight rather than cutting a job in half.
2026-09-13 | docs/DEPLOYMENT.md is written but has never been executed, and says so. Sizing is
derived from measured row and snapshot sizes rather than assumed.

## Launch packaging — 2026-09-13
2026-09-13 | Two supported launch paths: `docker compose up -d --build` for the whole stack,
and `scripts/bootstrap.sh` plus the systemd units in deploy/ for a plain host. One image
serves both the web and worker processes so their dependencies cannot drift apart.
2026-09-13 | Both paths run the offline synthetic cycle first. A first launch therefore proves
the install without touching the source or spending anything, and the operator switches to the
live source deliberately by setting WORKER_ARGS or the URL variables.
2026-09-13 | The web port is published on 127.0.0.1 only and the compose file exposes no
database port. The application has no authentication of its own, so deploy/nginx-tender-radar.conf
puts TLS and basic auth in front and leaves only /health open.
2026-09-13 | ci/validate.py now asserts that .env is git-ignored and untracked rather than
absent. A host that actually runs the platform needs a local .env, and bootstrap.sh creates
one; the real requirement was always that it never gets committed.
2026-09-13 | The worker unit uses SIGTERM with a 900 second stop timeout so a restart lets the
cycle in flight finish instead of cutting an import in half.
2026-09-13 | The Docker path is validated (`docker compose config`) but has never been built or
run: this development environment has no Docker daemon. The plain-host path was run end to end
here. Both facts are stated in docs/DEPLOYMENT.md rather than implied.
2026-09-13 | The worker idles in one second slices instead of one long sleep. Running the
platform as a real process showed that a SIGTERM arriving during the wait was swallowed until
the interval expired, and the worker then started a whole extra cycle after having been asked
to stop. It now stops within a second when idle, and still finishes a cycle already in flight.

## macOS environment and source contract verification — 2026-09-14
2026-09-14 | macOS environment setup: Python 3.12.14 installed via standalone binary (uv), and PostgreSQL 16.15 configured via official Postgres.app with dedicated local database (tender_radar) and test database (tender_radar_test) on 127.0.0.1:5432. All 140 pytest tests (including all database tests) and scaffold validation pass with zero skipped tests.
2026-09-14 | T1 Source contract verification:
- xarid.uzex.uz: Public unauthenticated endpoints verified on live portal.
  List endpoint: POST https://xarid-api-purchase.uzex.uz/Common/GetCompetitions with JSON range {"from": 1, "to": 50}.
  Detail endpoint: GET https://xarid-api-purchase.uzex.uz/Common/GetCompetition/{source_id}.
  Completed status (status_name: "Совершен") delivers full customer STIR (customer_inn), cost, date_of_opening_offers, line items in js_details, and winning supplier details in winners_ids.
- ebirja.uz: Verified that all lot and trade details are protected behind EDS (E-IMZO) challenge authentication (/api/eds/frontend/challenge). Public unauthenticated access returns 404. Under project rules (no E-IMZO bypass), ebirja data is designated for file import (source='ebirja-export', Task T2).
- Sanitized real request/response samples saved under samples/uzex/ with tokens stripped.
- radar/source/uzex_mapping.yaml and radar/source/parser.py updated with verified contract and fallbacks, passing tests for both real and synthetic fixtures.

## Deployment phase authorization — 2026-09-14
2026-09-14 | Project owner Umidjon Fatullaev (SOFTY) authorized transition from APPLICATION_DEVELOPMENT to DEPLOYMENT phase.
Why: T1 source contract verification on live xarid.uzex.uz API is completed, local MVP test suite (140 tests) and launch packaging are fully validated, and target host infrastructure is provisioned (Hostinger VPS 93.127.213.246).
Authorized actions:
- Deployment of the platform stack to Hostinger VPS (93.127.213.246) following docs/DEPLOYMENT.md.
- Live public UZEX import.
- Merges to main.
Strictly preserved prohibitions:
- No E-IMZO or CAPTCHA bypass.
- No login or session automation on ebirja.uz (cabinet data via file import only).
- Request interval must never be reduced below 3 seconds.
- Durable $10 AI classifier budget limit must not be removed.
- Web application has no built-in authentication and must not be exposed to the public internet without reverse proxy access control (nginx TLS + basic auth).

## Real import execution and rules calibration (T3 & T4) — 2026-09-14
2026-09-14 | Real UZEX import slice executed: 200 real lots imported cleanly via live xarid-api-purchase.uzex.uz endpoint (`from: 1, to: 50` range pagination).
- Duplicate count: 0 duplicates across all 200 procedures.
- Coverage metrics: completion date 100%, customer 100%, start price / amount 100%, quantity 100%. (Award 0% on recent active listings taking bids).
- Idempotency & Collation: Updated `upsert_organization` with Python Unicode-aware case comparison and `ON CONFLICT DO NOTHING` on `organization_alias` to ensure idempotent alias insertion across PostgreSQL collation environments without crashing on Cyrillic uppercase strings.
- Rules Calibration: Augmented `keywords.yaml` with public procurement domain terminology (Russian & Uzbek case forms for municipal and government tenders). Rule coverage reached 98.0% (196 out of 200 decided by rules: 5 IT, 191 non-IT; only 4 ambiguous lots left for AI).
- Cost Projections: At 98% rule coverage, 200 lots required only 1 AI batch costing ~$0.0001 under mock pricing, ensuring the $10 budget can handle tens of thousands of tenders.
- Golden Set: Replaced `samples/synthetic/known_lots.md` with verified real lots (IT and Non-IT). All 140 pytest tests pass.

## Gemini pricing review and budget enforcement verification — 2026-09-14
2026-09-14 | Official Gemini API pricing retrieved from https://ai.google.dev/gemini-api/docs/pricing and added to `radar/classify/pricing.yaml`:
- `gemini-2.5-flash-lite`: $0.10 input / $0.40 output per 1M tokens (reviewed 2026-09-14).
- `gemini-2.5-flash`: $0.30 input / $2.50 output per 1M tokens (reviewed 2026-09-14).
- `gemini-2.0-flash`: $0.10 input / $0.40 output per 1M tokens (reviewed 2026-09-14).
2026-09-14 | Budget stopping enforcement verified: `CostLedger` correctly halts classification prior to any network call when `CLASSIFIER_BUDGET_USD` cap is reached, raising `BudgetExceeded` and recording $0 in spend.

## Product normalization (brand, family, model, term) — 2026-09-14
2026-09-14 | Implemented product normalization module (`radar/normalize.py`) and schema migration (`alembic/versions/0003_product_normalization.py`):
- Added columns to `lot_item`: `brand` (varchar 100), `product_family` (varchar 100), `model` (varchar 255), `term_months` (integer).
- Extracted rules from parent project and expanded with IT brands (Autodesk, Microsoft, Kaspersky, Fortinet, Cisco, VMware, Oracle, Adobe, ESET, Zoom, etc.), product families (AutoCAD, Windows, Office 365, FortiGate, etc.), hardware models (e.g. FG-100F, PowerEdge R750), and license durations (e.g. "1 yil", "12 oy", "3 года", "1-Year" -> months).
- Integrated into `radar.importer.upsert_procedure` and verified via `radar reparse` over all 447 database snapshots (100% success, 0 errors).
- Unit tests added in `tests/test_normalize.py` (all 149 test cases pass).

## Bitrix24 CRM and sales workflow integration (Stage 3) — 2026-09-14
2026-09-14 | Ported `app/crm_service.py` from parent project into `radar/crm.py` with strict idempotency and relational storage:
- Added `crm_deal` and `crm_task` tables via Alembic migration `0004_crm_deal.py`.
- Enforced strict uniqueness on `crm_deal.procedure_id` (`uq_crm_deal_procedure`) guaranteeing a single lot/procedure can never generate duplicate deals in Bitrix24 or the database.
- Implemented `get_company_profile_and_timeline`, `generate_grounded_proposal` (grounded in normalized product brands/families, no made-up prices, `auto_send_allowed=False`), `push_deal_for_procedure`, and compatible `push_to_bitrix24`.
- Integrated REST API endpoint `crm.deal.add` via `urllib.request` using `BITRIX24_WEBHOOK_URL` (or local credentials path) with automatic fallback to traceable mock mode in test/offline environments.
- Added CLI commands: `crm-timeline`, `crm-proposal`, `crm-deal`, `crm-push` in `radar/cli.py`.
- Added web endpoints: `/api/companies/{stir}/timeline`, `/api/companies/{stir}/proposal`, `/api/procedures/{procedure_id}/bitrix`.
- All 157 pytest tests pass (0 skipped, 0 failed), ruff and validate pass.

## Platform audit, UZEX adapter compliance and Radar refresh — 2026-09-15
2026-09-15 | `radar/source/uzex.py` existed in the working tree but had never been committed, while the committed `radar/worker.py` did not yet import it. The branch was therefore unbuildable from a clean checkout, and the file's dependencies (`requests`, `urllib3`, `cryptography`) were absent from `pyproject.toml` — hidden locally because the virtualenv already carried them transitively. Only `requests` is now declared, because the two changes below removed the need for the other two.
2026-09-15 | Both source adapters paced themselves with a local `time.sleep` under the mandated floor — UZEX 0.7–1.4 s, E-Birja 0.6–1.2 s — against CLAUDE.md ("never below 3 seconds") and the 2026-09-13 decision fixing jitter at 3–4 s. Both now take the shared `RateLimiter` from `radar/source/client.py`, which clamps with `max(interval, MIN_INTERVAL_S)`. The floor is enforced in one place rather than restated per adapter, and `RateLimiter` accepts injected `sleep`/`clock`, so the pacing is now covered by tests instead of by a real delay.
2026-09-15 | UZEX requests carried a `Validation` header built by RSA-encrypting `{url}~{dd.MM.yyyy}` with a public key lifted from the site's Angular production bundle. Live checks against `GetCompletedDeals` and `GetOffersList` returned identical results with the header absent and TLS verification enabled, so the header and the embedded key were removed. Should UZEX begin enforcing it, this is the decision to revisit — reintroducing it needs an explicit call on whether replicating a client-side check is acceptable.
2026-09-15 | Certificate verification was disabled in both adapters (`session.verify = False`, `ssl._create_unverified_context()`). Both hosts answer correctly under normal verification, so it is enabled. `radar/eimzo.py` still uses an unverified context; that is left alone here because it also talks to the local E-IMZO daemon over a self-signed loopback certificate, which needs a separate decision.
2026-09-15 | The worker never called `compute_renewals()`. It imported `radar_rows`, which only reads. Renewal opportunities therefore froze at whichever manual `radar renewal` run came last: 401 classified IT lots against 101 stored opportunities. A `refresh_renewals()` stage now runs in every cycle, and the recompute raised the Radar to 164 opportunities.
2026-09-15 | The dashboard export ordered rows with winner-STIR-present first and cut at `LIMIT 1000`, which hid 3 802 awarded contracts behind a page that read as fully populated. Ordering is now by recency across every awarded contract. Winner STIR sits at roughly 23% and that gap is now visible rather than sorted out of view; it is a source limitation, not a parser defect — the E-Birja list API exposes no `tin` field and every stored XT-Xarid record carries `supplier_inn` as null.
2026-09-15 | Joining `lot_item` multiplied multi-item contracts into 5 867 rows for 4 948 contracts, so summing the won-amount column double-counted 919 rows. Replaced with a `LATERAL string_agg` over line-item names: one row per contract, product names aggregated into the cell.
2026-09-15 | `run_once()` had no exception handling, so one unreachable source ended the whole cycle including the deploy. Each stage is now isolated and logged, and `run_once()` returns a summary instead of raising. The nine existing worker tests exercised an API (`run_cycle`, `Stopper`, `build_source`) that no longer exists, leaving the worker uncovered; they are replaced with tests that pin the resilience contract.
2026-09-15 | E-Birja stamps its own IT type into the contract (`IT-dastur`, `IT-tarmoq`). The classifier missed all 67 such contracts because the bare words are too weak to decide on, while `IT-kompyuter` and `IT-server` happened to match existing keywords. The prefixed markers are treated as decisive and mapped to their categories; the bare-word weakness is unchanged, so a computer desk is still not a computer purchase. Separately, 88% of E-Birja rows carry no product name at all — the public list API returns only `lot_number` — which no keyword work can address.
2026-09-15 | Deployment credentials (SSH key path, host, port, remote path) and the dashboard build paths were hardcoded in `radar/worker.py`. Moved to environment settings; the worker skips deployment rather than failing when they are unset. The company STIR was hardcoded in three places and is now `COMPANY_TIN`. The E-IMZO session file is written with mode 0600.

## Correction: the 3-second floor was not actually enforced on retries — 2026-09-15
2026-09-15 | The entry above claiming the request floor "is enforced in one place" and "is now covered by tests instead of by a real delay" was wrong on the retry path, and a pre-merge review caught it. Both adapters called `limiter.wait()` once before the retry loop, so the second and third attempts re-issued the request after their own `time.sleep` of 2.0 s (UZEX) and 2.5 s (E-Birja) — under the floor CLAUDE.md lists as strictly prohibited, and firing precisely when the server returned 429 to ask for less traffic. `limiter.wait()` now sits inside the loop in both adapters, matching `HttpSource._fetch` in client.py, which has always paced inside `while True`.
2026-09-15 | The tests written alongside that change concealed the gap rather than catching it: the UZEX test stubbed a permanent HTTP 200 so no retry ever ran, and the E-Birja test called `client.limiter.wait()` directly instead of going through `_request`. Both are replaced with tests that force 429/503 responses and assert the limiter paced every attempt; reverting the fix now fails them. A test that cannot fail against the bug it names is worse than no test, because the green suite is then evidence for a claim it never checked.

## E-Birja: the contract list is gone, the auction list replaces it — 2026-11-16
2026-11-16 | `sync_ebirja` returned 0 every cycle. Probing each endpoint from this machine (one request per endpoint, 3 s apart) showed why, and the three failures are not one fault:
- `/common/contract/shop-list` → **HTTP 404**, `"Unable to resolve the request: common/contract/shop-list"`. The route was withdrawn; this was five of the seven requests the stage made per cycle.
- `/common/contract/external-tender` → **HTTP 403**, `"Captcha tekshiruvi muvaffaqiyatsiz"`.
- `/common/contract/external-offer-request` → **HTTP 403**, the same CAPTCHA wall.
- `/auction/auction/active` → **HTTP 200** with usable data, and `sync_ebirja` never called it.

The two 403s are a CAPTCHA gate, and CLAUDE.md lists CAPTCHA bypass as strictly prohibited, so the contract list is not a source any more and no amount of adapter work will make it one. That is a loss of kind, not of degree: those endpoints were the 32 491 historical E-Birja contracts, and the only authorised route to that data now is a cabinet export file. The stage therefore reads auctions instead, and the live list yields 14 of them — open lots with real buyers, amounts and bid deadlines, which is forward-looking lead data rather than contract history. The decision to revisit is the export-file importer, not the API.

2026-11-16 | `fetch_active_auctions` paged on `page`/`size`. The endpoint reads `currentPage`/`perPage` and silently ignored both parameters, so every call returned page 0 and any paging loop over it would have re-imported the first page forever. Confirmed against the live endpoint: `currentPage=1&perPage=5` returns `meta.currentPage=1, perPage=5, pageCount=3` and a different set of ids.

2026-11-16 | `_request` collapsed every HTTP error into `{"result": {"data": [], "meta": {"totalCount": 0}}}`, which is indistinguishable from a page with nothing on it. A dead source therefore looked exactly like a quiet one, which is how four endpoints could fail for weeks while the cycle logged a tidy `ebirja_inserted: 0`. It now also returns `http_status` and the server's own `message`, `_collect` returns the page `meta` so a refusal stops paging instead of reading as the last page, and the refusal is logged at ERROR with the text the server sent.

2026-11-16 | `parse_ebirja_auction` stored two numbers that were not what their columns mean: `position_count` (the count of positions in the auction) as a line-item `quantity` in `dona`, and `total_sum` (the auction total) as `unit_price_raw`. Both are now left empty — a missing number is recoverable, a confidently wrong one is not. The auction payload also carries `company.phone`, `company.account` and `company.director`; none is read, nothing stores a raw snapshot of the row, and a test asserts all three stay out of the record (docs/PRIVACY.md). A row with no title is now skipped rather than given a placeholder, because the title is the one field classification reads.

2026-11-16 | Auctions keep the `ebirja_a_` prefix on `source_id` under `source='ebirja'` rather than taking a new source name: auction and contract ids share a number space (both have an id 1328) and the prefix already separates them, so a second source value would change what every `group by source` reports for no gain. They are stored `status='ACTIVE'` with no award and no completion date, so they cannot enter the renewal radar or the awarded-contract export — verified in the database after the import, 0 of 14 carry either.

2026-11-16 | `source_url` for an auction is built as `https://ebirja.uz/uz/auction/{id}`. This could not be verified: the public site is a single-page app that answers HTTP 200 for any path, including an id of 99999999, so the status code proves nothing. The link is kept because a dead click costs little and no stored figure depends on it, but it is a guess and is commented as one.

## Hostinger deploy: the key works, the account has no shell — 2026-11-16
2026-11-16 | `rebuild_and_deploy` failed with `scp: Connection closed` (10 occurrences in the LaunchAgent error log). Verbose SSH to the deploy host shows the cause: `Authenticated to 62.72.50.47 using "publickey"` — the key is still in `authorized_keys` — followed by `/sbin/nologin: No such file or directory`. The account's login shell is a path that does not exist on the server, and the `sftp` subsystem is closed as well (`sftp` returns the same `Connection closed`), so neither of scp's two protocols can start a remote process. Port 65002 is open and port 21 answers, 22 does not. This is the shape of a Hostinger plan with SSH access switched off; it is re-enabled in hPanel under Advanced → SSH Access, and **no change in this repository can work around it**. An FTP fallback was considered and not built: port 21 is open, but it needs a password this repository must not hold, and re-enabling SSH restores the existing path with no new secret and no new code.
2026-11-16 | The deploy ran `subprocess.run(scp_cmd, check=True)`, so `CalledProcessError` carried only `returned non-zero exit status 1` while scp's actual reason went to a different stream (the LaunchAgent error log, not `worker.log`). The reason a reader needs was therefore never next to the failure. stderr is now captured and raised with the message, and when it matches this failure the exception also names the hPanel setting that fixes it. `BatchMode=yes` is set so a future credential prompt fails fast instead of hanging the stage to its 300 s timeout.

## E-Birja cabinet export importer — 2026-11-16
2026-11-16 | With the contract endpoints closed (404 + two CAPTCHA walls), a cabinet export file is the only authorised route to E-Birja contract history, so `radar/source/ebirja_export.py` reads one. It never touches the network: the owner downloads the file by hand, as CLAUDE.md requires.
2026-11-16 | **No real export file was available and none was fetched** — CLAUDE.md forbids logging in to ebirja.uz, and nothing in the project or on this machine held a sample. The column wordings in `ebirja_export_mapping.yaml` are therefore candidate Uzbek/Russian/English headers, not observed ones, and the importer is built around that uncertainty rather than hiding it: `radar import-ebirja-export --inspect <file>` prints the file's own headers, the column each field matched and the synonym it matched on, and names what went unmatched. A real wording the mapping missed is added to the YAML; no code changes. A file missing `contract_number` or `product_name` is refused with that report rather than imported into unclassifiable rows.
2026-11-16 | Column matching scores every (field, synonym, column) triple — 3 for an exact fold match, 2 when the header contains the synonym, 1 when the synonym contains the header — then assigns best-first with the longest synonym breaking ties, each field and each column used once. That ordering is the whole point: it is what makes "buyurtmachi inn" take the STIR column before the shorter "buyurtmachi" can claim it as a customer name, which is the mistake a naive substring match makes on a real export.
2026-11-16 | Rows are grouped by contract number, because a cabinet export normally carries one row per line item. The contract amount is the first non-empty value in the group and **never the sum**: if the column holds the contract total it is repeated on every row, and summing it would multiply the contract by its line count. Whether that column is a total or a per-line figure cannot be known in advance, so the report counts contracts whose rows disagree on the amount and warns that the mapping should point `amount` at the contract-total column — the ambiguity is surfaced instead of guessed.
2026-11-16 | Export contracts take their own source name, `ebirja_export`, with `source_id = ebirja_x_<contract number>`. The 32 489 rows imported before the API closed are keyed on E-Birja's internal numeric id (`ebirja_c_9998`), which an export file does not carry, so the two key spaces cannot be matched. **A contract present in both will therefore be stored twice**, and because both copies are COMPLETED with a completion date, the renewal radar can raise two opportunities for one contract. Keeping the export under its own source makes the overlap visible to any `group by source` rather than silently inflating `ebirja`, and the contract number stays recoverable from `source_id` for a dedupe pass — which needs a real export file to write, since matching the two sides depends on what the export actually contains.
2026-11-16 | `.xlsx` and `.csv` are both read, and the header is taken from the first row filling at least two cells: cabinet exports usually open with a title line and a blank. Amount parsing tolerates spaced, non-breaking-spaced and apostrophe thousands separators and a comma decimal, because which of those appears depends on who generated the file. Verified end to end against `samples/ebirja/export_SYNTHETIC.csv` — labelled synthetic in its filename, its first line and its README — which groups a two-line contract into one procedure and skips an unusable row.
