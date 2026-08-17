"""Refresh rotation, reuse detection and revocation — PRD-002."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.security.sessions import (
    InMemorySessions,
    State,
    TokenRejected,
    assert_usable,
    logout,
    now_utc,
    rotate,
    start_session,
)

WEEK = timedelta(days=7)


def store_with_login(user_id="u-1"):
    store = InMemorySessions()
    return store, start_session(user_id, store, lifetime=WEEK)


# ── rotation ────────────────────────────────────────────────────────────────

def test_a_refresh_token_is_single_use():
    store, first = store_with_login()
    second = rotate(first.jti, store, lifetime=WEEK)

    assert second.jti != first.jti
    assert store.get(first.jti).state is State.USED
    assert store.get(first.jti).replaced_by == second.jti
    assert second.state is State.ACTIVE


def test_the_successor_stays_in_the_same_family():
    """The family is what makes reuse detection possible at all — it is the
    handle on 'everything descended from this login'."""
    store, first = store_with_login()
    second = rotate(first.jti, store, lifetime=WEEK)
    third = rotate(second.jti, store, lifetime=WEEK)
    assert {r.family for r in (first, second, third)} == {first.family}


def test_a_fresh_login_opens_a_new_family():
    """Otherwise revoking a stolen session would log the user out of every
    device they have ever used."""
    store = InMemorySessions()
    a = start_session("u-1", store, lifetime=WEEK)
    b = start_session("u-1", store, lifetime=WEEK)
    assert a.family != b.family

    logout(a.jti, store)
    assert store.is_family_revoked(a.family)
    assert not store.is_family_revoked(b.family)


# ── the one that matters ────────────────────────────────────────────────────

def test_reusing_a_rotated_token_revokes_the_whole_family():
    """Two parties hold this token and there is no way to tell which is
    presenting it, so both lose the session. That does log the real user out;
    the alternative is guessing which of two identical requests is the thief."""
    store, first = store_with_login()
    second = rotate(first.jti, store, lifetime=WEEK)

    with pytest.raises(TokenRejected) as exc:
        rotate(first.jti, store, lifetime=WEEK)

    assert exc.value.reason == "reused"
    assert store.is_family_revoked(first.family)
    assert store.get(second.jti).state is State.REVOKED


def test_the_legitimate_successor_stops_working_too():
    """The cost of the trade, asserted rather than assumed."""
    store, first = store_with_login()
    second = rotate(first.jti, store, lifetime=WEEK)
    with pytest.raises(TokenRejected):
        rotate(first.jti, store, lifetime=WEEK)

    with pytest.raises(TokenRejected) as exc:
        rotate(second.jti, store, lifetime=WEEK)
    assert exc.value.reason == "revoked"


def test_the_reuse_detail_names_the_family_for_the_log():
    store, first = store_with_login()
    rotate(first.jti, store, lifetime=WEEK)
    with pytest.raises(TokenRejected) as exc:
        rotate(first.jti, store, lifetime=WEEK)
    assert "has been copied" in exc.value.detail
    assert "re-authenticate" in exc.value.detail


def test_there_is_no_grace_window_for_a_double_submit():
    """The tempting mitigation is to return the same token for a few seconds.
    That window is a replay window — an attacker needs only to use the stolen
    token inside it."""
    store, first = store_with_login()
    at = now_utc()
    rotate(first.jti, store, lifetime=WEEK, now=at)
    with pytest.raises(TokenRejected) as exc:
        rotate(first.jti, store, lifetime=WEEK, now=at)   # same instant
    assert exc.value.reason == "reused"


# ── everything else that is not a clean rotation ────────────────────────────

def test_an_unknown_jti_is_rejected_without_revoking_anything():
    """There is no family to name, so there is nothing to revoke — and
    revoking something arbitrary on a forged token would be a denial of
    service anyone could trigger."""
    store, first = store_with_login()
    with pytest.raises(TokenRejected) as exc:
        rotate("forged-jti", store, lifetime=WEEK)
    assert exc.value.reason == "unknown"
    assert not store.is_family_revoked(first.family)
    assert store.get(first.jti).state is State.ACTIVE


def test_an_expired_session_is_rejected():
    store, first = store_with_login()
    with pytest.raises(TokenRejected) as exc:
        rotate(first.jti, store, lifetime=WEEK,
               now=first.expires_at + timedelta(seconds=1))
    assert exc.value.reason == "expired"


def test_expiry_is_checked_at_the_boundary_not_after_it():
    store, first = store_with_login()
    with pytest.raises(TokenRejected):
        rotate(first.jti, store, lifetime=WEEK, now=first.expires_at)


def test_the_client_cannot_tell_the_causes_apart():
    """A different status or message per cause is an oracle: it tells an
    attacker whether a token was ever real, and whether they have been
    detected."""
    store, first = store_with_login()
    rotate(first.jti, store, lifetime=WEEK)

    causes = []
    for jti in ("forged", first.jti):
        try:
            rotate(jti, store, lifetime=WEEK)
        except TokenRejected as exc:
            causes.append(type(exc))
    assert len(set(causes)) == 1


# ── the revocation check get_current_user never made ────────────────────────

def test_a_revoked_family_stops_an_access_token_immediately():
    """Fifteen minutes is a long time to hold a stolen session open after the
    user has pressed Log out and been told it worked."""
    store, first = store_with_login()
    payload = {"user_id": "u-1", "family": first.family, "jti": first.jti}
    assert_usable(payload, store)          # fine before

    logout(first.jti, store)
    with pytest.raises(TokenRejected) as exc:
        assert_usable(payload, store)
    assert exc.value.reason == "revoked"


def test_a_token_with_no_family_is_rejected_rather_than_waved_through():
    """Tokens minted before rotation existed carry no family. Treating 'no
    family' as 'not revoked' would keep exactly the tokens this exists to stop
    working."""
    store, _ = store_with_login()
    with pytest.raises(TokenRejected) as exc:
        assert_usable({"user_id": "u-1"}, store)
    assert exc.value.reason == "no_family"


def test_an_individually_revoked_token_is_caught_even_in_a_live_family():
    store, first = store_with_login()
    store.get(first.jti).state = State.REVOKED
    with pytest.raises(TokenRejected):
        assert_usable(
            {"user_id": "u-1", "family": first.family, "jti": first.jti}, store,
        )


# ── logout ──────────────────────────────────────────────────────────────────

def test_logout_ends_the_session_even_after_rotation():
    """Revoking only the presented jti leaves the successor alive, which is
    not what anyone means by 'log out'."""
    store, first = store_with_login()
    second = rotate(first.jti, store, lifetime=WEEK)
    logout(first.jti, store)               # the token the client still held
    with pytest.raises(TokenRejected):
        rotate(second.jti, store, lifetime=WEEK)


def test_logout_on_an_unknown_token_is_a_no_op():
    store, first = store_with_login()
    logout("never-existed", store)
    assert not store.is_family_revoked(first.family)


# ── time handling ───────────────────────────────────────────────────────────

def test_every_timestamp_is_timezone_aware():
    """`datetime.utcnow()` returns a NAIVE datetime that claims to be timezone.utc, and
    comparing it against an aware one raises."""
    _, first = store_with_login()
    assert first.issued_at.tzinfo is not None
    assert first.expires_at.tzinfo is not None
    assert now_utc().tzinfo is not None


def test_ids_are_unpredictable_and_unique():
    from backend.security.sessions import new_id

    ids = {new_id() for _ in range(500)}
    assert len(ids) == 500
    assert all(len(i) >= 24 for i in ids)


def test_a_record_serialises_without_leaking_anything_secret():
    _, first = store_with_login()
    d = first.to_dict()
    assert d["state"] == "active"
    assert d["replaced_by"] is None
    assert set(d) == {
        "jti", "family", "user_id", "issued_at", "expires_at", "state",
        "replaced_by",
    }


# ── the wiring: a token now carries a handle ────────────────────────────────

def test_every_issued_token_carries_a_revocable_handle():
    """Without jti and family a token cannot be revoked and cannot be checked
    against the sessions table — which is why logout did nothing."""
    from backend.security.jwt_handler import (
        create_access_token,
        create_refresh_token,
        verify_token,
    )

    access = verify_token(create_access_token("u-1"), token_type="access")
    refresh = verify_token(create_refresh_token("u-1"), token_type="refresh")
    for payload in (access, refresh):
        assert payload["jti"]
        assert payload["family"]


def test_a_caller_that_forgets_still_gets_a_revocable_token():
    """Defaulting to a fresh id rather than to None: a forgotten argument
    produces a revocable token in its own family, not an anonymous one that
    silently escapes every check."""
    from backend.security.jwt_handler import create_access_token, verify_token

    a = verify_token(create_access_token("u-1"), token_type="access")
    b = verify_token(create_access_token("u-1"), token_type="access")
    assert a["jti"] != b["jti"]


def test_an_access_token_can_be_tied_to_the_session_family():
    from backend.security.jwt_handler import create_access_token, verify_token

    store, first = store_with_login()
    token = create_access_token("u-1", jti=first.jti, family=first.family)
    payload = verify_token(token, token_type="access")

    assert_usable(payload, store)
    logout(first.jti, store)
    with pytest.raises(TokenRejected):
        assert_usable(payload, store)


def test_no_naive_utcnow_survives_in_the_token_path():
    """The claim is a unix timestamp either way, but a naive utcnow() is how a
    token gets an expiry an hour out in a non-timezone.utc deployment.

    Checked over the AST rather than the file text: the docstring names
    utcnow() deliberately, to say why it is not used, and scanning raw text
    would flag the explanation as the offence.
    """
    import ast
    import pathlib

    import backend.security.jwt_handler as mod

    tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
    calls = [
        ast.unparse(n) for n in ast.walk(tree)
        if isinstance(n, ast.Call) and "utcnow" in ast.unparse(n.func)
    ]
    assert calls == [], calls
