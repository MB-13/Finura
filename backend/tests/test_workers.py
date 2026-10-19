from doctune.workers.celery_app import QUEUES, app
from doctune.workers.tasks.system import ping


def test_ping_task_runs() -> None:
    assert ping.apply().get() == "pong"


def test_queues_and_routes() -> None:
    assert set(QUEUES) == {"parse", "llm", "embed", "default", "inference"}
    routes = app.conf.task_routes
    assert routes["doctune.workers.tasks.parse.*"] == {"queue": "parse"}
    assert app.conf.task_acks_late is True
    assert app.conf.worker_prefetch_multiplier == 1
