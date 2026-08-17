"""Evidence Pack content model — EVD-006.

Pure `PackContent` only: hashes, appendix, assumptions, closed windows. The
rendering and vault tests live in `backend/services/tests/` because the
import-linter purity contract forbids `backend.core` — including its tests —
from reaching `backend.services`, and it is right to. A test that has to
violate an architectural boundary is a test in the wrong place.

The keystone assertion (numeric_provenance over the finished PDF) is therefore
in the services suite, where the renderer lives.
"""

from __future__ import annotations

from datetime import date

from backend.core.provenance.evidence_pack import (
    PACK_FORMAT_VERSION,
    ClosedWindow,
    InputRecord,
    build_pack,
    closed_windows_from_outcomes,
)
from backend.core.provenance.money import rupees
from backend.core.rules import load_ruleset
from backend.core.tax_engine import TaxInput, compute_tax

FY = "2026-27"
RS = load_ruleset(FY)
WHEN = date(2026, 8, 12)


def _result(**kw):
    kw.setdefault("salary", rupees(1_500_000))
    kw.setdefault("deductions", {"80C": rupees(150_000)})
    return compute_tax(TaxInput(fy=FY, regime=kw.pop("regime", "new"), **kw))


def _pack(**kw):
    r = _result()
    base = {
        "title": "Tax computation",
        "fy": FY,
        "worksheets": [r.trace],
        "confidence": r.confidence,
        "generated_on": WHEN,
    }
    base.update(kw)
    return build_pack(**base)


# ══ the keystone: no LLM figures ════════════════════════════════════════════

class TestNoFigureComesFromProse:
    def test_notes_are_prose_and_carry_no_asserted_figure(self) -> None:
        """The only free-text channel into the pack. If a number could ride in
        on a note, the guarantee would be aspirational rather than mechanical."""
        pack = _pack(notes=["Figures assume no other income."])
        assert pack.notes
        # Every figure the pack asserts comes from the ledger, which is built
        # from traces — not from notes.
        assert all(e.label for e in pack.figures())

    def test_figures_come_only_from_the_worksheets(self) -> None:
        one = _pack()
        two = _pack(worksheets=[_result().trace, _result(salary=rupees(3_000_000)).trace])
        assert len(two.figures()) > len(one.figures())


# ══ every number traces to a rule and a source ══════════════════════════════

class TestEveryFigureIsAttributed:
    def test_each_has_a_provision_and_a_verification_date(self) -> None:
        for entry in _pack().figures():
            assert entry.citation_display
            assert entry.verified_on is not None

    def test_each_carries_at_least_one_source_url(self) -> None:
        for entry in _pack().figures():
            assert entry.source_urls

    def test_the_rule_pack_version_and_date_are_recorded(self) -> None:
        pack = _pack()
        assert pack.rule_pack_id == "fy_2026_27"
        assert pack.rule_pack_verified_on == RS.verified_on

    def test_the_governing_act_is_named(self) -> None:
        assert _pack().governing_act == "Income-tax Act, 2025"


# ══ assumptions are separated from stated facts ═════════════════════════════

class TestAssumptions:
    def test_they_are_counted_separately(self) -> None:
        pack = _pack(inputs=[
            InputRecord("Salary", "₹15,00,000", "Form 16"),
            InputRecord("Rent", "₹3,60,000", "assumed from city average",
                        is_assumption=True),
        ])
        assert len(pack.inputs) == 2
        assert len(pack.assumptions) == 1
        assert pack.assumptions[0].label == "Rent"

    def test_an_assumption_presented_as_fact_would_be_the_whole_problem(self) -> None:
        """A pack is evidence. An assumption recorded as something the user
        stated is evidence for a figure nobody agreed to."""
        assumed = InputRecord("Rent", "₹3,60,000", "assumed", is_assumption=True)
        assert assumed.to_dict()["is_assumption"] is True


# ══ closed windows ══════════════════════════════════════════════════════════

class TestClosedWindows:
    def test_they_are_listed_with_the_closing_date(self) -> None:
        pack = _pack(closed_windows=[ClosedWindow(
            "EV loan interest (80EEB)", date(2023, 3, 31), rupees(150_000),
            "Loan had to be sanctioned by 31 March 2023.", "80EEB",
        )])
        w = pack.closed_windows[0]
        assert w.closed_on == date(2023, 3, 31)
        assert w.would_have_been_worth == rupees(150_000)
        assert w.to_dict()["closed_on"] == "2023-03-31"

    def test_only_closed_outcomes_are_lifted(self) -> None:
        """An eligible benefit belongs in the recommendation. A closed one
        belongs in the pack, because it is the thing the user is most likely to
        be wrong about."""
        from backend.core.eligibility.evaluator import Outcome, Status

        outcomes = [
            Outcome("a", "Still available", Status.ELIGIBLE, rupees(50_000)),
            Outcome("b", "Gone", Status.WINDOW_CLOSED, rupees(150_000),
                    closed_on=date(2023, 3, 31)),
            Outcome("c", "Unknown", Status.INSUFFICIENT_DATA),
        ]
        lifted = closed_windows_from_outcomes(outcomes)
        assert [w.name for w in lifted] == ["Gone"]

    def test_a_pack_with_no_closed_windows_simply_has_none(self) -> None:
        assert _pack().closed_windows == []


# ══ reproducibility groundwork (EVD-007 builds on this) ═════════════════════

class TestHashes:
    def test_the_content_hash_ignores_the_generation_date(self) -> None:
        """Otherwise the hash cannot prove reproducibility — regenerating next
        week from identical inputs would produce a different value."""
        assert _pack(generated_on=date(2026, 8, 12)).content_hash() == _pack(
            generated_on=date(2027, 1, 1)
        ).content_hash()

    def test_but_it_changes_when_an_input_changes(self) -> None:
        a = _pack(inputs=[InputRecord("Salary", "₹15,00,000", "Form 16")])
        b = _pack(inputs=[InputRecord("Salary", "₹18,00,000", "Form 16")])
        assert a.content_hash() != b.content_hash()

    def test_and_when_the_arithmetic_changes(self) -> None:
        a = _pack()
        b = _pack(worksheets=[_result(salary=rupees(3_000_000)).trace])
        assert a.content_hash() != b.content_hash()

    def test_the_input_hash_is_independent_of_the_arithmetic(self) -> None:
        inputs = [InputRecord("Salary", "₹15,00,000", "Form 16")]
        a = _pack(inputs=inputs)
        b = _pack(inputs=inputs, worksheets=[_result(salary=rupees(3_000_000)).trace])
        assert a.input_hash() == b.input_hash()
        assert a.content_hash() != b.content_hash()

    def test_hashes_are_stable_across_runs(self) -> None:
        assert _pack().content_hash() == _pack().content_hash()


# ══ the machine-readable appendix ═══════════════════════════════════════════

class TestAppendix:
    def test_it_carries_everything_needed_to_re_run(self) -> None:
        """The difference between a document that asserts a number and one that
        lets you check it."""
        a = _pack(inputs=[InputRecord("Salary", "₹15,00,000", "Form 16")]).appendix()
        assert {
            "fy", "rule_pack_id", "rule_pack_verified_on", "rule_pack_sources",
            "inputs", "worksheets", "ledger", "content_hash", "input_hash",
        } <= set(a)

    def test_the_worksheets_are_replayable_from_it(self) -> None:
        a = _pack().appendix()
        assert a["worksheets"][0]["steps"]

    def test_it_is_json_serialisable(self) -> None:
        import json

        assert json.loads(json.dumps(_pack().appendix(), default=str))

    def test_the_format_version_is_stamped(self) -> None:
        """So a future reader knows which schema it is looking at."""
        assert _pack().appendix()["pack_format_version"] == PACK_FORMAT_VERSION
