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
