from celery import Celery
from kombu import Queue

from doctune.core.config import get_settings
from doctune.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)

QUEUES = ("parse", "llm", "embed", "default", "inference")

app = Celery(
    "doctune",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "doctune.workers.tasks.system",
        "doctune.workers.tasks.parse",
        "doctune.workers.tasks.embed",
        "doctune.workers.tasks.housekeeping",
        "doctune.workers.tasks.keys",
        "doctune.workers.tasks.notify",
        "doctune.workers.tasks.generate",
        "doctune.workers.tasks.finalize",
        "doctune.workers.tasks.models",
        "doctune.workers.tasks.training",
        "doctune.workers.tasks.kaggle",
        "doctune.workers.tasks.inference",
    ],
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_default_queue="default",
    task_queues=[Queue(name) for name in QUEUES],
    # tasks pick their queue by module; new task modules get a route here
    task_routes={
        "doctune.workers.tasks.parse.*": {"queue": "parse"},
        "doctune.workers.tasks.generate.*": {"queue": "llm"},
        "doctune.workers.tasks.keys.*": {"queue": "llm"},
        "doctune.workers.tasks.kaggle.*": {"queue": "default"},
        "doctune.workers.tasks.finalize.*": {"queue": "default"},
        "doctune.workers.tasks.embed.*": {"queue": "embed"},
        "doctune.workers.tasks.inference.*": {"queue": "inference"},
        "doctune.workers.tasks.models.score_evaluation": {"queue": "llm"},
        "doctune.workers.tasks.models.convert_adapter": {"queue": "inference"},
    },
    beat_schedule={
        "beat-heartbeat": {"task": "doctune.workers.tasks.system.beat_heartbeat", "schedule": 300.0},
        "resume-generation": {"task": "doctune.workers.tasks.generate.resume_runs", "schedule": 300.0},
        "monitor-heartbeats": {"task": "doctune.workers.tasks.training.monitor_heartbeats", "schedule": 60.0},
        "token-reminders": {"task": "doctune.workers.tasks.training.token_reminders", "schedule": 6 * 3600.0},
        "poll-kaggle": {"task": "doctune.workers.tasks.kaggle.poll_kaggle_jobs", "schedule": 120.0},
        "playground-idle": {"task": "doctune.workers.tasks.inference.stop_idle", "schedule": 120.0},
        "cleanup-retention": {"task": "doctune.workers.tasks.training.cleanup_retention", "schedule": 24 * 3600.0},
    },
)
