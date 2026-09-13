# tender-radar

Public UZEX procurement history → IT classification → Renewal Radar → earlier sales outreach.

The pipeline runs end to end today: import, classify, renewal scoring, Excel export and a
`/radar` web page. **No real procurement data has been imported.** The public endpoint
contract is UNVERIFIED (see [docs/SOURCE_API.md](docs/SOURCE_API.md)), so everything
importable right now comes from clearly labelled synthetic fixtures, and every output that
contains them says so.

[Specification](docs/SPEC.md) · [Progress](PROGRESS.md) · [Database](docs/DATABASE.md) ·
[Deployment](docs/DEPLOYMENT.md) · [Cloud workflow](docs/CLOUD_WORKFLOW.md)

## Launch it

Everything in containers, including the database, migrations, worker and web:

```bash
echo "POSTGRES_PASSWORD=choose-one" >> .env
make up-all                  # docker compose up -d --build
curl http://127.0.0.1:8000/health
```

Or on a plain host with Python 3.12 and PostgreSQL 16:

```bash
./scripts/bootstrap.sh       # virtualenv, .env, migrations, one synthetic cycle
make web                     # http://127.0.0.1:8000/radar and /health
```

Both paths first run the offline synthetic cycle, so the install proves itself before
anything touches the source or costs money. For a server, install the unit files in `deploy/`
and follow the launch checklist in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

For development against an existing database:

```bash
make install
export DATABASE_URL=postgresql://tender:PASSWORD@localhost:5432/tender_radar
make demo                    # migrate, synthetic import, classify, renewal, export
```

`make demo` uses `--mock-ai`, a deterministic offline model, so it costs nothing and needs no
API key. Individual steps are `make migrate import-synthetic classify renewal export web`.
`make worker ARGS="--fixtures samples/synthetic --mock-ai"` runs the same chain as one cycle in
a single process, which is how it is meant to run on a server.

## What each step does

**import** walks the listing page by page and commits after every page, so an interrupted run
resumes from its cursor instead of starting over. Every response is stored zstd-compressed in
`raw_snapshot`, so parsing can be re-run without re-fetching. Writes are upserts keyed on
`(source, source_id)`, so re-running never duplicates.

**classify** runs keyword and regex rules first, in Uzbek-Latin, Uzbek-Cyrillic and Russian.
Anything the rules settle never reaches the model. What is left is deduplicated by text hash,
looked up in `ai_cache`, then sent to Gemini in batches of 20 with a JSON schema. Each batch
reserves its estimated cost in `ai_cost_ledger` before the call, so the $10 cap holds across
runs and across crashes.

**renewal** rebuilds `renewal_opportunity` from the classifications. Expected renewal is the
completion date plus the category lifecycle, clamped to month ends. Contact date is 60 days
earlier. Scoring weights live in `radar/lifecycle.yaml` and reach 75, not 100; see
DECISIONS.md.

**export** writes `out/renewal_radar.xlsx` with Radar, IT_Lots and Stats sheets. The Stats
sheet carries coverage percentages: how many lots actually have a completion date, a customer,
an amount, an award and a quantity. A Radar built on lots missing those would look full and
mean nothing, so the numbers are published next to the results.

**web** serves `/radar` and `/health` on a single worker.

**reparse** rebuilds rows from stored snapshots after a parser or mapping fix, verifying each
checksum and never touching the network. **worker** runs import, classify, renewal and export
as one ordered cycle in one process, optionally repeating on an interval.

## Configuration

Copy `.env.example` and fill what you need. `DATABASE_URL` is the only requirement for the
offline demo. A live import additionally needs `UZEX_LIST_URL`, `UZEX_DETAIL_URL` and
`CONTACT_EMAIL`; they are empty by default so a live run cannot start by accident. Paid
classification needs `GEMINI_API_KEY`, `GEMINI_MODEL` and a reviewed price in
`radar/classify/pricing.yaml` — prices are never guessed, so it refuses to start without one.

Tests need a throwaway database: `export TEST_DATABASE_URL=...tender_radar_test && make test`.
Without it the database tests skip instead of failing. `make lint` runs ruff and
`make validate` runs the offline repository checks that CI also runs.

## Source safety

A live import makes one request per 3 seconds plus jitter, from one worker, with
`CONTACT_EMAIL` in the User-Agent. It backs off 10 → 160 seconds on 429 and 5xx, and after
five consecutive failures it persists the cursor and exits. It stops immediately on 401, 403,
any redirect, or a login or CAPTCHA page. There is no bypass path in the code, and PDFs are
out of scope.

## Cloud execution

`Checks` validates the repository and runs ruff and pytest against a disposable PostgreSQL 16
service, carrying no provider secrets. `Agent supervisor` is a manual review-only job whose
two-hour schedule is gated off by `ENABLE_AGENT_SCHEDULE`. It reads
`prompts/CLOUD_REVIEW_PROMPT.md`, returns a review artifact, and never edits, commits, merges
or deploys.
