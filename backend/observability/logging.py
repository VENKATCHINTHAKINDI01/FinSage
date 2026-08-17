"""Logs that cannot leak a taxpayer — PRD-004.

The threat is not the log line someone wrote on purpose
--------------------------------------------------------
Nobody types `logger.info(pan)`. PII reaches logs through the incidental
route: an exception whose message quotes the row it failed on, a request body
echoed into a 500, a dict dumped for debugging that happens to contain
`annual_income`. So redaction is applied at the FORMATTER — the single point
every line passes through — rather than at call sites, which is a rule someone
has to remember and eventually does not.

Redact by SHAPE, not by field name
------------------------------------
A field-name allowlist misses `{"pan_of_spouse": ...}`, `payload["PAN"]` and a
PAN sitting in the middle of a sentence. Indian identifiers have distinctive
formats — PAN is five letters, four digits, a letter; Aadhaar is twelve digits;
GSTIN is fifteen with the PAN embedded — so the shape is the reliable signal
and it works wherever the value appears.

Aadhaar deserves its own note. It is twelve digits, and so are plenty of
harmless numbers, so a bare twelve-digit match would redact rupee amounts and
timestamps. The Verhoeff checksum every Aadhaar carries is what separates them,
and using it means a real Aadhaar is caught while ₹1,23,45,67,890 is not.

What this does NOT do
----------------------
It does not make the logs safe to publish. It removes the identifiers it can
recognise. A free-text field where a user typed their own address is still
personal data, and the answer to that is not logging free text.
"""

from __future__ import annotations

import logging
import re
from typing import Any

# PAN: AAAAA9999A. The fourth letter is the holder type and the fifth is the
# first letter of the surname, but matching the full shape is enough.
PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
# GSTIN: 2-digit state code, PAN, entity number, 'Z', checksum.
GSTIN = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")
AADHAAR_SHAPED = re.compile(r"\b(?!0|1)[2-9][0-9]{3}[\s-]?[0-9]{4}[\s-]?[0-9]{4}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Indian mobile numbers, with or without the country code.
PHONE = re.compile(r"(?<![\d])(?:\+?91[\s-]?)?[6-9][0-9]{9}(?![\d])")
ACCOUNT = re.compile(r"\b(?:IFSC|A/?C|ACCOUNT)[\s:#]*([A-Z0-9]{6,20})\b", re.I)

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6), (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4), (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2), (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def is_aadhaar(digits: str) -> bool:
    """Verhoeff check.

    Twelve digits alone is not a signal — plenty of rupee amounts and
    timestamps are twelve digits, and redacting those makes the logs useless
    and trains people to turn the filter off.
    """
    digits = re.sub(r"\D", "", digits)
    if len(digits) != 12:
        return False
    checksum = 0
    for i, ch in enumerate(reversed(digits)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[i % 8][int(ch)]]
    return checksum == 0


def redact_pii(text: str) -> str:
    """Every identifier this can recognise, replaced in place."""
    out = PAN.sub("[PAN]", text)
    out = GSTIN.sub("[GSTIN]", out)
    out = AADHAAR_SHAPED.sub(
        lambda m: "[AADHAAR]" if is_aadhaar(m.group(0)) else m.group(0), out,
    )
    out = EMAIL.sub("[EMAIL]", out)
    out = PHONE.sub("[PHONE]", out)
    out = ACCOUNT.sub(lambda m: m.group(0).replace(m.group(1), "[ACCOUNT]"), out)
    return out


class RedactingFormatter(logging.Formatter):
    """Applied at the single point every line passes through.

    Redacting at call sites is a rule someone has to remember. Redacting at the
    formatter catches the exception traceback nobody wrote, which is where PII
    actually escapes.
    """

    def __init__(self, *args: Any, secrets_source: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._secrets_source = secrets_source

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        rendered = redact_pii(rendered)
        if self._secrets_source is not None:
            from backend.security.startup import redact

            rendered = redact(rendered, self._secrets_source)
        return rendered


def install(logger: logging.Logger | None = None, *, secrets_source: Any = None) -> None:
    """Wrap every existing handler's formatter rather than adding one.

    Adding a handler duplicates output; replacing them loses whatever
    configuration is already there. Wrapping keeps the format string and adds
    the guarantee.
    """
    target = logger or logging.getLogger()
    for handler in target.handlers:
        existing = handler.formatter
        handler.setFormatter(RedactingFormatter(
            fmt=getattr(existing, "_fmt", None),
            datefmt=getattr(existing, "datefmt", None),
            secrets_source=secrets_source,
        ))


__all__ = [
    "AADHAAR_SHAPED",
    "ACCOUNT",
    "EMAIL",
    "GSTIN",
    "PAN",
    "PHONE",
    "RedactingFormatter",
    "install",
    "is_aadhaar",
    "redact_pii",
]
