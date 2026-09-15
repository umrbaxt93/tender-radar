#!/usr/bin/env bash
# Prepare an agent sandbox (Codex, Claude Code, Antigravity, CI) to run this project.
# Idempotent. Installs PostgreSQL 16 if missing (needs root and apt), starts it, creates the
# dev and test databases, builds the virtualenv and prints the environment to export.
#
#   bash scripts/agent_env_setup.sh
#   eval "$(bash scripts/agent_env_setup.sh --print-env)"
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DB_USER=tender; DB_PASS=tender; DB_MAIN=tender_radar; DB_TEST=tender_radar_test
DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_MAIN"
TEST_DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_TEST"

if [ "${1:-}" = "--print-env" ]; then
  echo "export DATABASE_URL=$DATABASE_URL"
  echo "export TEST_DATABASE_URL=$TEST_DATABASE_URL"
  exit 0
fi

say() { printf '\n==> %s\n' "$1"; }

say "PostgreSQL 16"
if ! command -v pg_lsclusters >/dev/null 2>&1; then
  if [ "$(id -u)" -ne 0 ]; then echo "need root to install PostgreSQL" >&2; exit 1; fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq && apt-get install -y -qq postgresql-16 postgresql-contrib >/dev/null
fi
if pg_lsclusters | grep -q "16 .*down"; then pg_ctlcluster 16 main start; fi
pg_lsclusters | tail -n +2

say "Databases"
su_psql() { su postgres -c "psql -v ON_ERROR_STOP=1 -qtAc \"$1\""; }
if [ "$(su_psql "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'")" != "1" ]; then
  su_psql "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' CREATEDB"
fi
for db in "$DB_MAIN" "$DB_TEST"; do
  if [ "$(su_psql "SELECT 1 FROM pg_database WHERE datname='$db'")" != "1" ]; then
    su_psql "CREATE DATABASE $db OWNER $DB_USER"
  fi
done
psql "$DATABASE_URL" -qtAc "SELECT version()" | cut -d, -f1

say "Python 3.12 virtualenv"
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then uv venv --python 3.12 .venv
  else python3.12 -m venv .venv; fi
fi
if command -v uv >/dev/null 2>&1; then uv pip install -q -p .venv/bin/python -e ".[dev]"
else .venv/bin/python -m pip install -q -e ".[dev]"; fi
.venv/bin/python --version

say "Checks"
export DATABASE_URL TEST_DATABASE_URL
.venv/bin/python -m radar migrate >/dev/null 2>&1
.venv/bin/ruff check radar tests scripts
.venv/bin/pytest -q 2>&1 | grep -E "passed|failed"
python3 ci/validate.py | tail -1

cat <<EOT

Ready. Export these in your shell (or: eval "\$(bash scripts/agent_env_setup.sh --print-env)"):
  export DATABASE_URL=$DATABASE_URL
  export TEST_DATABASE_URL=$TEST_DATABASE_URL
Then: make demo, make web, make test
EOT
