"""HTTP metrics middleware and the scrape endpoint — PRD-004.

Two things here are easy to get wrong and expensive to get wrong late.

**The route label must be the template.** Starlette resolves the matched route
into `scope["route"]`, whose `path_format` is `/api/v1/users/{user_id}`. The
obvious label, `scope["path"]`, is the RESOLVED path — one time series per
user id, per document id, per session token that ever appeared in a URL. That
grows without bound, is never garbage collected, and looks perfectly healthy
until the process is weeks old. A request that matched no route is labelled
`unmatched`, deliberately collapsing every 404 into one series: a scanner
probing random paths must not be able to inflate the metrics store.

**The scrape endpoint is not public.** `/metrics` tells a stranger the request
volume, the error rate, the deployed version and — for this service — how
often the reviewer is blocking answers. That is competitive and operational
intelligence, and none of it is any of the internet's business. It requires a
bearer token in production, and the app refuses to serve it at all when the
token has not been configured, on the same reasoning as PRD-005: an endpoint
that silently opens because a variable is unset is how this goes wrong.

Timing wraps `call_next` including response generation but excluding the time
the client spends reading the body, which is the number an operator wants —
a slow client should not look like a slow server.
"""

from __future__ import annotations

import logging
import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Match

from backend.observability import metrics

logger = logging.getLogger(__name__)

METRICS_PATH = "/metrics"

# Routes that raised while being matched, so the warning is emitted once each
# rather than on every request that walks past them.
_unmatchable_routes: set[str] = set()


def _route_template(request: Request) -> str:
    """The matched route's template, or `unmatched`.

    `scope["route"]` is only populated after routing, and this middleware runs
    before it, so the routes are matched here explicitly. The cost is one pass
    over the route table per request; the alternative is either a label with
    unbounded cardinality or no route label at all.
    """
    routes = getattr(request.app, "routes", None) or []
    for route in routes:
        try:
            match, _ = route.matches(request.scope)
        except Exception:
            # A route that raises while being matched is a routing bug, and it
            # will announce itself as a 500 on its own path. Here it must not
            # break the labelling of every OTHER request, so it is logged once
            # per route and skipped. Not silent — ruff's S112 is right in
            # general — and not repeated at request rate.
            name = getattr(route, "path", repr(route))
            if name not in _unmatchable_routes:
                _unmatchable_routes.add(name)
                logger.warning(
                    "metrics: route %s raised while matching; requests to it "
                    "will be labelled `unmatched`.", name,
                )
            continue
        if match is Match.FULL:
            return getattr(route, "path_format", None) or getattr(
                route, "path", "unmatched"
            )
    return "unmatched"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == METRICS_PATH:
            # Scraping is not traffic. Counting it would put a floor under the
            # request rate proportional to the scrape interval, and make an
            # idle service look busy.
            return await call_next(request)

        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            metrics.record_http(
                method=request.method,
                route=_route_template(request),
                status=status,
                duration_s=time.perf_counter() - started,
            )


def install(app, *, token: str | None, is_production: bool) -> None:
    """Add the middleware and the scrape endpoint.

    `token` is passed in rather than read from settings so that this is
    testable without an environment, and so the decision about what happens
    when it is missing lives in one visible place.
    """
    app.add_middleware(MetricsMiddleware)

    if not token and is_production:
        # Not an exception: metrics are not worth refusing to boot over, and a
        # service that will not start because monitoring is unconfigured is a
        # service that gets started with monitoring deleted. Refuse the
        # ENDPOINT, loudly, and serve everything else.
        logger.error(
            "%s is disabled: METRICS__TOKEN is not set. Metrics reveal request "
            "volume, error rates and how often answers are being withheld, so "
            "the endpoint is not served without authentication rather than "
            "served openly.",
            METRICS_PATH,
        )

    @app.get(METRICS_PATH, include_in_schema=False)
    async def scrape(request: Request) -> Response:
        if not token:
            if is_production:
                return PlainTextResponse(
                    "metrics are not configured", status_code=404,
                )
            # Development: open, because a local Prometheus with a token is
            # friction nobody accepts, and there is nothing here to protect.
            body, content_type = metrics.render()
            return Response(content=body, media_type=content_type)

        provided = request.headers.get("authorization", "")
        scheme, _, presented = provided.partition(" ")
        # Constant time: a scrape endpoint is unauthenticated by definition
        # until this check passes, so it is directly attacker-reachable.
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            presented, token,
        ):
            # 404, not 401. An unauthenticated caller learns nothing about
            # whether metrics exist here at all.
            return PlainTextResponse("not found", status_code=404)

        body, content_type = metrics.render()
        return Response(content=body, media_type=content_type)


__all__ = ["METRICS_PATH", "MetricsMiddleware", "install"]
