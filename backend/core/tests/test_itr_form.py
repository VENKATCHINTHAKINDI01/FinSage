"""ITR form selection — PLN-004.

Three kinds of claim are tested here, in descending order of how badly a
mistake hurts:

  * an entity is never routed to a form it may not legally file — the class of
    error v1 shipped, where ITR-5 was described as a form for "high income
    individuals"
  * every disqualifier in the department's own exclusion list actually
    disqualifies
  * the answer explains itself, with the specific fact that triggered it
"""

from __future__ import annotations

import pytest

from backend.core.provenance.money import rupees
from backend.core.rules import RuleError, load_ruleset
from backend.core.tax_engine.itr_form import (
    EntityType as E,
)
from backend.core.tax_engine.itr_form import (
    FilerProfile,
    Residency,
    select_itr_form,
)

FY = "2026-27"


def _pick(**kw) -> str:
    return select_itr_form(FilerProfile(**kw), FY).form


def _salaried(**kw) -> dict:
    base = {"has_salary": True, "house_properties": 1,
            "total_income": rupees(1_800_000)}
    base.update(kw)
    return base


# ══ entity routing — the class of error v1 shipped ══════════════════════════

class TestNoEntityGetsAFormItCannotFile:
    """v1's table said ITR-5 was for "high income individuals > 50 lakh".
    No individual may ever file ITR-5, ITR-6 or ITR-7, and no company may file
    ITR-1 through ITR-4."""

    @pytest.mark.parametrize("entity,expected", [
        (E.FIRM, "ITR-5"), (E.LLP, "ITR-5"), (E.AOP, "ITR-5"),
        (E.BOI, "ITR-5"), (E.AJP, "ITR-5"),
        (E.COMPANY, "ITR-6"),
        (E.TRUST, "ITR-7"), (E.POLITICAL_PARTY, "ITR-7"),
        (E.RESEARCH_INSTITUTION, "ITR-7"),
    ])
    def test_non_individual_entities_route_by_what_they_are(
        self, entity, expected
    ) -> None:
        assert _pick(entity=entity, total_income=rupees(1_000_000)) == expected

    def test_a_company_claiming_section_11_exemption_files_itr_7(self) -> None:
        assert _pick(entity=E.COMPANY, claims_section_11_exemption=True) == "ITR-7"

    def test_no_individual_is_ever_sent_to_itr_5_6_or_7(self) -> None:
        """Swept across every profile shape an individual could have."""
        for kwargs in (
            {}, {"has_business_income": True}, {"total_income": rupees(50_000_000)},
            {"has_foreign_income": True}, {"house_properties": 9},
            {"is_company_director": True}, {"has_other_capital_gains": True},
        ):
            form = _pick(entity=E.INDIVIDUAL, **kwargs)
            assert form in {"ITR-1", "ITR-2", "ITR-3", "ITR-4"}, (
                f"an individual was routed to {form} with {kwargs}"
            )

    def test_a_huf_cannot_use_itr_1(self) -> None:
        """ITR-1 is for individuals only. A HUF with nothing but rental income
        passes every other test and is still ineligible — it files ITR-2."""
        assert _pick(entity=E.HUF, house_properties=1,
                     total_income=rupees(1_000_000)) == "ITR-2"

    def test_but_a_huf_may_use_itr_4_on_a_presumptive_basis(self) -> None:
        assert _pick(entity=E.HUF, has_business_income=True,
                     uses_presumptive_scheme=True,
                     total_income=rupees(1_000_000)) == "ITR-4"

    def test_a_firm_on_presumptive_uses_itr_4_not_itr_5(self) -> None:
        assert _pick(entity=E.FIRM, has_business_income=True,
                     uses_presumptive_scheme=True,
                     total_income=rupees(1_000_000)) == "ITR-4"

    def test_but_an_llp_on_presumptive_still_uses_itr_5(self) -> None:
        """The one exception that stops the entity check routing every
        firm-like entity the same way."""
        assert _pick(entity=E.LLP, has_business_income=True,
                     uses_presumptive_scheme=True,
                     total_income=rupees(1_000_000)) == "ITR-5"


# ══ ITR-1, and the two thresholds CBDT moved ════════════════════════════════

class TestItr1:
    def test_the_ordinary_salaried_case(self) -> None:
        assert _pick(**_salaried()) == "ITR-1"

    def test_two_house_properties_are_now_allowed(self) -> None:
        """Changed for AY 2026-27 (CBDT, 30 March 2026). Before that a second
        flat forced ITR-2, and a selector written from older guidance sends
        every two-property filer to the wrong form."""
        assert _pick(**_salaried(house_properties=2)) == "ITR-1"

    def test_three_house_properties_are_not(self) -> None:
        assert _pick(**_salaried(house_properties=3)) == "ITR-2"

    def test_equity_ltcg_within_the_exemption_is_now_allowed(self) -> None:
        """Also new: LTCG u/s 112A up to ₹1,25,000 may be reported in ITR-1.
        Older guidance says any capital gain disqualifies, which is no longer
        true and pushes people onto a harder form for nothing."""
        assert _pick(**_salaried(ltcg_112a=rupees(125_000))) == "ITR-1"

    def test_equity_ltcg_over_the_exemption_is_not(self) -> None:
        assert _pick(**_salaried(ltcg_112a=rupees(125_001))) == "ITR-2"

    def test_short_term_gains_disqualify_however_small(self) -> None:
        """The concession is for s.112A LTCG only. A single equity sale inside
        twelve months moves you to ITR-2."""
        assert _pick(**_salaried(has_short_term_capital_gains=True)) == "ITR-2"

    def test_fifty_lakh_is_the_ceiling(self) -> None:
        assert _pick(**_salaried(total_income=rupees(5_000_000))) == "ITR-1"
        assert _pick(**_salaried(total_income=rupees(5_000_001))) == "ITR-2"

    @pytest.mark.parametrize("flag", [
        "is_company_director",
        "holds_unlisted_equity_shares",
        "has_foreign_assets_or_signing_authority",
        "has_foreign_income",
        "tds_under_194n",
        "has_deferred_esop_tax",
        "has_carry_forward_loss",
        "has_lottery_or_racehorse_income",
        "has_special_rate_income",
        "has_retirement_benefit_account_relief",
        "has_section_5a_apportionment",
        "has_other_capital_gains",
    ])
    def test_every_status_disqualifier_actually_disqualifies(self, flag) -> None:
        """Straight from the department's own ITR-1 exclusion list. Any one of
        these alone is enough."""
        assert _pick(**_salaried(**{flag: True})) == "ITR-2"

    def test_agricultural_income_over_five_thousand_disqualifies(self) -> None:
        assert _pick(**_salaried(agricultural_income=rupees(5_000))) == "ITR-1"
        assert _pick(**_salaried(agricultural_income=rupees(5_001))) == "ITR-2"

    @pytest.mark.parametrize("residency", [
        Residency.NOT_ORDINARILY_RESIDENT, Residency.NON_RESIDENT,
    ])
    def test_only_the_ordinarily_resident_may_use_it(self, residency) -> None:
        assert _pick(**_salaried(residency=residency)) == "ITR-2"


# ══ ITR-3 and ITR-4 — the two forms v1 got most wrong ═══════════════════════

class TestBusinessIncome:
    def test_presumptive_income_within_the_limit_uses_itr_4(self) -> None:
        assert _pick(has_business_income=True, uses_presumptive_scheme=True,
                     total_income=rupees(4_000_000)) == "ITR-4"

    def test_the_itr_4_limit_is_total_income_not_turnover(self) -> None:
        """v1 said "turnover < 5 crore", a figure lifted from the audit
        provisions. The form is conditioned on ₹50 lakh of TOTAL INCOME, which
        is a different number about a different thing."""
        assert _pick(has_business_income=True, uses_presumptive_scheme=True,
                     total_income=rupees(5_000_000)) == "ITR-4"
        assert _pick(has_business_income=True, uses_presumptive_scheme=True,
                     total_income=rupees(5_000_001)) == "ITR-3"

    def test_business_income_without_presumptive_uses_itr_3(self) -> None:
        """ITR-3 was absent from v1's table entirely — the form most people
        with business income actually need."""
        assert _pick(has_business_income=True,
                     total_income=rupees(1_000_000)) == "ITR-3"

    @pytest.mark.parametrize("flag", [
        "is_company_director", "holds_unlisted_equity_shares",
        "has_foreign_income", "has_short_term_capital_gains",
    ])
    def test_the_same_disqualifiers_push_a_presumptive_filer_to_itr_3(
        self, flag
    ) -> None:
        assert _pick(has_business_income=True, uses_presumptive_scheme=True,
                     total_income=rupees(1_000_000), **{flag: True}) == "ITR-3"

    def test_capital_gains_alone_do_not_create_business_income(self) -> None:
        """Someone with gains but no business files ITR-2, not ITR-3."""
        assert _pick(**_salaried(has_other_capital_gains=True)) == "ITR-2"


# ══ the explanation ═════════════════════════════════════════════════════════

class TestExplanations:
    def test_every_exclusion_names_the_fact_that_triggered_it(self) -> None:
        r = select_itr_form(
            FilerProfile(**_salaried(house_properties=5)), FY
        )
        exclusion = next(e for e in r.excluded if "house properties" in e.reason)
        assert exclusion.fact == "5 properties"
        assert exclusion.form == "ITR-1"

    def test_all_the_reasons_are_reported_not_just_the_first(self) -> None:
        """A user who fixes one answer should not come back and discover a
        second problem they could have been told about at the same time."""
        r = select_itr_form(
            FilerProfile(**_salaried(
                is_company_director=True, has_foreign_income=True,
                holds_unlisted_equity_shares=True,
            )),
            FY,
        )
        reasons = " ".join(e.reason for e in r.excluded)
        assert "director" in reasons
        assert "outside India" in reasons
        assert "unlisted equity shares" in reasons

    def test_a_clean_itr_1_case_has_nothing_to_explain(self) -> None:
        r = select_itr_form(FilerProfile(**_salaried()), FY)
        assert r.excluded == []
        assert "ruled out" not in r.summary()

    def test_the_income_limit_exclusion_quotes_the_actual_income(self) -> None:
        r = select_itr_form(
            FilerProfile(**_salaried(total_income=rupees(6_000_000))), FY
        )
        assert any("₹60,00,000" in e.fact for e in r.excluded)


# ══ vintage — the honesty that keeps this from going quietly stale ══════════

class TestScopingVintage:
    def test_the_answer_declares_which_year_the_scoping_came_from(self) -> None:
        """The AY 2027-28 forms are not notified until around March 2027. A
        selector that presents last year's rules as this year's is wrong the
        moment CBDT moves a threshold — which it did twice for ITR-1 in two
        years."""
        r = select_itr_form(FilerProfile(**_salaried()), FY)
        assert r.notified_for_ay == "2026-27"
        assert r.applies_to_ay == "2027-28"
        assert r.scoping_is_provisional
        assert any("most recent notified" in n for n in r.notes)

    def test_a_year_with_no_form_scoping_refuses_rather_than_guesses(self) -> None:
        """An empty scoping would find no disqualifiers and recommend ITR-1 to
        everybody — confidently wrong and entirely plausible-looking."""
        with pytest.raises(RuleError, match="no `itr_forms` block"):
            select_itr_form(FilerProfile(**_salaried()), "2024-25")

    def test_the_rule_pack_is_what_moves_the_thresholds(self) -> None:
        """Not the code. Adding AY 2027-28 should be a YAML edit."""
        cfg = load_ruleset(FY).itr_forms
        assert cfg["ITR-1"]["max_house_properties"] == 2
        assert cfg["ITR-1"]["allows_ltcg_112a_upto"] == 125000
        assert cfg["ITR-1"]["total_income_limit"] == 5000000


# ══ Form 10-IEA ═════════════════════════════════════════════════════════════

class TestForm10IEA:
    def test_a_business_filer_leaving_the_new_regime_needs_it(self) -> None:
        r = select_itr_form(
            FilerProfile(has_business_income=True, total_income=rupees(1_000_000)),
            FY,
        )
        assert r.form == "ITR-3"
        assert r.needs_form_10iea
        assert any("BEFORE filing" in n for n in r.notes)

    def test_a_salaried_itr_1_filer_does_not(self) -> None:
        """ITR-1 and ITR-2 filers just tick a box. Telling them to file 10-IEA
        would send them chasing a form they do not need."""
        r = select_itr_form(FilerProfile(**_salaried()), FY)
        assert not r.needs_form_10iea

    def test_nor_does_an_itr_2_filer_with_capital_gains(self) -> None:
        r = select_itr_form(
            FilerProfile(**_salaried(has_other_capital_gains=True)), FY
        )
        assert r.form == "ITR-2"
        assert not r.needs_form_10iea


def test_a_carry_forward_loss_carries_the_deadline_warning() -> None:
    """Filing late forfeits the loss entirely — the most expensive consequence
    of missing 31 July there is."""
    r = select_itr_form(
        FilerProfile(**_salaried(has_carry_forward_loss=True)), FY
    )
    assert any("forfeits it entirely" in n for n in r.notes)


def test_serialises() -> None:
    d = select_itr_form(FilerProfile(**_salaried(house_properties=4)), FY).to_dict()
    assert d["form"] == "ITR-2"
    assert d["scoping_is_provisional"] is True
    assert d["excluded"][0]["fact"] == "4 properties"


def test_a_reason_that_blocks_two_forms_is_stated_once() -> None:
    """`excluded` is per-form and correct, but rendering it flat repeats
    "you were a director in a company" for ITR-1 and again for ITR-4, which
    reads like a bug. `blocking_reasons` says each thing once and names the
    forms it rules out."""
    r = select_itr_form(
        FilerProfile(**_salaried(house_properties=3, is_company_director=True)), FY
    )
    director = next(
        b for b in r.blocking_reasons() if "director" in b["reason"]
    )
    assert director["rules_out"] == ["ITR-1", "ITR-4"]
    assert sum("director" in b["reason"] for b in r.blocking_reasons()) == 1
    assert len([e for e in r.excluded if "director" in e.reason]) == 2


def test_the_summary_counts_reasons_not_form_rejections() -> None:
    r = select_itr_form(
        FilerProfile(**_salaried(house_properties=3, is_company_director=True)), FY
    )
    assert "3 thing(s)" in r.summary()


# ══ golden corpus ═══════════════════════════════════════════════════════════

def _golden() -> list[dict]:
    import pathlib

    import yaml

    path = pathlib.Path(__file__).parent / "golden" / "itr_form" / "fy_2026_27.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


GOLDEN = _golden()

_MONEY_FIELDS = {"total_income", "ltcg_112a", "agricultural_income"}


@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_golden_itr_form(case: dict) -> None:
    kwargs = {}
    for key, value in case["profile"].items():
        if key == "entity":
            kwargs[key] = E(value)
        elif key == "residency":
            kwargs[key] = Residency(value)
        elif key in _MONEY_FIELDS:
            kwargs[key] = rupees(value)
        else:
            kwargs[key] = value

    r = select_itr_form(FilerProfile(**kwargs), FY)
    actual = {
        "form": r.form,
        "needs_form_10iea": r.needs_form_10iea,
        "blocking_reasons": len(r.blocking_reasons()),
    }
    mismatches = [
        f"    {k}: expected {v}, got {actual[k]}"
        for k, v in case["expect"].items()
        if actual[k] != v
    ]
    if mismatches:
        pytest.fail(
            f"\n{case['id']}\n" + "\n".join(mismatches)
            + f"\n  verified against: {case['verified_against'].strip()}"
            + "\n  ruled out: "
            + "; ".join(b["reason"] for b in r.blocking_reasons())
        )


def test_every_golden_case_shows_its_working() -> None:
    for case in GOLDEN:
        assert case.get("verified_against", "").strip(), f"{case['id']} has none"


def test_the_corpus_pins_all_three_v1_errors() -> None:
    """A corpus that only covered the happy path would pass with v1's table
    restored."""
    marked = " ".join(
        c["verified_against"] for c in GOLDEN if "v1" in c["verified_against"]
    )
    assert "high income individuals" in marked      # ITR-5 misdescribed
    assert "OMITTED ITR-3 ENTIRELY" in marked       # ITR-3 missing
    assert "turnover < 5 crore" in marked           # ITR-4 wrong condition


def test_the_corpus_covers_every_form() -> None:
    forms = {c["expect"]["form"] for c in GOLDEN}
    assert forms == {"ITR-1", "ITR-2", "ITR-3", "ITR-4", "ITR-5", "ITR-6", "ITR-7"}
