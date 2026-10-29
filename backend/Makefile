.DEFAULT_GOAL := help
COMPOSE := docker compose
API ?= http://localhost:8000

help:            ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

init:            ## Create/extend .env with generated local secrets (never overwrites keys)
	python3 scripts/init_env.py

up:              ## Build and start the stack
	$(COMPOSE) up --build -d

down:            ## Stop the stack (keeps volumes)
	$(COMPOSE) down

destroy:         ## Stop the stack and DELETE all local data volumes
	$(COMPOSE) down -v

logs:            ## Follow logs of all services
	$(COMPOSE) logs -f --tail=100

ps:              ## Service status
	$(COMPOSE) ps

migrate:         ## Apply database migrations
	$(COMPOSE) run --rm migrate

bootstrap:       ## Dev-only: create demo admin (password printed once) + demo documents
	$(COMPOSE) --profile tools run --rm bootstrap

smoke:           ## End-to-end smoke test against $(API)
	set -a; . ./.env; set +a; uv run python -m scripts.smoke_test --api $(API)

test:            ## Unit + integration tests (Testcontainers; needs Docker)
	uv run pytest

test-unit:       ## Unit tests only (no Docker needed)
	uv run pytest tests/unit

test-docker:     ## Full suite (incl. OCR tests) inside the test image, against the running compose data services
	docker build --target test -t docintel-ai:test .
	-$(COMPOSE) exec -T postgres createdb -U docintel docintel_test 2>/dev/null
	set -a; . ./.env; set +a; docker run --rm --network docintel_data \
	  -e TEST_DATABASE_URL=postgresql+asyncpg://docintel:$$POSTGRES_PASSWORD@postgres:5432/docintel_test \
	  -e TEST_REDIS_URL=redis://redis:6379/15 -e TEST_S3_ENDPOINT_URL=http://minio:9000 \
	  -e TEST_S3_ACCESS_KEY=$$MINIO_ROOT_USER -e TEST_S3_SECRET_KEY=$$MINIO_ROOT_PASSWORD \
	  docintel-ai:test pytest -q -p no:warnings

lint:            ## Ruff + mypy
	uv run ruff check . && uv run ruff format --check . && uv run mypy app

evaluate:        ## End-to-end evaluation on the labeled dataset against the running stack
	uv run python -m evaluation.evaluate --api $(API)

benchmark:       ## Large-document throughput benchmark (1,000-page PDF) against the running stack
	set -a; . ./.env; set +a; uv run python -m scripts.benchmark --api $(API)

backup-db:       ## pg_dump to ./backups (custom format)
	mkdir -p backups && $(COMPOSE) exec -T postgres pg_dump -U docintel -d docintel -Fc > backups/docintel-$$(date +%Y%m%d%H%M%S).dump

restore-db:      ## Restore FILE=backups/x.dump into the running database
	$(COMPOSE) exec -T postgres pg_restore -U docintel -d docintel --clean --if-exists < $(FILE)

.PHONY: help init up down destroy logs ps migrate bootstrap smoke test test-unit test-docker lint evaluate benchmark backup-db restore-db
