"""Broker P&L parsers — DOC-002.

Turns a broker's tradewise statement into `Disposal` objects the capital gains
engine can price. This is where retail investors actually lose money: the
holding period, the ₹1,25,000 s.112A exemption and the pre-2018 grandfathering
are all mechanical, all easy to get wrong by hand, and all worth real rupees.

Design
------
Brokers export CSVs with different headers for the same columns. Rather than
one parser per broker, there is one parser and a **column map** per broker —
adding Groww or CAMS is a dictionary entry, not a new module.

Reconciliation is mandatory
---------------------------
Every statement states its own totals. After parsing, the sum of the parsed
rows must match the stated total, or the parse FAILS. A parser that silently
drops three rows out of two hundred produces a plausible, precisely wrong
capital gains figure — which is exactly the class of error this project exists
to eliminate. Better to refuse than to under-report someone's gains to the
department.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from backend.core.provenance.money import Money
from backend.core.tax_engine.capital_gains import AssetClass, Disposal

# Equity acquired before this date gets a fair-market-value step-up under the
# s.112A grandfathering proviso.
GRANDFATHER_DATE = date(2018, 1, 31)


class Broker(str, Enum):
    ZERODHA = "zerodha"
    GROWW = "groww"
    CAMS = "cams"


class BrokerParseError(Exception):
    """The statement could not be read, or does not reconcile."""


# ── column maps ─────────────────────────────────────────────────────────────
#
# Header text is matched case-insensitively after stripping punctuation, so
# "Buy Date", "buy_date" and "Buy date" all resolve to the same field.

_COLUMN_MAPS: dict[Broker, dict[str, tuple[str, ...]]] = {
    Broker.ZERODHA: {
        "symbol": ("symbol", "scrip", "instrument"),
        "isin": ("isin",),
        "quantity": ("quantity", "qty"),
        "acquired_on": ("buy date", "buy_date", "purchase date"),
        "sold_on": ("sell date", "sell_date", "sale date"),
        "cost": ("buy value", "buy_value", "purchase value"),
        "consideration": ("sell value", "sell_value", "sale value"),
    },
    Broker.GROWW: {
        "symbol": ("stock name", "scheme name", "symbol"),
        "isin": ("isin",),
        "quantity": ("quantity", "units"),
        "acquired_on": ("buy date", "purchase date"),
        "sold_on": ("sell date", "redemption date"),
        "cost": ("buy amount", "purchase amount", "cost of acquisition"),
        "consideration": ("sell amount", "redemption amount", "sale consideration"),
    },
    Broker.CAMS: {
        "symbol": ("scheme name", "fund name"),
        "isin": ("isin",),
        "quantity": ("units",),
        "acquired_on": ("purchase date", "allotment date"),
        "sold_on": ("redemption date", "sale date"),
        "cost": ("cost of acquisition", "purchase amount"),
        "consideration": ("redemption amount", "sale amount"),
        "asset_class": ("scheme type", "category"),
    },
}

# Statement-level totals, used for the reconciliation check.
_TOTAL_LABELS = (
    "total realised p&l", "total realized p&l", "total p&l",
    "net realised gain", "total gain", "grand total",
)


def _normalise(header: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", header.strip().lower()).strip()


def _resolve_columns(
    headers: list[str], column_map: dict[str, tuple[str, ...]]
) -> dict[str, int]:
    """Map our field names to this statement's column indices."""
    normalised = [_normalise(h) for h in headers]
    resolved: dict[str, int] = {}

    for field_name, candidates in column_map.items():
        for candidate in candidates:
            for i, header in enumerate(normalised):
                if header == candidate or candidate in header:
                    resolved[field_name] = i
                    break
            if field_name in resolved:
                break
    return resolved


_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y")


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = re.sub(r"[₹,\s]|Rs\.?|INR", "", str(raw), flags=re.IGNORECASE)
    if not cleaned or cleaned in {"-", "--"}:
        return None
    # Brokers write losses as (1,234) as well as -1234.
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if negative else value


def _cell(row: list[str], columns: dict[str, int], name: str) -> str:
    """Read a named column from a row, tolerating short rows."""
    idx = columns.get(name)
    return row[idx].strip() if idx is not None and idx < len(row) else ""


def _infer_asset_class(symbol: str, scheme_type: str = "") -> AssetClass:
    """Classify from the scheme description.

    Debt funds bought on or after 1 April 2023 are always short-term and
    slab-taxed, so getting this wrong changes the rate entirely.
    """
    text = f"{symbol} {scheme_type}".lower()
    if any(w in text for w in ("debt", "liquid", "gilt", "bond", "money market",
                               "corporate bond", "credit risk", "overnight")):
        return AssetClass.DEBT_MF
    if any(w in text for w in ("equity", "elss", "index", "large cap", "mid cap",
                               "small cap", "flexi", "nifty", "sensex")):
        return AssetClass.EQUITY_MF
    if "gold" in text:
        return AssetClass.GOLD
    return AssetClass.LISTED_EQUITY


# ── result ──────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ParsedStatement:
    broker: Broker
    disposals: list[Disposal] = field(default_factory=list)
    skipped_rows: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stated_total: Decimal | None = None

    @property
    def computed_total(self) -> Decimal:
        return sum(
            (d.consideration.amount - d.cost.amount for d in self.disposals),
            Decimal(0),
        )

    @property
    def needs_fmv(self) -> list[Disposal]:
        """Pre-2018 equity holdings, which need a 31 Jan 2018 fair market value
        before they can be priced correctly.

        Without it the engine uses actual cost, which OVERSTATES the gain — the
        user pays tax they do not owe. Surfaced rather than silently accepted.
        """
        return [
            d for d in self.disposals
            if d.asset.is_equity
            and d.acquired_on < GRANDFATHER_DATE
            and d.fmv_2018_01_31 is None
        ]

    def reconcile(self) -> None:
        """The statement must agree with itself, or we refuse it.

        A parser that quietly drops rows produces a plausible, precisely wrong
        gains figure. Under-reporting to the department is not a rounding error.
        """
        if self.stated_total is None:
            self.warnings.append(
                "the statement declares no total, so the parse could not be "
                "cross-checked against it"
            )
            return

        drift = self.computed_total - self.stated_total
        if abs(drift) > Decimal("1"):
            raise BrokerParseError(
                f"parsed rows total {self.computed_total:,} but the statement "
                f"states {self.stated_total:,} (difference {drift:,}). "
                f"{len(self.skipped_rows)} row(s) were skipped. Refusing to "
                f"return a gains figure that does not match the source."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker.value,
            "disposals": len(self.disposals),
            "skipped_rows": self.skipped_rows,
            "warnings": self.warnings,
            "stated_total": str(self.stated_total) if self.stated_total is not None else None,
            "computed_total": str(self.computed_total),
            "needs_fmv": [d.description for d in self.needs_fmv],
        }


# ── parsing ─────────────────────────────────────────────────────────────────

def parse_csv(text: str, broker: Broker) -> ParsedStatement:
    """Parse a broker's tradewise CSV export."""
    if not text or not text.strip():
        raise BrokerParseError("empty statement")

    column_map = _COLUMN_MAPS[broker]
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise BrokerParseError("no rows found")

    # Brokers put preamble above the table, so find the header row rather than
    # assuming it is first.
    header_index, columns = None, {}
    for i, row in enumerate(rows[:40]):
        resolved = _resolve_columns(row, column_map)
        if {"acquired_on", "sold_on", "cost", "consideration"} <= resolved.keys():
            header_index, columns = i, resolved
            break

    if header_index is None:
        raise BrokerParseError(
            f"could not find a recognisable {broker.value} tradewise table. "
            f"Expected columns for buy date, sell date, buy value and sell "
            f"value. Refusing to guess at which columns mean what."
        )

    statement = ParsedStatement(broker=broker)

    for row in rows[header_index + 1 :]:
        if not any(cell.strip() for cell in row):
            continue

        joined = " ".join(row).lower()
        if any(label in joined for label in _TOTAL_LABELS):
            for cell in row:
                if (value := _parse_amount(cell)) is not None:
                    statement.stated_total = value
            continue

        acquired = _parse_date(_cell(row, columns, "acquired_on"))
        sold = _parse_date(_cell(row, columns, "sold_on"))
        cost = _parse_amount(_cell(row, columns, "cost"))
        consideration = _parse_amount(_cell(row, columns, "consideration"))
        symbol = _cell(row, columns, "symbol") or "unknown"

        missing = [
            name for name, value in (
                ("buy date", acquired), ("sell date", sold),
                ("buy value", cost), ("sell value", consideration),
            ) if value is None
        ]
        if missing:
            statement.skipped_rows.append(
                f"{symbol}: could not read {', '.join(missing)}"
            )
            continue

        if sold < acquired:
            statement.skipped_rows.append(
                f"{symbol}: sell date {sold} precedes buy date {acquired}"
            )
            continue

        statement.disposals.append(
            Disposal(
                asset=_infer_asset_class(symbol, _cell(row, columns, "asset_class")),
                acquired_on=acquired,
                sold_on=sold,
                cost=Money(cost),
                consideration=Money(consideration),
                description=symbol,
            )
        )

    if not statement.disposals:
        raise BrokerParseError(
            "no usable rows. "
            + ("; ".join(statement.skipped_rows[:3]) if statement.skipped_rows
               else "the table was empty")
        )

    if statement.skipped_rows:
        statement.warnings.append(
            f"{len(statement.skipped_rows)} row(s) could not be read and are "
            f"excluded — check them by hand before filing"
        )

    if statement.needs_fmv:
        statement.warnings.append(
            f"{len(statement.needs_fmv)} pre-2018 equity holding(s) need their "
            f"31 January 2018 fair market value. Without it the gain is "
            f"OVERSTATED and you would pay tax you do not owe."
        )

    statement.reconcile()
    return statement
