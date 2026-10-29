"""Celery application.

Delivery is at-least-once (acks_late + reject_on_worker_lost; Redis visibility
timeout may redeliver). PostgreSQL leases and idempotent handlers make
duplicate deliveries harmless; Celery is never assumed to be exactly-once.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.signals import setup_logging, worker_process_init, worker_ready, worker_shutting_down
from kombu import Exchange, Queue

import app.models  # noqa: F401  (register every table so foreign keys resolve)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.modules.jobs.outbox import QUEUES

settings = get_settings()

celery_app = Celery("docintel", broker=settings.broker_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=True,
    worker_prefetch_multiplier=1,
    task_track_started=False,
    task_ignore_result=True,
    result_backend=None,
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        # Must exceed the longest hard time limit, or Redis redelivers running tasks.
        "visibility_timeout": settings.celery_visibility_timeout_seconds,
        "socket_timeout": 10,
        "socket_connect_timeout": 10,
    },
    # One direct exchange per queue with a matching routing key, so
    # ``send_task(queue=...)`` always lands in the declared queue.
    task_queues=[Queue(name, Exchange(name, type="direct"), routing_key=name, durable=True) for name in QUEUES],
    task_default_queue="maintenance",
    task_default_exchange="maintenance",
    task_default_routing_key="maintenance",
    task_create_missing_queues=False,
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_max_tasks_per_child=200,
    worker_max_memory_per_child=int(os.getenv("WORKER_MAX_MEMORY_KB", "1500000")),
    beat_schedule={
        "recover-stale-work": {"task": "docintel.maintenance.recover", "schedule": 60.0, "options": {"queue": "maintenance"}},
        "cleanup-storage": {"task": "docintel.maintenance.cleanup", "schedule": 3600.0, "options": {"queue": "maintenance"}},
        "purge-outbox": {"task": "docintel.maintenance.purge", "schedule": 3600.0, "options": {"queue": "maintenance"}},
    },
)

logger = get_logger(__name__)


@setup_logging.connect
def _setup_logging(**_: object) -> None:
    # Connecting this signal stops Celery from installing its own handlers.
    configure_logging(settings.log_level, settings.log_json, service=settings.service_name)


@worker_process_init.connect
def _init_process(**_: object) -> None:
    from app.core.database import reset_engines

    configure_logging(settings.log_level, settings.log_json, service=settings.service_name)
    reset_engines()


@worker_ready.connect
def _ready(**_: object) -> None:
    configure_logging(settings.log_level, settings.log_json, service=settings.service_name)
    from app.workers.metrics_server import start_worker_metrics_server

    start_worker_metrics_server()
    logger.info("worker_ready")


@worker_shutting_down.connect
def _shutdown(**_: object) -> None:
    logger.info("worker_shutting_down")
