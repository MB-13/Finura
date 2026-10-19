import structlog

from doctune.inference import manager
from doctune.workers.celery_app import app

log = structlog.get_logger()


@app.task(name="doctune.workers.tasks.inference.ensure_loaded", soft_time_limit=600, time_limit=660)
def ensure_loaded(key: str, base_repo: str, base_file: str, adapter_key: str) -> bool:
    try:
        manager.load(key, base_repo, base_file, adapter_key)
    except Exception:
        log.exception("playground_load_failed", key=key)
        return False
    return True


@app.task(name="doctune.workers.tasks.inference.stop_idle")
def stop_idle() -> bool:
    return manager.stop_if_idle()
