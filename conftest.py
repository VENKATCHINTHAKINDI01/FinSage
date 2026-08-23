"""Test-session setup that applies to every suite.

The problem this solves
-----------------------
`pyproject.toml` has declared a marker —

    "integration: requires Postgres/Redis/Qdrant",

— that nothing ever used. So the tests which genuinely need a database did
not skip when there was no database; they ERRORED, nine of them, on
`ConnectionRefusedError` during fixture setup. That is worse than it sounds:
a run with nine errors looks the same whether the cause is a missing service
or genuinely broken code, so the signal that a real regression produces is
one a developer has already been trained to ignore.

Why probe rather than skip on an environment variable
------------------------------------------------------
A `SKIP_INTEGRATION=1` flag records an intention. A connection probe records
a fact. The difference matters in CI, where the flag would be set once, by
someone, for a reason that stopped being true — and the integration tests
would then silently never run again while the summary line still said
"passed". A probe cannot drift: if Postgres is up, they run.

The probe is deliberately narrow
---------------------------------
It opens a TCP connection and closes it. It does not run a query, create a
schema or import the ORM, because a probe that can fail for its own reasons
is just another test. The consequence is that a Postgres which accepts
connections but has the wrong schema produces a real failure, which is
correct — that is a broken environment, not an absent one.
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

import pytest

_PROBE_TIMEOUT_S = 0.4


def _reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_S):
            return True
    except OSError:
        return False


def _database_endpoint() -> tuple[str, int]:
    """Where the tests would look for Postgres.

    Read from configuration rather than hardcoded, so that a developer who
    points the suite at a container on another port gets their integration
    tests run instead of skipped.
    """
    try:
        from backend.config import settings

        url = str(getattr(settings.database, "url", "") or "")
    except Exception:
        url = ""

    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    return (parsed.hostname or "localhost", parsed.port or 5432)


def pytest_collection_modifyitems(config, items):
    marked = [item for item in items if item.get_closest_marker("integration")]
    if not marked:
        return

    host, port = _database_endpoint()
    if _reachable(host, port):
        return

    skip = pytest.mark.skip(
        reason=(
            f"integration: no Postgres at {host}:{port}. These tests are not "
            f"disabled — start the database and they run. If you meant to "
            f"exercise them, `docker compose up db` first."
        )
    )
    for item in marked:
        item.add_marker(skip)
