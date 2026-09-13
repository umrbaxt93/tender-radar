# Handoff — start here

This file is the entry point for any agent or person continuing the project: Claude Code,
ChatGPT/Codex, Antigravity or a human. Read it fully, then AGENTS.md, then PROGRESS.md.
Everything below was true on 2026-09-13 at commit `e5fb0b5` on branch
`claude/tender-radar-mvp-5pp4mn`.

## What this is

Tender Radar collects completed public procurement lots from Uzbekistan, classifies the IT
ones, computes when each licence or subscription will come up for renewal, and tells a sales
manager whom to call before a tender is published. Output: `out/renewal_radar.xlsx` and a
web page at `/radar`. Specification: docs/SPEC.md.

## State in one paragraph

The whole pipeline exists, is tested and runs unattended in one process: import → classify →
renewal → export, plus the web page, a snapshot re-parser and launch packaging (Docker
compose, bootstrap script, systemd units). 139 tests pass, CI is green. **No real
procurement data has ever been imported.** The environment this was built in could not reach
any `.uz` host, so the public endpoint contract is UNVERIFIED and every row so far comes from
synthetic fixtures that are labelled synthetic in the data, the Excel file and the web page.
The single thing that turns this into a working product is a verified source.

## Repository map

| Path | What it does |
|---|---|
| `radar/cli.py` | `python -m radar <cmd>`: migrate, import, reparse, classify, renewal, export, web, worker, stats, health |
| `radar/models.py`, `alembic/` | Schema (docs/DATABASE.md). Migrations 0001, 0002 |
| `radar/source/client.py` | Rate-limited public HTTP client (3 s + jitter, backoff, hard stop on 401/403/redirect/CAPTCHA) and a fixture-directory source |
| `radar/source/parser.py`, `radar/source/uzex_mapping.yaml` | Mapping-driven parser. **Edit the YAML, not the parser, when the real JSON shape is known** |
| `radar/importer.py` | Resumable, idempotent import; one list page per transaction; `reparse` from snapshots |
| `radar/snapshots.py` | zstd raw snapshots with sha256 |
| `radar/classify/rules.py`, `keywords.yaml` | Keyword/regex pre-filter, Uzbek-Latin/Cyrillic/Russian. Rules may abstain, must never be wrong |
| `radar/classify/gemini.py`, `pipeline.py`, `budget.py`, `pricing.yaml` | Gemini with JSON schema, batching, dedup, cache, reservation-first $10 ledger, offline mock |
| `radar/renewal.py`, `radar/lifecycle.yaml` | Renewal dates (month-end clamped), scoring (max 75), Radar window |
| `radar/export.py` | Excel: Radar, IT_Lots, Stats |
| `radar/web.py`, `radar/templates/radar.html` | FastAPI `/radar`, `/health` |
| `radar/worker.py` | One ordered cycle in one process, interval mode, clean SIGTERM |
| `scripts/gen_synthetic_fixtures.py` | Generates labelled synthetic fixtures |
| `scripts/bootstrap.sh`, `Dockerfile`, `docker-compose.yml`, `deploy/` | Launch packaging |
| `samples/synthetic/` | Synthetic fixtures + `known_lots.md` golden set for the rules |
| `tests/` | 139 pytest tests; DB tests need `TEST_DATABASE_URL` |
| `ci/`, `.github/workflows/` | `Checks` (ruff, pytest, validation). `Agent supervisor` is review-only |
| `docs/SOURCE_API.md` | UNVERIFIED. Must be filled from real captured requests |
| `docs/DEPLOYMENT.md` | Runbook, never executed on a real host |
| `DECISIONS.md` | Every non-obvious choice and why. Append, never rewrite |

## Run it

In a fresh agent sandbox (Codex, Claude Code, CI) one script prepares everything, including
PostgreSQL 16 if it is missing, and runs the checks:

```bash
bash scripts/agent_env_setup.sh
eval "$(bash scripts/agent_env_setup.sh --print-env)"
```

By hand:

```bash
make install                                   # Python 3.12 virtualenv
export DATABASE_URL=postgresql://tender:PASSWORD@localhost:5432/tender_radar   # PostgreSQL 16
make demo                                      # migrate, synthetic import, mock classify, renewal, export
make web                                       # http://127.0.0.1:8000/radar
export TEST_DATABASE_URL=postgresql://tender:PASSWORD@localhost:5432/tender_radar_test
make test lint validate
```

Containers: `echo POSTGRES_PASSWORD=... >> .env && make up-all`. The compose file validates but
has never been built (no Docker daemon where it was written).

## Rules that must keep holding

These come from AGENTS.md and the owner. They are not negotiable for any agent.

1. Public pages only. No login, no E-IMZO, no CAPTCHA bypass, no cookies or tokens from a
   browser session, no PDFs. If a page needs a login, stop and say so.
2. Never invent an endpoint, a lot id, a price or a test result. Say "unverified".
3. Synthetic data stays labelled synthetic everywhere. Never present it as real.
4. One request per 3 seconds, one worker, backoff, durable cursor. Never faster.
5. AI only behind rules, dedup, cache and the reservation-first cost ledger. Prices come from
   the official pricing page into `pricing.yaml`, never from memory.
6. No secrets in git, ever. `.env` is git-ignored; `ci/validate.py` checks it stays untracked.
7. Work on a branch. No merge to `main`, no external deployment, no paid schedule, no CI write
   access without the owner's explicit say-so.
8. Run `make test lint validate` before every commit. Update PROGRESS.md and TODO.md; append
   decisions to DECISIONS.md. `STATUS: DONE` only after the Definition of Done in docs/SPEC.md
   is independently verified against real data.

## What is blocked and what unblocks it

| Blocked | Unblocked by |
|---|---|
| Real import | A captured public list request + JSON response and one detail request + response from the source, sanitized. Then fill `uzex_mapping.yaml` and docs/SOURCE_API.md |
| Real classification | `GEMINI_API_KEY` in the environment (not in chat, not in git) plus the model's two prices copied into `pricing.yaml` |
| Real launch | A VPS (2 vCPU / 4 GB / 80 GB) and someone running docs/DEPLOYMENT.md on it |
| Cabinet-only data | If the data only exists behind a login (e.g. a supplier cabinet on ebirja.uz), a **person** exports it from the cabinet and hands over the file. The platform then imports the file. Automating a login is out of bounds |

## Next tasks, in order, with acceptance checks

**T1. Source contract.** Owner captures, from a browser with no login: the list request
(as cURL), its JSON, one detail request and its JSON, with Cookie/Authorization/tokens
removed. Agent: fill docs/SOURCE_API.md (origin, method, params, pagination, date and amount
formats, ids, award availability), adjust `uzex_mapping.yaml`, add the sanitized files under
`samples/` (not under `samples/synthetic/`), make `tests/test_parser.py` pass on them.
Accept: parser tests green on real samples; `docs/SOURCE_API.md` no longer says UNVERIFIED.

**T2. File import for cabinet exports (only if T1 shows the data lives behind a login).**
Add `radar/source/file_source.py` that reads an exported XLSX/CSV, mapping columns via a YAML
next to `uzex_mapping.yaml`, producing the same `ProcedureRecord`. Rows get
`procedure.source = 'ebirja-export'` (never `uzex`, never `synthetic`). Accept: import of the
owner's real export file, counts reported, no duplicates on re-import, tests on a small
sanitized sample.

**T3. First real slice.** `python -m radar import --since 2025-09-13 --limit 200`. Check
`python -m radar stats` coverage percentages. Then the full half year since 2025-09-13.
Accept: counts in PROGRESS.md, zero duplicate `(source, source_id)`, cursor resumes.

**T4. Rules calibration.** Replace `samples/synthetic/known_lots.md` with 5 verified IT and
5 verified non-IT real lots (keep the table shape). Adjust `keywords.yaml` until
`tests/test_rules.py` passes. Accept: rules never contradict the golden labels.

**T5. Real Gemini run.** Owner sets `GEMINI_API_KEY` and `GEMINI_MODEL` in the environment
and provides the two prices; agent writes them into `pricing.yaml` with the date. Run
`classify` (no `--mock-ai`) on the imported slice. Accept: `ai_spent_usd` matches the
provider's billing within reason; the $10 stop was never crossed.

**T6. Renewal, Excel, /radar on real data.** Run `renewal`, `export`, `web`. Hand the owner
the top 20 Radar rows. Accept: owner confirms rows are plausible.

**T7. Launch.** docs/DEPLOYMENT.md on the VPS; `docker compose up -d --build` or
`bootstrap.sh` + systemd units; nginx with TLS and auth in front. Then correct the runbook from
what actually happened. Accept: `/health` ok from the server, worker cycles hourly, backup taken.

**T8. Phase 2, only after T1–T7.** Bitrix24 idempotent lead/task sync with a feedback loop,
category → manager mapping, daily new-tender alerts, then competitor and price intelligence
(product normalization first). See TODO.md.

## Working without the owner present

Codex or another hosted agent can drive T1–T7 alone under these conditions: the GitHub
repository is connected to the agent (it stays private; public access is neither needed nor
wanted), the sandbox may reach `xarid.uzex.uz` and `ebirja.uz` so the public pages can be
inspected, and `scripts/agent_env_setup.sh` is used as the environment setup command. Two
things still need a person: merging to `main`, and exporting data from any cabinet that
requires a login. Everything else is the agent's.

## Conventions

- Branch per agent; the current one is `claude/tender-radar-mvp-5pp4mn`. Do not force-push.
- Commit messages say what changed and what was verified. Keep the attribution trailer style
  used in `git log`.
- Every claim in PROGRESS.md must be something that was actually run. If it was not run,
  write BLOCKED or TODO.
- Prefer editing YAML (`uzex_mapping.yaml`, `keywords.yaml`, `lifecycle.yaml`,
  `pricing.yaml`) over Python when the change is data.
