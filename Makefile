.PHONY: install bootstrap validate supervisor up up-all down logs migrate import \
        import-synthetic reparse worker demo classify renewal export web stats health test lint
VENV ?= .venv
PY ?= $(VENV)/bin/python
ARGS ?=

install:
	uv venv --python 3.12 $(VENV) || python3.12 -m venv $(VENV)
	uv pip install -p $(PY) -e ".[dev]" || $(PY) -m pip install -e ".[dev]"

validate:
	python3 -m unittest discover -s tests_automation -v
	python3 ci/validate.py

supervisor:
	python3 ci/github_review.py

# Prepare a host without Docker: virtualenv, .env, migrations, synthetic verification.
bootstrap:
	./scripts/bootstrap.sh $(ARGS)

# Database only, for local development against the host virtualenv.
up:
	docker compose up -d --wait postgres

# The whole platform in containers: database, migrations, worker and web.
up-all:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

migrate:
	$(PY) -m radar migrate

# Live import. Requires a verified public endpoint contract in docs/SOURCE_API.md plus
# UZEX_LIST_URL / UZEX_DETAIL_URL / CONTACT_EMAIL. Refuses to start without them.
import:
	$(PY) -m radar import $(ARGS)

# Offline import from the labelled synthetic fixtures. Never real data.
import-synthetic:
	$(PY) -m radar import --fixtures samples/synthetic $(ARGS)

# Rebuild rows from stored snapshots after a parser or mapping fix. No network access.
reparse:
	$(PY) -m radar reparse $(ARGS)

# One process, one cycle: import, classify, renewal, export. Add --interval N to repeat.
worker:
	$(PY) -m radar worker $(ARGS)

classify:
	$(PY) -m radar classify $(ARGS)

renewal:
	$(PY) -m radar renewal

export:
	$(PY) -m radar export

web:
	$(PY) -m radar web $(ARGS)

stats:
	$(PY) -m radar stats

health:
	$(PY) -m radar health

# End-to-end offline run: schema, synthetic import, mock classification, renewal, Excel.
demo: migrate import-synthetic
	$(PY) -m radar classify --mock-ai
	$(PY) -m radar renewal
	$(PY) -m radar export
	$(PY) -m radar stats

test:
	$(PY) -m pytest

lint:
	$(VENV)/bin/ruff check radar tests scripts
