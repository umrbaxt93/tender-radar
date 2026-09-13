# Deployment runbook

Nothing here has been executed. The application has only ever run locally against synthetic
fixtures, and no production host exists yet. This is the intended shape of a deployment, to be
verified the first time it is actually performed.

## What the application needs

One small Linux host and one PostgreSQL 16 database. There is no broker, no cache server and
no second process: `worker.py` runs the jobs and the FastAPI app serves two endpoints. Both are
single-worker by design, because the source rate limit allows one request every three seconds
and a second worker would break it.

Sizing follows from the data. A lot occupies roughly 2–5 KB as rows and 10–20 KB including its
compressed snapshot.

| Lots stored | Database and snapshots | Host |
|---|---|---|
| 100k | 2–3 GB | 2 vCPU, 4 GB RAM, 40 GB SSD |
| 500k | 8–12 GB | 2 vCPU, 4 GB RAM, 80 GB SSD |
| 1M | 15–25 GB | 2–4 vCPU, 8 GB RAM, 80–100 GB SSD |

Shared web hosting is not suitable: it cannot run a long-lived worker process, and the
PostgreSQL extension and connection requirements do not fit.

## First install

1. Create the database and enable the extension the schema needs. The `pg_trgm` extension is
   created by migration `0001`, which requires a superuser or a managed PostgreSQL that
   pre-enables it.
2. Clone the repository, `make install`, and write `.env` from `.env.example`. `.env` is
   git-ignored and must never be committed.
3. `make migrate`.
4. Verify with the offline path first: `make import-synthetic classify renewal export`. It
   proves the install without touching the source or spending anything.
5. Only then configure `UZEX_LIST_URL`, `UZEX_DETAIL_URL` and `CONTACT_EMAIL`, and run a small
   real import with `--limit`. Read docs/SOURCE_API.md first: until it is verified, there is
   nothing correct to put in those variables.

## Running the jobs

`python -m radar worker --interval 3600` runs one cycle an hour in a single process. Use a
systemd unit with `Restart=on-failure`; the worker finishes the cycle in flight when it
receives SIGTERM, so a restart never cuts a job in half. A cycle that fails at import or at the
budget stop does not go on to publish a Radar from half-imported data.

The web process is separate: `python -m radar web --host 127.0.0.1 --port 8000`, behind a
reverse proxy that terminates TLS. There is no authentication in the application, so it must
not be exposed to the internet without one in front of it.

## Costs and limits

The classifier's $10 cap lives in `ai_cost_ledger` and holds across runs and restarts. Set
`CLASSIFIER_BUDGET_USD` deliberately and put the reviewed model price in
`radar/classify/pricing.yaml`; without a price a paid run refuses to start. Set the
provider-side spending limit as well: the ledger protects against this application's own spend,
not against anything else using the same key.

## Backups and recovery

Take a nightly `pg_dump` to storage outside the host and test a restore before relying on it.
Raw snapshots are the expensive thing to lose: everything derived from them, parsed rows,
classifications and the Radar, can be rebuilt with `make reparse` and `make classify renewal
export`, without re-fetching from the source. That is why snapshots are stored with checksums,
and why `reparse` reports checksum failures rather than quietly reparsing corrupted data.

## Secrets

`GEMINI_API_KEY`, the database password and any future Bitrix24 webhook belong in the host's
`.env` or in a secrets manager, never in the repository. The cloud review workflow keeps its
own secrets in the GitHub Actions `agent-review` environment; those are unrelated to the
application runtime and are not used by it.
