"""Prometheus endpoint for Celery workers (multiprocess-safe)."""

from __future__ import annotations

import os

from prometheus_client import CollectorRegistry, start_http_server

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def start_worker_metrics_server() -> None:
    port = get_settings().metrics_port
    if port <= 0:
        return
    registry = None
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    try:
        if registry is not None:
            start_http_server(port, registry=registry)
        else:
            start_http_server(port)
        logger.info("worker_metrics_listening", extra={"port": port})
    except OSError:
        logger.warning("worker_metrics_port_in_use", extra={"port": port})
