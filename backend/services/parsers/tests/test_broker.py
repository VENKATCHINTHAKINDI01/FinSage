"""Broker P&L parsers — DOC-002.

The load-bearing test here is `test_dropped_rows_fail_the_parse`. Everything
else is plumbing; that one is the difference between a tool and a liability.
A parser that silently loses three rows out of two hundred under-reports
someone's capital gains to the department, and nothing downstream would notice.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.core.tax_engine.capital_gains import AssetClass
from backend.services.parsers.broker import (
    Broker,
    BrokerParseError,
    parse_csv,
)

# ── fixtures ────────────────────────────────────────────────────────────────

ZERODHA = """Tradewise Exits from 2026-04-01 to 2027-03-31
Symbol,ISIN,Quantity,Buy Date,Buy Value,Sell Date,Sell Value
INFY,INE009A01021,100,2020-05-01,500000.00,2026-09-01,900000.00
TCS,INE467B01029,50,2026-01-10,200000.00,2026-08-01,260000.00
Total Realised P&L,,,,,,460000.00
"""

# Same data, a different broker's headers and date format.
GROWW = """Capital Gains Statement
Stock Name,ISIN,Quantity,Purchase Date,Purchase Amount,Sell Date,Sell Amount
Reliance Industries,INE002A01018,20,15-06-2019,180000.00,10-09-2026,320000.00
HDFC Bank Equity Fund,INF179K01XQ0,500,01-04-2024,250000.00,15-12-2026,310000.00
Total Gain,,,,,,200000.00
"""

CAMS = """CONSOLIDATED CAPITAL GAINS STATEMENT
Scheme Name,Scheme Type,ISIN,Units,Purchase Date,Cost of Acquisition,Redemption Date,Redemption Amount
Axis Liquid Fund,Debt Scheme,INF846K01EW2,1000,10-Jun-2023,100000.00,12-Aug-2026,112000.00
Nifty 50 Index Fund,Equity Scheme,INF204KB14I2,800,05-Mar-2021,150000.00,20-Nov-2026,290000.00
Grand Total,,,,,,,152000.00
"""


# ── the happy path ──────────────────────────────────────────────────────────

class TestZerodha:
    def test_rows_parse(self) -> None:
        s = parse_csv(ZERODHA, Broker.ZERODHA)
        assert len(s.disposals) == 2
        assert s.skipped_rows == []

    def test_dates_and_amounts(self) -> None:
        infy = parse_csv(ZERODHA, Broker.ZERODHA).disposals[0]
        assert infy.description == "INFY"
        assert infy.acquired_on == date(2020, 5, 1)
        assert infy.sold_on == date(2026, 9, 1)
        assert infy.cost.amount == Decimal("500000.00")
        assert infy.consideration.amount == Decimal("900000.00")

    def test_it_reconciles_against_the_stated_total(self) -> None:
        s = parse_csv(ZERODHA, Broker.ZERODHA)
        assert s.stated_total == Decimal("460000.00")
        assert s.computed_total == Decimal("460000.00")

    def test_output_prices_through_the_engine(self) -> None:
        """The whole point: statement in, correct tax out, no manual entry."""
        from backend.core.rules import load_ruleset
        from backend.core.tax_engine import compute_capital_gains

        s = parse_csv(ZERODHA, Broker.ZERODHA)
        r = compute_capital_gains(s.disposals, load_ruleset("2026-27"))

        # INFY held 6 years -> 112A long term, 4,00,000 gain less the
        # 1,25,000 exemption at 12.5%. TCS held 7 months -> 111A at a flat 20%.
        assert r.equity_ltcg_gross.amount == Decimal("400000.00")
        assert r.equity_ltcg_exemption.amount == Decimal("125000.00")
        assert r.equity_stcg.amount == Decimal("60000.00")
        assert r.total_tax.amount == Decimal("46375.00")


def test_a_different_brokers_headers_and_date_format() -> None:
    s = parse_csv(GROWW, Broker.GROWW)
    assert len(s.disposals) == 2
    assert s.disposals[0].acquired_on == date(2019, 6, 15)
    assert s.disposals[0].consideration.amount == Decimal("320000.00")


class TestCams:
    def test_scheme_type_drives_the_asset_class(self) -> None:
        """Debt versus equity changes the rate entirely — debt units bought
        after April 2023 are always short-term and slab-taxed."""
        by_name = {d.description: d for d in parse_csv(CAMS, Broker.CAMS).disposals}
        assert by_name["Axis Liquid Fund"].asset is AssetClass.DEBT_MF
        assert by_name["Nifty 50 Index Fund"].asset is AssetClass.EQUITY_MF

    def test_month_name_dates(self) -> None:
        s = parse_csv(CAMS, Broker.CAMS)
        assert s.disposals[0].acquired_on == date(2023, 6, 10)


# ── the test that matters most ──────────────────────────────────────────────

def test_dropped_rows_fail_the_parse() -> None:
    """A row the parser cannot read must not simply vanish.

    Here one row has an unreadable sell value. The remaining rows no longer sum
    to the stated total, and the parse refuses rather than returning a gains
    figure that is quietly too low.
    """
    broken = ZERODHA.replace(
        "TCS,INE467B01029,50,2026-01-10,200000.00,2026-08-01,260000.00",
        "TCS,INE467B01029,50,2026-01-10,200000.00,2026-08-01,NOT-A-NUMBER",
    )
    with pytest.raises(BrokerParseError) as exc:
        parse_csv(broken, Broker.ZERODHA)

    assert "does not match the source" in str(exc.value)
    assert "1 row(s) were skipped" in str(exc.value)


def test_a_statement_with_no_total_warns_rather_than_silently_passing() -> None:
    """Without a stated total there is nothing to check against, and saying so
    is better than implying the parse was verified."""
    no_total = "\n".join(
        ln for ln in ZERODHA.splitlines() if "Total Realised" not in ln
    )
    s = parse_csv(no_total, Broker.ZERODHA)
    assert s.stated_total is None
    assert any("could not be cross-checked" in w for w in s.warnings)


# ── refusals ────────────────────────────────────────────────────────────────

class TestRefusals:
    def test_empty(self) -> None:
        with pytest.raises(BrokerParseError, match="empty"):
            parse_csv("", Broker.ZERODHA)

    def test_an_unrecognisable_table(self) -> None:
        with pytest.raises(BrokerParseError, match="Refusing to guess"):
            parse_csv("Name,Address,Phone\nA,B,C", Broker.ZERODHA)

    def test_a_table_with_no_usable_rows(self) -> None:
        header = ZERODHA.splitlines()[1]
        with pytest.raises(BrokerParseError, match="no usable rows"):
            parse_csv(f"{header}\nX,Y,1,bad,bad,bad,bad\n", Broker.ZERODHA)

    def test_a_sell_before_a_buy_is_rejected_not_computed(self) -> None:
        reversed_dates = ZERODHA.replace(
            "INFY,INE009A01021,100,2020-05-01,500000.00,2026-09-01,900000.00",
            "INFY,INE009A01021,100,2026-09-01,500000.00,2020-05-01,900000.00",
        )
        with pytest.raises(BrokerParseError):
            parse_csv(reversed_dates, Broker.ZERODHA)


# ── grandfathering ──────────────────────────────────────────────────────────

def test_pre_2018_equity_is_flagged_as_needing_a_fair_market_value() -> None:
    """Without the 31 Jan 2018 FMV the engine uses actual cost, which
    OVERSTATES the gain — the user pays tax they do not owe. That has to be
    surfaced, not quietly accepted."""
    old = """Symbol,ISIN,Quantity,Buy Date,Buy Value,Sell Date,Sell Value
WIPRO,INE075A01022,200,2015-03-01,100000.00,2026-09-01,400000.00
Total Realised P&L,,,,,,300000.00
"""
    s = parse_csv(old, Broker.ZERODHA)
    assert len(s.needs_fmv) == 1
    assert any("OVERSTATED" in w for w in s.warnings)


def test_post_2018_equity_needs_no_fair_market_value() -> None:
    s = parse_csv(ZERODHA, Broker.ZERODHA)
    assert s.needs_fmv == []


# ── amount formats ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "cell,expected",
    [
        ("1,25,000.50", Decimal("125000.50")),
        ("₹ 90,000", Decimal("90000")),
        ("Rs 1234", Decimal("1234")),
        ("(4,500)", Decimal("-4500")),   # brokers write losses in brackets
        ("-4500", Decimal("-4500")),
    ],
)
def test_amount_formats(cell: str, expected: Decimal) -> None:
    from backend.services.parsers.broker import _parse_amount

    assert _parse_amount(cell) == expected


def test_a_loss_making_row_parses_as_a_loss() -> None:
    losing = """Symbol,ISIN,Quantity,Buy Date,Buy Value,Sell Date,Sell Value
YESBANK,INE528G01035,500,2025-01-01,100000.00,2026-06-01,60000.00
Total Realised P&L,,,,,,-40000.00
"""
    s = parse_csv(losing, Broker.ZERODHA)
    assert s.computed_total == Decimal("-40000.00")


def test_serialises() -> None:
    d = parse_csv(ZERODHA, Broker.ZERODHA).to_dict()
    assert d["broker"] == "zerodha"
    assert d["disposals"] == 2
    assert d["computed_total"] == "460000.00"


@pytest.mark.skip(
    reason="DOC-002 acceptance requires real broker exports. These fixtures are "
           "synthetic; the real risk is column drift between broker versions, "
           "which cannot be measured against fixtures I wrote myself."
)
def test_against_real_broker_exports() -> None:
    """Deliberately visible. DOC-002 does not reach `verified` without this."""
