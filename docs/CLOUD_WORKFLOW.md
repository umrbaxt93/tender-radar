# GitHub cloud workflow

Repository: https://github.com/umrbaxt93/tender-radar (private).
No development tools, local cron or local database are required on the user's computer.

## Workflows

`Scaffold checks` runs on pushes, pull requests and manual dispatch. It runs offline orchestration tests, scaffold validation and a PostgreSQL 16 connectivity test in a disposable hosted runner. No provider secrets enter this job.

`Agent supervisor` is manual by default. The two-hour UTC schedule is gated by repository variable ENABLE_AGENT_SCHEDULE=true, initially absent/off. Manual runs and schedule runs must use main; no pull_request_target trigger exists. It has contents:read only, checkout credentials are not persisted and it never pushes, merges or deploys. Review output is unverified advice, not product completion.

## Credentials and costs

Add environment secrets to the GitHub Actions environment `agent-review`: GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY. Add environment variables GEMINI_MODEL, CLAUDE_MODEL, CODEX_MODEL with economical model IDs available to the corresponding accounts. Only configured providers are attempted. Never paste keys into chat, .env.example or repository files. Use dedicated authorized provider accounts and configure spending controls before starting paid reviews.

The provider sequence is Gemini → Claude → Codex. Gemini and Claude run via bounded non-interactive CLIs, maximum 180 seconds each; Claude additionally uses a $0.25 per-run cap. Codex is a separate official openai/codex-action step with drop-sudo, read-only sandbox and a proxy that keeps the raw OpenAI API key outside the agent process. Its complete action step (including installation) has a five-minute timeout. The total review job is capped at 15 minutes. These time limits are not an aggregate dollar guarantee. The future application's $10 classification budget is separate and unimplemented.

Gemini/Claude receive a fixed documentation snapshot through stdin, run in a temporary HOME/empty directory and cannot use tools. Codex receives the same snapshot. Shell/unified execution/web search/app integrations are disabled for its read-only review. Raw Gemini/Claude output and credentials are not uploaded; only sanitized review text and fixed status categories are saved. The official Codex action may emit its normal execution events to the private Actions log.

Action revisions are pinned to inspected commit SHAs; CLI versions are pinned. Npm lifecycle scripts are disabled for Gemini/Claude. Transitive npm dependencies and container tags are not yet immutable. No untrusted application install/test hooks run in the secret-bearing job. Review all workflow and supervisor changes before they reach main. Configure branch/environment protection if the account plan supports it; do not assume those protections already exist.

## Running and stopping

Actions → Scaffold checks → Run workflow verifies setup.
Actions → Agent supervisor → Run workflow performs one review after keys/models are configured.
Artifacts → scaffold-review contains review.md and status.json (7-day retention).
Remove or set ENABLE_AGENT_SCHEDULE=false to stop future scheduled work; cancel a running workflow to stop its runner. STATUS: DONE in PROGRESS.md suppresses provider calls, but must only be set after the full application Definition of Done is independently verified.

No schedule spending is enabled initially. Scheduled reviews do not deduplicate snapshots in this initial GitHub adapter; enable only when useful and use provider limits. No Telegram delivery is configured because no bot or destination was supplied.

Hosted Actions minutes/runner eligibility are account prerequisites. This CI does not provide durable production hosting. Real imports require managed PostgreSQL and persistent snapshots. Original fixtures were missing; do not invent API endpoints or real lots.

`ci/supervisor.py` retains the portable CLI functions and historical GitLab entrypoint as a reference; GitHub calls `ci/github_review.py` and the official Codex action. supervisor.sh/.ps1 route to the GitHub adapter. No GitLab workflow is active here.

## Sources checked 2026-09-13
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://learn.chatgpt.com/docs/github-action
- https://geminicli.com/docs/cli/headless/
- https://geminicli.com/docs/reference/policy-engine/
- https://code.claude.com/docs/en/cli-reference
