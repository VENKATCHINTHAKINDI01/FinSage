"""Refresh rotation, reuse detection and revocation — PRD-002.

Three holes, and the third is the one that makes the other two matter
----------------------------------------------------------------------
**A token could not be revoked.** Nothing in the JWT identified it, so there
was no handle to revoke. `jti` fixes that.

**`get_current_user` never looked at the sessions table.** A row was written at
login and read by nothing, so logging out deleted a record while the token in
the attacker's hands carried on working for the rest of its fifteen minutes.

**A refresh token was reusable for a week.** Steal one and you can mint access
tokens for seven days, and nothing anywhere would notice. This module makes a
refresh token SINGLE USE and treats a second presentation as evidence of theft.

Why reuse means revoke the whole family
----------------------------------------
Rotation issues a new refresh token and marks the old one used. If a used token
is presented again, two people hold copies: the legitimate user and someone
else. **There is no way to tell which one is presenting it** — the attacker may
have raced ahead, or the victim may be replaying an old one — so the only safe
action is to invalidate every token descended from that login and make both
parties authenticate again.

That does log the real user out. It is the correct trade and it is worth being
explicit about: the alternative is guessing which of two identical requests is
the thief, and guessing wrong leaves the thief with a valid session.

Why there is no grace window
-----------------------------
The tempting mitigation for double-submits and network retries is to return the
same new token for a few seconds. That window is a replay window: an attacker
who captures a refresh token needs only to use it inside it. Rotation is made
atomic on the client instead, and a benign double-submit costs one
re-authentication rather than every user a five-second hole.

The store is injected
----------------------
Same shape as `SearchFn` and `ExtractFn`. The rotation logic is pure and
exhaustively testable; whether sessions live in Postgres or Redis is not this
module's business, and a protocol keeps the decision out of the security
reasoning.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol


class TokenRejected(Exception):
    """The caller must be sent 401. Carries a machine-readable reason.

    A single exception type rather than one per cause, because the CLIENT must
    not be able to tell an expired token from a revoked one from a reused one —
    that difference is an oracle. The reason is for the log.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class State(str, Enum):
    ACTIVE = "active"
    USED = "used"            # rotated out normally
    REVOKED = "revoked"      # family killed


def new_id() -> str:
    return secrets.token_urlsafe(24)


def now_utc() -> datetime:
    """Timezone-aware, always.

    `datetime.utcnow()` returns a NAIVE datetime that claims to be timezone.utc, and
    comparing it against an aware one raises — or worse, silently compares
    against local time somewhere else in the stack.
    """
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SessionRecord:
    """One issued refresh token."""

    jti: str
    family: str
    user_id: str
    issued_at: datetime
    expires_at: datetime
    state: State = State.ACTIVE
    replaced_by: str = ""

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "jti": self.jti,
            "family": self.family,
            "user_id": self.user_id,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "state": self.state.value,
            "replaced_by": self.replaced_by or None,
        }


class SessionStore(Protocol):
    """What rotation needs from persistence, and nothing else."""

    def get(self, jti: str) -> SessionRecord | None: ...
    def put(self, record: SessionRecord) -> None: ...
    def family_members(self, family: str) -> list[SessionRecord]: ...
    def is_family_revoked(self, family: str) -> bool: ...


@dataclass(slots=True)
class InMemorySessions:
    """Reference implementation, and the one the tests run against.

    Kept in the same module as the protocol so the semantics have exactly one
    definition. A Postgres or Redis store is correct when it behaves like this.
    """

    records: dict[str, SessionRecord] = field(default_factory=dict)
    revoked_families: set[str] = field(default_factory=set)

    def get(self, jti: str) -> SessionRecord | None:
        return self.records.get(jti)

    def put(self, record: SessionRecord) -> None:
        self.records[record.jti] = record

    def family_members(self, family: str) -> list[SessionRecord]:
        return [r for r in self.records.values() if r.family == family]

    def is_family_revoked(self, family: str) -> bool:
        return family in self.revoked_families

    def revoke_family(self, family: str) -> None:
        self.revoked_families.add(family)
        for record in self.family_members(family):
            record.state = State.REVOKED


def revoke_family(store: Any, family: str) -> None:
    """Kill every token descended from one login."""
    if hasattr(store, "revoke_family"):
        store.revoke_family(family)
        return
    for record in store.family_members(family):
        record.state = State.REVOKED
        store.put(record)


# ── issuing ─────────────────────────────────────────────────────────────────

def start_session(
    user_id: str, store: SessionStore, *, lifetime: timedelta,
    now: datetime | None = None,
) -> SessionRecord:
    """A fresh login. Opens a new family."""
    at = now or now_utc()
    record = SessionRecord(
        jti=new_id(), family=new_id(), user_id=user_id,
        issued_at=at, expires_at=at + lifetime,
    )
    store.put(record)
    return record


def rotate(
    jti: str, store: SessionStore, *, lifetime: timedelta,
    now: datetime | None = None,
) -> SessionRecord:
    """Exchange a refresh token for the next one in its family.

    Raises `TokenRejected` for everything that is not a clean rotation, and
    revokes the family when the reason is reuse.
    """
    at = now or now_utc()
    record = store.get(jti)

    if record is None:
        # Unknown jti. Either forged, or from a store that has been cleared.
        # Nothing to revoke — there is no family to name.
        raise TokenRejected("unknown", f"no session for jti {jti[:8]}…")

    if store.is_family_revoked(record.family) or record.state is State.REVOKED:
        raise TokenRejected(
            "revoked",
            f"family {record.family[:8]}… was revoked; re-authentication "
            f"required.",
        )

    if record.state is State.USED:
        # THE ONE THAT MATTERS. Two parties hold this token and there is no way
        # to tell which is presenting it, so both lose the session.
        revoke_family(store, record.family)
        raise TokenRejected(
            "reused",
            f"refresh token {jti[:8]}… had already been rotated out (replaced "
            f"by {record.replaced_by[:8] or 'unknown'}…). A second use means "
            f"the token has been copied. Family {record.family[:8]}… revoked; "
            f"every session from that login must re-authenticate.",
        )

    if record.is_expired(at):
        raise TokenRejected("expired", f"session {jti[:8]}… expired.")

    successor = SessionRecord(
        jti=new_id(), family=record.family, user_id=record.user_id,
        issued_at=at, expires_at=at + lifetime,
    )
    record.state = State.USED
    record.replaced_by = successor.jti
    store.put(record)
    store.put(successor)
    return successor


def logout(jti: str, store: SessionStore) -> None:
    """Deliberately revokes the whole family, not just this token.

    Logging out of a session whose refresh token has already been rotated
    should still end the session. Revoking only the presented jti leaves the
    successor alive, which is not what anyone means by "log out".
    """
    record = store.get(jti)
    if record is not None:
        revoke_family(store, record.family)


# ── the check that was missing ──────────────────────────────────────────────

def assert_usable(
    payload: dict[str, Any], store: SessionStore, *,
    now: datetime | None = None,
) -> None:
    """The revocation check `get_current_user` never made.

    An access token carries the family it was issued under, so a revoked login
    stops working immediately rather than at the end of its fifteen minutes.
    Fifteen minutes is a long time to hold a stolen session open after the user
    has pressed Log out and been told it worked.

    A token with no family claim is REJECTED rather than waved through. Tokens
    minted before this feature existed have none, and treating "no family" as
    "not revoked" would keep exactly the tokens this is meant to stop working.
    """
    family = payload.get("family")
    if not family:
        raise TokenRejected(
            "no_family",
            "token carries no session family and cannot be checked against "
            "revocations. Tokens issued before rotation existed have none; "
            "they must be re-issued rather than trusted.",
        )
    if store.is_family_revoked(str(family)):
        raise TokenRejected("revoked", f"family {str(family)[:8]}… was revoked.")

    jti = payload.get("jti")
    if jti:
        record = store.get(str(jti))
        if record is not None and record.state is State.REVOKED:
            raise TokenRejected("revoked", f"token {str(jti)[:8]}… was revoked.")


__all__ = [
    "InMemorySessions",
    "SessionRecord",
    "SessionStore",
    "State",
    "TokenRejected",
    "assert_usable",
    "logout",
    "new_id",
    "now_utc",
    "revoke_family",
    "rotate",
    "start_session",
]
