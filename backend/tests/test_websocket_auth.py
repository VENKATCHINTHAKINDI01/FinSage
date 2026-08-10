"""WebSocket authentication — AGT-007.

The hole this closes
--------------------
The endpoint was declared as:

    async def websocket_agent_stream(websocket, conversation_id,
                                     user_id: str = Query(...))

The caller simply asserted who they were. Anyone who could guess or observe a
conversation id could open

    /ws/agent-stream/<id>?user_id=<somebody else>

and stream that person's live agent activity — including their income, their
deductions and their computed tax. There was no verification of any kind.

The socket now requires a signed access token and closes with 4401 if it is
missing, malformed, expired, or subjectless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.api.websocket import _authenticate
from backend.security.jwt_handler import create_access_token


@dataclass
class FakeSocket:
    """Records what the endpoint did instead of talking to a browser."""

    closed_with: tuple[int, str] | None = None
    accepted: bool = False
    sent: list[Any] = field(default_factory=list)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = (code, reason)

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: Any) -> None:
        self.sent.append(payload)


async def test_a_valid_token_authenticates() -> None:
    ws = FakeSocket()
    token = create_access_token("user-123")

    assert await _authenticate(ws, token) == "user-123"
    assert ws.closed_with is None


async def test_no_token_is_rejected() -> None:
    """The v1 behaviour: no token at all, and it connected happily."""
    ws = FakeSocket()
    assert await _authenticate(ws, None) is None
    assert ws.closed_with == (4401, "authentication required")


async def test_empty_token_is_rejected() -> None:
    ws = FakeSocket()
    assert await _authenticate(ws, "") is None
    assert ws.closed_with[0] == 4401


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "eyJhbGciOiJIUzI1NiJ9.tampered.signature",
        "user-456",                    # what an attacker would have passed before
        "Bearer eyJhbGciOiJIUzI1NiJ9",
    ],
)
async def test_a_forged_or_malformed_token_is_rejected(token: str) -> None:
    ws = FakeSocket()
    assert await _authenticate(ws, token) is None
    assert ws.closed_with == (4401, "invalid or expired token")


async def test_impersonation_by_asserting_a_user_id_no_longer_works() -> None:
    """The exact attack the old signature allowed: pass somebody else's id.

    It is now just an unparseable token.
    """
    ws = FakeSocket()
    assert await _authenticate(ws, "victim-user-id") is None
    assert ws.closed_with[0] == 4401


async def test_a_refresh_token_cannot_open_a_stream() -> None:
    """Token type is checked, not just the signature. A refresh token is for
    minting access tokens, not for reading a live session."""
    from backend.security.jwt_handler import create_refresh_token

    ws = FakeSocket()
    assert await _authenticate(ws, create_refresh_token("user-123")) is None
    assert ws.closed_with[0] == 4401


async def test_the_identity_comes_from_the_token_not_the_caller() -> None:
    """The property that makes the rest safe: whatever the client says, the
    user is whoever the signed token says."""
    ws = FakeSocket()
    resolved = await _authenticate(ws, create_access_token("real-user"))
    assert resolved == "real-user"
