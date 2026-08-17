"""Landed cost — PRC-003.

Three claims, in descending order of how much money a mistake costs:

  * GST credit on a passenger vehicle is BLOCKED — granting it overstates the
    saving by the entire GST amount, the largest error available here
  * an unlisted state RAISES rather than averaging road tax
  * the depreciation half-rate under 180 days is applied, because it is what
    makes 31 March and 1 April different dates for a business buyer
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.core.costing.landed_cost import (
    Purchase,
    StateNotCovered,
    compute_landed_cost,
    gst_rate_for,
    itc_available,
    road_tax_rate,
)
from backend.core.provenance.money import ZERO, rupees
from backend.core.rules.loader import RuleError

FY = "2026-27"
WHEN = date(2026, 8, 12)


def _load(name):
    import pathlib

    import yaml

    from backend.core.rules.loader import RULES_DIR

    return yaml.safe_load(
        (pathlib.Path(RULES_DIR) / name).read_text(encoding="utf-8")
    )


GST = _load("gst.yaml")
PROC = _load("procurement.yaml")


def ev(**kw) -> Purchase:
    base = {
        "item": "Electric hatchback", "ex_showroom": rupees(1_400_000),
        "category": "electric_vehicle", "state": "KA", "purchase_date": WHEN,
        "is_electric": True,
    }
    base.update(kw)
    return Purchase(**base)


# ══ GST 2.0, effective-dated ════════════════════════════════════════════════

class TestGst:
    def test_an_ev_is_five_percent(self) -> None:
        assert gst_rate_for("electric_vehicle", WHEN, GST)[0] == Decimal("0.05")

    def test_a_large_petrol_car_is_forty(self) -> None:
        assert gst_rate_for("petrol_vehicle_large", WHEN, GST)[0] == Decimal("0.40")

    def test_gold_sits_outside_the_headline_slabs_at_three(self) -> None:
        """A long-standing special rate, not an error."""
        assert gst_rate_for("gold_jewellery", WHEN, GST)[0] == Decimal("0.03")

    def test_completed_property_attracts_no_gst(self) -> None:
        assert gst_rate_for("completed_property", WHEN, GST)[0] == ZERO.amount

    def test_the_abolished_slabs_are_gone_from_the_current_schedule(self) -> None:
        """GST 2.0 removed 12% and 28%. Any engine still carrying them
        mis-costs a large share of goods."""
        current = gst_rate_for("electronics_consumer", WHEN, GST)[1]
        schedule = next(s for s in GST["schedules"] if s["name"] == current)
        assert "0.12" not in schedule["slabs"]
        assert "0.28" not in schedule["slabs"]
        assert set(schedule["abolished_slabs"]) == {"0.12", "0.28"}

    def test_a_purchase_before_the_restructure_uses_the_old_schedule(self) -> None:
        """GST 2.0 landed mid-year on 22 September 2025. A dealer-quote
        teardown or revised return still needs the schedule that applied."""
        _, name = gst_rate_for("electronics_consumer", date(2025, 6, 1), GST)
        assert name == "GST 1.0"
        _, name = gst_rate_for("electronics_consumer", date(2025, 10, 1), GST)
        assert name == "GST 2.0"

    def test_an_unknown_category_falls_to_the_default_slab(self) -> None:
        assert gst_rate_for("something_new", WHEN, GST)[0] == Decimal("0.18")


# ══ road tax: an unlisted state raises ══════════════════════════════════════

class TestRoadTax:
    def test_an_unlisted_state_raises_rather_than_averaging(self) -> None:
        """Road tax is a state levy with thirty-odd schedules. An average is
        wrong by tens of thousands while looking authoritative."""
        with pytest.raises(StateNotCovered, match="averaging it"):
            road_tax_rate("UP", ev(state="UP"), PROC)

    def test_the_error_lists_what_is_covered(self) -> None:
        with pytest.raises(StateNotCovered) as e:
            road_tax_rate("UP", ev(state="UP"), PROC)
        assert "'KA'" in str(e.value)

    @pytest.mark.parametrize("state", ["KA", "MH", "DL", "TN"])
    def test_every_covered_state_exempts_evs(self, state) -> None:
        assert road_tax_rate(state, ev(state=state), PROC) == ZERO.amount

    def test_a_petrol_car_is_banded_by_price(self) -> None:
        cheap = Purchase("car", rupees(400_000), "petrol_vehicle_small", "KA", WHEN)
        dear = Purchase("car", rupees(2_500_000), "petrol_vehicle_large", "KA", WHEN)
        assert road_tax_rate("KA", cheap, PROC) < road_tax_rate("KA", dear, PROC)

    def test_the_top_band_has_no_ceiling(self) -> None:
        huge = Purchase("car", rupees(90_000_000), "petrol_vehicle_large", "KA", WHEN)
        assert road_tax_rate("KA", huge, PROC) == Decimal("0.18")


# ══ ITC: the largest available error ════════════════════════════════════════

class TestInputTaxCredit:
    def test_a_consultancy_buying_a_car_gets_no_credit(self) -> None:
        """s.17(5) blocks it. Granting it overstates the saving by the whole
        GST amount — the single largest error in this model."""
        ok, why = itc_available(
            ev(is_gst_registered=True, is_business_use=True,
               business_use_kind="general"),
            PROC,
        )
        assert not ok
        assert "blocked under s.17(5)" in why
        assert "however legitimate" in why

    @pytest.mark.parametrize(
        "kind",
        ["resale_of_vehicles", "passenger_transport_service", "driving_school",
         "goods_transport"],
    )
    def test_the_four_permitted_uses_do_get_credit(self, kind) -> None:
        ok, _ = itc_available(
            ev(is_gst_registered=True, is_business_use=True,
               business_use_kind=kind),
            PROC,
        )
        assert ok

    def test_an_unregistered_buyer_has_no_credit_to_claim(self) -> None:
        ok, why = itc_available(ev(is_business_use=True), PROC)
        assert not ok and "not GST-registered" in why

    def test_a_personal_purchase_raises_no_credit(self) -> None:
        ok, why = itc_available(ev(is_gst_registered=True), PROC)
        assert not ok and "personal use" in why

    def test_the_blocked_reason_reaches_the_output(self) -> None:
        r = compute_landed_cost(
            ev(is_gst_registered=True, is_business_use=True,
               business_use_kind="general", depreciation_block="motor_vehicle"),
            FY,
        )
        assert any("No input tax credit" in n for n in r.notes)
        assert not any(x.label == "Input tax credit" for x in r.lines)

    def test_a_taxi_operator_does_get_the_credit_line(self) -> None:
        r = compute_landed_cost(
            ev(is_gst_registered=True, is_business_use=True,
               business_use_kind="passenger_transport_service"),
            FY,
        )
        itc = next(x for x in r.lines if x.label == "Input tax credit")
        assert itc.amount == rupees(70_000)      # 5% of 14,00,000
        assert itc.is_deduction


# ══ depreciation and the 180-day rule ═══════════════════════════════════════

class TestDepreciation:
    def _landed(self, days: int):
        return compute_landed_cost(
            ev(is_business_use=True, depreciation_block="motor_vehicle",
               days_used_in_year=days, marginal_tax_rate=Decimal("0.30")),
            FY,
        )

    def test_full_rate_when_used_over_180_days(self) -> None:
        """14,00,000 x 15% x 30% = 63,000 of tax saved."""
        line = next(
            x for x in self._landed(200).lines if "depreciation" in x.label.lower()
        )
        assert line.amount == rupees(63_000)

    def test_half_rate_under_180_days(self) -> None:
        line = next(
            x for x in self._landed(100).lines if "depreciation" in x.label.lower()
        )
        assert line.amount == rupees(31_500)

    def test_the_boundary_is_exclusive(self) -> None:
        assert self._landed(180).landed < self._landed(179).landed

    def test_the_user_is_told_the_other_half_is_not_lost(self) -> None:
        note = next(n for n in self._landed(100).notes if "half" in n.lower())
        assert "not lost" in note
        assert "written-down value" in note

    def test_an_unknown_block_raises_rather_than_guessing(self) -> None:
        with pytest.raises(RuleError, match="no depreciation rate"):
            compute_landed_cost(
                ev(is_business_use=True, depreciation_block="spaceship"), FY,
            )


# ══ the worked example ══════════════════════════════════════════════════════

class TestWorkedExample:
    def test_an_ev_in_karnataka_end_to_end(self) -> None:
        """14,00,000 + 5% GST + 0% road tax + 600 registration + 45,000
        insurance = 15,15,600. Every line checkable by hand."""
        r = compute_landed_cost(ev(insurance=rupees(45_000)), FY)
        assert r.on_road == rupees(1_515_600)
        assert r.landed == r.on_road, "no business reliefs for a personal buyer"

    def test_the_petrol_equivalent_is_four_lakh_dearer(self) -> None:
        """5% vs 18% GST and 0% vs 14% road tax on the same 14L car."""
        e = compute_landed_cost(ev(insurance=rupees(45_000)), FY)
        p = compute_landed_cost(
            Purchase("Petrol hatchback", rupees(1_400_000),
                     "petrol_vehicle_small", "KA", WHEN,
                     insurance=rupees(45_000)),
            FY,
        )
        assert p.on_road - e.on_road == rupees(420_000)

    def test_subsidies_and_discounts_come_off(self) -> None:
        r = compute_landed_cost(
            ev(subsidies={"State EV incentive": rupees(50_000)},
               discounts={"Dealer discount": rupees(25_000)}),
            FY,
        )
        assert r.total_deductions == rupees(75_000)
        assert r.landed == r.on_road - rupees(75_000)

    def test_a_personal_buyer_is_told_the_reliefs_do_not_apply(self) -> None:
        r = compute_landed_cost(ev(), FY)
        assert any("business reliefs" in n for n in r.notes)

    def test_the_worksheet_replays(self) -> None:
        assert compute_landed_cost(ev(insurance=rupees(45_000)), FY).trace.verify() == []

    def test_serialises_with_every_line_sourced(self) -> None:
        d = compute_landed_cost(ev(insurance=rupees(45_000)), FY).to_dict(WHEN)
        assert d["on_road"] == "1515600.00"
        for line in d["lines"]:
            assert line["source"]["may_drive_a_cost_line"] is True
            assert line["source"]["fetched_on"]


# ── PRC-003: coverage comes from the gatherer, not from this repository ─────

def _fact(key: str, value: str):
    from backend.core.provenance.sourcing import SourcedFact, Tier
    return SourcedFact(
        key=key, value=value, source_url="https://transport.tr.gov.in/rates",
        tier=Tier.OFFICIAL, fetched_on=date(2026, 6, 1), source_kind="road_tax",
    )


def _tripura(**kw):
    base = {
        "item": "Hatchback", "ex_showroom": rupees(800000),
        "category": "motor_vehicle", "state": "TR",
        "purchase_date": date(2026, 6, 1),
    }
    base.update(kw)
    return Purchase(**base)


def test_an_uncovered_state_still_raises_when_nothing_has_been_gathered():
    """The refusal that made the table honest stays. Averaging road tax is
    wrong by tens of thousands of rupees while looking authoritative."""
    with pytest.raises(StateNotCovered, match="no road tax rate for 'TR'"):
        compute_landed_cost(_tripura(), "2026-27")


def test_a_gathered_fact_brings_a_state_into_coverage():
    """A state now arrives by being SOURCED rather than by being typed into
    this repository, which is what stops the four-state table being a ceiling
    on the product."""
    result = compute_landed_cost(
        _tripura(), "2026-27",
        facts={"road_tax.TR": _fact("road_tax.TR", "0.07")},
    )
    line = next(x for x in result.lines if x.label == "Road tax")
    assert line.amount == rupees(56000)          # 7% of ₹8,00,000
    assert line.fact.source_url.endswith("/rates")


def test_a_gathered_fact_wins_over_the_pack():
    """It is dated, it carries its URL, and it was re-read more recently than
    the file. The pack entry is a hand-taken snapshot of the same thing."""
    from_pack = compute_landed_cost(
        Purchase(item="Hatchback", ex_showroom=rupees(800000),
                 category="motor_vehicle", state="KA",
                 purchase_date=date(2026, 6, 1)),
        "2026-27",
    )
    from_fact = compute_landed_cost(
        Purchase(item="Hatchback", ex_showroom=rupees(800000),
                 category="motor_vehicle", state="KA",
                 purchase_date=date(2026, 6, 1)),
        "2026-27",
        facts={"road_tax.KA": _fact("road_tax.KA", "0.09")},
    )
    pack_line = next(x for x in from_pack.lines if x.label == "Road tax")
    fact_line = next(x for x in from_fact.lines if x.label == "Road tax")
    assert fact_line.amount == rupees(72000)     # 9%, the gathered rate
    assert fact_line.amount != pack_line.amount


def test_the_ev_specific_key_is_preferred_for_an_ev():
    result = compute_landed_cost(
        _tripura(is_electric=True, category="electric_vehicle"), "2026-27",
        facts={
            "road_tax.TR": _fact("road_tax.TR", "0.07"),
            "road_tax.TR.ev": _fact("road_tax.TR.ev", "0.00"),
        },
    )
    line = next(x for x in result.lines if x.label == "Road tax")
    assert line.amount == ZERO


def test_a_gathered_state_is_named_in_the_worksheet():
    """The pack supplies the pretty name; a gathered-only state has none, and
    falling over on a missing display string would be a poor reason to lose
    the computation."""
    result = compute_landed_cost(
        _tripura(), "2026-27",
        facts={"road_tax.TR": _fact("road_tax.TR", "0.07")},
    )
    assert "Road tax — TR at 7%" in result.trace.render()
