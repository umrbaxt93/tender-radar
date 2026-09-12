.PHONY: install validate supervisor up migrate import import-synthetic classify renewal export web test lint stats
VENV ?= .venv
PY ?= $(VENV)/bin/python

install:
	uv venv --python 3.12 $(VENV) || python3.12 -m venv $(VENV)
	uv pip install -p $(PY) -e ".[dev]" || $(PY) -m pip install -e ".[dev]"

validate:
	python3 -m unittest discover -s tests_automation -v
	python3 ci/validate.py

supervisor:
	python3 ci/github_review.py

up:
	docker compose up -d --wait postgres

migrate:
	$(PY) -m radar migrate

# Live import. Requires a verified public endpoint contract in docs/SOURCE_API.md
# plus UZEX_LIST_URL / UZEX_DETAIL_URL / CONTACT_EMAIL in the environment.
import:
	$(PY) -m radar import $(ARGS)

# Offline import from the labelled synthetic fixtures (never real data).
import-synthetic:
	$(PY) -m radar import --fixtures samples/synthetic $(ARGS)

stats:
	$(PY) -m radar stats

test:
	$(PY) -m pytest

lint:
	$(VENV)/bin/ruff check radar tests scripts

# Not implemented yet; see PROGRESS.md for the tracked execution order.
classify renewal export web:
	@echo "Stage not implemented yet: $@. See PROGRESS.md."
	@exit 2
