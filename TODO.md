# TODO

## Blocked on source access
- [x] Verify the public list/detail endpoint contract from a network that can reach
      xarid.uzex.uz, fill docs/SOURCE_API.md, adjust radar/source/uzex_mapping.yaml.
- [x] Commit sanitized real fixtures and replace the synthetic golden set in
      samples/synthetic/known_lots.md with verified IT and non-IT lots.
- [ ] Import 90 days of real completed lots, then re-measure rule coverage, AI spend and the
      coverage percentages reported by `stats`.
- [ ] Re-check the renewal lifecycle table against what real purchase intervals show.

## Blocked on credentials or cost approval
- [x] Add the chosen Gemini model price to radar/classify/pricing.yaml from the official
      pricing page, with the date it was checked.
- [ ] Run one small paid batch and compare real spend against the ledger.
- [ ] Provider-side spending controls before enabling any recurring paid job.

## Ready for host deployment (Hostinger VPS 93.127.213.246)
- [ ] Build the image and run `docker compose up -d --build` on the target host (Hostinger VPS 93.127.213.246).
- [ ] Execute docs/DEPLOYMENT.md end to end on the target host, then correct it from what
      actually happened.
- [ ] Put the reverse proxy and an access control (nginx TLS + basic auth) in front of the web process before it is
      reachable from anywhere but localhost. The application has no built-in authentication.
- [ ] Nightly pg_dump off the host, and a tested restore.

## Open code work
- [ ] Parent organization relationships, so a ministry and its subordinate bodies can be read
      as one customer where that is the right view.
- [x] Product normalization to brand, model and licence term, which price analysis depends on.
- [ ] Supplier side analysis once award data proves rich enough to support it.

## Phase 2
- [x] Bitrix24 idempotent lead/deal/task creation module (`radar/crm.py`) ported from parent project with unique constraint per procedure.
- [ ] Category to manager mapping and automatic scoring feedback loop into CRM.
- [ ] Daily import and alerts, competitor and price intelligence.

## Future Phase: E-IMZO Elektron Kalit Autentifikatsiyasi (Deferred)
- [ ] E-IMZO orqali Toshkent tovar xomashyo birjasi davlat xaridlari portaliga (xarid.ebirja.uz) ulanish va yopiq shartnomalarni yuklab tahlil qilish moduli.
- [ ] E-IMZO brauzer plagini / E-IMZO daemon (Port 64443 / 127.0.0.1) bilan integratsiya. Hozirda Faza 0 AppSec audit talablariga binoan interfeysdan olib tashlangan va alohida faza sifatida rejalashtirilgan.

## Blocked on an action outside this repository (2026-11-16)
- [ ] **Hostinger SSH access** — re-enable it in hPanel (Advanced → SSH Access). The deploy key still authenticates, but the account's login shell is `/sbin/nologin` and the sftp subsystem is closed, so `scp` cannot start a remote process and `softy.uz/radar/` has served the 18 October page ever since. No code change can work around this; see DECISIONS.md, 2026-11-16.
- [ ] **E-Birja cabinet export importer** — the contract list endpoints are a 404 and two CAPTCHA walls, so the 32 491 historical contracts have no API route left. A cabinet export file is the authorised route (CLAUDE.md), and an importer for it is the replacement for `fetch_shop_contracts`.
- [ ] **`GEMINI_API_KEY` is invalid** (`401 UNAUTHENTICATED`), so the AI advisor silently falls back to local reasoning and `ai_cost_ledger` stays empty.

## Found while fixing E-Birja, not yet addressed (2026-11-16)
- [ ] Two `source='cooperation'` rows (`source_id` 10650 and 9814, both FortiGate) carry `status='COMPLETED'` and a completion date, which `parse_cooperation_row` cannot produce — it hardcodes `PLANNED` and `completed_at=None`. They predate the cooperation importer, so something else wrote them under that source name. Worth identifying before they are read as completed contracts by the renewal radar.
- [ ] `parse_datetime` reads a naive source timestamp as UTC, but UZEX and E-Birja both publish Tashkent local time (UTC+5). Every one of the 113 000 stored rows shares the convention, so this is consistent rather than selectively wrong, and changing it is a project-wide migration — but an auction `deadline_at` is now five hours off the real bid deadline, which matters more than a completion date being off.
