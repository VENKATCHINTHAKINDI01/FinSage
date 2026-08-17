"""Reproducibility and integrity — EVD-007.

Three questions, deliberately kept apart because they mean different things:

    is this pack intact          → the content hash still matches
    can I get this answer again  → replay under the SAME pinned rule pack
    is it still right today      → recompute under the CURRENT pack and DIFF

The third is the one with teeth. A pack issued in August is read in January by
which time a rate may have been corrected. Quietly recomputing and showing a
different number is the failure this feature exists to prevent.
"""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from datetime import date

import pytest

from backend.core.provenance.evidence_pack import InputRecord, build_pack
from backend.core.provenance.money import rupees
from backend.core.provenance.reproduce import (
    Pin,
    ReplayMismatch,
    assert_reproduces,
    diff_under,
    pin_of,
    verify,
)
from backend.core.rules import load_ruleset
from backend.core.rules.loader import RULES_DIR
from backend.core.tax_engine import TaxInput, compute_tax

FY = "2026-27"
WHEN = date(2026, 8, 12)
SALARY = InputRecord("Salary", "₹15,00,000", "Form 16")


def _pack(*, salary: int = 1_500_000, inputs=None, on: date = WHEN):
    r = compute_tax(TaxInput(fy=FY, regime="new", salary=rupees(salary)))
    return build_pack(
        "Tax computation", FY, worksheets=[r.trace],
        inputs=list(inputs) if inputs is not None else [SALARY],
        generated_on=on,
    )


@contextmanager
def amended_rule(old: str, new: str):
    """Edit one line of the FY 2026-27 pack on disk, then restore it."""
    path = RULES_DIR / "fy_2026_27.yaml"
    backup = path.with_suffix(".yaml.evd007bak")
    shutil.copy2(path, backup)
    try:
        text = path.read_text(encoding="utf-8")
        assert old in text, f"target {old!r} not found; update this helper"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        load_ruleset.cache_clear()
        yield load_ruleset(FY)
    finally:
        shutil.copy2(backup, path)
        backup.unlink()
        load_ruleset.cache_clear()


@contextmanager
def amended_cess_rate():
    """Change the cess rate on disk, as a real mid-year correction would.

    A context manager rather than a fixture because the test needs to build the
    ISSUED pack against the pristine file first, then amend, then rebuild. A
    fixture amends before the test body runs, which makes "before" unreachable.

    `load_ruleset` is cached, so the cache is cleared on both sides.
    """
    path = RULES_DIR / "fy_2026_27.yaml"
    backup = path.with_suffix(".yaml.evd007bak")
    shutil.copy2(path, backup)
    try:
        text = path.read_text(encoding="utf-8")
        assert 'rate: "0.04"' in text, "cess rate line moved; update this helper"
        path.write_text(
            text.replace('rate: "0.04"', 'rate: "0.05"', 1), encoding="utf-8"
        )
        load_ruleset.cache_clear()
        yield load_ruleset(FY)
    finally:
        shutil.copy2(backup, path)
        backup.unlink()
        load_ruleset.cache_clear()


# ══ the pin is a fact about the file, not a claim inside it ═════════════════

class TestTheRulePackFingerprint:
    def test_the_version_carries_a_hash_of_the_file(self) -> None:
        rs = load_ruleset(FY)
        assert rs.version.startswith("fy_2026_27@")
        assert rs.content_hash[:12] in rs.version

    def test_editing_a_rate_changes_the_version_without_touching_the_date(
        self,
    ) -> None:
        """`verified_on` is a claim written inside the pack; a file hash is a
        fact about it. This edits a RATE and leaves the date alone — pinning the
        date would let that replay clean, which is not integrity.
        """
        before = load_ruleset(FY)
        before_version, before_verified = before.version, before.verified_on

        with amended_cess_rate() as after:
            assert after.version != before_version
            assert after.verified_on == before_verified, (
                "the point of this test is that the DATE did not move"
            )

    def test_the_version_is_stable_when_nothing_changes(self) -> None:
        assert load_ruleset(FY).version == load_ruleset(FY).version

    def test_different_years_have_different_versions(self) -> None:
        assert load_ruleset(FY).version != load_ruleset("2025-26").version


# ══ 1 & 2: intact, and replays ══════════════════════════════════════════════

class TestReplay:
    def test_the_same_inputs_reproduce_exactly(self) -> None:
        pin = pin_of(_pack())
        result = verify(pin, _pack())
        assert result.fully_reproduced
        assert "Reproduced exactly" in result.detail

    def test_a_later_generation_date_still_reproduces(self) -> None:
        """The whole reason `content_hash` excludes `generated_on`. If it did
        not, no pack could ever be shown to reproduce."""
        assert verify(pin_of(_pack()), _pack(on=date(2027, 1, 9))).fully_reproduced

    def test_different_inputs_do_not(self) -> None:
        pin = pin_of(_pack())
        result = verify(pin, _pack(salary=1_800_000))
        assert not result.intact
        assert "bug or tampering, not a rule change" in result.detail

    def test_an_untouched_computation_is_intact_but_still_not_reproduced(
        self,
    ) -> None:
        """The case that pins `fully_reproduced` to requiring BOTH conditions.

        The equity STCG rate is changed — a real edit that does not touch a
        plain salary computation. So the pack is byte-identical (`intact`) while
        the rule pack has moved. `fully_reproduced` must still be False: the
        reader is entitled to know the rulebook changed underneath them even
        where their own figures did not.

        Without this test, collapsing `fully_reproduced` to just `intact`
        passes the entire suite.
        """
        pin = pin_of(_pack())
        with amended_rule('rate: "0.20"\n    holding_months: 12',
                          'rate: "0.25"\n    holding_months: 12') as after:
            result = verify(pin, _pack(), ruleset=after)

        assert result.intact, "a salary computation does not use the STCG rate"
        assert not result.rule_pack_unchanged
        assert not result.fully_reproduced

    def test_the_two_failure_modes_are_reported_separately(self) -> None:
        """A hash mismatch under an unchanged pack is a bug. A mismatch because
        the pack changed is expected. Collapsing them into one boolean loses
        exactly the information a reader needs."""
        result = verify(pin_of(_pack()), _pack(salary=1_800_000))
        assert result.rule_pack_unchanged is True
        assert result.intact is False

    def test_the_strict_form_raises(self) -> None:
        with pytest.raises(ReplayMismatch, match="bug or tampering"):
            assert_reproduces(pin_of(_pack()), _pack(salary=1_800_000))

    def test_the_strict_form_is_silent_on_success(self) -> None:
        assert assert_reproduces(pin_of(_pack()), _pack()) is None

    def test_the_strict_form_also_raises_when_only_the_rules_moved(self) -> None:
        """An intact pack under a changed rule pack is not a reproduction. The
        guarantee the pack asserts is about both."""
        pin = pin_of(_pack())
        with (
            amended_cess_rate() as after,
            pytest.raises(ReplayMismatch, match="rule pack has changed"),
        ):
            assert_reproduces(pin, _pack(), ruleset=after)

    def test_a_pin_does_not_carry_the_answer(self) -> None:
        """A pin that held the output could be replayed against itself and
        always agree. The point is to recompute from inputs."""
        fields = set(Pin.__slots__)
        assert not {"total_tax", "figures", "result", "output"} & fields

    def test_a_pin_round_trips_through_json(self) -> None:
        pin = pin_of(_pack())
        assert Pin.from_dict(pin.to_dict()) == pin


# ══ 3: a changed rule pack is shown as a change ═════════════════════════════

class TestDiffUnderANewerRulePack:
    def test_a_changed_pack_is_detected_and_explained(self) -> None:
        pin = pin_of(_pack())
        with amended_cess_rate() as after:
            result = verify(pin, _pack(), ruleset=after)
            assert not result.rule_pack_unchanged
            assert "rule pack has changed" in result.detail
            assert "explained by that, not by an error" in result.detail
            # `fully_reproduced` must require BOTH conditions. Mutating it to
            # return just `intact` passed the whole suite until this line
            # existed.
            assert not result.fully_reproduced
            # And the message must attribute the difference to the RULE change,
            # never to tampering. Getting that wrong sends someone hunting a
            # bug that does not exist.
            assert "bug or tampering" not in result.detail

    def test_the_figures_that_moved_are_listed_with_both_values(self) -> None:
        """Cess 4% → 5% on a ₹15L salary. The pack as issued and the same inputs
        computed today are BOTH shown; neither replaces the other."""
        issued = _pack()
        pin = pin_of(issued)

        with amended_cess_rate() as after:
            r = compute_tax(
                TaxInput(fy=FY, regime="new", salary=rupees(1_500_000)),
                ruleset=after,
            )
            today = build_pack(
                "Tax computation", FY, worksheets=[r.trace], inputs=[SALARY],
                generated_on=date(2027, 1, 9), ruleset=after,
            )
            diff = diff_under(issued, today, pin, current_ruleset=after)

        assert diff.rule_pack_changed
        assert diff.figures_changed
        cess = next(c for c in diff.changes if "Cess" in c.label)
        # rupees() refuses a float, correctly — 4,687.50 is exactly the kind of
        # value binary floating point cannot hold, so it goes in as a string.
        assert cess.was == rupees(3_750)          # 4% of ₹93,750
        assert cess.now == rupees("4687.50")      # 5% of ₹93,750
        assert cess.direction == "increased"
        assert "was ₹3,750" in cess.sentence()

    def test_a_rate_change_is_one_change_not_a_removal_plus_an_addition(
        self,
    ) -> None:
        """Step labels embed the rate they applied — "Cess @ 4%". Keying the
        diff on the raw label reported a REMOVED "Cess @ 4%" and an ADDED
        "Cess @ 5%" instead of a single change, burying the one line the reader
        needs. Matching normalises the rate out; the displayed label keeps it.
        """
        issued = _pack()
        pin = pin_of(issued)
        with amended_cess_rate() as after:
            r = compute_tax(
                TaxInput(fy=FY, regime="new", salary=rupees(1_500_000)),
                ruleset=after,
            )
            today = build_pack(
                "Tax computation", FY, worksheets=[r.trace], inputs=[SALARY],
                generated_on=date(2027, 1, 9), ruleset=after,
            )
            diff = diff_under(issued, today, pin, current_ruleset=after)

        assert any("Cess" in c.label for c in diff.changes)
        assert not any("Cess" in label for label in diff.added)
        assert not any("Cess" in label for label in diff.removed)
        # The label shown is today's, so it describes today's rule.
        assert "5%" in next(c for c in diff.changes if "Cess" in c.label).label

    def test_the_headline_warns_before_any_number_is_read(self) -> None:
        """The reader must be told the rules moved BEFORE they look at a figure,
        or they will read a revision as the original."""
        issued = _pack()
        pin = pin_of(issued)
        with amended_cess_rate() as after:
            r = compute_tax(
                TaxInput(fy=FY, regime="new", salary=rupees(1_500_000)),
                ruleset=after,
            )
            today = build_pack(
                "Tax computation", FY, worksheets=[r.trace], inputs=[SALARY],
                generated_on=date(2027, 1, 9), ruleset=after,
            )
            headline = diff_under(
                issued, today, pin, current_ruleset=after
            ).headline()

        assert "⚠" in headline
        assert "AT THE TIME" in headline
        assert "would hide that anything moved" in headline

    def test_an_unchanged_pack_says_so_plainly(self) -> None:
        pack = _pack()
        diff = diff_under(pack, _pack(on=date(2027, 1, 9)), pin_of(pack))
        assert not diff.rule_pack_changed
        assert "have not changed" in diff.headline()
        assert diff.changes == []

    def test_comparing_different_declared_inputs_is_refused(self) -> None:
        """A difference between packs built from different facts says nothing
        about the rules, so producing a 'rule diff' from them would be a lie."""
        pack = _pack()
        other = _pack(salary=1_800_000,
                      inputs=[InputRecord("Salary", "₹18,00,000", "Form 16")])
        with pytest.raises(ReplayMismatch, match="different inputs"):
            diff_under(pack, other, pin_of(pack))

    def test_the_input_hash_covers_declared_inputs_only(self) -> None:
        """A known limitation, recorded rather than assumed away.

        `input_hash` hashes the `InputRecord` list — what the pack SAYS it was
        based on. It does not verify that the worksheets were actually computed
        from those figures. Two packs with identical declared inputs and
        different arithmetic therefore share an input hash, and `diff_under`
        will compare them without complaint.

        That is acceptable because both packs are built by the same engine from
        the same call site, but it means the input hash is a statement about the
        pack's own consistency, not a proof of it. `content_hash` DOES cover the
        arithmetic, which is why replay checks that.
        """
        declared = [InputRecord("Salary", "₹15,00,000", "Form 16")]
        a = _pack(inputs=declared)
        b = _pack(salary=1_800_000, inputs=declared)

        assert a.input_hash() == b.input_hash()
        assert a.content_hash() != b.content_hash()


# ══ what the pack asserts about itself ══════════════════════════════════════

def test_the_pack_prints_its_own_content_hash() -> None:
    """So a reader can verify the document they hold, not just one the server
    still has."""
    pack = _pack()
    assert pack.content_hash() == pin_of(pack).content_hash


def test_the_pin_records_the_rule_pack_version_not_just_the_year() -> None:
    pin = pin_of(_pack())
    assert "@" in pin.rule_pack_version
    assert pin.rule_pack_version.startswith("fy_2026_27@")


def test_the_fixture_restores_the_rule_pack() -> None:
    """Guards the fixture itself. A test that leaves a mutated cess rate behind
    would make every later run wrong in a way nothing else checks."""
    from decimal import Decimal

    assert load_ruleset(FY).cess_rate == Decimal("0.04")
