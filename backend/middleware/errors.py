"""Error handling — DEM-008.

What this replaces
------------------
Roughly a dozen handlers ended with:

    raise HTTPException(status_code=500, detail=str(e))

`str(e)` on a SQLAlchemy error includes the connection string. On a Pydantic
error it includes the internal model shape. On a Groq error it can include
request metadata. All of it went straight to the browser.

Now: the detail is logged with a correlation id, and the client receives the id
and a neutral message. A user reporting "error a3f8c210" is enough to find the
exact log line, without the error itself being an information-disclosure
channel.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"

GENERIC_MESSAGE = (
    "Something went wrong on our side. Nothing was changed. "
    "Quote the reference below if you get in touch."
)


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:8]


async def correlation_middleware(
    request: Request, call_next: Callable[[Request], Awaitable]
):
    """Attach a correlation id to every request and echo it on the response."""
    cid = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
    request.state.correlation_id = cid
    response = await call_next(request)
    response.headers[CORRELATION_HEADER] = cid
    return response


def install_error_handlers(app: FastAPI) -> None:
    app.middleware("http")(correlation_middleware)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Deliberate HTTPExceptions keep their message — a 404 or a 400 raised
        by our own code is meant to be read by the user."""
        cid = getattr(request.state, "correlation_id", new_correlation_id())
        if exc.status_code >= 500:
            logger.error(
                "correlation_id=%s %s %s -> %s: %s",
                cid, request.method, request.url.path, exc.status_code, exc.detail,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": GENERIC_MESSAGE, "correlation_id": cid},
                headers={CORRELATION_HEADER: cid},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "correlation_id": cid},
            headers={CORRELATION_HEADER: cid},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Anything uncaught. The exception text is logged, never returned."""
        cid = getattr(request.state, "correlation_id", new_correlation_id())
        logger.exception(
            "correlation_id=%s unhandled on %s %s",
            cid, request.method, request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": GENERIC_MESSAGE, "correlation_id": cid},
            headers={CORRELATION_HEADER: cid},
        )
