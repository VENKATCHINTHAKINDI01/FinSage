"""Money, Citation, Trace and Confidence — CORE-010, EVD-001, EVD-002."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.core.provenance import (
    ZERO,
    Citation,
    Confidence,
    Level,
    Money,
    Op,
    Provenance,
    SourceRef,
    Step,
    Trace,
    format_rate,
    maximum,
    minimum,
    pct_of,
    rate,
    rupees,
)

# ═══ Money ═══════════════════════════════════════════════════════════════════

class TestMoneyRefusesFloat:
    """v1 computed tax in floats. The drift is invisible per operation and
    unbounded across a return."""

    def test_constructor(self) -> None:
        with pytest.raises(TypeError, match="refuses float"):
            Money(1.5)

    def test_multiplication(self) -> None:
        with pytest.raises(TypeError, match="express rates as"):
            rupees(100) * 0.05

    def test_division(self) -> None:
        with pytest.raises(TypeError, match="cannot divide"):
            rupees(100) / 2.0

    def test_addition(self) -> None:
        with pytest.raises(TypeError, match="cannot combine"):
            rupees(100) + 1.5

    def test_conversion_out(self) -> None:
        with pytest.raises(TypeError, match="refusing to convert"):
            float(rupees(100))

    def test_unsupported_type(self) -> None:
        with pytest.raises(TypeError, match="cannot build Money"):
            Money([1, 2])  # type: ignore[arg-type]


class TestMoneyArithmetic:
    def test_construction_forms(self) -> None:
        assert Money(100) == Money("100") == Money(Decimal(100)) == Money(Money(100))

    def test_exact_decimal(self) -> None:
        assert rupees("0.1") + rupees("0.2") == rupees("0.3")

    def test_operators(self) -> None:
        a, b = rupees(100), rupees(30)
        assert a + b == rupees(130)
        assert a - b == rupees(70)
        assert a * 3 == rupees(300)
        assert a / 4 == rupees(25)
        assert -a == rupees(-100)
        assert abs(rupees(-100)) == a

    def test_reflected_operators(self) -> None:
        assert 100 + rupees(30) == rupees(130)
        assert 3 * rupees(30) == rupees(90)
        assert 100 - rupees(30) == rupees(70)

    def test_comparison(self) -> None:
        assert rupees(100) > rupees(50)
        assert rupees(50) < rupees(100)
        assert rupees(100) >= rupees(100)
        assert rupees(100) <= rupees(100)
        assert rupees(100) == 100
        assert rupees(100) != rupees(50)

    def test_comparison_with_other_type_is_not_implemented(self) -> None:
        assert (rupees(100) == "100") is False

    def test_truthiness_and_hash(self) -> None:
        assert bool(rupees(1)) and not bool(ZERO)
        assert len({rupees(100), Money("100.00")}) == 1

    def test_int_conversion(self) -> None:
        assert int(rupees("100.75")) == 100

    def test_helpers(self) -> None:
        assert minimum(rupees(5), rupees(3)) == rupees(3)
        assert maximum(rupees(5), rupees(3)) == rupees(5)
        assert pct_of(rupees(1000), rate("0.05")) == rupees(50)


class TestMoneyRounding:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("60432.60", 60430),
            ("60435", 60440),
            ("4", 0),
            ("5", 10),      # s.288B: a last digit of five rounds UP
            ("6", 10),
            ("0", 0),
        ],
    )
    def test_288b_to_nearest_ten(self, value: str, expected: int) -> None:
        """Legacy s.288B: ignore paise, then round the last digit — five or
        more goes up, less than five goes down."""
        assert Money(value).round_288b() == Money(expected)

    def test_288a_matches_288b_shape(self) -> None:
        assert Money("12345.67").round_288a() == Money(12350)

    def test_to_rupees(self) -> None:
        assert Money("100.49").to_rupees() == Money(100)
        assert Money("100.50").to_rupees() == Money(101)

    def test_clamp_non_negative(self) -> None:
        assert rupees(-500).clamp_non_negative() == ZERO
        assert rupees(500).clamp_non_negative() == rupees(500)


class TestMoneyFormatting:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, "0"), (999, "999"), (1000, "1,000"), (99999, "99,999"),
            (100000, "1,00,000"), (1275000, "12,75,000"),
            (10000000, "1,00,00,000"), (-1275000, "-12,75,000"),
        ],
    )
    def test_indian_digit_grouping(self, value: int, expected: str) -> None:
        assert rupees(value).indian_format() == expected

    def test_str_and_repr(self) -> None:
        assert str(rupees(1275000)) == "₹12,75,000"
        assert repr(rupees(100)) == "Money('100.00')"

    def test_to_json_is_a_string_not_a_number(self) -> None:
        """JSON numbers are IEEE 754 doubles at the far end."""
        assert rupees("1275000.50").to_json() == "1275000.50"


@pytest.mark.parametrize(
    "r,expected", [("0.10", "10"), ("0.05", "5"), ("0.125", "12.5"), ("0", "0")]
)
def test_format_rate_avoids_scientific_notation(r: str, expected: str) -> None:
    """Decimal.normalize() renders 10 as '1E+1'. A worksheet line reading
    "@ 1E+1%" is not something you show a taxpayer."""
    assert format_rate(Decimal(r)) == expected


# ═══ Citation ════════════════════════════════════════════════════════════════

class TestCitation:
    def test_requires_a_section(self) -> None:
        with pytest.raises(ValueError, match="at least one section"):
            Citation()

    def test_shows_both_numberings_during_the_transition(self) -> None:
        c = Citation(section="156", legacy_section="87A", fy="2026-27")
        assert c.display == "Income-tax Act, 2025 · s.156 (formerly s.87A) · FY 2026-27"

    def test_legacy_only(self) -> None:
        assert "s.87A" in Citation(legacy_section="87A").display

    def test_serialises(self) -> None:
        d = Citation(section="156", legacy_section="87A", fy="2026-27",
                     retrieved_at=date(2026, 8, 9)).to_dict()
        assert d["retrieved_at"] == "2026-08-09"
        assert d["note"] is None


class TestSourceRef:
    def test_rejects_an_invalid_tier(self) -> None:
        with pytest.raises(ValueError, match="tier must be"):
            SourceRef("https://x", 4, date(2026, 8, 9))

    @pytest.mark.parametrize("tier,allowed", [(1, True), (2, True), (3, False)])
    def test_only_tiers_1_and_2_may_drive_a_figure(self, tier: int, allowed: bool) -> None:
        ref = SourceRef("https://x", tier, date(2026, 8, 9))
        assert ref.may_drive_a_figure is allowed
        assert ref.to_dict()["may_drive_a_figure"] is allowed


# ═══ Trace ═══════════════════════════════════════════════════════════════════

class TestTraceReplay:
    def test_every_operation_recomputes(self) -> None:
        t = Trace("ops")
        t.literal("given", rupees(1000))
        t.sum_of("sum", rupees(10), rupees(20))
        t.subtract("subtract", rupees(100), rupees(30))
        t.multiply("multiply", rupees(200), Decimal("0.05"))
        t.lesser_of("min", rupees(50), rupees(80))
        t.greater_of("max", rupees(50), rupees(80))
        t.clamp_zero("clamp", rupees(-5))
        t.rounded("round", rupees(103), rupees(100), note="s.288B")
        assert t.verify() == []

    def test_slab_step_sums_its_bands(self) -> None:
        bands = [
            Step("b1", Op.MULTIPLY, rupees(20000), operands=(rupees(400000),),
                 factor=Decimal("0.05")),
            Step("b2", Op.MULTIPLY, rupees(40000), operands=(rupees(400000),),
                 factor=Decimal("0.10")),
        ]
        t = Trace("slab")
        assert t.slab("total", bands) == rupees(60000)
        assert t.verify() == []

    def test_tampering_is_caught(self) -> None:
        t = Trace("t")
        t.subtract("taxable", rupees(1000), rupees(100))
        t.steps[-1] = Step("taxable", Op.SUBTRACT, rupees(999),
                           operands=(rupees(1000), rupees(100)))
        with pytest.raises(AssertionError, match="does not replay"):
            t.replay()

    def test_malformed_multiply_is_reported_not_raised(self) -> None:
        t = Trace("t")
        t.add(Step("bad", Op.MULTIPLY, rupees(10), operands=()))
        assert any("replay raised" in p for p in t.verify())

    def test_unknown_operation_is_reported(self) -> None:
        t = Trace("t")
        t.add(Step("bad", "not_an_op", rupees(10)))  # type: ignore[arg-type]
        assert any("replay raised" in p for p in t.verify())

    def test_empty_operand_subtract_and_sum(self) -> None:
        assert Step("s", Op.SUBTRACT, ZERO).recompute() == ZERO
        assert Step("s", Op.SUM, ZERO).recompute() == ZERO


class TestTraceOutput:
    def _trace(self) -> Trace:
        t = Trace("Worksheet")
        t.literal("Gross", rupees(1275000), note="Form 16")
        t.literal("Standard deduction", rupees(75000),
                  citation=Citation(legacy_section="16(ia)", fy="2026-27"))
        t.subtract("Taxable", rupees(1275000), rupees(75000))
        return t

    def test_result_is_the_last_step(self) -> None:
        assert self._trace().result == rupees(1200000)

    def test_empty_trace_result(self) -> None:
        assert Trace("empty").result == ZERO

    def test_render_includes_labels_citations_and_notes(self) -> None:
        out = self._trace().render()
        assert "Worksheet" in out and "Form 16" in out and "s.16(ia)" in out

    def test_str_matches_render(self) -> None:
        t = self._trace()
        assert str(t) == t.render()

    def test_citations_deduplicated(self) -> None:
        t = Trace("t")
        c = Citation(legacy_section="87A", fy="2026-27")
        t.literal("a", rupees(1), citation=c)
        t.literal("b", rupees(2), citation=c)
        assert len(t.citations()) == 1

    def test_citations_found_in_children(self) -> None:
        child = Step("band", Op.LITERAL, rupees(10),
                     citation=Citation(legacy_section="115BAC", fy="2026-27"))
        t = Trace("t")
        t.slab("total", [child])
        assert [c.legacy_section for c in t.citations()] == ["115BAC"]

    def test_serialises_to_json_shape(self) -> None:
        d = self._trace().to_dict()
        assert d["result"] == "1200000.00"
        assert len(d["steps"]) == 3
        assert d["steps"][1]["citation"]["legacy_section"] == "16(ia)"

    def test_nested_subtrace(self) -> None:
        inner = Trace("inner")
        inner.literal("x", rupees(5))
        outer = Trace("outer")
        outer.nest("folded", inner, rupees(5))
        assert outer.result == rupees(5)
        assert outer.verify() == []


# ═══ Confidence ══════════════════════════════════════════════════════════════

class TestConfidence:
    def test_complete_official_inputs_report_certain_not_a_percentage(self) -> None:
        """Fake precision is itself a trust leak. v1 hardcoded 0.80 and 0.88."""
        c = Confidence()
        assert c.level is Level.CERTAIN
        assert c.score == Decimal("1.00")
        assert "exact" in c.summary
        assert c.to_dict()["is_certain"] is True

    def test_official_and_verified_sources_carry_no_penalty(self) -> None:
        c = Confidence()
        c.input_from("salary", Provenance.OFFICIAL_DOCUMENT)
        c.input_from("interest", Provenance.VERIFIED_PARSE)
        assert c.level is Level.CERTAIN

    @pytest.mark.parametrize(
        "prov,expected_level",
        [
            (Provenance.PARSED, Level.HIGH),
            (Provenance.USER_STATED, Level.HIGH),
            (Provenance.DEFAULT, Level.PARTIAL),
            (Provenance.ASSUMED, Level.PARTIAL),
        ],
    )
    def test_weaker_provenance_lowers_the_level(self, prov, expected_level) -> None:
        c = Confidence()
        c.input_from("income", prov)
        assert c.level is expected_level

    def test_blocking_gap_is_insufficient_not_a_low_score(self) -> None:
        c = Confidence()
        c.missing("total income", "cannot compute tax at all", blocks=True)
        assert c.level is Level.INSUFFICIENT
        assert "Not enough information" in c.summary

    def test_missing_field_names_itself_and_its_consequence(self) -> None:
        c = Confidence()
        c.missing("rent paid", "HRA exemption excluded")
        assert "rent paid" in c.signals[0].detail
        assert "HRA exemption excluded" in c.signals[0].detail

    def test_stale_rules_degrade_by_age(self) -> None:
        today = date(2026, 8, 9)
        fresh, mid, old = Confidence(), Confidence(), Confidence()
        fresh.rule_age("2026-27", date(2026, 8, 1), today)
        mid.rule_age("2026-27", date(2026, 4, 1), today)
        old.rule_age("2026-27", date(2025, 1, 1), today)
        assert fresh.signals == []
        assert mid.score > old.score

    def test_source_tier_penalty(self) -> None:
        t1, t2, t3 = Confidence(), Confidence(), Confidence()
        t1.source_tier("GST rate", 1)
        t2.source_tier("price", 2)
        t3.source_tier("price", 3)
        assert t1.signals == []
        assert t2.score > t3.score
        assert "not official" in t3.signals[0].detail

    def test_llm_generated_marks_the_result_non_deterministic(self) -> None:
        """Should never fire inside the core. If it does, the answer is not
        deterministic and must not be presented as exact."""
        c = Confidence()
        c.llm_generated("estimated deduction")
        assert c.deterministic is False
        assert c.level is Level.LOW
        assert c.to_dict()["deterministic"] is False

    def test_score_is_clamped(self) -> None:
        c = Confidence()
        for _ in range(20):
            c.assumption("x", "y")
        assert c.score == Decimal("0.00")

    def test_improvements_are_ordered_by_impact(self) -> None:
        c = Confidence()
        c.input_from("income", Provenance.USER_STATED)   # 0.05
        c.assumption("age", "35")                        # 0.10
        c.source_tier("price", 3)                        # 0.25
        assert c.improvements()[0] == "confirm against the official portal"

    def test_summary_names_the_largest_cause(self) -> None:
        c = Confidence()
        c.missing("rent paid", "HRA excluded")
        assert "rent paid" in c.summary

    def test_serialisation_shape(self) -> None:
        c = Confidence()
        c.assumption("age", "35")
        d = c.to_dict()
        assert set(d) >= {"level", "display", "score", "summary", "signals",
                          "blocking", "improvements", "is_certain"}
        assert d["signals"][0]["penalty"] == "0.10"

    def test_provenance_labels_are_human_readable(self) -> None:
        assert Provenance.OFFICIAL_DOCUMENT.label == "official document"

    def test_level_display_strings(self) -> None:
        assert Level.CERTAIN.display == "Certain"
        assert Level.INSUFFICIENT.display == "Not enough information"
