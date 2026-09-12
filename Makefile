.PHONY: validate supervisor up migrate import classify renewal export web test lint
validate:
	python3 -m unittest discover -s tests_automation -v
	python3 ci/validate.py
supervisor:
	python3 ci/github_review.py
up:
	docker compose up -d --wait postgres
# Reserved product interface; source implementation is intentionally absent.
migrate import classify renewal export web test lint:
	@echo "Application phase not implemented; see PROGRESS.md. Scaffold checks: make validate."
	@exit 2
