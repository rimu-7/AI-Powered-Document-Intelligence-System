#!/bin/sh
# Single entrypoint for all process types. tini (PID 1) forwards signals.
set -eu

# /tmp is a tmpfs when the root filesystem is read-only; recreate work dirs.
mkdir -p "${WORKER_TMP_DIR:-/tmp/docintel}"
# Fresh multiprocess metrics directory per container start.
if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
  rm -rf "${PROMETHEUS_MULTIPROC_DIR:?}"/* 2>/dev/null || true
fi

role="${1:-api}"
shift || true

case "$role" in
  api)
    # Prometheus multiprocess mode is only needed for prefork workers.
    unset PROMETHEUS_MULTIPROC_DIR
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
      --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
      --timeout-graceful-shutdown "${GRACEFUL_TIMEOUT:-30}" --no-server-header "$@"
    ;;
  worker)
    # QUEUES, CONCURRENCY and POOL are set per deployment (OCR is CPU/memory heavy).
    exec celery -A app.workers.celery_app:celery_app worker \
      --queues "${QUEUES:?QUEUES is required}" \
      --concurrency "${CONCURRENCY:-2}" --pool "${POOL:-prefork}" \
      --hostname "${WORKER_NAME:-worker}@%h" --without-gossip --without-mingle \
      --loglevel "${LOG_LEVEL:-INFO}" "$@"
    ;;
  dispatcher)
    unset PROMETHEUS_MULTIPROC_DIR
    exec python -m app.workers.dispatcher
    ;;
  beat)
    exec celery -A app.workers.celery_app:celery_app beat --loglevel "${LOG_LEVEL:-INFO}" \
      --schedule /tmp/docintel/celerybeat-schedule "$@"
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  bootstrap)
    exec python -m scripts.bootstrap "$@"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
