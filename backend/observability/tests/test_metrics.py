"""PRD-004. The two failure modes worth testing are cardinality and silence.

A metrics layer fails in ways ordinary tests miss. It does not raise; it
quietly records the wrong thing, or records too many things, and the damage
shows up weeks later as either a misleading dashboard or a dead process. So
these tests are mostly about what must NOT be recorded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY as _DEFAULT_REGISTRY

from backend.middleware.metrics import METRICS_PATH
from backend.middleware.metrics import install as install_metrics
from backend.observability import metrics


def _value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


# ── cardinality ─────────────────────────────────────────────────────────────

def test_a_label_value_outside_the_permitted_set_is_dropped():
    """The memory leak that looks healthy in testing.

    Prometheus keeps one series per label combination for the life of the
    process. A label fed from user input grows without bound. Dropping the
    sample loses one data point; recording it loses the process.
    """
    before = _value(metrics.metrics_errors, kind="label_not_permitted")

    metrics.record_http(
        method="TRACE",  # not in the permitted set
        route="/api/v1/x",
        status=200,
        duration_s=0.01,
    )

    assert _value(metrics.metrics_errors, kind="label_not_permitted") == before + 1
    body = metrics.render()[0].decode()
    assert 'method="TRACE"' not in body


def test_the_drop_is_logged_once_not_on_every_request(caplog):
    """A per-request warning is its own outage.

    The point of dropping rather than raising is that the request survives.
    That is undone if the log fills at request rate — which is how a team ends
    up deleting the logger and losing the signal entirely.
    """
    metrics._warned.discard("label:method:CONNECT")
    with caplog.at_level(logging.WARNING, logger="backend.observability.metrics"):
        for _ in range(5):
            metrics.record_http(
                method="CONNECT", route="/x", status=200, duration_s=0.0,
            )

    warnings = [r for r in caplog.records if "not in the permitted set" in r.message]
    assert len(warnings) == 1


def test_permitted_values_are_declared_for_every_label_used():
    """The guard is only a guard if it covers the labels that exist.

    A new label added without an entry in `_LABEL_VALUES` passes `_permitted`
    unconditionally, so the protection would silently not apply to the newest
    and least-reviewed code. `route` and `status` are the deliberate
    exceptions and are named here so that their absence is a decision on
    record rather than an oversight.
    """
    unbounded_by_design = {"route", "status", "version", "rules_version"}
    used: set[str] = set()
    for collector in (
        metrics.answers, metrics.review_findings, metrics.http_requests,
        metrics.http_latency, metrics.metrics_errors, metrics.build_info,
    ):
        used.update(collector._labelnames)

    undeclared = used - set(metrics._LABEL_VALUES) - unbounded_by_design
    assert not undeclared, (
        f"labels with no permitted-value set: {sorted(undeclared)}. Either "
        f"declare them or add them to unbounded_by_design with a reason."
    )


# ── classification ──────────────────────────────────────────────────────────

@dataclass
class _Answer:
    withheld: bool = False
    notes: list[str] = field(default_factory=list)
    redrafted: bool = False


@dataclass
class _Result:
    answer: Any
    reviews: list[Any] = field(default_factory=list)
    total_latency_ms: float = 100.0
    llm_calls: int = 1


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (_Answer(), "served"),
        (_Answer(notes=["a caveat the reviewer required"]), "amended"),
        (_Answer(withheld=True), "withheld"),
        (_Answer(withheld=True, notes=["x"]), "withheld"),
    ],
)
def test_answers_are_classified_by_what_the_review_did(answer, expected):
    """Withheld outranks amended.

    An answer that was both amended and then withheld is withheld — counting
    it as amended would understate the rate that matters.
    """
    before = _value(metrics.answers, outcome=expected)
    metrics.record_pipeline_result(_Result(answer=answer))
    assert _value(metrics.answers, outcome=expected) == before + 1


def test_a_result_with_no_answer_is_counted_as_failed_not_ignored():
    before = _value(metrics.answers, outcome="failed")
    metrics.record_pipeline_result(_Result(answer=None))
    assert _value(metrics.answers, outcome="failed") == before + 1


def test_findings_are_recorded_by_verdict_and_category():
    """The fabricated-figure count is the reason this feature exists."""
    from backend.agents.review_protocol import Category, Finding, Verdict

    before = _value(
        metrics.review_findings,
        verdict="block", category="fabricated_figure", reviewer="ca",
    )
    metrics.record_findings([
        Finding(
            verdict=Verdict.BLOCK,
            category=Category.FABRICATED_FIGURE,
            detail="a figure appeared that no tool produced",
        ),
    ])
    assert _value(
        metrics.review_findings,
        verdict="block", category="fabricated_figure", reviewer="ca",
    ) == before + 1


def test_enum_and_string_labels_agree():
    """`str(SomeEnum.X)` is `'SomeEnum.X'` unless the enum derives from str.

    Depending on `review_protocol.Verdict` staying a `str` subclass would make
    a harmless refactor there produce a permanently empty dashboard here.
    """
    from backend.agents.review_protocol import Verdict

    assert metrics._enum_value(Verdict.BLOCK) == "block"
    assert metrics._enum_value("block") == "block"


# ── never break the request ─────────────────────────────────────────────────

def test_a_broken_recorder_does_not_propagate(monkeypatch):
    class Exploding:
        @property
        def answer(self):
            raise RuntimeError("boom")

    before = _value(metrics.metrics_errors, kind="record_failed")
    metrics.record_pipeline_result(Exploding())  # must not raise
    assert _value(metrics.metrics_errors, kind="record_failed") == before + 1


# ── the endpoint ────────────────────────────────────────────────────────────

def _app(**install_kwargs) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/users/{user_id}")
    async def _user(user_id: str):
        return {"id": user_id}

    install_metrics(app, **install_kwargs)
    return app


def test_the_route_label_is_the_template_not_the_resolved_path():
    """One series for all users, not one per user.

    This is the whole reason the middleware matches routes itself instead of
    reading `request.url.path`.
    """
    app = _app(token=None, is_production=False)
    with TestClient(app) as client:
        for user_id in ("alice", "bob", "carol"):
            assert client.get(f"/api/v1/users/{user_id}").status_code == 200

    body = metrics.render()[0].decode()
    assert 'route="/api/v1/users/{user_id}"' in body
    assert "alice" not in body and "bob" not in body


def test_every_unmatched_path_collapses_into_one_series():
    """A scanner probing random URLs must not be able to grow the metrics store."""
    app = _app(token=None, is_production=False)
    with TestClient(app) as client:
        for junk in ("/wp-admin", "/.env", "/phpmyadmin"):
            client.get(junk)

    body = metrics.render()[0].decode()
    assert 'route="unmatched"' in body
    assert "wp-admin" not in body and ".env" not in body


def test_production_without_a_token_serves_no_metrics():
    """Request volumes, error rates and withheld counts are not public.

    404 rather than 401 — an unauthenticated caller learns nothing about
    whether this endpoint exists.
    """
    app = _app(token=None, is_production=True)
    with TestClient(app) as client:
        assert client.get(METRICS_PATH).status_code == 404


def test_production_with_a_token_requires_it():
    app = _app(token="s3cret-token-value", is_production=True)
    with TestClient(app) as client:
        assert client.get(METRICS_PATH).status_code == 404
        assert client.get(
            METRICS_PATH, headers={"Authorization": "Bearer wrong"},
        ).status_code == 404
        ok = client.get(
            METRICS_PATH, headers={"Authorization": "Bearer s3cret-token-value"},
        )
        assert ok.status_code == 200
        assert "finsage_answers_total" in ok.text


def test_development_serves_metrics_openly():
    """Friction people route around is worse than no control at all."""
    app = _app(token=None, is_production=False)
    with TestClient(app) as client:
        assert client.get(METRICS_PATH).status_code == 200


def test_scraping_is_not_counted_as_traffic():
    """Otherwise an idle service shows a request rate set by the scrape interval."""
    app = _app(token=None, is_production=False)
    with TestClient(app) as client:
        client.get(METRICS_PATH)
        body = client.get(METRICS_PATH).text

    assert 'route="/metrics"' not in body


def test_metrics_are_not_registered_on_the_library_default_registry():
    """A stray collector in someone else's registry is not our scrape's problem.

    Also protects against double registration blowing up on module reimport,
    which is how metrics modules usually break a test suite.
    """
    names = {m.name for m in _DEFAULT_REGISTRY.collect()}
    assert not any(n.startswith("finsage_") for n in names)
