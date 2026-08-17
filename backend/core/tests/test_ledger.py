"""Citation ledger — PLN-007.

The one invariant that matters: a figure with no provenance cannot be built,
so it cannot be displayed. Everything else here is in service of that.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.provenance.ledger import (
    Ledger,
    LedgerEntry,
    UndatedFigure,
    entry_from_citation,
    ledger_from_trace,
)
from backend.core.provenance.money import rupees
from backend.core.rules import load_ruleset
from backend.core.rules.aliases import cite
from backend.core.tax_engine import TaxInput, compute_tax

FY = "2026-27"
RS = load_ruleset(FY)


def _entry(**kw) -> LedgerEntry:
    base = {
        "label": "Standard deduction",
        "value": rupees(75_000),
        "fy": FY,
        "act": "Income-tax Act, 2025",
        "verified_on": date(2026, 8, 9),
        "legacy_section": "16(ia)",
    }
    base.update(kw)
    return LedgerEntry(**base)


# ══ the invariant ═══════════════════════════════════════════════════════════

class TestAnUndatedFigureCannotExist:
    """Raising rather than flagging. A figure whose provenance is unknown must
    not reach a user at all, so the absence of a date is a bug rather than a
    display state."""

    def test_no_verification_date_raises(self) -> None:
        with pytest.raises(UndatedFigure, match="no verification date"):
            _entry(verified_on=None)

    def test_nothing_to_click_through_to_raises(self) -> None:
        with pytest.raises(UndatedFigure, match="nothing for a user"):
            _entry(legacy_section=None, section=None, rule_id=None)

    def test_a_rule_id_alone_is_enough(self) -> None:
        """Not every step has a section — the slab table is in the rule pack,
        not in a numbered provision. A rule id is a legitimate destination."""
        assert _entry(legacy_section=None, rule_id="fy_2026_27").rule_id

    def test_the_error_names_the_figure(self) -> None:
        """So a developer knows which one, without bisecting a trace."""
        with pytest.raises(UndatedFigure, match="Cess"):
            _entry(label="Cess", verified_on=None)


# ══ both numbering schemes ══════════════════════════════════════════════════

class TestNumberingSchemes:
    def test_both_are_shown_when_both_are_known(self) -> None:
        e = _entry(section="202", legacy_section="115BAC")
        assert e.shows_both_numbering_schemes
        assert "s.202 (formerly s.115BAC)" in e.citation_display

    def test_only_the_legacy_number_where_the_mapping_is_unverified(self) -> None:
        """`cite()` refuses to assert an unverified 2025-Act number, and the
        ledger carries that refusal through to what the user reads."""
        e = entry_from_citation("Rebate", rupees(60_000), cite("87A", FY), RS)
        assert e.section is None
        assert e.legacy_section == "87A"
        assert not e.shows_both_numbering_schemes
        assert "provisionally s.156" in e.note

    def test_the_act_name_follows_the_year(self) -> None:
        assert "Income-tax Act, 2025" in entry_from_citation(
            "Rebate", rupees(60_000), cite("87A", FY), RS
        ).citation_display


# ══ joining the citation to the rule pack ═══════════════════════════════════

class TestProvenanceJoin:
    def test_the_verification_date_comes_from_the_rule_pack(self) -> None:
        """A `Citation` knows the section but not when anyone last checked it.
        That lives in the pack's meta block, and neither alone can render a
        figure a user is able to verify."""
        e = entry_from_citation("Rebate", rupees(60_000), cite("87A", FY), RS)
        assert e.verified_on == RS.verified_on

    def test_source_urls_fall_back_to_the_rule_pack(self) -> None:
        e = entry_from_citation("Rebate", rupees(60_000), cite("87A", FY), RS)
        assert e.source_urls == RS.sources
        assert any("incometax" in u for u in e.source_urls)

    def test_an_assumption_is_labelled_as_one(self) -> None:
        e = entry_from_citation(
            "Assumed rent", rupees(240_000), cite("10(13A)", FY), RS,
            is_assumption=True,
        )
        assert e.is_assumption
        assert e.to_dict()["is_assumption"]


# ══ staleness ═══════════════════════════════════════════════════════════════

class TestStaleness:
    def test_a_fresh_rule_is_not_stale(self) -> None:
        assert not _entry().is_stale(date(2026, 9, 1))

    def test_past_the_window_it_is(self) -> None:
        assert _entry().is_stale(date(2027, 6, 1))

    def test_the_boundary_is_exclusive(self) -> None:
        e = _entry(verified_on=date(2026, 1, 1))
        assert not e.is_stale(date(2026, 6, 30), window_days=180)
        assert e.is_stale(date(2026, 7, 1), window_days=180)

    def test_the_ledger_can_list_only_the_stale_ones(self) -> None:
        led = Ledger(fy=FY)
        led.add(_entry(label="fresh", verified_on=date(2027, 5, 1)))
        led.add(_entry(label="old", verified_on=date(2026, 1, 1)))
        assert [e.label for e in led.stale(date(2027, 6, 1))] == ["old"]


# ══ built from the trace, not from memory ═══════════════════════════════════

class TestLedgerFromTrace:
    def _ledger(self) -> Ledger:
        r = compute_tax(TaxInput(
            fy=FY, regime="new", salary=rupees(1_500_000),
            deductions={"80C": rupees(150_000)},
        ))
        return ledger_from_trace(r.trace, FY)

    def test_every_step_becomes_an_entry(self) -> None:
        """Walking the trace means the ledger cannot disagree with the
        arithmetic: a figure is listed because a step produced it, not because
        someone remembered to register it."""
        led = self._ledger()
        assert len(led.entries) > 5
        labels = {e.label for e in led.entries}
        assert "Taxable income" in labels
        assert "Standard deduction (salary)" in labels

    def test_cited_steps_keep_their_section(self) -> None:
        led = self._ledger()
        sd = next(e for e in led.entries if "Standard deduction" in e.label)
        assert sd.legacy_section == "16(ia)"

    def test_uncited_steps_are_attributed_to_the_rule_pack(self) -> None:
        """Honest rather than blank: the slab table has a verification date
        even where the step carries no section number."""
        led = self._ledger()
        gross = next(e for e in led.entries if e.label == "Gross total income")
        assert gross.rule_id == "fy_2026_27"
        assert gross.verified_on == RS.verified_on

    def test_nested_slab_bands_are_included(self) -> None:
        led = self._ledger()
        assert any("@ 5%" in e.label or "@ 10%" in e.label for e in led.entries)

    def test_every_entry_in_a_real_trace_is_renderable(self) -> None:
        """The end-to-end version of the invariant: a full computation produces
        no figure the UI would have to refuse."""
        for e in self._ledger().entries:
            assert e.verified_on is not None
            assert e.section or e.legacy_section or e.rule_id

    def test_serialises_for_the_ui(self) -> None:
        d = self._ledger().to_dict()
        assert d["count"] == len(d["entries"])
        first = d["entries"][0]
        assert {"display", "citation", "verified_on", "source_urls"} <= set(first)
        assert "₹" in first["display"]
