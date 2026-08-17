"""Evidence panel payload — EVD-005.

The acceptance criteria, in the order they matter:

  * Working renders the actual trace, not a re-narration
  * every assumption is labelled AND addressable, so it can be edited in place
  * Confidence says concretely what would raise it, and by how much
  * the panel's four tabs come from ONE computation, not four
"""

from __future__ import annotations

import pytest

from backend.core.provenance.money import rupees
from backend.core.provenance.panel import build_panel
from backend.core.tax_engine import TaxInput, compute_tax

FY = "2026-27"


def _result(**kw):
    kw.setdefault("salary", rupees(1_500_000))
    kw.setdefault("deductions", {"80C": rupees(150_000)})
    return compute_tax(TaxInput(fy=FY, regime=kw.pop("regime", "new"), **kw))


def _panel(**kw):
    return build_panel(_result(**kw), FY)


# ══ Working is a rendering, not a narration ═════════════════════════════════

class TestWorkingTab:
    def test_the_lines_are_the_trace_itself(self) -> None:
        """Character for character. A re-narration can drift from the
        arithmetic; a rendering cannot, because `verify()` fails if the steps
        stop reproducing their own results."""
        result = _result()
        working = build_panel(result, FY).working()[0]
        assert working["lines"] == result.trace.render().splitlines()

    def test_the_worksheet_reports_whether_it_replays(self) -> None:
        assert build_panel(_result(), FY).working()[0]["replays"] is True

    def test_a_worksheet_that_does_not_replay_is_flagged(self) -> None:
        """Presenting a broken worksheet as evidence is worse than showing
        nothing. The panel surfaces it rather than rendering it silently."""
        result = _result()
        # Must tamper with a DERIVED step. steps[0] is a literal, whose
        # recompute() trivially returns its own value, so corrupting it does not
        # break replay — my first attempt at this test asserted nothing.
        derived = next(s for s in result.trace.steps if s.op.value == "sum")
        object.__setattr__(derived, "result", rupees(1))
        panel = build_panel(result, FY)
        assert panel.working()[0]["replays"] is False
        assert panel.has_unreplayable_worksheet
        assert panel.to_dict()["has_unreplayable_worksheet"]

    def test_a_clean_panel_is_not_flagged(self) -> None:
        assert not _panel().has_unreplayable_worksheet

    def test_extra_worksheets_are_included(self) -> None:
        other = _result(salary=rupees(3_000_000))
        panel = build_panel(_result(), FY, extra_worksheets=[other.trace])
        assert len(panel.working()) == 2


# ══ Sources ═════════════════════════════════════════════════════════════════

class TestSourcesTab:
    def test_each_provision_appears_once(self) -> None:
        """A slab table cited on six steps is one source. Listing it six times
        makes the tab look thorough and reads worse."""
        sources = _panel().sources()
        assert len({s["citation"] for s in sources}) == len(sources)

    def test_a_source_says_what_it_decided(self) -> None:
        sd = next(
            s for s in _panel().sources() if "16(ia)" in s["citation"]
        )
        assert "Standard deduction (salary)" in sd["decided"]

    def test_a_source_accumulates_every_figure_it_decided(self) -> None:
        """The rule pack decides many figures — gross income, taxable income,
        the total. All of them must appear under that one source.

        Without this the dedup could reset the list on each hit, keeping only
        the last label, and the tab would under-report what each provision
        actually drove. A mutation doing exactly that passed until this test
        existed.
        """
        sources = _panel().sources()
        pack = next(s for s in sources if "fy_2026_27" in s["citation"])
        assert len(pack["decided"]) > 3
        assert "Gross total income" in pack["decided"]
        assert "Taxable income" in pack["decided"]

    def test_every_source_carries_a_verification_date(self) -> None:
        assert all(s["verified_on"] for s in _panel().sources())

    def test_both_numbering_schemes_are_flagged_where_known(self) -> None:
        """For FY 2026-27 the governing Act renumbered everything, so the panel
        has to be able to say "s.X, the one you know as s.Y"."""
        for s in _panel().sources():
            assert isinstance(s["both_numbering_schemes"], bool)

    def test_sources_are_ordered_stably(self) -> None:
        a = [s["citation"] for s in _panel().sources()]
        assert a == sorted(a)


# ══ Assumptions are labelled AND addressable ════════════════════════════════

class TestAssumptionsTab:
    def _with(self, **assumptions):
        return build_panel(_result(assumptions=assumptions), FY)

    def test_an_assumption_becomes_an_editable_row(self) -> None:
        rows = self._with(rent="₹30,000 a month").assumptions_tab()
        assert len(rows) == 1
        assert rows[0]["what"] == "rent"
        assert rows[0]["value"] == "₹30,000 a month"

    def test_it_names_the_field_it_would_edit(self) -> None:
        """An assumption the user can see but not correct is an irritation.
        `edits_field` is a field name, not a value, because correcting one must
        re-run the computation rather than patch the answer."""
        rows = self._with(city_of_residence="Pune").assumptions_tab()
        assert rows[0]["edits_field"] == "city_of_residence"

    def test_it_states_what_confirming_is_worth(self) -> None:
        rows = self._with(rent="₹30,000 a month").assumptions_tab()
        assert rows[0]["gain_if_confirmed"] == "0.10"

    def test_every_row_is_marked_as_an_assumption(self) -> None:
        rows = self._with(rent="₹30,000", city="Pune").assumptions_tab()
        assert all(r["is_assumption"] for r in rows)

    def test_no_assumptions_means_an_empty_tab_not_a_fabricated_one(self) -> None:
        assert _panel().assumptions_tab() == []

    def test_a_value_that_already_says_assumed_is_not_doubled(self) -> None:
        """The signal read "assumed rent = assumed ₹30k/mo…" because the label
        prefixed a word the value already carried."""
        rows = self._with(rent="assumed ₹30k/mo from a city average").assumptions_tab()
        assert rows[0]["what"] == "rent"
        assert not rows[0]["value"].startswith("assumed assumed")

    def test_only_assumption_signals_become_rows(self) -> None:
        """A user-stated input carries a confidence penalty too, but it is not
        an assumption and must not be offered for 'correction'."""
        panel = _panel()
        assert panel.confidence is not None
        assert any(s.kind == "input_provenance" for s in panel.confidence.signals)
        assert panel.assumptions_tab() == []


# ══ Confidence says what would raise it, and by how much ════════════════════

class TestConfidenceTab:
    def test_it_lists_remedies_with_their_gain(self) -> None:
        """"Confirm your rent" is advice. "Confirm your rent, worth 0.10" is a
        reason to bother. Remedies without weights make every one look equally
        urgent, which is how users ignore all of them."""
        tab = build_panel(
            _result(assumptions={"rent": "₹30,000 a month"}), FY
        ).confidence_tab()
        top = tab["what_would_raise_it"][0]
        assert top["gain"] == "0.10"
        assert "rent" in top["remedy"]
        assert top["because"]

    def test_they_are_ordered_by_how_much_they_are_worth(self) -> None:
        tab = build_panel(
            _result(assumptions={"rent": "₹30,000", "city": "Pune"}), FY
        ).confidence_tab()
        gains = [float(i["gain"]) for i in tab["what_would_raise_it"]]
        assert gains == sorted(gains, reverse=True)

    def test_the_level_is_a_level_not_a_manufactured_percentage(self) -> None:
        """EVD-003 removed fabricated scores. The panel shows the composed
        level, and CERTAIN means exact rather than 'high'."""
        from backend.core.provenance.confidence import Level

        tab = _panel().confidence_tab()
        # Taken from the enum rather than hardcoded — I guessed this set wrong
        # first time, which would have let a renamed level slip through.
        assert tab["level"] in {level.value for level in Level} | {"unknown"}
        assert not tab["level"].endswith("%")

    def test_a_missing_confidence_is_reported_as_unknown(self) -> None:
        class Bare:
            trace = _result().trace

        tab = build_panel(Bare(), FY).confidence_tab()
        assert tab["level"] == "unknown"
        assert "No confidence assessment" in tab["summary"]
        assert tab["improvements"] == []


# ══ one computation, four tabs ══════════════════════════════════════════════

def test_the_tabs_are_built_from_a_single_result() -> None:
    """`build_panel` takes the whole result rather than its parts, so the four
    tabs cannot be assembled from different runs — which is how a panel shows a
    worksheet for one computation beside a confidence score for another."""
    import inspect

    from backend.core.provenance import panel as module

    params = list(inspect.signature(module.build_panel).parameters)
    assert params[0] == "result"
    assert "trace" not in params and "confidence" not in params


def test_the_ledger_covers_every_worksheet_supplied() -> None:
    other = _result(salary=rupees(3_000_000))
    one = build_panel(_result(), FY)
    two = build_panel(_result(), FY, extra_worksheets=[other.trace])
    assert len(two.ledger.entries) > len(one.ledger.entries)


def test_serialises_with_all_four_tabs_and_counts() -> None:
    d = build_panel(_result(assumptions={"rent": "₹30,000"}), FY).to_dict()
    assert set(d["tabs"]) == {"working", "sources", "assumptions", "confidence"}
    assert d["counts"]["worksheets"] == 1
    assert d["counts"]["assumptions"] == 1
    assert d["counts"]["sources"] == len(d["tabs"]["sources"])


@pytest.mark.parametrize("fy", ["2024-25", "2025-26", "2026-27"])
def test_panels_build_for_every_supported_year(fy: str) -> None:
    r = compute_tax(TaxInput(fy=fy, regime="new", salary=rupees(1_500_000)))
    assert build_panel(r, fy).to_dict()["tabs"]["working"]
