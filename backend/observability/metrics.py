"""Metrics — PRD-004.

What is worth measuring here, and what is not
----------------------------------------------
The default instinct is request rate, error rate and latency, and those are
here. But they would not have caught a single defect this project has actually
found. A service can serve every request in 200ms with a 200 status and be
telling people the wrong tax.

So the metrics that lead are the ones that watch the safety properties:

  finsage_answers_total{outcome}      served / amended / withheld
  finsage_review_findings_total{...}  what the reviewers are catching
  finsage_redrafts_total              how often the first draft was blocked

A rising `withheld` rate means the analyst has started producing answers the
reviewer will not stand behind — the single most important thing to know about
this system, and until now nothing anywhere reported it. A withheld rate that
drops to zero is just as interesting: either the model got better or the
reviewer stopped working, and those are worth being able to tell apart.

`fabricated_figure` deserves its own attention. `numeric_provenance` is the
mechanical guarantee that no rupee figure originates from a language model. In
the eval suite that is checked. In production it was unobserved.

Cardinality is a correctness property, not a tuning knob
----------------------------------------------------------
Prometheus keeps one time series per distinct label combination, forever, in
memory. A label whose values come from user input — a user id, a query, a raw
URL path — is an unbounded memory leak that looks fine in testing and takes
the process down in production after a few weeks.

That is too easy to get wrong by accident, so it is enforced rather than
documented: `_LABEL_VALUES` declares the permitted values for every label, and
`_checked()` drops a sample whose label is not in the set, loudly, once. The
HTTP middleware labels by ROUTE TEMPLATE (`/api/v1/users/{user_id}`) and never
by the resolved path, which is the same bug in its most common disguise.

Recording must never break a request
--------------------------------------
Every public function here swallows its own exceptions. A metrics bug that
500s the endpoint it is measuring is worse than having no metrics. But
swallowing is not silence: the first failure of each kind is logged, and
`finsage_metrics_errors_total` counts the rest, so a permanently broken
recorder is visible rather than merely quiet.

Multiprocess deployments
--------------------------
Under gunicorn with several workers, each worker holds its own registry and a
scrape reaches whichever one the load balancer picks, so counters appear to
jump backwards. `prometheus_client` solves this with
`PROMETHEUS_MULTIPROC_DIR`; `multiprocess_mode_note()` states the requirement
rather than pretending a single-process registry is enough.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterable
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

# One registry owned by this module rather than the library default, so tests
# can build a fresh one and so nothing a dependency happens to register leaks
# into our scrape.
REGISTRY = CollectorRegistry()

# ── the closed sets ─────────────────────────────────────────────────────────
# Every label value that may ever appear. Anything else is dropped rather than
# recorded: an unbounded label is a memory leak with a delayed fuse.

_LABEL_VALUES: dict[str, frozenset[str]] = {
    "outcome": frozenset({"served", "amended", "withheld", "failed"}),
    "verdict": frozenset({"block", "amend", "flag"}),
    "category": frozenset({
        "fabricated_figure", "omitted_option", "dropped_window",
        "misleading_framing", "invalid_citation", "out_of_scope",
        "unasked_question", "documentation_risk",
    }),
    "reviewer": frozenset({"ca", "risk"}),
    "method": frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD",
                         "OPTIONS"}),
    "kind": frozenset({"label_not_permitted", "record_failed"}),
}

_warned: set[str] = set()


def _warn_once(key: str, message: str, *args: Any) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(message, *args)


def _permitted(label: str, value: str) -> bool:
    allowed = _LABEL_VALUES.get(label)
    if allowed is None or value in allowed:
        return True
    _warn_once(
        f"label:{label}:{value}",
        "metrics: dropping sample with %s=%r, which is not in the permitted "
        "set. An unbounded label value is a memory leak, so the sample is "
        "discarded rather than recorded. Permitted: %s",
        label, value, sorted(allowed),
    )
    metrics_errors.labels(kind="label_not_permitted").inc()
    return False


# ── the safety metrics ──────────────────────────────────────────────────────

answers = Counter(
    "finsage_answers_total",
    "Answers by what the review protocol did to them.",
    ["outcome"],
    registry=REGISTRY,
)

review_findings = Counter(
    "finsage_review_findings_total",
    "Reviewer objections, by severity and kind. `fabricated_figure` rising is "
    "the signal that matters most: it means figures are reaching the draft "
    "without tool grounding.",
    ["verdict", "category", "reviewer"],
    registry=REGISTRY,
)

redrafts = Counter(
    "finsage_redrafts_total",
    "Drafts blocked on the first pass and sent back to the analyst.",
    registry=REGISTRY,
)

llm_calls = Counter(
    "finsage_llm_calls_total",
    "Language model invocations. Divided by finsage_answers_total this is the "
    "cost per answered question.",
    registry=REGISTRY,
)

pipeline_latency = Histogram(
    "finsage_pipeline_latency_seconds",
    "Analyst → review → answer, end to end.",
    # Bucketed around the 3s p95 budget DEM-005 has to meet, not around the
    # library defaults, which top out at 10s and would put every interesting
    # value in one bucket.
    buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 15.0, 30.0, 60.0),
    registry=REGISTRY,
)

# ── the ordinary ones ───────────────────────────────────────────────────────

http_requests = Counter(
    "finsage_http_requests_total",
    "HTTP requests by route TEMPLATE — never the resolved path, which would "
    "create one series per user id.",
    ["method", "route", "status"],
    registry=REGISTRY,
)

http_latency = Histogram(
    "finsage_http_request_seconds",
    "HTTP request duration by route template.",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

metrics_errors = Counter(
    "finsage_metrics_errors_total",
    "Failures inside the metrics layer itself. Non-zero means some other "
    "metric on this page is undercounting.",
    ["kind"],
    registry=REGISTRY,
)

build_info = Gauge(
    "finsage_build_info",
    "Always 1. The labels carry the version so a dashboard can tell which "
    "build produced a change in any other series.",
    ["version", "rules_version"],
    registry=REGISTRY,
)


# ── recording ───────────────────────────────────────────────────────────────

def record_pipeline_result(result: Any) -> None:
    """Everything one pipeline run says about the system's health.

    Takes the result object rather than loose arguments so a caller cannot
    record the latency and forget the verdicts — the interesting failures are
    all in the parts people forget.
    """
    try:
        answer = getattr(result, "answer", None)

        if answer is None:
            outcome = "failed"
        elif getattr(answer, "withheld", False):
            outcome = "withheld"
        elif getattr(answer, "notes", None):
            # `apply` attaches the reviewer's caveats verbatim as notes, so a
            # non-empty notes list is exactly the amend/flag path.
            outcome = "amended"
        else:
            outcome = "served"

        if _permitted("outcome", outcome):
            answers.labels(outcome=outcome).inc()

        if getattr(answer, "redrafted", False):
            redrafts.inc()

        calls = getattr(result, "llm_calls", 0) or 0
        if calls:
            llm_calls.inc(calls)

        latency_ms = getattr(result, "total_latency_ms", None)
        if latency_ms:
            pipeline_latency.observe(latency_ms / 1000.0)

        for review in getattr(result, "reviews", None) or []:
            record_findings(getattr(review, "findings", None) or [])

    except Exception:
        _warn_once(
            "record_pipeline_result",
            "metrics: failed to record a pipeline result; the request is "
            "unaffected and this is logged once per process.",
        )
        _count_error()


def record_findings(findings: Iterable[Any]) -> None:
    try:
        for finding in findings:
            verdict = _enum_value(getattr(finding, "verdict", None))
            category = _enum_value(getattr(finding, "category", None))
            reviewer = str(getattr(finding, "reviewer", "ca") or "ca")
            if (
                _permitted("verdict", verdict)
                and _permitted("category", category)
                and _permitted("reviewer", reviewer)
            ):
                review_findings.labels(
                    verdict=verdict, category=category, reviewer=reviewer,
                ).inc()
    except Exception:
        _warn_once("record_findings", "metrics: failed to record findings.")
        _count_error()


def record_http(
    *, method: str, route: str, status: int, duration_s: float,
) -> None:
    """One HTTP request.

    `route` must be the template. Passing `request.url.path` here is the
    cardinality bug this module exists to prevent, so an unmatched request is
    recorded as the literal string "unmatched" rather than as its own series.
    """
    try:
        method = (method or "").upper()
        if not _permitted("method", method):
            return
        http_requests.labels(
            method=method, route=route, status=str(status),
        ).inc()
        http_latency.labels(method=method, route=route).observe(duration_s)
    except Exception:
        _warn_once("record_http", "metrics: failed to record an HTTP request.")
        _count_error()


def _count_error() -> None:
    """The bottom of the stack.

    Ruff asks for the exception to be logged here (S110) and it is right
    almost everywhere — but not here. This is the handler the OTHER handlers
    call, so logging from it means a failure in the logging subsystem is
    reported by logging, which recurses. Nothing is swallowed in practice:
    every caller has already emitted a `_warn_once` before reaching this
    line, so the incident is on the record and this is only the tally.
    """
    with contextlib.suppress(Exception):
        metrics_errors.labels(kind="record_failed").inc()


def _enum_value(value: Any) -> str:
    """`Verdict.BLOCK` and `"block"` must produce the same label.

    `str(Verdict.BLOCK)` is `"Verdict.BLOCK"` on a plain Enum, and this file
    must not depend on `review_protocol` deriving from `str` — that is exactly
    the kind of coupling that turns a harmless refactor into a silently empty
    dashboard.
    """
    if value is None:
        return ""
    return str(getattr(value, "value", value))


class _Timer:
    """`with observe_pipeline(): ...` for callers that do not build a result."""

    __slots__ = ("_started",)

    def __enter__(self) -> _Timer:
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            pipeline_latency.observe(time.perf_counter() - self._started)
        except Exception:
            _count_error()


def observe_pipeline() -> _Timer:
    return _Timer()


# ── exposition ──────────────────────────────────────────────────────────────

def render() -> tuple[bytes, str]:
    """The scrape body and its content type."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def set_build_info(version: str, rules_version: str) -> None:
    try:
        build_info.labels(version=version, rules_version=rules_version).set(1)
    except Exception:
        _count_error()


def multiprocess_mode_note() -> str:
    """Why a multi-worker deployment needs one more environment variable.

    Stated as a string rather than a comment so the operations documentation
    and the code cannot drift apart.
    """
    return (
        "Running more than one worker requires PROMETHEUS_MULTIPROC_DIR to be "
        "set to a writable, EMPTY directory, and the directory must be cleared "
        "on restart. Without it each worker keeps its own counters and a "
        "scrape reaches an arbitrary one, so every counter appears to move "
        "backwards at random — which reads as data loss and is not."
    )


__all__ = [
    "REGISTRY",
    "answers",
    "http_latency",
    "http_requests",
    "llm_calls",
    "metrics_errors",
    "multiprocess_mode_note",
    "observe_pipeline",
    "pipeline_latency",
    "record_findings",
    "record_http",
    "record_pipeline_result",
    "redrafts",
    "render",
    "review_findings",
    "set_build_info",
]
