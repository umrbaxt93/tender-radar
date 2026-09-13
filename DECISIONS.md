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
