# syntax=docker/dockerfile:1.7
# One image for API, workers, dispatcher, beat and migrations (different commands).

ARG PYTHON_IMAGE=python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754

FROM ${UV_IMAGE} AS uv

# --- build: resolve locked dependencies into a virtualenv ----------------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# --- runtime base: OS packages shared by runtime and test images ----------------------
FROM ${PYTHON_IMAGE} AS runtime-base
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd libglib2.0-0 libgomp1 tini ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 docintel \
 && useradd --system --uid 10001 --gid docintel --home-dir /app --shell /usr/sbin/nologin docintel
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH \
    WORKER_TMP_DIR=/tmp/docintel PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
WORKDIR /app

# --- test image: dev dependencies + sources (used by CI and `make test-docker`) -------
FROM runtime-base AS test
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
COPY . .
ENV PROMETHEUS_MULTIPROC_DIR=
CMD ["pytest", "-q"]

# --- runtime ----------------------------------------------------------------------------
FROM runtime-base AS runtime
COPY --from=build /opt/venv /opt/venv
COPY --chown=docintel:docintel alembic.ini ./
COPY --chown=docintel:docintel alembic ./alembic
COPY --chown=docintel:docintel app ./app
COPY --chown=docintel:docintel scripts ./scripts
COPY --chown=docintel:docintel evaluation/__init__.py evaluation/synthetic.py ./evaluation/
COPY --chown=docintel:docintel docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh && mkdir -p /tmp/docintel /tmp/prometheus && chown docintel:docintel /tmp/docintel /tmp/prometheus
USER 10001:10001
EXPOSE 8000 9100
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["api"]
