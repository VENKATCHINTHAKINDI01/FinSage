"""Rule packs, loader and section aliases — CORE-001, CORE-002.

The loader is where v1's defining failure gets prevented: no default financial
year, no fallback to the nearest pack, and an immutable result so one request
cannot mutate another's rates.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.rules import (
    RuleError,
    available_years,
    cite,
    fy_for_date,
    load_aliases,
    load_ruleset,
    ruleset_for_date,
    unverified_aliases,
)


class TestNoDefaultsNoFallbacks:
    """An implicit year is how v1 kept computing FY 2023-24 tax two years on."""

    @pytest.mark.parametrize("bad", ["2026", "current", "FY2026-27", "", "26-27"])
    def test_malformed_year_raises(self, bad: str) -> None:
        with pytest.raises(RuleError, match="must look like"):
            load_ruleset(bad)

    def test_non_string_year_raises(self) -> None:
        with pytest.raises(RuleError, match="must look like"):
            load_ruleset(2026)  # type: ignore[arg-type]

    def test_unknown_year_raises_rather_than_falling_back(self) -> None:
        with pytest.raises(RuleError, match="no rule pack"):
            load_ruleset("2030-31")

    def test_error_lists_what_is_available(self) -> None:
        with pytest.raises(RuleError, match="2026-27"):
            load_ruleset("2030-31")


class TestRulesetLoading:
    def test_available_years(self) -> None:
        assert available_years() == ("2024-25", "2025-26", "2026-27")

    def test_metadata(self) -> None:
        rs = load_ruleset("2026-27")
        assert rs.assessment_year == "2027-28"
        assert rs.governing_act == "Income-tax Act, 2025"
        assert rs.verified_on == date(2026, 8, 9)
        assert rs.effective_from == date(2026, 4, 1)
        assert rs.effective_to == date(2027, 3, 31)
        assert rs.sources

    def test_pre_2026_years_cite_the_1961_act(self) -> None:
        assert load_ruleset("2025-26").governing_act == "Income-tax Act, 1961"

    def test_split_year_flag(self) -> None:
        assert load_ruleset("2024-25").is_split_year
        assert not load_ruleset("2026-27").is_split_year

    def test_covers_and_age(self) -> None:
        rs = load_ruleset("2026-27")
        assert rs.covers(date(2026, 8, 9))
        assert not rs.covers(date(2026, 3, 31))
        assert rs.age_days(date(2026, 8, 19)) == 10

    def test_repr(self) -> None:
        assert "2026-27" in repr(load_ruleset("2026-27"))

    def test_is_cached(self) -> None:
        assert load_ruleset("2026-27") is load_ruleset("2026-27")


class TestImmutability:
    """A shared mutable ruleset is a race: one request normalising a rate in
    place would change every other request's tax."""

    def test_top_level(self) -> None:
        with pytest.raises(TypeError):
            load_ruleset("2026-27").data["cess"] = {}

    def test_nested(self) -> None:
        with pytest.raises(TypeError):
            load_ruleset("2026-27").data["cess"]["rate"] = "0.99"

    def test_lists_become_tuples(self) -> None:
        assert isinstance(load_ruleset("2026-27").regime("new")["slabs"], tuple)


class TestSlabResolution:
    def test_new_regime_ignores_age(self) -> None:
        rs = load_ruleset("2026-27")
        assert rs.slabs("new", 35) == rs.slabs("new", 62) == rs.slabs("new", 85)

    @pytest.mark.parametrize("age,first_band", [(45, 250000), (65, 300000), (85, 500000)])
    def test_old_regime_age_bands(self, age: int, first_band: int) -> None:
        assert load_ruleset("2026-27").slabs("old", age)[0]["upto"] == first_band

    def test_unknown_regime_raises(self) -> None:
        with pytest.raises(RuleError, match="no regime"):
            load_ruleset("2026-27").regime("hybrid")


class TestDeductions:
    def test_lookup_normalises_the_code(self) -> None:
        rs = load_ruleset("2026-27")
        assert rs.deduction("80ccd(1b)") == rs.deduction("80CCD_1B")

    def test_unknown_deduction_raises(self) -> None:
        with pytest.raises(RuleError, match="no deduction"):
            load_ruleset("2026-27").deduction("80ZZZ")

    def test_has_deduction(self) -> None:
        rs = load_ruleset("2026-27")
        assert rs.has_deduction("80C") and not rs.has_deduction("80ZZZ")

    def test_regime_gate(self) -> None:
        rs = load_ruleset("2026-27")
        assert rs.deduction_allowed_in("80C", "old")
        assert not rs.deduction_allowed_in("80C", "new")
        assert rs.deduction_allowed_in("80CCD_2", "new")


class TestSectionAccessors:
    def test_cess_surcharge_and_the_rest(self) -> None:
        rs = load_ruleset("2026-27")
        assert str(rs.cess_rate) == "0.04"
        assert rs.surcharge["marginal_relief"] is True
        assert rs.capital_gains["equity_ltcg"]["rate"] == "0.125"
        assert rs.presumptive["44AD"]["turnover_limit"] == 20000000
        assert rs.advance_tax["threshold"] == 10000
        assert rs.deadlines["updated_return_itr_u_months"] == 48

    def test_cii(self) -> None:
        rs = load_ruleset("2026-27")
        assert rs.cii("2026-27") == 384
        assert rs.cii("2001-02") == 100

    def test_missing_cii_raises(self) -> None:
        with pytest.raises(RuleError, match="Cost Inflation Index"):
            load_ruleset("2026-27").cii("1995-96")


class TestDateHelpers:
    @pytest.mark.parametrize(
        "when,fy",
        [
            (date(2026, 4, 1), "2026-27"),
            (date(2026, 8, 9), "2026-27"),
            (date(2027, 3, 31), "2026-27"),
            (date(2026, 3, 31), "2025-26"),
            (date(2026, 1, 15), "2025-26"),
        ],
    )
    def test_fy_for_date(self, when: date, fy: str) -> None:
        assert fy_for_date(when) == fy

    def test_ruleset_for_date(self) -> None:
        assert ruleset_for_date(date(2026, 8, 9)).fy == "2026-27"

    def test_uncovered_date_raises(self) -> None:
        with pytest.raises(RuleError, match="no rule pack covers"):
            ruleset_for_date(date(2019, 1, 1))


class TestSectionAliases:
    def test_map_loads(self) -> None:
        amap = load_aliases()
        assert amap.applies_from_fy == "2026-27"
        assert amap.by_legacy["87A"].current == "156"

    def test_resolve_from_either_direction(self) -> None:
        amap = load_aliases()
        assert amap.resolve("87A") is amap.resolve("156")
        assert amap.resolve("nonexistent") is None

    def test_applies_only_from_2026_27(self) -> None:
        amap = load_aliases()
        assert amap.applies_to("2026-27") and not amap.applies_to("2025-26")

    def test_unverified_mapping_is_flagged_not_asserted(self) -> None:
        """Printing a section number nobody checked is exactly the failure this
        project exists to avoid, so an unverified alias goes in the note rather
        than the citation."""
        c = cite("87A", "2026-27")
        assert c.section is None
        assert "provisionally s.156" in c.note
        assert "not yet verified" in c.note

    def test_pre_transition_years_use_1961_numbering(self) -> None:
        c = cite("87A", "2025-26")
        assert c.act == "Income-tax Act, 1961"
        assert c.section is None

    def test_unmapped_section_still_cites(self) -> None:
        c = cite("80ZZZ", "2026-27")
        assert c.legacy_section == "80ZZZ"

    def test_unverified_list_gates_core_002(self) -> None:
        """CORE-002 cannot move to `verified` while this is non-empty."""
        assert "87A" in unverified_aliases()
