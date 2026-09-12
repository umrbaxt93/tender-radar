### Project
`tender-radar` — collect completed IT procurement lots from xarid.uzex.uz (Uzbekistan, public pages only, no login), classify them as IT / non-IT with category, and produce a **Renewal Radar**: customers whose IT license/subscription purchases are due for renewal within the next 60 days, so a sales manager knows whom to call before any tender is published. Output: `out/renewal_radar.xlsx` and a web page `/radar`.

### Inputs in repo
`samples/list_request.curl.txt`, `samples/list_response.json`, `samples/detail_request.curl.txt`, `samples/detail_response.json`, optional `samples/participants_*.json`, `samples/known_lots.md` (test fixtures). `.env` with `GEMINI_API_KEY`, `DATABASE_URL`, `CONTACT_EMAIL`.

FIRST: study the samples and reproduce the same JSON requests with `httpx` (headers, params, pagination). If impossible, fall back to Playwright headless Chromium with the same rate limits. Document the endpoint contract in `docs/SOURCE_API.md`.

### Stack (fixed)
Python 3.12, httpx, pydantic, SQLAlchemy 2 + Alembic, PostgreSQL 16 via docker-compose, google-genai SDK, openpyxl, FastAPI + Jinja2, pytest, ruff. One `worker.py` process for jobs. No Redis, Celery, or brokers.

### Hard constraints
- Rate limit: 1 request / 3 s ± 1 s jitter, single worker, User-Agent contains `CONTACT_EMAIL`.
- 429/5xx: backoff 10→20→40→80→160 s; after 5 consecutive failures pause 30 min and log.
- Resumable: `import_cursor(job_name, last_page, last_source_id, updated_at)` committed after every page.
- Idempotent: `procedure.source_id` UNIQUE, all writes upsert.
- Every raw JSON response stored in `raw_snapshot` (zstd bytea, url, fetched_at, sha256). Parsing re-runnable from snapshots.
- No PDF downloads in this MVP.

### Database (Alembic migrations)
```
organization(id, stir UNIQUE, name_canonical, region, created_at)
organization_alias(org_id, name_raw, UNIQUE(org_id,name_raw))
procedure(id, source='uzex', source_id UNIQUE, source_url, procedure_type, customer_org_id,
          title, published_at, deadline_at, completed_at, status, currency, start_price,
          raw_snapshot_id, created_at, updated_at)
lot_item(id, procedure_id, raw_name, quantity, unit, unit_price_raw)
award(procedure_id, supplier_org_id, amount, awarded_at)          -- only if data exists
classification(procedure_id UNIQUE, is_it, category, subcategory, brand, model_hint,
               is_subscription, term_months, method 'rule'|'ai', model_name, confidence,
               input_hash, created_at)
renewal_opportunity(id, customer_org_id, procedure_id, category, brand, last_purchase_at,
                    lifecycle_months, expected_renewal_at, contact_by_at, amount, score, computed_at)
import_cursor(job_name PK, last_page, last_source_id, updated_at)
raw_snapshot(id, url, fetched_at, sha256, body bytea)
ai_cache(input_hash PK, response_json, model_name, created_at)
```
Indexes: organization.stir, procedure.completed_at, classification.category, pg_trgm GIN on organization_alias.name_raw.

### Classification (cost-minimising)
1. `classify/rules.py` + `classify/keywords.yaml`: keyword/regex pre-filter over title+items in Uzbek-Latin, Uzbek-Cyrillic, Russian. IT keywords (server/сервер, switch/коммутатор, firewall/межсетевой экран, антивирус, Kaspersky, Microsoft, Windows, Office, лицензия/litsenziya, ноутбук/notebook, kompyuter, принтер, МФУ, UPS/ИБП, видеонаблюдение/CCTV, СХД/storage, Cisco, HPE, Dell, Lenovo, Fortinet, Zoom, hosting, dasturiy ta'minot/программное обеспечение…) and NOT-IT keywords (mebel, qurilish, oziq-ovqat, avtomobil, kanselyariya, dori…). Output `likely_it: yes|no|unsure`. `no` → method=rule, is_it=false, never sent to AI.
2. `classify/gemini.py`: cheapest current Gemini Flash-Lite tier (list models at runtime, log chosen name, fallback to a Flash model). JSON mode with schema:
   `{"is_it":bool,"category":str,"subcategory":str,"brand":str|null,"model_hint":str|null,"is_subscription":bool,"term_months":int|null,"confidence":number,"summary":str}`
   Fixed categories: Server, Storage, Network, Firewall, Antivirus/EDR, DLP, SIEM/SOC, Cybersecurity-Other, Microsoft, Google Workspace, Collaboration, Software Licenses, Cloud, Computer/Notebook, Printer/MFP, UPS, CCTV, Data Center, IT Services, Software Development, Telecom, Other IT.
   Input truncated to 2 500 chars; cache by sha256 in `ai_cache`; batch ~20 lots per request; log token usage; hard stop if estimated cumulative cost > $10.

### Renewal logic (`radar/renewal.py`, `radar/lifecycle.yaml`)
Lifecycle months: Microsoft 12, Antivirus/EDR 12, DLP 12, SIEM/SOC 12, Collaboration 12, Software Licenses 12, Cloud 12, Google Workspace 12, Firewall 12 (subscription), Telecom 12; hardware categories 48 and excluded from Radar unless `is_subscription=true`.
`expected_renewal_at = completed_at + lifecycle_months`; `contact_by_at = expected_renewal_at − 60 days`.
Score 0–100: +40 contact_by within 30 days, +25 within 31–60 days, +15 amount above category median, +10 customer has ≥2 IT purchases in 12 months, +10 brand in priority list (Fortinet, Microsoft, Kaspersky, Zoom; editable). Sort desc.

### Deliverables
- `docker-compose.yml`, `Makefile` (`up migrate import classify renewal export web test lint`).
- CLI: `python -m radar import --since YYYY-MM-DD --limit N`, `classify`, `renewal`, `export` → `out/renewal_radar.xlsx` (sheets: Radar, IT_Lots, Stats). Radar columns: customer, STIR, region, category, brand, last purchase, amount, expected renewal, contact by, score, source URL.
- FastAPI: `GET /radar` HTML table, `GET /health`.
- Tests: parser on samples; rules classifier on known_lots; renewal math; cursor resume after simulated crash; upsert idempotency.
- Docs: README, docs/SOURCE_API.md, docs/DATABASE.md, DECISIONS.md, PROGRESS.md, TODO.md, .env.example.

### Execution order (tracked in PROGRESS.md)
1. Repo skeleton, docker-compose, Alembic, models; `make up migrate` works.
2. Reproduce list+detail requests from samples with httpx; parser; tests pass on samples.
3. Importer with cursor, backoff, raw snapshots; run `--limit 500`; verify counts; commit.
4. Run `--limit 5000`; fix breakages; commit.
5. Rules + Gemini classifier + cache; run on all imported; report totals, AI calls, tokens, cost.
6. Renewal computation + Excel export + `/radar` page.
7. Import last 90 days fully (background), continue with 8–9.
8. Full tests green, ruff clean.
9. Final PROGRESS.md summary, top 20 Radar rows, TODO.md for Phase 2 (Bitrix24 Deal creation for score ≥ 70, category→manager mapping, daily new-tender import + alerts, Telegram failure alerts, VPS deploy docs).

### Definition of Done
- `make up migrate import classify renewal export web` runs end-to-end on a clean machine.
- ≥ 90 days of completed lots imported, resumable, no duplicates.
- `out/renewal_radar.xlsx` exists with real rows; `/radar` renders them.
- Tests pass; ruff clean; no secrets in git; `STATUS: DONE` in PROGRESS.md.


### Cloud scaffold amendment — 2026-09-13
The original MVP specification above is preserved. Current authorization is scaffold and automation only. No application implementation, source collection, model classification, production deployment, or application completion is claimed. Cloud execution decisions in DECISIONS.md resolve operational ambiguities. CI secret variables replace local .env.
