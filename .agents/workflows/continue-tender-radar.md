---
description: Continue the tender-radar project from docs/HANDOFF.md, one task at a time
---

# Continue tender-radar

Read `docs/HANDOFF.md` fully before doing anything. Then `AGENTS.md`, `docs/SPEC.md`,
`PROGRESS.md`, `DECISIONS.md`, `TODO.md`. The rules in `.agents/rules/tender-radar.md`
are binding for every step below.

## 0. Environment
- Confirm PostgreSQL 16 is reachable: `python -m radar health` (needs `DATABASE_URL`).
  If not, on Linux/WSL run `bash scripts/agent_env_setup.sh`; on Windows start the database
  with `docker compose up -d --wait postgres` and set `DATABASE_URL` in `.env`.
- `make install && make test lint validate` must be green before any change.

## 1. Pick the first unfinished task
Tasks are T1..T8 in `docs/HANDOFF.md`. Take the first one whose acceptance check is not met.
Do not skip ahead. Do not redo a task PROGRESS.md marks DONE.

## 2. Source work (T1) — public pages only
- Open the source in the browser **without logging in**. If the completed-lots listing is
  visible without a login, capture the list request and one detail request (DevTools →
  Network → Fetch/XHR → Copy as cURL) and their JSON responses.
- Strip `Cookie`, `Authorization`, tokens and personal data. Save under `samples/`
  (never under `samples/synthetic/`).
- Fill `docs/SOURCE_API.md`. Adjust `radar/source/uzex_mapping.yaml`. Make
  `tests/test_parser.py` pass on the real samples.
- If the listing needs a login, E-IMZO or a CAPTCHA: stop, record that in
  `docs/SOURCE_API.md`, and switch to T2 (file import of an export the owner downloads).
  Never automate a login.

## 3. Before every commit
- `make test lint validate` green.
- PROGRESS.md and TODO.md updated with what was actually run; DECISIONS.md appended for any
  non-obvious choice.
- No `.env`, keys or unsanitized responses in the diff.
- Commit on the current branch. Do not merge to `main`, do not force-push, do not deploy.

## 4. Report
End with: what was verified (commands and numbers), what is blocked and what unblocks it.
Synthetic data is always called synthetic.
