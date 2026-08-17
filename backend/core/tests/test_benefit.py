"""What a scheme is worth to this buyer — PRC-004.

CORE-009 is tested elsewhere for *whether* a benefit is available. This is
about *how much*, which is where a scalar `max_benefit` was quietly wrong.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import yaml

from backend.core.eligibility import Facts, Status, evaluate_all, total_claimable
from backend.core.eligibility.benefit import (
    BenefitError,
    BenefitKind,
    compute_benefit,
)
from backend.core.eligibility.evaluator import RULES_FILE, evaluate_rule
from backend.core.provenance.money import Money

PACK = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
RULES = {r["id"]: r for r in PACK["rules"]}


def facts(**kw) -> Facts:
    as_of = kw.pop("as_of", date(2026, 8, 13))
    regime = kw.pop("regime", "new")
    return Facts(values=kw, as_of=as_of, regime=regime)


# ── the bug this feature exists to fix ──────────────────────────────────────

def test_a_small_battery_gets_the_computed_incentive_not_the_cap():
    """The live bug PRC-004 found.

    `benefit_per_kwh: 2500` sat in the rule pack beside `max_benefit: 5000`
    and the evaluator read only the second, so every scooter was quoted
    ₹5,000. A 1.5 kWh model is worth ₹3,750 and quoting ₹5,000 is the same
    class of error as quoting a closed window.
    """
    out = evaluate_rule(RULES["PM_E_DRIVE_2W"], facts(
        asset_type="electric_vehicle", vehicle_category="two_wheeler",
        battery_kwh="1.5", purchase_date="2026-06-01",
    ))
    assert out.status is Status.ELIGIBLE
    assert out.max_benefit == Money("3750")
    assert "3,750" in out.message


def test_a_large_battery_is_capped_and_the_cap_is_a_traced_step():
    """A benefit that silently returns the cap is indistinguishable from one
    that computed correctly and happened to land there."""
    out = evaluate_rule(RULES["PM_E_DRIVE_2W"], facts(
        asset_type="electric_vehicle", vehicle_category="two_wheeler",
        battery_kwh="4", purchase_date="2026-06-01",
    ))
    assert out.max_benefit == Money("5000")
    assert out.benefit.capped
    assert "10,000" in out.benefit.trace.render()   # the uncapped ₹2,500 × 4
    assert "Capped at" in out.benefit.trace.render()


def test_the_worksheet_replays():
    out = evaluate_rule(RULES["PM_E_DRIVE_2W"], facts(
        asset_type="electric_vehicle", vehicle_category="two_wheeler",
        battery_kwh="2.2", purchase_date="2026-06-01",
    ))
    assert out.benefit.trace.verify() == []
    assert out.benefit.trace.replay() == Money("5000")


# ── the four computable kinds ───────────────────────────────────────────────

def test_flat():
    got = compute_benefit(
        {"id": "X", "name": "X", "benefit": {"kind": "flat", "amount": 150000}},
        facts(),
    )
    assert got.amount == Money("150000")
    assert got.stated


def test_percentage_of_a_named_field():
    got = compute_benefit(
        {"id": "X", "name": "X",
         "benefit": {"kind": "percentage", "rate": "0.30", "of": "benchmark_cost"}},
        facts(benchmark_cost="270000"),
    )
    assert got.amount == Money("81000")


def test_percentage_respects_its_cap():
    got = compute_benefit(
        {"id": "X", "name": "X",
         "benefit": {"kind": "percentage", "rate": "0.30",
                     "of": "benchmark_cost", "cap": 50000}},
        facts(benchmark_cost="270000"),
    )
    assert got.amount == Money("50000")
    assert got.capped


def test_slab_picks_the_first_band_it_fits():
    """A genuine slab: the whole value takes one band's amount.

    Deliberately NOT modelled on PM-Surya Ghar, which looks like a slab in
    every secondary summary and is not one — see the tiered tests below.
    """
    rule = {"id": "X", "name": "X", "benefit": {
        "kind": "slab", "on": "seats", "bands": [
            {"upto": 4, "amount": 10000, "label": "up to 4 seats"},
            {"upto": 7, "amount": 25000, "label": "up to 7 seats"},
            {"upto": None, "amount": 40000, "label": "8 or more"},
        ]}}
    assert compute_benefit(rule, facts(seats="4")).amount == Money("10000")
    assert compute_benefit(rule, facts(seats="5")).amount == Money("25000")
    assert compute_benefit(rule, facts(seats="9")).amount == Money("40000")


def test_a_missing_input_is_named_rather_than_defaulted():
    got = compute_benefit(RULES["PM_E_DRIVE_2W"], facts())
    assert got.missing_fields == ("battery_kwh",)
    assert not got.computable
    assert "battery_kwh" in got.phrase()


def test_a_rule_with_no_benefit_block_still_uses_the_legacy_scalar():
    """Every CORE-009 rule keeps working unchanged. A flat deduction ceiling
    genuinely is a scalar and rewriting it as a block adds ceremony, not
    truth."""
    got = compute_benefit(RULES["80EEB"], facts())
    assert got.amount == Money("150000")
    assert got.stated


# ── tiered: the kind that reading the primary source forced ─────────────────

def solar(capacity: str, **kw):
    base = {
        "asset_type": "rooftop_solar",
        "connection_type": "residential",
        "installation_mode": "capex",
        "domestic_content_modules": True,
        "capacity_kw": capacity,
        "purchase_date": "2026-06-01",
    }
    base.update(kw)
    return facts(**base)


@pytest.mark.parametrize(
    ("capacity", "expected"),
    [
        # The ministry's own three illustrations, verbatim from §5(h) of the
        # PM-Surya Ghar CFA operational guidelines.
        ("1.5", "45000"),   # 30,000 × 1.5
        ("2.5", "69000"),   # 30,000 × 2 + 18,000 × 0.5
        ("6",   "78000"),   # 30,000 × 2 + 18,000 × 1, nothing beyond 3 kWp
    ],
)
def test_pm_surya_ghar_matches_the_ministrys_own_worked_examples(capacity, expected):
    out = evaluate_rule(RULES["PM_SURYA_GHAR_CFA"], solar(capacity))
    assert out.status is Status.ELIGIBLE
    assert out.max_benefit == Money(expected)


def test_the_slab_reading_of_pm_surya_ghar_would_overstate_a_small_system():
    """Why `tiered` exists at all.

    Every secondary source renders this scheme as "₹30,000 for 1 kW, ₹60,000
    for 2 kW, ₹78,000 for 3 kW and above". Read as a slab, a 1.5 kW system
    comes out at ₹60,000. The guidelines put it at ₹45,000. Since most
    residential installations are not whole numbers of kW, the slab model is
    wrong for the majority of people it would be shown to — and wrong in the
    direction of promising money that will not arrive.
    """
    computed = compute_benefit(RULES["PM_SURYA_GHAR_CFA"], solar("1.5")).amount
    slab_reading = Money("60000")
    assert computed == Money("45000")
    assert slab_reading - computed == Money("15000")


def test_the_tiered_worksheet_shows_each_tier_and_replays():
    got = compute_benefit(RULES["PM_SURYA_GHAR_CFA"], solar("2.5"))
    rendered = got.trace.render()
    assert "first 2 kWp" in rendered
    assert "additional 1 kWp" in rendered
    assert got.trace.verify() == []
    assert got.trace.replay() == Money("69000")


def test_a_large_system_is_told_why_it_gets_nothing_more():
    """A 6 kW buyer seeing ₹78,000 with no explanation assumes a cap they can
    argue with. The zero-rate tier is a line in the worksheet, not a silent
    truncation."""
    got = compute_benefit(RULES["PM_SURYA_GHAR_CFA"], solar("6"))
    assert "no additional CFA" in got.trace.render()


def test_special_category_states_use_the_higher_tier_rates():
    out = evaluate_rule(RULES["PM_SURYA_GHAR_CFA_SPECIAL_STATES"],
                        solar("2.5", state="HP"))
    assert out.max_benefit == Money("75900")     # 33,000×2 + 19,800×0.5


def test_pm_surya_ghar_runs_to_2027_not_2026():
    """The correction that went the other way.

    The MNRE programme page carries "Period of existing Phase-II scheme: Till
    31.03.2026" and an earlier pass applied it here. §4(a) of the guidelines:
    Phase-II "stands subsumed within" PM-Surya Ghar; §2(d): the implementation
    period runs "till 31st March, 2027". Closing a live scheme tells a user
    they missed money they can still claim.
    """
    assert evaluate_rule(RULES["PM_SURYA_GHAR_CFA"],
                         solar("3")).status is Status.ELIGIBLE
    closed = evaluate_rule(RULES["PM_SURYA_GHAR_CFA"],
                           solar("3", purchase_date="2027-06-01"))
    assert closed.status is Status.WINDOW_CLOSED
    assert closed.closed_on == date(2027, 3, 31)


def test_a_government_employee_installing_at_home_still_qualifies():
    """The exclusion in the guidelines is of the government SEGMENT — the
    electricity connection the plant is tagged to — not of people employed by
    the government. An earlier pass conflated the two and would have denied
    the subsidy to every government employee putting solar on their own
    house."""
    out = evaluate_rule(RULES["PM_SURYA_GHAR_CFA"],
                        solar("3", buyer_profile="government_employee"))
    assert out.status is Status.ELIGIBLE
    assert out.max_benefit == Money("78000")


def test_a_commercial_connection_gets_nothing():
    out = evaluate_rule(RULES["PM_SURYA_GHAR_CFA"],
                        solar("3", connection_type="commercial"))
    assert out.status is Status.INELIGIBLE


def test_non_dcr_modules_disqualify_the_whole_installation():
    out = evaluate_rule(RULES["PM_SURYA_GHAR_CFA"],
                        solar("3", domestic_content_modules=False))
    assert out.status is Status.INELIGIBLE


def test_a_resco_installation_is_out_of_scope_of_these_guidelines():
    out = evaluate_rule(RULES["PM_SURYA_GHAR_CFA"],
                        solar("3", installation_mode="resco"))
    assert out.status is Status.INELIGIBLE


def test_a_tiered_benefit_with_no_tiers_raises():
    with pytest.raises(BenefitError, match="needs tiers"):
        compute_benefit({"id": "X", "name": "X",
                         "benefit": {"kind": "tiered", "measure": "capacity_kw"}},
                        facts(capacity_kw="2"))


# ── the fifth kind, which is the point ──────────────────────────────────────

UNVERIFIED_RULE = {
    "id": "SOME_STATE_SCHEME",
    "name": "A state scheme whose amount we have not read",
    "benefit": {
        "kind": "unverified",
        "note": "The amount is published in a state notification this system "
                "has not read. See the state nodal agency.",
    },
}


def test_an_unverified_amount_is_reported_as_unverified_not_as_zero():
    """Rendering an unconfirmed amount as ₹0 reads as 'this scheme is worth
    nothing to you' — a false statement wearing the clothes of a computed
    one."""
    out = evaluate_rule(UNVERIFIED_RULE, facts())
    assert out.status is Status.ELIGIBLE
    assert not out.amount_is_stated
    assert "not verified" in out.message or "has not verified" in out.message
    assert "₹0" not in out.message


def test_an_unverified_benefit_must_say_what_was_not_verified():
    """An unexplained 'unverified' is indistinguishable from an oversight."""
    with pytest.raises(BenefitError, match="must say what has not been"):
        compute_benefit(
            {"id": "X", "name": "X", "benefit": {"kind": "unverified"}},
            facts(),
        )


def test_a_closed_window_with_an_unverified_amount_reads_sensibly():
    rule = dict(UNVERIFIED_RULE)
    rule["windows"] = [{"field": "purchase_date", "to": "2026-03-31"}]
    out = evaluate_rule(rule, facts(purchase_date="2026-06-01"))
    assert out.status is Status.WINDOW_CLOSED
    assert "31 March 2026" in out.message
    assert "would have given you" not in out.message


# ── the finding that mattered ───────────────────────────────────────────────

def test_the_two_solar_schemes_do_not_share_a_closing_date():
    """The correction that only reading both primary sources produces.

    MNRE publishes PM-KUSUM as running "Till 31.03.2026" and PM-Surya Ghar's
    guidelines as running "till 31st March, 2027". A first pass here applied
    the earlier date to both, because the rooftop programme page leads with
    the superseded Phase-II period — which §4(a) of the guidelines says
    "stands subsumed within" PM-Surya Ghar.
    """
    kusum = evaluate_rule(RULES["PM_KUSUM_B"], facts(
        asset_type="solar_pump", buyer_profile="farmer", grid_connected=False,
        benchmark_cost="270000", purchase_date="2026-08-01",
    ))
    assert kusum.status is Status.WINDOW_CLOSED
    assert kusum.closed_on == date(2026, 3, 31)

    surya = evaluate_rule(RULES["PM_SURYA_GHAR_CFA"], solar("3"))
    assert surya.status is Status.ELIGIBLE


def test_kusum_central_share_is_thirty_percent_and_the_state_share_is_not_claimed():
    """MNRE: CFA of 30% of the benchmark or tender cost, whichever is lower;
    the state adds at least 30%. Only the central share is modelled, because
    the state share varies by state and year and was not verified."""
    out = evaluate_rule(RULES["PM_KUSUM_B"], facts(
        asset_type="solar_pump", buyer_profile="farmer", grid_connected=False,
        benchmark_cost="270000", purchase_date="2025-06-01",
    ))
    assert out.status is Status.ELIGIBLE
    assert out.max_benefit == Money("81000")


def test_special_category_states_get_fifty_percent():
    common = {"asset_type": "solar_pump", "buyer_profile": "farmer",
              "grid_connected": False, "benchmark_cost": "270000",
              "purchase_date": "2025-06-01"}
    hp = evaluate_rule(RULES["PM_KUSUM_B_SPECIAL_STATES"],
                       facts(state="HP", **common))
    ka = evaluate_rule(RULES["PM_KUSUM_B_SPECIAL_STATES"],
                       facts(state="KA", **common))
    assert hp.status is Status.ELIGIBLE
    assert hp.max_benefit == Money("135000")
    assert ka.status is Status.INELIGIBLE


# ── entitlement and quantum are different questions ─────────────────────────

def test_a_missing_amount_field_does_not_make_the_user_ineligible():
    """"You qualify, and how much depends on your battery capacity" is true and
    useful. Collapsing it into INSUFFICIENT_DATA says "we cannot tell whether
    you qualify", which is false."""
    out = evaluate_rule(RULES["PM_E_DRIVE_2W"], facts(
        asset_type="electric_vehicle", vehicle_category="two_wheeler",
        purchase_date="2026-06-01",
    ))
    assert out.status is Status.ELIGIBLE
    assert not out.amount_is_known
    assert out.amount_missing_fields == ("battery_kwh",)
    assert out.missing_fields == ()          # entitlement asks nothing
    assert "battery_kwh" in out.message      # but the question still gets asked


def test_totalling_returns_what_it_could_not_include():
    """A function returning only the total would let a caller print a confident
    figure that quietly omits every unquantified benefit. Same argument as
    facts_for_costing in PRC-010."""
    out = evaluate_all(facts(
        asset_type="electric_vehicle", vehicle_category="two_wheeler",
        purchase_date="2026-06-01",
    ))
    total, unquantified = total_claimable(out)
    assert "PM_E_DRIVE_2W" in {o.rule_id for o in unquantified}
    assert total == Money(0)

    supplied = evaluate_all(facts(
        asset_type="electric_vehicle", vehicle_category="two_wheeler",
        battery_kwh="1.5", purchase_date="2026-06-01",
    ))
    total, unquantified = total_claimable(supplied)
    assert total == Money("3750")
    assert unquantified == []


def test_an_unverified_amount_is_excluded_from_the_total_and_named():
    out = [evaluate_rule(UNVERIFIED_RULE, facts())]
    total, unquantified = total_claimable(out)
    assert "SOME_STATE_SCHEME" in {o.rule_id for o in unquantified}
    assert total == Money(0)


# ── the buyer dimension ─────────────────────────────────────────────────────

def test_the_same_asset_answers_differently_for_a_different_buyer():
    """The premise of the whole buyer-profile dimension. Without it, a
    government employee and a farmer get the same answer about the same solar
    installation and it is wrong for at least one of them."""
    farmer = evaluate_all(facts(
        asset_type="solar_pump", buyer_profile="farmer", grid_connected=False,
        benchmark_cost="270000", purchase_date="2025-06-01",
    ))
    employee = evaluate_all(facts(
        asset_type="solar_pump", buyer_profile="government_employee",
        grid_connected=False, benchmark_cost="270000",
        purchase_date="2025-06-01",
    ))
    claimable = {o.rule_id for o in farmer if o.status is Status.ELIGIBLE}
    assert "PM_KUSUM_B" in claimable
    assert "PM_KUSUM_B" not in {
        o.rule_id for o in employee if o.status is Status.ELIGIBLE
    }


def test_every_buyer_profile_named_in_a_rule_is_in_the_vocabulary():
    """A ratchet against a silently dead rule.

    A condition on `buyer_profile: farmr` never matches and never errors, so
    the rule is simply invisible to every user forever, with nothing to
    notice.
    """
    known = set(PACK["meta"]["buyer_profiles"])
    used: set[str] = set()
    for rule in PACK["rules"]:
        for cond in rule.get("conditions", []):
            if cond.get("field") != "buyer_profile":
                continue
            if "equals" in cond:
                used.add(cond["equals"])
            used.update(cond.get("in", []))
    assert used, "no rule uses buyer_profile — the dimension is not wired up"
    assert used <= known, f"not in meta.buyer_profiles: {sorted(used - known)}"


# ── malformed packs fail loudly ─────────────────────────────────────────────

def test_an_unknown_benefit_kind_raises_rather_than_returning_zero():
    """A pack that does not parse is a bug in the pack, not a fact about the
    user, and degrading to zero would hide it."""
    with pytest.raises(BenefitError, match="unknown benefit kind"):
        compute_benefit({"id": "X", "name": "X",
                         "benefit": {"kind": "vibes"}}, facts())


def test_a_slab_with_no_bands_raises():
    with pytest.raises(BenefitError, match="needs bands"):
        compute_benefit({"id": "X", "name": "X",
                         "benefit": {"kind": "slab", "on": "capacity_kw"}},
                        facts(capacity_kw="2"))


def test_every_rule_in_the_pack_computes_without_raising():
    """The pack is data, so a typo in it is not caught by any type checker."""
    for rule in PACK["rules"]:
        compute_benefit(rule, facts())


def test_the_benefit_kinds_are_a_closed_set():
    assert {k.value for k in BenefitKind} == {
        "flat", "per_unit", "percentage", "slab", "tiered", "unverified",
    }


def test_rates_stay_exact():
    """A float rate would make 30% of ₹2,70,000 come out at ₹80,999.99…"""
    got = compute_benefit(
        {"id": "X", "name": "X",
         "benefit": {"kind": "percentage", "rate": "0.30", "of": "cost"}},
        facts(cost="270000"),
    )
    assert got.amount.amount == Decimal("81000.00")
