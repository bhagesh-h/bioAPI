# Docker is the only supported toolchain for bioAPI. Nothing here installs a
# Python package, creates a virtualenv or runs an interpreter on the host.

COMPOSE ?= docker compose

.PHONY: help build up down logs test test-watch cov lint format shell smoke clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build: ## Build the runtime and dev images
	$(COMPOSE) build

up: ## Serve the API on http://127.0.0.1:8000
	$(COMPOSE) up api

down: ## Stop and remove containers
	$(COMPOSE) down --remove-orphans

logs: ## Follow the API container logs
	$(COMPOSE) logs -f api

test: ## Run the full test suite with the coverage gate
	$(COMPOSE) run --rm test

cov: ## Run the tests and write an HTML coverage report to htmlcov/
	$(COMPOSE) run --rm test pytest --cov-report=html:/app/htmlcov

lint: ## Check formatting, lint rules and types
	$(COMPOSE) run --rm lint

format: ## Rewrite the source with ruff format and apply safe fixes
	$(COMPOSE) run --rm format

shell: ## Open a shell inside the dev image
	$(COMPOSE) run --rm --entrypoint sh test

smoke: ## Start the API, probe it, and tear it down
	$(COMPOSE) up -d api
	@echo "waiting for the container to report healthy..."
	@for i in $$(seq 1 30); do \
		status=$$(docker inspect --format '{{.State.Health.Status}}' bioapi 2>/dev/null || echo starting); \
		[ "$$status" = "healthy" ] && break; sleep 1; \
	done
	curl -fsS http://127.0.0.1:8000/health/ready
	@echo
	$(COMPOSE) down

clean: ## Remove containers, images and local caches
	$(COMPOSE) down --remove-orphans --rmi local --volumes
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml
