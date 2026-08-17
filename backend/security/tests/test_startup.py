"""Refusing to start on a bad secret — PRD-005."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from backend.security.startup import (
    MIN_SECRET_LENGTH,
    InsecureConfiguration,
    audit,
    check_secret,
    dev_secret,
    enforce,
    fingerprint,
    looks_like_a_placeholder,
    redact,
)

GOOD = "kf3Q7xR2pLmN8vTzB1yWcE4sHjA6dGuXoZ9nYrKtVbSi"


def settings(**kw):
    base = {
        "environment": "production",
        "debug": False,
        "allowed_origins": ["https://app.example.com"],
        "auth": SimpleNamespace(secret_key=GOOD),
        "database": SimpleNamespace(url="postgresql+asyncpg://u:p@db.internal/finsage"),
        "redis": SimpleNamespace(url="redis://cache.internal:6379"),
        "llm": SimpleNamespace(api_key="gsk_live_abcdef123456"),
        "search": SimpleNamespace(tavily_api_key="", serper_api_key=""),
        "qdrant": SimpleNamespace(api_key=None),
        "telegram": SimpleNamespace(bot_token=""),
        "email": SimpleNamespace(resend_api_key=None),
        "s3": SimpleNamespace(access_key_id="", secret_access_key=""),
    }
    base.update(kw)
    obj = SimpleNamespace(**base)
    obj.is_production = str(base["environment"]).lower() == "production"
    return obj


# ── the shipped hole ────────────────────────────────────────────────────────

def test_the_shipped_placeholder_is_refused():
    """It defaulted to this, so any deployment that never set the variable
    signed its JWTs with a constant in a public repository."""
    problems = check_secret(
        "your-super-secret-key-change-in-production", setting="auth.secret_key",
    )
    assert problems
    assert any("published secret" in p.reason for p in problems)


def test_production_refuses_to_start_on_a_placeholder():
    with pytest.raises(InsecureConfiguration, match="Refusing to start"):
        enforce(settings(auth=SimpleNamespace(secret_key="change-me-please-1234567890abcd")))


def test_the_error_names_every_problem_not_just_the_first():
    """An operator who fixes the secret, redeploys, and is then told about
    debug mode has been made to do two deployments to learn two facts."""
    with pytest.raises(InsecureConfiguration) as exc:
        enforce(settings(
            auth=SimpleNamespace(secret_key="changeme"),
            debug=True,
            allowed_origins=["*"],
        ))
    text = str(exc.value)
    assert "auth.secret_key" in text
    assert "debug" in text
    assert "allowed_origins" in text


def test_a_good_configuration_starts():
    enforce(settings())


# ── what counts as bad ──────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "your-secret-key-here-please-change-it",
    "example-key-example-key-example-key",
    "insecure-development-only-key-1234567",
    "password123password123password123",
])
def test_placeholder_shapes_are_caught(value):
    assert looks_like_a_placeholder(value)


def test_a_generated_secret_is_not_mistaken_for_a_placeholder():
    """A false positive costs one regeneration; a false negative costs the
    product. But a checker that rejects real secrets gets removed."""
    import secrets as std

    for _ in range(50):
        assert not looks_like_a_placeholder(std.token_urlsafe(48))


def test_a_short_secret_is_refused():
    problems = check_secret("aB3$xY9!kL2#", setting="auth.secret_key")
    assert any("brute-forceable" in p.reason for p in problems)
    assert str(MIN_SECRET_LENGTH) in " ".join(p.reason for p in problems)


def test_length_without_variety_is_not_entropy():
    """A 64-character run of one letter is a one-character secret."""
    problems = check_secret("a" * 64, setting="auth.secret_key")
    assert any("not entropy" in p.reason for p in problems)


def test_an_empty_secret_is_refused_and_says_so_plainly():
    problems = check_secret("", setting="auth.secret_key")
    assert len(problems) == 1
    assert "is empty" in problems[0].reason


def test_every_problem_says_how_to_fix_it_with_the_variable_name():
    for p in check_secret("changeme", setting="auth.secret_key"):
        assert "AUTH__SECRET_KEY" in p.fix
        assert "token_urlsafe" in p.fix


# ── there is no shared default ──────────────────────────────────────────────

def test_the_development_default_is_random_per_process():
    """A default that is the same on every machine is a published secret, and
    the only reason the shipped one survived is that it worked."""
    assert dev_secret() != dev_secret()
    assert len(dev_secret()) >= MIN_SECRET_LENGTH
    assert not check_secret(dev_secret(), setting="auth.secret_key")


def test_the_config_module_ships_no_secret_constant():
    """The regression this feature exists for."""
    import pathlib

    import backend.config as cfg

    text = pathlib.Path(cfg.__file__).read_text(encoding="utf-8")
    assert 'default="your-super-secret-key-change-in-production"' not in text
    assert "default_factory=dev_secret" in text


# ── development warns rather than blocks ────────────────────────────────────

def test_development_logs_and_carries_on(caplog):
    """A checker that blocks local work gets disabled, and then it is not
    checking anything in production either."""
    with caplog.at_level(logging.WARNING, logger="security.startup"):
        enforce(settings(environment="development", debug=True,
                         auth=SimpleNamespace(secret_key="changeme")))
    assert any("would fail in production" in r.message for r in caplog.records)


# ── loopback is not an insecure origin ──────────────────────────────────────

@pytest.mark.parametrize("origin", [
    "http://localhost:5173", "http://127.0.0.1:3000", "http://[::1]:5173",
])
def test_loopback_origins_are_not_flagged(origin):
    """A checker that cries wolf on the developer's own machine gets muted."""
    problems = audit(settings(allowed_origins=[origin]))
    assert not any(p.setting == "allowed_origins" for p in problems)


def test_a_plaintext_public_origin_is_flagged():
    problems = audit(settings(allowed_origins=["http://app.example.com"]))
    assert any(p.setting == "allowed_origins" for p in problems)


def test_a_wildcard_origin_is_flagged():
    problems = audit(settings(allowed_origins=["*"]))
    assert any("wildcard" in p.reason for p in problems)


def test_a_development_database_url_in_production_is_flagged():
    problems = audit(settings(
        database=SimpleNamespace(url="postgresql+asyncpg://user:pass@localhost:5432/finsage"),
    ))
    assert any(p.setting == "database.url" for p in problems)


# ── nothing ever prints a secret ────────────────────────────────────────────

def test_no_message_contains_the_secret_itself():
    """The check exists to protect the secret, so leaking it in the complaint
    would be a complete own goal."""
    leaky = "changeme-but-this-is-the-actual-value-9876"
    for p in check_secret(leaky, setting="auth.secret_key"):
        assert leaky not in str(p)

    with pytest.raises(InsecureConfiguration) as exc:
        enforce(settings(auth=SimpleNamespace(secret_key=leaky)))
    assert leaky not in str(exc.value)


def test_redact_strips_every_configured_secret():
    s = settings()
    line = f"calling llm with key {s.llm.api_key} and db {s.database.url}"
    out = redact(line, s)
    assert s.llm.api_key not in out
    assert "[redacted]" in out


def test_redact_strips_credentials_from_a_url_it_has_never_seen():
    """A connection string assembled at runtime matches no single setting, so
    credentials inside a URL are stripped by shape as well."""
    out = redact(
        "connect postgresql://someuser:s3cr3tpw@other.host:5432/db", settings(),
    )
    assert "s3cr3tpw" not in out
    assert "[redacted]" in out


def test_redact_handles_a_secret_that_is_a_prefix_of_another():
    """Longest first. Otherwise the shorter one matches inside the longer and
    leaves a tail of the longer secret in the log."""
    s = settings(
        llm=SimpleNamespace(api_key="abcdef"),
        telegram=SimpleNamespace(bot_token="abcdefghijkl"),
    )
    out = redact("token=abcdefghijkl", s)
    assert "ghijkl" not in out


def test_a_fingerprint_is_comparable_but_not_reversible():
    assert fingerprint(GOOD) == fingerprint(GOOD)
    assert fingerprint(GOOD) != fingerprint(GOOD + "x")
    assert GOOD not in fingerprint(GOOD)
    assert fingerprint("") == "unset"
