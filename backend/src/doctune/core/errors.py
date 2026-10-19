from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorOut(BaseModel):
    error: str
    message: str
    details: dict[str, Any] | None = None


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Bad request"

    def __init__(self, message: str | None = None, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.code = code or self.code
        self.details = details


class Unauthorized(AppError):
    status_code, code, message = 401, "unauthorized", "Authentication required"


class Forbidden(AppError):
    status_code, code, message = 403, "forbidden", "Not allowed"


class NotFound(AppError):
    status_code, code, message = 404, "not_found", "Not found"


class Conflict(AppError):
    status_code, code, message = 409, "conflict", "Conflict"


class LimitExceeded(AppError):
    status_code, code, message = 413, "limit_exceeded", "Limit exceeded"


class RateLimited(AppError):
    status_code, code, message = 429, "rate_limited", "Too many requests"


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorOut(error=code, message=message, details=details).model_dump(exclude_none=True)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
            fields.setdefault(loc or "_", []).append(str(err.get("msg", "invalid")))
        return JSONResponse(_body("validation_error", "Invalid request", {"fields": fields}), status_code=422)
