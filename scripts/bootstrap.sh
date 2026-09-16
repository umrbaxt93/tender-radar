#!/usr/bin/env bash
# Prepare a host to run Tender Radar without Docker.
#
# Idempotent: safe to re-run. It installs the project into a virtualenv, creates .env from
# the example if missing, applies migrations and runs the offline synthetic cycle so the
# install is proven before anything touches the real source or spends money.
#
#   ./scripts/bootstrap.sh                 # install and verify with synthetic data
#   ./scripts/bootstrap.sh --no-demo       # install and migrate only
#
# It never installs system packages, never writes secrets and never starts a live import.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV="${VENV:-$ROOT/.venv}"
RUN_DEMO=1
[ "${1:-}" = "--no-demo" ] && RUN_DEMO=0

say() { printf '\n==> %s\n' "$1"; }

say "Checking Python 3.12"
PY_BIN="$(command -v python3.12 || true)"
if [ -z "$PY_BIN" ]; then
  echo "python3.12 not found. Install Python 3.12 first; the stack is pinned to it." >&2
  exit 1
fi

say "Creating the virtualenv at $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  if command -v uv >/dev/null 2>&1; then uv venv --python 3.12 "$VENV"
  else "$PY_BIN" -m venv "$VENV"; fi
fi

say "Installing dependencies"
if command -v uv >/dev/null 2>&1; then uv pip install -q -p "$VENV/bin/python" -e ".[dev]"
else "$VENV/bin/python" -m pip install -q --upgrade pip && "$VENV/bin/python" -m pip install -q -e ".[dev]"; fi

if [ ! -f .env ]; then
  say "Creating .env from .env.example"
  cp .env.example .env
  chmod 600 .env
  echo "Edit .env and set DATABASE_URL before continuing. Nothing else is required for the"
  echo "offline run. .env is git-ignored; never commit it."
  exit 0
fi

# shellcheck disable=SC1091
set -a; . ./.env; set +a

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is empty in .env. Set it, then re-run." >&2
  exit 1
fi

say "Checking the database connection"
"$VENV/bin/python" -m radar health

say "Applying migrations"
"$VENV/bin/python" -m radar migrate

if [ "$RUN_DEMO" -eq 1 ]; then
  say "Proving the install with synthetic data (no source access, no cost)"
  "$VENV/bin/python" -m radar worker --fixtures samples/synthetic --mock-ai
  "$VENV/bin/python" -m radar stats
  cat <<'NEXT'

Install verified with synthetic data. Nothing above is a real procurement result.

Next, in order:
  1. Verify the public endpoint contract and record it in docs/SOURCE_API.md.
  2. Set UZEX_LIST_URL, UZEX_DETAIL_URL and CONTACT_EMAIL in .env.
  3. Import a small slice first:  .venv/bin/python -m radar import --limit 200
  4. Price your model in radar/classify/pricing.yaml, then classify without --mock-ai.
  5. Start the services:          deploy/tender-radar-{web,worker}.service
NEXT
fi
