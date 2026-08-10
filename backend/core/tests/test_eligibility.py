"""Date-windowed eligibility — CORE-009.

The 80EEB case is the reason this subsystem exists. The section still reads
"₹1,50,000" and still appears in every listing of EV tax benefits, but the
sanction window closed on 31 March 2023. Any system that matches on the section
without checking the date tells a buyer today that they can claim it.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.eligibility import Facts, Status, claimable, closed_windows, evaluate_all

TODAY = date(2026, 8, 9)


def _facts(**values: object) -> Facts:
    regime = values.pop("regime", "old")
    return Facts(values=dict(values), as_of=TODAY, regime=str(regime))


def _one(facts: Facts, rule_id: str):
    matches = [o for o in evaluate_all(facts) if o.rule_id == rule_id]
    assert matches, f"rule {rule_id} not evaluated"
    return matches[0]


# ── the canonical trap ──────────────────────────────────────────────────────

def test_80eeb_window_closed_for_a_loan_taken_today() -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", taxpayer_type="individual",
               loan_sanction_date=date(2026, 9, 1)),
        "80EEB",
    )
    assert out.status is Status.WINDOW_CLOSED
    assert out.closed_on == date(2023, 3, 31)
    assert "31 March 2023" in out.message


def test_80eeb_eligible_inside_the_window() -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", taxpayer_type="individual",
               loan_sanction_date=date(2022, 6, 1)),
        "80EEB",
    )
    assert out.status is Status.ELIGIBLE


@pytest.mark.parametrize(
    "sanction,status",
    [
        (date(2018, 12, 31), Status.INELIGIBLE),      # before the window opened
        (date(2019, 1, 1), Status.ELIGIBLE),          # first eligible day
        (date(2023, 3, 31), Status.ELIGIBLE),         # last eligible day
        (date(2023, 4, 1), Status.WINDOW_CLOSED),     # first day after
    ],
)
def test_80eeb_window_boundaries(sanction: date, status: Status) -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", taxpayer_type="individual",
               loan_sanction_date=sanction),
        "80EEB",
    )
    assert out.status is status


def test_missing_date_asks_rather_than_assumes() -> None:
    """Defaulting the sanction date to today would silently reopen every
    closed window. Absence must be a question."""
    out = _one(
        _facts(asset_type="electric_vehicle", taxpayer_type="individual"),
        "80EEB",
    )
    assert out.status is Status.INSUFFICIENT_DATA
    assert out.missing_fields == ("loan_sanction_date",)
    assert "loan_sanction_date" in out.message


# ── precedence: a closed window outranks a changeable regime ────────────────

def test_closed_window_reported_even_on_the_wrong_regime() -> None:
    """Reporting "switch to the old regime" would be actionable and useless —
    the window shut in 2023 either way."""
    out = _one(
        _facts(asset_type="electric_vehicle", taxpayer_type="individual",
               loan_sanction_date=date(2026, 9, 1), regime="new"),
        "80EEB",
    )
    assert out.status is Status.WINDOW_CLOSED


def test_regime_reported_when_the_window_is_open() -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", taxpayer_type="individual",
               loan_sanction_date=date(2022, 6, 1), regime="new"),
        "80EEB",
    )
    assert out.status is Status.INELIGIBLE
    assert "new regime" in out.reason


# ── applicability: don't show a car buyer the two-wheeler scheme ────────────

def test_car_buyer_is_not_shown_the_two_wheeler_incentive() -> None:
    facts = _facts(asset_type="electric_vehicle", vehicle_category="car",
                   purchase_date=date(2026, 9, 1))
    out = _one(facts, "PM_E_DRIVE_2W")
    assert out.status is Status.INELIGIBLE
    assert not out.status.should_surface


def test_pm_edrive_does_not_cover_cars() -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", vehicle_category="car",
               purchase_date=date(2026, 9, 1)),
        "PM_E_DRIVE_CAR",
    )
    assert out.status is Status.INELIGIBLE
    assert "does not cover electric cars" in out.reason


def test_pm_edrive_car_rule_stays_quiet_for_a_gold_buyer() -> None:
    """An always-ineligible rule must not raise a question it can only answer
    with 'no'."""
    out = _one(_facts(asset_type="gold", purchase_date=date(2026, 9, 1)), "PM_E_DRIVE_CAR")
    assert out.status is Status.INELIGIBLE
    assert out.missing_fields == ()


@pytest.mark.parametrize(
    "purchase,status",
    [
        (date(2026, 7, 31), Status.ELIGIBLE),
        (date(2026, 8, 1), Status.WINDOW_CLOSED),
    ],
)
def test_pm_edrive_two_wheeler_terminal_date(purchase: date, status: Status) -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", vehicle_category="two_wheeler",
               purchase_date=purchase),
        "PM_E_DRIVE_2W",
    )
    assert out.status is status


def test_three_wheeler_runs_to_2028() -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", vehicle_category="three_wheeler",
               purchase_date=date(2027, 6, 1)),
        "PM_E_DRIVE_3W",
    )
    assert out.status is Status.ELIGIBLE


# ── availability is not eligibility ─────────────────────────────────────────

def test_sgb_primary_issuance_is_discontinued() -> None:
    """v1 recommends buying these. Primary issuance stopped in Feb 2024."""
    out = _one(_facts(asset_type="gold", purchase_date=date(2026, 9, 1)), "SGB_PRIMARY")
    assert out.status is Status.WINDOW_CLOSED
    assert "no new Sovereign Gold Bond tranche" in out.reason


def test_sgb_not_raised_for_an_unrelated_purchase() -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", vehicle_category="car",
               purchase_date=date(2026, 9, 1)),
        "SGB_PRIMARY",
    )
    assert out.status is Status.INELIGIBLE


# ── conditions ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("age,status", [(59, Status.INELIGIBLE), (60, Status.ELIGIBLE)])
def test_80ttb_age_condition(age: int, status: Status) -> None:
    assert _one(_facts(age=age), "80TTB").status is status


def test_80eea_stamp_duty_ceiling() -> None:
    out = _one(
        _facts(asset_type="residential_property", loan_sanction_date=date(2021, 6, 1),
               stamp_duty_value=5_000_000, owns_other_property=False),
        "80EEA",
    )
    assert out.status is Status.INELIGIBLE
    assert "at most" in out.reason


def test_24b_has_no_window() -> None:
    """The deduction most home buyers actually want once 80EE/80EEA turn out
    to be closed."""
    out = _one(_facts(property_use="self_occupied"), "24B_SELF_OCCUPIED")
    assert out.status is Status.ELIGIBLE
    assert out.max_benefit.amount == 200_000


# ── aggregate helpers and ordering ──────────────────────────────────────────

def test_claimable_returns_only_eligible() -> None:
    facts = _facts(age=65, property_use="self_occupied")
    assert all(o.status is Status.ELIGIBLE for o in claimable(facts))
    assert {o.rule_id for o in claimable(facts)} >= {"80TTB", "24B_SELF_OCCUPIED"}


def test_closed_windows_helper() -> None:
    facts = _facts(asset_type="electric_vehicle", taxpayer_type="individual",
                   loan_sanction_date=date(2026, 9, 1))
    assert {o.rule_id for o in closed_windows(facts)} == {"80EEB"}


def test_ordering_puts_actionable_first() -> None:
    facts = _facts(asset_type="electric_vehicle", taxpayer_type="individual",
                   loan_sanction_date=date(2026, 9, 1), age=65,
                   property_use="self_occupied")
    statuses = [o.status for o in evaluate_all(facts)]
    assert statuses == sorted(
        statuses,
        key=lambda s: [Status.ELIGIBLE, Status.WINDOW_CLOSED,
                       Status.INSUFFICIENT_DATA, Status.INELIGIBLE].index(s),
    )


def test_only_filter() -> None:
    facts = _facts(age=65)
    assert [o.rule_id for o in evaluate_all(facts, only=["80TTB"])] == ["80TTB"]


def test_outcome_serialises() -> None:
    out = _one(
        _facts(asset_type="electric_vehicle", taxpayer_type="individual",
               loan_sanction_date=date(2026, 9, 1)),
        "80EEB",
    )
    d = out.to_dict()
    assert d["status"] == "window_closed"
    assert d["closed_on"] == "2023-03-31"
    assert d["citation"]["legacy_section"] == "80EEB"
