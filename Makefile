.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose
DEV := $(COMPOSE) -f compose.yaml -f compose.dev.yaml
API ?= http://localhost:8000
WEB ?= http://localhost:3000
LOAD_ENV := set -a; . ./.env; set +a

help: ## Show all targets
	@awk 'BEGIN {FS = ":.*?## "} /^##@/ {printf "\n%s\n", substr($$0, 5)} /^[a-zA-Z_-]+:.*?## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Setup
init: ## Create .env from .env.example and fill in generated local secrets (never overwrites values)
	@test -f .env || cp .env.example .env
	python3 backend/scripts/init_env.py .env

install: ## Install host toolchains for development and tests (uv + pnpm)
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile

##@ Run
up: ## Build both images and start the whole system (web on :3000, API on :8000)
	$(COMPOSE) up --build -d

dev: ## Same, plus API hot reload and data services on localhost (compose.dev.yaml)
	$(DEV) up --build -d

web-dev: ## Next.js dev server on the host against the API on $(API)
	cd frontend && API_INTERNAL_URL=$(API) pnpm run dev

down: ## Stop everything (keeps data volumes)
	$(COMPOSE) down

destroy: ## Stop everything and DELETE all local data volumes
	$(COMPOSE) down -v

logs: ## Follow logs (all services, or S=api)
	$(COMPOSE) logs -f --tail=100 $(S)

ps: ## Service status
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(COMPOSE) run --rm migrate

bootstrap: ## Dev only: create a demo admin (password printed once) and demo documents
	$(COMPOSE) --profile tools run --rm bootstrap

##@ Quality
lint: lint-backend lint-frontend ## All linters, formatters and type checks

lint-backend: ## Ruff (lint + format) and mypy
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app

lint-frontend: ## ESLint, Prettier and TypeScript
	cd frontend && pnpm run lint && pnpm run format:check && pnpm run typecheck

test: test-backend test-frontend ## All tests on the host

test-backend: ## Backend unit + integration tests (Testcontainers: needs Docker)
	cd backend && uv run pytest

test-backend-unit: ## Backend unit tests only (no Docker)
	cd backend && uv run pytest tests/unit

test-frontend: ## Frontend unit and component tests (Vitest)
	cd frontend && pnpm run test

test-docker: ## Both suites inside their images; backend runs against the running data services
	docker build --target test -t docintel-backend:test backend
	docker build --target test -t docintel-frontend:test frontend
	-$(COMPOSE) exec -T postgres createdb -U docintel docintel_test 2>/dev/null
	$(LOAD_ENV); docker run --rm --network docintel_data \
	  -e TEST_DATABASE_URL=postgresql+asyncpg://docintel:$$POSTGRES_PASSWORD@postgres:5432/docintel_test \
	  -e TEST_REDIS_URL=redis://redis:6379/15 -e TEST_S3_ENDPOINT_URL=http://minio:9000 \
	  -e TEST_S3_ACCESS_KEY=$$MINIO_ROOT_USER -e TEST_S3_SECRET_KEY=$$MINIO_ROOT_PASSWORD \
	  docintel-backend:test pytest -q -p no:warnings
	docker run --rm docintel-frontend:test

test-e2e: ## Playwright end-to-end + accessibility tests against the running system ($(WEB))
	cd frontend && pnpm exec playwright install chromium && PLAYWRIGHT_BASE_URL=$(WEB) pnpm run test:e2e

smoke: ## API smoke test: upload → OCR → extraction → validation → search → reconciliation
	$(LOAD_ENV); cd backend && uv run python -m scripts.smoke_test --api $(API)

api-types: ## Regenerate frontend API types from the backend's OpenAPI schema
	cd backend && ENV_FILE= uv run python -m scripts.export_openapi ../frontend/openapi.json
	cd frontend && pnpm run gen:api

##@ Data and evaluation
evaluate: ## Labeled dataset through the running system → accuracy, timing, success/failure rates
	cd backend && uv run python -m evaluation.evaluate --api $(API)

benchmark: ## 1,000-page PDF throughput benchmark against the running system
	$(LOAD_ENV); cd backend && uv run python -m scripts.benchmark --api $(API)

backup-db: ## pg_dump to ./backups (custom format)
	mkdir -p backups && $(COMPOSE) exec -T postgres pg_dump -U docintel -d docintel -Fc > backups/docintel-$$(date +%Y%m%d%H%M%S).dump

restore-db: ## Restore FILE=backups/x.dump into the running database
	$(COMPOSE) exec -T postgres pg_restore -U docintel -d docintel --clean --if-exists < $(FILE)

.PHONY: help init install up dev web-dev down destroy logs ps migrate bootstrap lint lint-backend lint-frontend \
	test test-backend test-backend-unit test-frontend test-docker test-e2e smoke api-types evaluate benchmark backup-db restore-db
