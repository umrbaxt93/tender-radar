# tender-radar

Public UZEX procurement history → IT classification → Renewal Radar → earlier sales outreach.

**Phase: application development.** Schema, parser, importer and CLI exist and are tested.
Classification, renewal scoring, Excel export and the `/radar` page are not implemented yet.
**No real procurement data has been imported.** The public endpoint contract is UNVERIFIED
(see [docs/SOURCE_API.md](docs/SOURCE_API.md)); everything importable today comes from clearly
labelled synthetic fixtures under `samples/synthetic/`.

[Specification](docs/SPEC.md) · [Progress](PROGRESS.md) · [Database](docs/DATABASE.md) ·
[Cloud workflow](docs/CLOUD_WORKFLOW.md)

## Run it locally

Requires Python 3.12 and PostgreSQL 16 (either `make up` with Docker, or an existing server).

```bash
make install                      # .venv with runtime and dev dependencies
cp .env.example .env              # .env is git-ignored; fill DATABASE_URL at minimum
export DATABASE_URL=postgresql://tender:PASSWORD@localhost:5432/tender_radar
make migrate                      # Alembic revision 0001
make import-synthetic             # 12 labelled synthetic lots
make stats
```

Tests need a throwaway database: `export TEST_DATABASE_URL=...tender_radar_test && make test`.
Without it the database tests skip rather than fail. `make lint` runs ruff, `make validate`
runs the offline repository checks that CI also runs.

A live import stays impossible by accident: `UZEX_LIST_URL` and `UZEX_DETAIL_URL` are empty by
default, and the client refuses to start without them and without `CONTACT_EMAIL`. When
configured it makes one request per 3 s plus jitter, backs off on 429/5xx, and stops on 401,
403, redirects or a login/CAPTCHA page. There is no bypass path.

## Cloud execution
`Checks` validates the repository, runs ruff and pytest against a disposable PostgreSQL 16
service, and carries no provider secrets. `Agent supervisor` is a manual, review-only job;
its two-hour schedule is gated off by `ENABLE_AGENT_SCHEDULE`. It reads
`prompts/CLOUD_REVIEW_PROMPT.md`, returns a review artifact, and never edits, commits, merges
or deploys. Review order is Gemini → Claude → Codex, stopping at the first success.

- Run checks: Actions → Checks → Run workflow.
- Run a review: Actions → Agent supervisor → Run workflow.
- Review output: artifact `scaffold-review`, retained 7 days.
