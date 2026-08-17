"""Consent, purpose limitation, retention and erasure — PRD-001."""

from __future__ import annotations

import inspect
from datetime import date, timedelta

import pytest

from backend.compliance.dpdp.consent import (
    RETENTION_DAYS,
    ConsentError,
    ConsentLedger,
    ErasureIncomplete,
    Notice,
    NoticeRegistry,
    Purpose,
    RetainedItem,
    assert_erased,
    due_for_erasure,
    erase,
    require_consent,
)

TODAY = date(2026, 8, 13)

TEXT_V1 = {
    Purpose.TAX_COMPUTATION: "To compute your income tax for the year.",
    Purpose.ITR_FILING: "To prepare and file your return.",
    Purpose.PRODUCT_ANALYTICS: "To count feature usage, without your name.",
    Purpose.MARKETING: "To email you about new features.",
}
V1 = Notice("v1", date(2026, 1, 1), TEXT_V1, "A Person", "grievance@example.in")


def notice(version: str, **changes) -> Notice:
    text = dict(TEXT_V1)
    text.update(changes)
    return Notice(version, date(2026, 6, 1), text, "A Person", "grievance@example.in")


def ledger_with(purpose=Purpose.TAX_COMPUTATION, n=V1):
    ledger = ConsentLedger()
    ledger.grant("p-1", purpose, n, TODAY)
    registry = NoticeRegistry()
    registry.publish(n)
    return ledger, registry


# ── consent is per purpose ──────────────────────────────────────────────────

def test_consent_to_one_purpose_is_not_consent_to_another():
    """A single `consent: true` column means agreeing to file your return also
    agreed to marketing."""
    ledger, registry = ledger_with(Purpose.TAX_COMPUTATION)
    require_consent("p-1", Purpose.TAX_COMPUTATION, ledger, V1, registry)
    with pytest.raises(ConsentError, match="no live consent"):
        require_consent("p-1", Purpose.MARKETING, ledger, V1, registry)


def test_consent_is_per_person():
    ledger, registry = ledger_with()
    with pytest.raises(ConsentError):
        require_consent("p-2", Purpose.TAX_COMPUTATION, ledger, V1, registry)


def test_a_purpose_the_notice_never_described_cannot_be_consented_to():
    """Consent must be informed. You cannot be informed about text that does
    not exist."""
    ledger = ConsentLedger()
    with pytest.raises(ConsentError, match="does not describe"):
        ledger.grant("p-1", Purpose.PROCUREMENT_ADVICE, V1, TODAY)


def test_the_purposes_are_a_closed_set():
    """s.6 requires the purpose to be SPECIFIED. A free-text purpose is not
    specified — it is whatever the caller typed that day."""
    assert not hasattr(Purpose, "OTHER")
    assert len(set(Purpose)) == 6


def test_analytics_and_marketing_are_refusable_without_losing_the_service():
    """Bundling them with the service is the thing the Act calls out."""
    assert Purpose.TAX_COMPUTATION.is_necessary_for_service
    assert not Purpose.PRODUCT_ANALYTICS.is_necessary_for_service
    assert not Purpose.MARKETING.is_necessary_for_service


# ── a notice version bump ───────────────────────────────────────────────────

def test_a_consent_survives_a_version_bump_that_did_not_change_its_wording():
    """Invalidating everything on every edit trains people to click through,
    which is its own harm."""
    ledger, registry = ledger_with(Purpose.TAX_COMPUTATION)
    v2 = notice("v2", **{Purpose.MARKETING: "Different marketing words."})
    registry.publish(v2)
    require_consent("p-1", Purpose.TAX_COMPUTATION, ledger, v2, registry)


def test_a_consent_dies_when_its_own_purpose_was_reworded():
    """The person agreed to different words, so 'informed' no longer holds."""
    ledger, registry = ledger_with(Purpose.TAX_COMPUTATION)
    v2 = notice("v2", **{
        Purpose.TAX_COMPUTATION: "To compute tax AND share it with partners.",
    })
    registry.publish(v2)
    with pytest.raises(ConsentError, match="description changed"):
        require_consent("p-1", Purpose.TAX_COMPUTATION, ledger, v2, registry)


def test_an_unknown_prior_notice_version_does_not_carry_over():
    """If the old text cannot be produced, there is no evidence of what the
    person was told."""
    ledger, _ = ledger_with(Purpose.TAX_COMPUTATION)
    empty = NoticeRegistry()
    v2 = notice("v2")
    with pytest.raises(ConsentError):
        require_consent("p-1", Purpose.TAX_COMPUTATION, ledger, v2, empty)


# ── withdrawal is as easy as granting ───────────────────────────────────────

def test_withdraw_takes_exactly_the_same_arguments_as_grant():
    """s.6(6) is testable, not a UI aspiration: no reason, no extra evidence,
    no second confirmation."""
    grant = inspect.signature(ConsentLedger.grant).parameters
    withdraw = inspect.signature(ConsentLedger.withdraw).parameters
    assert list(withdraw) == list(grant)


def test_withdrawal_stops_processing():
    ledger, registry = ledger_with()
    ledger.withdraw("p-1", Purpose.TAX_COMPUTATION, V1, TODAY)
    with pytest.raises(ConsentError):
        require_consent("p-1", Purpose.TAX_COMPUTATION, ledger, V1, registry)


def test_the_record_of_consent_survives_withdrawal():
    """Deleting the row destroys the evidence that consent was ever held,
    which is exactly what a Data Fiduciary must be able to show."""
    ledger, _ = ledger_with()
    ledger.withdraw("p-1", Purpose.TAX_COMPUTATION, V1, TODAY)
    assert len(ledger.records) == 1
    assert ledger.records[0].withdrawn_on == TODAY
    assert ledger.records[0].given_on == TODAY


def test_consent_can_be_given_again_after_withdrawal():
    ledger, registry = ledger_with()
    ledger.withdraw("p-1", Purpose.TAX_COMPUTATION, V1, TODAY)
    ledger.grant("p-1", Purpose.TAX_COMPUTATION, V1, TODAY + timedelta(days=1))
    require_consent("p-1", Purpose.TAX_COMPUTATION, ledger, V1, registry)


# ── retention is a job, not a paragraph ─────────────────────────────────────

def item(purpose=Purpose.PRODUCT_ANALYTICS, days_ago=0, store="postgres"):
    return RetainedItem(
        "p-1", purpose, TODAY - timedelta(days=days_ago), store, "row-1",
    )


def test_nothing_is_due_before_its_retention_period_runs():
    assert due_for_erasure([item(days_ago=10)], TODAY) == []


def test_data_past_its_retention_period_is_due():
    old = item(purpose=Purpose.PRODUCT_ANALYTICS,
               days_ago=RETENTION_DAYS[Purpose.PRODUCT_ANALYTICS] + 1)
    assert due_for_erasure([old], TODAY) == [old]


def test_tax_records_are_kept_longer_and_the_reason_is_not_our_choice():
    """A return can be revised or reopened, and ITR-U runs 48 months from the
    end of the assessment year. Deleting at 12 months would leave a user unable
    to answer a notice about their own filing."""
    assert RETENTION_DAYS[Purpose.TAX_COMPUTATION] > RETENTION_DAYS[Purpose.MARKETING]
    assert RETENTION_DAYS[Purpose.TAX_COMPUTATION] >= 4 * 365


def test_withdrawal_makes_data_due_immediately_not_at_the_end_of_the_window():
    """Continuing to hold it because the clock has not run is processing
    without a basis."""
    ledger = ConsentLedger()
    ledger.grant("p-1", Purpose.MARKETING, V1, TODAY)
    fresh = item(purpose=Purpose.MARKETING, days_ago=1)
    assert due_for_erasure([fresh], TODAY, ledger) == []

    ledger.withdraw("p-1", Purpose.MARKETING, V1, TODAY)
    assert due_for_erasure([fresh], TODAY, ledger) == [fresh]


def test_a_re_granted_consent_takes_the_item_off_the_erasure_list():
    ledger = ConsentLedger()
    ledger.grant("p-1", Purpose.MARKETING, V1, TODAY)
    ledger.withdraw("p-1", Purpose.MARKETING, V1, TODAY)
    ledger.grant("p-1", Purpose.MARKETING, V1, TODAY)
    assert due_for_erasure([item(purpose=Purpose.MARKETING, days_ago=1)],
                           TODAY, ledger) == []


# ── erasure must be verified ────────────────────────────────────────────────

def stores(present: set[str] | None = None):
    """Deleters that actually remove, confirmers that actually look."""
    live = set(present or {"row-1"})
    deleters = {
        "postgres": lambda ref: (live.discard(ref), True)[1],
        "vault": lambda ref: (live.discard(ref), True)[1],
        "qdrant": lambda ref: (live.discard(ref), True)[1],
    }
    confirmers = {name: (lambda ref: ref in live) for name in deleters}
    return deleters, confirmers, live


def test_a_confirmed_deletion_passes():
    deleters, confirmers, _ = stores()
    receipts = erase([item()], deleters, confirmers)
    assert all(r.ok for r in receipts)
    assert_erased(receipts)


def test_a_delete_that_did_not_actually_delete_is_a_failure():
    """The one that matters. A compliance record asserting something untrue is
    worse than no record."""
    deleters = {"postgres": lambda ref: True}       # says yes, does nothing
    confirmers = {"postgres": lambda ref: True}     # still there
    receipts = erase([item()], deleters, confirmers)
    assert not receipts[0].ok
    assert "still present" in receipts[0].detail
    with pytest.raises(ErasureIncomplete):
        assert_erased(receipts)


def test_a_store_with_no_confirmer_is_a_failure_not_an_assumption():
    """'We have no way to check' is not 'it is gone'."""
    receipts = erase([item()], {"postgres": lambda ref: True}, {})
    assert not receipts[0].ok
    assert "not a deletion — it is a claim" in receipts[0].detail


def test_a_store_with_no_deleter_is_named_rather_than_skipped():
    receipts = erase([item(store="qdrant")], {"postgres": lambda ref: True},
                     {"postgres": lambda ref: False})
    assert not receipts[0].ok
    assert "qdrant" in receipts[0].detail


def test_every_store_is_reported_even_when_one_succeeds():
    """A partial erasure reported as success is the failure this exists to
    prevent."""
    deleters, confirmers, _live = stores({"row-1", "doc-1"})
    items = [item(store="postgres"), RetainedItem(
        "p-1", Purpose.DOCUMENT_STORAGE, TODAY, "vault", "doc-1")]
    deleters["vault"] = lambda ref: True            # lies
    receipts = erase(items, deleters, confirmers)
    assert receipts[0].ok
    assert not receipts[1].ok
    with pytest.raises(ErasureIncomplete, match="1 of 2"):
        assert_erased(receipts)


def test_a_raising_deleter_is_reported_not_swallowed():
    def boom(ref):
        raise ConnectionError("vault unreachable")

    receipts = erase([item()], {"postgres": boom}, {"postgres": lambda r: True})
    assert not receipts[0].ok
    assert "vault unreachable" in receipts[0].detail


def test_a_raising_confirmer_is_reported_not_treated_as_absent():
    def boom(ref):
        raise ConnectionError("index down")

    receipts = erase([item()], {"postgres": lambda r: True}, {"postgres": boom})
    assert not receipts[0].ok
    assert "could not confirm" in receipts[0].detail
