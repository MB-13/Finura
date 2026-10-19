import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from doctune.core.config import Settings, get_settings
from doctune.core.errors import install_error_handlers
from doctune.core.logging import RequestIdMiddleware, configure_logging
from doctune.routers import (
    admin,
    compute,
    dataset,
    documents,
    events,
    generation,
    health,
    keys,
    me,
    notebook,
    playground,
    projects,
    storage,
    training,
)


def _scrub_sentry(event: dict, _hint: dict) -> dict:  # type: ignore[type-arg]
    request = event.get("request") or {}
    headers = request.get("headers") or {}
    for name in list(headers):
        if name.lower() in {"authorization", "cookie"}:
            headers[name] = "[redacted]"
    return event


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            traces_sample_rate=0.05,
            send_default_pii=False,
            before_send=_scrub_sentry,  # type: ignore[arg-type]
        )

    app = FastAPI(title="DocTune API", version=settings.app_version)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin, *settings.cors_extra_origins],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["authorization", "content-type", "x-request-id"],
        expose_headers=["x-request-id"],
    )
    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(projects.router)
    app.include_router(documents.router)
    app.include_router(events.router)
    app.include_router(keys.router)
    app.include_router(compute.router)
    app.include_router(generation.router)
    app.include_router(dataset.router)
    app.include_router(training.router)
    app.include_router(notebook.router)
    app.include_router(playground.router)
    app.include_router(admin.router)
    if settings.storage_backend == "local":
        app.include_router(storage.router)
    return app


app = create_app()
