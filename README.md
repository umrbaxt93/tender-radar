# tender-radar

Public UZEX procurement history → IT classification → Renewal Radar → earlier sales outreach.

**Phase: scaffold only. No application source has been written.**
[Original MVP specification](docs/SPEC.md) · [Progress](PROGRESS.md) · [Cloud workflow](docs/CLOUD_WORKFLOW.md)

## GitHub cloud execution
No local installation is required. The `Scaffold checks` workflow validates the scaffold and checks disposable PostgreSQL 16 connectivity. `Agent supervisor` supports manual review and a two-hour schedule gated off by default.

Review order: Gemini → Claude → Codex, stop at the first successful response. Models return review artifacts only; no automatic source edits, commits, merges or deployments. Codex uses OpenAI's official action with a read-only sandbox and API-key proxy.

- Progress: PROGRESS.md and the repository Actions tab.
- Run checks: Actions → Scaffold checks → Run workflow.
- Run a configured review: Actions → Agent supervisor → Run workflow.
- Review output: workflow artifacts `scaffold-review`, retained 7 days.
- Schedule remains off unless repository variable ENABLE_AGENT_SCHEDULE is true.

Provider credentials/model IDs have not been configured. No authenticated agent execution is claimed. Current setup details are in docs/CLOUD_WORKFLOW.md.

The Makefile reserves future application commands, which intentionally fail until implementation. CI's database is temporary test infrastructure, not production storage.
