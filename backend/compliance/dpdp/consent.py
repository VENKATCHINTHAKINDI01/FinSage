"""Consent, purpose limitation, retention and erasure — PRD-001.

Handling income figures and PAN makes this a Data Fiduciary under the Digital
Personal Data Protection Act 2023. v1's README claimed compliance with nothing
behind it, which is worse than claiming nothing: it is a representation to
users about how their data is handled.

Four structural decisions, and each one is a way the usual implementation
quietly fails.

1. Consent is per PURPOSE and against a NOTICE VERSION
-------------------------------------------------------
A single `consent: true` column cannot express s.6 — consent must be "free,
specific, informed" and limited to the specified purpose. One flag means
agreeing to file your return also agreed to marketing.

And a consent recorded against version 1 of the notice does NOT carry to
version 3. If the notice changed, the person was informed of something else,
and "informed" is the word the Act uses. So a notice version bump invalidates
consents given against the old text for any purpose whose description changed
— rather than silently inheriting them, which is the common shortcut and the
one that makes the whole record worthless as evidence.

2. Withdrawal is the same shape as granting
---------------------------------------------
s.6(6): withdrawal must be as easy as giving. That is not a UI aspiration, it
is testable: `withdraw()` takes the same arguments as `grant()` and needs no
extra evidence, no reason, and no second confirmation. A test asserts the
signatures match.

3. Retention is a job, not a paragraph
---------------------------------------
A retention policy in a PDF deletes nothing. `due_for_erasure` is pure and
returns exactly what a scheduled job must delete today, so the policy is
executable and the test is the audit.

4. Erasure must be VERIFIED, per store
----------------------------------------
Personal data here lives in Postgres, an encrypted document vault and a vector
store. A delete that reports success without confirming each is worse than no
delete at all — it produces a compliance record asserting something untrue. So
`erase` returns a receipt per store and a store that cannot CONFIRM absence is
a failure, not a warning.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any


class ConsentError(Exception):
    """A processing attempt with no lawful basis."""


class ErasureIncomplete(Exception):
    """At least one store could not confirm the data is gone."""


class Purpose(str, Enum):
    """Every purpose the product processes personal data for.

    A closed set, because s.6 requires the purpose to be SPECIFIED. A free-text
    purpose is not specified — it is whatever the caller typed that day.
    """

    TAX_COMPUTATION = "tax_computation"
    ITR_FILING = "itr_filing"
    DOCUMENT_STORAGE = "document_storage"
    PROCUREMENT_ADVICE = "procurement_advice"
    PRODUCT_ANALYTICS = "product_analytics"
    MARKETING = "marketing"

    @property
    def is_necessary_for_service(self) -> bool:
        """Whether refusing it means the product cannot function.

        The distinction matters because s.7(a) allows processing for the
        purpose the person voluntarily provided data for, while analytics and
        marketing need their own consent and must be refusable without losing
        the service. Bundling them is the thing the Act calls out.
        """
        return self in (
            Purpose.TAX_COMPUTATION,
            Purpose.ITR_FILING,
            Purpose.DOCUMENT_STORAGE,
        )


# How long each purpose justifies keeping the data, from the last activity.
# s.8(7): erase when the purpose is no longer being served.
#
# Tax records are the long one and for a reason that is not our choice: a
# return can be revised or reopened, and ITR-U runs 48 months from the end of
# the assessment year. Deleting at 12 months would leave a user unable to
# answer a notice about their own filing.
RETENTION_DAYS: dict[Purpose, int] = {
    Purpose.TAX_COMPUTATION: 8 * 365,
    Purpose.ITR_FILING: 8 * 365,
    Purpose.DOCUMENT_STORAGE: 8 * 365,
    Purpose.PROCUREMENT_ADVICE: 2 * 365,
    Purpose.PRODUCT_ANALYTICS: 400,
    Purpose.MARKETING: 400,
}


@dataclass(frozen=True, slots=True)
class Notice:
    """The itemised notice under s.5, and its version.

    `purpose_text` is per purpose because the notice must be itemised. A single
    blob cannot say which description changed, and that is what decides whether
    an existing consent survives a new version.
    """

    version: str
    published_on: date
    purpose_text: Mapping[Purpose, str]
    grievance_officer: str
    grievance_contact: str

    def describes(self, purpose: Purpose) -> str:
        text = self.purpose_text.get(purpose, "")
        if not text:
            raise ConsentError(
                f"notice {self.version} does not describe {purpose.value}. "
                f"Consent cannot be informed for a purpose the notice never "
                f"mentioned."
            )
        return text


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    principal_id: str
    purpose: Purpose
    notice_version: str
    given_on: date
    withdrawn_on: date | None = None

    @property
    def is_live(self) -> bool:
        return self.withdrawn_on is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "purpose": self.purpose.value,
            "notice_version": self.notice_version,
            "given_on": self.given_on.isoformat(),
            "withdrawn_on": (
                self.withdrawn_on.isoformat() if self.withdrawn_on else None
            ),
            "live": self.is_live,
        }


@dataclass(slots=True)
class ConsentLedger:
    """Append-only. A withdrawal supersedes, it does not erase the record.

    Deleting the consent row on withdrawal destroys the evidence that consent
    was ever held, which is exactly what a Data Fiduciary must be able to show.
    """

    records: list[ConsentRecord] = field(default_factory=list)

    def grant(
        self, principal_id: str, purpose: Purpose, notice: Notice, on: date,
    ) -> ConsentRecord:
        notice.describes(purpose)          # raises if the notice is silent
        record = ConsentRecord(
            principal_id=principal_id, purpose=purpose,
            notice_version=notice.version, given_on=on,
        )
        self.records.append(record)
        return record

    # `live_for` was here and has been removed. It answered the same question
    # as `require_consent` with weaker semantics — it returned the record on a
    # version match and None otherwise, without consulting the registry — and
    # nothing called it. Mutation-testing found it: breaking its version check
    # failed no test, because there was no caller to break. Two functions
    # answering one question differently is a trap for whoever writes the third
    # caller, so the unused one is gone rather than tested.

    def withdraw(
        self, principal_id: str, purpose: Purpose, notice: Notice, on: date,
    ) -> None:
        """Same arguments as `grant`, deliberately — s.6(6).

        No reason required, no second confirmation, no extra evidence. The
        symmetry is asserted by a test over the signatures, because "as easy to
        withdraw as to give" is a property of the interface, not a promise in a
        policy document.
        """
        for i, record in enumerate(self.records):
            if (
                record.principal_id == principal_id
                and record.purpose is purpose
                and record.is_live
            ):
                self.records[i] = ConsentRecord(
                    principal_id=record.principal_id, purpose=record.purpose,
                    notice_version=record.notice_version,
                    given_on=record.given_on, withdrawn_on=on,
                )


@dataclass(slots=True)
class NoticeRegistry:
    """Every version ever published, so a stale consent can be re-checked."""

    versions: dict[str, Notice] = field(default_factory=dict)

    def publish(self, notice: Notice) -> None:
        self.versions[notice.version] = notice

    def carries_over(
        self, record: ConsentRecord, current: Notice,
    ) -> bool:
        """Whether a consent given against an older notice still holds.

        True only when the wording for that specific purpose is unchanged. A
        version bump that reworded an unrelated purpose does not invalidate
        this one — invalidating everything on every edit trains people to click
        through, which is its own harm.
        """
        old = self.versions.get(record.notice_version)
        if old is None:
            return False
        try:
            return old.describes(record.purpose) == current.describes(record.purpose)
        except ConsentError:
            return False


def require_consent(
    principal_id: str, purpose: Purpose, ledger: ConsentLedger,
    notice: Notice, registry: NoticeRegistry,
) -> ConsentRecord:
    """The check every processing path must pass. Raises, never warns."""
    for record in reversed(ledger.records):
        if (
            record.principal_id != principal_id
            or record.purpose is not purpose
            or not record.is_live
        ):
            continue
        if record.notice_version == notice.version or registry.carries_over(
            record, notice,
        ):
            return record
        raise ConsentError(
            f"{principal_id} consented to {purpose.value} under notice "
            f"{record.notice_version}, and the description changed in "
            f"{notice.version}. Consent must be re-taken — they agreed to "
            f"different words."
        )
    raise ConsentError(
        f"no live consent for {purpose.value}. Processing without one has no "
        f"lawful basis under s.6."
    )


# ── retention ───────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class RetainedItem:
    principal_id: str
    purpose: Purpose
    last_activity: date
    store: str
    ref: str

    def erase_on(self) -> date:
        return self.last_activity + timedelta(days=RETENTION_DAYS[self.purpose])


def due_for_erasure(
    items: Sequence[RetainedItem], today: date, ledger: ConsentLedger | None = None,
) -> list[RetainedItem]:
    """What a scheduled job must delete today.

    Two triggers, both from s.8(7): the retention period has run, OR consent
    was withdrawn. A withdrawal makes data due IMMEDIATELY rather than at the
    end of its retention window — continuing to hold it because the clock has
    not run is processing without a basis.
    """
    withdrawn: set[tuple[str, Purpose]] = set()
    if ledger is not None:
        for record in ledger.records:
            if not record.is_live:
                withdrawn.add((record.principal_id, record.purpose))
        for record in ledger.records:
            if record.is_live:
                withdrawn.discard((record.principal_id, record.purpose))

    return [
        item for item in items
        if item.erase_on() <= today
        or (item.principal_id, item.purpose) in withdrawn
    ]


# ── erasure, verified ───────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ErasureReceipt:
    store: str
    ref: str
    deleted: bool
    confirmed_absent: bool
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.deleted and self.confirmed_absent


def erase(
    items: Sequence[RetainedItem],
    deleters: Mapping[str, Callable[[str], bool]],
    confirmers: Mapping[str, Callable[[str], bool]],
) -> list[ErasureReceipt]:
    """Delete, then CHECK, per store.

    A delete that reports success without confirming is worse than no delete:
    it produces a compliance record asserting something untrue, and the record
    is what a regulator reads. A store with no confirmer is a failure rather
    than an assumption — "we have no way to check" is not "it is gone".
    """
    receipts: list[ErasureReceipt] = []
    for item in items:
        deleter = deleters.get(item.store)
        confirmer = confirmers.get(item.store)
        if deleter is None:
            receipts.append(ErasureReceipt(
                item.store, item.ref, False, False,
                f"no deleter registered for store {item.store!r}; data cannot "
                f"be erased from a store nothing knows how to reach.",
            ))
            continue
        if confirmer is None:
            receipts.append(ErasureReceipt(
                item.store, item.ref, False, False,
                f"no confirmer registered for store {item.store!r}. An "
                f"unverifiable deletion is not a deletion — it is a claim.",
            ))
            continue

        try:
            deleted = bool(deleter(item.ref))
        except Exception as exc:
            receipts.append(ErasureReceipt(
                item.store, item.ref, False, False, f"delete failed: {exc}",
            ))
            continue

        try:
            still_there = bool(confirmer(item.ref))
        except Exception as exc:
            receipts.append(ErasureReceipt(
                item.store, item.ref, deleted, False,
                f"could not confirm absence: {exc}",
            ))
            continue

        receipts.append(ErasureReceipt(
            item.store, item.ref, deleted, not still_there,
            "" if deleted and not still_there else "still present after delete",
        ))
    return receipts


def assert_erased(receipts: Sequence[ErasureReceipt]) -> None:
    """The strict form, for the endpoint that tells a user their data is gone.

    Raises rather than returning, because a partial erasure reported as success
    is the failure this whole module exists to prevent.
    """
    failed = [r for r in receipts if not r.ok]
    if failed:
        raise ErasureIncomplete(
            f"{len(failed)} of {len(receipts)} deletions could not be "
            f"confirmed:\n  - "
            + "\n  - ".join(f"{r.store}/{r.ref}: {r.detail}" for r in failed)
        )


__all__ = [
    "RETENTION_DAYS",
    "ConsentError",
    "ConsentLedger",
    "ConsentRecord",
    "ErasureIncomplete",
    "ErasureReceipt",
    "Notice",
    "NoticeRegistry",
    "Purpose",
    "RetainedItem",
    "assert_erased",
    "due_for_erasure",
    "erase",
    "require_consent",
]
