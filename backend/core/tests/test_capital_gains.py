"""Capital gains — CORE-007.

v1's two errors, in opposite directions:
  * all LTCG at a flat 20% with no exemption (overstates equity LTCG by ~60%)
  * equity STCG added to slab income (wrong either way, depending on bracket)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.core.provenance.money import ZERO, Money, rupees
from backend.core.rules import RuleError, load_ruleset
from backend.core.tax_engine.capital_gains import (
    AssetClass,
    Disposal,
    compute_capital_gains,
    harvesting_headroom,
)

RS = load_ruleset("2026-27")


def _equity(cost: int, sale: int, *, months: int = 24, **kw) -> Disposal:
    sold = date(2026, 9, 1)
    acquired = date(sold.year - months // 12, sold.month - months % 12 or 1, 1)
    return Disposal(AssetClass.LISTED_EQUITY, acquired, sold,
                    rupees(cost), rupees(sale), **kw)


# ── s.112A: 12.5% with a ₹1,25,000 exemption ────────────────────────────────

def test_equity_ltcg_exemption_then_12_5_percent() -> None:
    r = compute_capital_gains([_equity(500_000, 900_000)], RS)
    assert r.equity_ltcg_gross == Money(400_000)
    assert r.equity_ltcg_exemption == Money(125_000)
    assert r.equity_ltcg_taxable == Money(275_000)
    assert r.total_tax == Money(34_375)          # v1 would say ₹80,000


def test_exemption_applies_once_across_all_disposals() -> None:
    r = compute_capital_gains(
        [_equity(100_000, 200_000), _equity(100_000, 200_000)], RS
    )
    assert r.equity_ltcg_gross == Money(200_000)
    assert r.equity_ltcg_exemption == Money(125_000)
    assert r.equity_ltcg_taxable == Money(75_000)


def test_gain_below_the_exemption_is_untaxed() -> None:
    r = compute_capital_gains([_equity(100_000, 200_000)], RS)
    assert r.equity_ltcg_taxable == ZERO
    assert r.total_tax == ZERO


def test_exemption_edge_exactly_at_limit() -> None:
    r = compute_capital_gains([_equity(100_000, 225_000)], RS)
    assert r.equity_ltcg_gross == Money(125_000)
    assert r.total_tax == ZERO


# ── s.111A: flat 20%, never the slab ────────────────────────────────────────

def test_equity_stcg_is_flat_20_percent() -> None:
    r = compute_capital_gains([_equity(200_000, 260_000, months=6)], RS)
    assert r.equity_stcg == Money(60_000)
    assert r.total_tax == Money(12_000)
    assert r.slab_taxed_gains == ZERO, "111A gains must never enter slab income"


def test_holding_period_boundary_at_12_months() -> None:
    sold = date(2026, 9, 1)
    short = Disposal(AssetClass.LISTED_EQUITY, date(2025, 9, 2), sold,
                     rupees(100_000), rupees(300_000))
    long_ = Disposal(AssetClass.LISTED_EQUITY, date(2025, 9, 1), sold,
                     rupees(100_000), rupees(300_000))
    assert compute_capital_gains([short], RS).equity_stcg == Money(200_000)
    assert compute_capital_gains([long_], RS).equity_ltcg_gross == Money(200_000)


# ── grandfathering ──────────────────────────────────────────────────────────

def test_pre_2018_cost_is_stepped_up() -> None:
    d = Disposal(AssetClass.LISTED_EQUITY, date(2015, 3, 1), date(2026, 9, 1),
                 rupees(100_000), rupees(400_000), fmv_2018_01_31=rupees(250_000))
    r = compute_capital_gains([d], RS)
    assert r.equity_ltcg_gross == Money(150_000)
    assert "stepped up" in r.lines[0].notes[0]


def test_step_up_is_capped_at_consideration_so_it_cannot_manufacture_a_loss() -> None:
    """A share whose price fell after Jan 2018 must not produce a phantom loss."""
    d = Disposal(AssetClass.LISTED_EQUITY, date(2015, 3, 1), date(2026, 9, 1),
                 rupees(100_000), rupees(180_000), fmv_2018_01_31=rupees(500_000))
    r = compute_capital_gains([d], RS)
    assert r.equity_ltcg_gross == ZERO
    assert r.lines[0].gain == ZERO


def test_no_step_up_for_post_2018_acquisitions() -> None:
    d = Disposal(AssetClass.LISTED_EQUITY, date(2019, 3, 1), date(2026, 9, 1),
                 rupees(100_000), rupees(400_000), fmv_2018_01_31=rupees(250_000))
    assert compute_capital_gains([d], RS).equity_ltcg_gross == Money(300_000)


def test_step_up_ignored_when_actual_cost_is_higher() -> None:
    d = Disposal(AssetClass.LISTED_EQUITY, date(2015, 3, 1), date(2026, 9, 1),
                 rupees(300_000), rupees(400_000), fmv_2018_01_31=rupees(250_000))
    r = compute_capital_gains([d], RS)
    assert r.equity_ltcg_gross == Money(100_000)
    assert r.lines[0].notes == []


# ── immovable property: the surviving use of the CII ────────────────────────

def test_pre_reform_property_takes_the_lower_of_two_computations() -> None:
    d = Disposal(AssetClass.IMMOVABLE_PROPERTY, date(2015, 6, 1), date(2026, 9, 1),
                 rupees(5_000_000), rupees(9_000_000), description="flat")
    r = compute_capital_gains([d], RS)
    note = r.lines[0].notes[0]
    assert "beats" in note and "applied the lower" in note
    assert r.total_tax > ZERO


def test_post_reform_property_has_no_indexation_option() -> None:
    d = Disposal(AssetClass.IMMOVABLE_PROPERTY, date(2024, 8, 1), date(2026, 9, 1),
                 rupees(5_000_000), rupees(9_000_000))
    r = compute_capital_gains([d], RS)
    assert r.lines[0].rate == Decimal("0.125")
    assert r.lines[0].notes == [], "acquired after 23 Jul 2024 — no indexation option"


def test_indexation_option_is_only_for_residents() -> None:
    d = Disposal(AssetClass.IMMOVABLE_PROPERTY, date(2015, 6, 1), date(2026, 9, 1),
                 rupees(5_000_000), rupees(9_000_000))
    r = compute_capital_gains([d], RS, resident_individual=False)
    assert r.lines[0].notes == []
    assert r.lines[0].rate == Decimal("0.125")


# ── slab-taxed categories ───────────────────────────────────────────────────

def test_debt_funds_are_always_slab_taxed() -> None:
    d = Disposal(AssetClass.DEBT_MF, date(2023, 6, 1), date(2026, 9, 1),
                 rupees(100_000), rupees(150_000))
    r = compute_capital_gains([d], RS)
    assert r.slab_taxed_gains == Money(50_000)
    assert r.total_tax == ZERO
    assert any("slab" in n for n in r.notes)


def test_short_term_non_equity_is_slab_taxed() -> None:
    d = Disposal(AssetClass.GOLD, date(2026, 1, 1), date(2026, 9, 1),
                 rupees(100_000), rupees(160_000))
    r = compute_capital_gains([d], RS)
    assert r.slab_taxed_gains == Money(60_000)


def test_long_term_gold_is_12_5_percent() -> None:
    d = Disposal(AssetClass.GOLD, date(2023, 1, 1), date(2026, 9, 1),
                 rupees(100_000), rupees(300_000))
    r = compute_capital_gains([d], RS)
    assert r.other_ltcg == Money(200_000)
    assert r.total_tax == Money(25_000)


# ── transfer expenses and improvement ───────────────────────────────────────

def test_transfer_expenses_reduce_the_gain() -> None:
    d = Disposal(AssetClass.LISTED_EQUITY, date(2020, 1, 1), date(2026, 9, 1),
                 rupees(100_000), rupees(500_000), transfer_expenses=rupees(10_000))
    assert compute_capital_gains([d], RS).equity_ltcg_gross == Money(390_000)


def test_improvement_cost_reduces_the_gain() -> None:
    d = Disposal(AssetClass.IMMOVABLE_PROPERTY, date(2024, 8, 1), date(2026, 9, 1),
                 rupees(1_000_000), rupees(2_000_000), improvement_cost=rupees(200_000))
    assert compute_capital_gains([d], RS).other_ltcg == Money(800_000)


# ── split year: refuse rather than guess ────────────────────────────────────

def test_fy_2024_25_refuses_a_pre_reform_transfer() -> None:
    rs = load_ruleset("2024-25")
    d = Disposal(AssetClass.LISTED_EQUITY, date(2020, 1, 1), date(2024, 6, 1),
                 rupees(100_000), rupees(200_000))
    with pytest.raises(RuleError, match="straddles"):
        compute_capital_gains([d], rs)


def test_fy_2024_25_accepts_a_post_reform_transfer() -> None:
    rs = load_ruleset("2024-25")
    d = Disposal(AssetClass.LISTED_EQUITY, date(2020, 1, 1), date(2024, 9, 1),
                 rupees(100_000), rupees(400_000))
    assert compute_capital_gains([d], rs).equity_ltcg_gross == Money(300_000)


# ── harvesting headroom ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "realised,expected",
    [(0, 125_000), (50_000, 75_000), (125_000, 0), (300_000, 0)],
)
def test_harvesting_headroom(realised: int, expected: int) -> None:
    assert harvesting_headroom(rupees(realised), RS) == Money(expected)


# ── trace and misc ──────────────────────────────────────────────────────────

def test_trace_replays() -> None:
    r = compute_capital_gains(
        [_equity(500_000, 900_000), _equity(200_000, 260_000, months=6)], RS
    )
    assert r.trace.verify() == []


def test_empty_disposals() -> None:
    r = compute_capital_gains([], RS)
    assert r.total_tax == ZERO and r.lines == []


def test_asset_class_is_equity_flag() -> None:
    assert AssetClass.LISTED_EQUITY.is_equity
    assert AssetClass.EQUITY_MF.is_equity
    assert not AssetClass.GOLD.is_equity


def test_special_rate_income_feeds_the_surcharge_calculation() -> None:
    r = compute_capital_gains([_equity(500_000, 900_000)], RS)
    assert r.total_special_rate_income == Money(275_000)


def test_property_holding_period_is_24_months_not_12() -> None:
    """The error that made two of these tests fail on first run: property is a
    24-month asset, so 15 months of ownership is SHORT term and slab-taxed."""
    sold = date(2026, 9, 1)
    short = Disposal(AssetClass.IMMOVABLE_PROPERTY, date(2025, 6, 1), sold,
                     rupees(1_000_000), rupees(1_500_000))
    long_ = Disposal(AssetClass.IMMOVABLE_PROPERTY, date(2024, 8, 1), sold,
                     rupees(1_000_000), rupees(1_500_000))
    assert compute_capital_gains([short], RS).slab_taxed_gains == Money(500_000)
    assert compute_capital_gains([long_], RS).other_ltcg == Money(500_000)
