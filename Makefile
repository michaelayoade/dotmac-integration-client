.DEFAULT_GOAL := help
.PHONY: help install poetry-lock-check lint format-check test package-check check

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n",$$1,$$2}'

install: ## Install the committed dependency graph
	poetry install

poetry-lock-check: ## Exact Poetry pin + committed lock; never regenerates
	python3 scripts/check_poetry_toolchain.py --active
	poetry check --lock

lint: ## Ruff lint
	poetry run ruff check src tests scripts

format-check: ## Formatting gate
	poetry run ruff format --check src tests scripts

test: ## Behaviour and architecture tests
	poetry run pytest tests -q

package-check: ## Build the wheel and prove its top-level namespace
	poetry build --format wheel
	poetry run python scripts/check_wheel_namespace.py $$(find dist -maxdepth 1 -name '*.whl' -print -quit)

check: poetry-lock-check lint format-check test package-check ## Full local and CI gate
