"""Logs that cannot leak a taxpayer — PRD-004."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from backend.observability.logging import (
    RedactingFormatter,
    install,
    is_aadhaar,
    redact_pii,
)

VALID_AADHAAR = "234567890124"      # Verhoeff-valid
BAD_CHECKSUM = "234567890125"       # same shape, wrong check digit


def formatted(message, *, exc=None, secrets_source=None):
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, message, (), exc,
    )
    return RedactingFormatter("%(message)s",
                              secrets_source=secrets_source).format(record)


# ── redact by shape, not by field name ──────────────────────────────────────

@pytest.mark.parametrize(("raw", "token"), [
    ("PAN is ABCDE1234F today", "[PAN]"),
    ("gstin 29ABCDE1234F1Z5 registered", "[GSTIN]"),
    ("write to person@example.co.in please", "[EMAIL]"),
    ("call 9876543210 now", "[PHONE]"),
    ("call +91 9876543210 now", "[PHONE]"),
])
def test_identifiers_are_caught_wherever_they_appear(raw, token):
    """A field-name allowlist misses `pan_of_spouse`, `payload["PAN"]` and an
    identifier sitting mid-sentence. Shape works everywhere."""
    out = redact_pii(raw)
    assert token in out
    assert raw.split()[-2] not in out or token in out


def test_a_key_name_is_not_required_for_the_value_to_be_caught():
    assert "[PAN]" in redact_pii("ABCDE1234F")
    assert "[PAN]" in redact_pii('{"pan_of_spouse": "ABCDE1234F"}')


# ── Aadhaar needs its checksum ──────────────────────────────────────────────

def test_a_real_aadhaar_is_redacted():
    assert "[AADHAAR]" in redact_pii(f"aadhaar {VALID_AADHAAR}")
    assert "[AADHAAR]" in redact_pii("aadhaar 2345 6789 0124")


def test_a_twelve_digit_number_that_is_not_an_aadhaar_survives():
    """A bare twelve-digit match would redact rupee amounts and timestamps,
    which makes the logs useless and trains people to turn the filter off."""
    assert BAD_CHECKSUM in redact_pii(f"reference {BAD_CHECKSUM}")
    assert "123456789012" in redact_pii("amount 123456789012 paise")


def test_the_checksum_is_what_separates_them():
    assert is_aadhaar(VALID_AADHAAR)
    assert not is_aadhaar(BAD_CHECKSUM)
    assert not is_aadhaar("12345")


# ── the formatter is the point ──────────────────────────────────────────────

def test_redaction_happens_at_the_formatter_not_the_call_site():
    """Nobody types logger.info(pan). PII escapes through the incidental
    route, so the single point every line passes through is where it has to be
    caught."""
    assert "[PAN]" in formatted("processing ABCDE1234F")


def test_an_exception_traceback_is_redacted_too():
    """The line nobody wrote — an exception whose message quotes the row it
    failed on — is exactly how PII reaches a log."""
    try:
        raise ValueError("could not parse PAN ABCDE1234F for a@b.com")
    except ValueError:
        import sys

        out = formatted("failed", exc=sys.exc_info())
    assert "ABCDE1234F" not in out
    assert "a@b.com" not in out


def test_secrets_are_redacted_alongside_pii_when_a_source_is_given():
    """PRD-005 handles configured secrets; this composes the two rather than
    reimplementing either."""
    settings = SimpleNamespace(
        auth=SimpleNamespace(secret_key="kf3Q7xR2pLmN8vTzB1yWcE4sHjA6dGuXoZ9n"),
        llm=SimpleNamespace(api_key="gsk_live_abcdef123456"),
        search=SimpleNamespace(tavily_api_key="", serper_api_key=""),
        qdrant=SimpleNamespace(api_key=None),
        telegram=SimpleNamespace(bot_token=""),
        email=SimpleNamespace(resend_api_key=None),
        s3=SimpleNamespace(access_key_id="", secret_access_key=""),
        database=SimpleNamespace(url="postgresql://u:p@h/db"),
        redis=SimpleNamespace(url="redis://h:6379"),
    )
    out = formatted("key gsk_live_abcdef123456 for ABCDE1234F",
                    secrets_source=settings)
    assert "gsk_live_abcdef123456" not in out
    assert "[PAN]" in out


def test_install_wraps_existing_handlers_rather_than_adding_one():
    """Adding a handler duplicates output; replacing them loses whatever
    configuration is already there."""
    logger = logging.getLogger("prd004-test")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("PREFIX %(message)s"))
    logger.addHandler(handler)

    install(logger)

    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, RedactingFormatter)
    record = logging.LogRecord("t", logging.INFO, __file__, 1,
                               "ABCDE1234F", (), None)
    out = logger.handlers[0].formatter.format(record)
    assert out.startswith("PREFIX ")
    assert "[PAN]" in out


def test_ordinary_text_is_left_alone():
    """A filter that mangles normal lines gets turned off."""
    line = "computed tax of 97500 for FY 2026-27 in 42ms"
    assert redact_pii(line) == line


def test_redaction_is_installed_by_the_real_logging_setup():
    """The wiring, not just the component. A formatter nobody attached
    protects nothing, and PRD-004 was recorded as unwired until an end-to-end
    check of the folder found it really was.
    """
    import logging as std

    from backend.logging_config import setup_logging

    setup_logging()
    handlers = std.getLogger().handlers
    assert handlers
    assert all(isinstance(h.formatter, RedactingFormatter) for h in handlers)
