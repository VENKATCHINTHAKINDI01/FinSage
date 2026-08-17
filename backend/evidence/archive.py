"""Source archival and access dating — EVD-004.

The problem
-----------
A citation is a URL and a date. Both rot. The page changes, the notification is
superseded, the URL 404s — and a pack issued last August now points at something
that says something else. "We read this on 9 August 2026" is only checkable if
what was read was kept.

What is stored, and what is not
-------------------------------
The EXTRACT, not the page. Archiving whole government portals would grow without
bound and most of the bytes are navigation. What matters is the sentence the
figure came from, its hash, and when it was read. A few hundred bytes per
citation instead of a few hundred kilobytes.

Detecting change without re-reading everything
----------------------------------------------
The extract's hash is the tripwire. Re-fetch, hash, compare: unchanged means the
cached fact stands, changed means every fact that cited it is flagged for review
— not silently recomputed. Silently recomputing is how a user's answer changes
between two readings of the same document with no explanation.

The invariant this shares with the ledger
------------------------------------------
No undated source may appear in user-facing output. `ArchivedSource` refuses to
construct without `retrieved_at`, for the same reason `LedgerEntry` refuses
without `verified_on`: a figure whose provenance is unknown must fail loudly in
the engine rather than render as a plausible number.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

MAX_EXTRACT_CHARS = 4_000


class UndatedSource(Exception):
    """A source was archived without the date it was read."""


def extract_hash(text: str) -> str:
    """Hash the NORMALISED extract.

    Whitespace and case are stripped first, so a page reflowing its HTML does
    not read as a policy change. Only the substance is being fingerprinted —
    otherwise the tripwire fires constantly and stops being watched.
    """
    normalised = " ".join(text.split()).lower()
    return hashlib.sha256(normalised.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ArchivedSource:
    url: str
    extract: str
    retrieved_at: date
    tier: int
    title: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.retrieved_at:
            raise UndatedSource(
                f"{self.url} was archived without a retrieval date. An undated "
                f"source cannot appear in user-facing output — 'GST is 5%' is "
                f"only true as of a date."
            )
        if self.tier not in (1, 2, 3):
            raise ValueError(f"source tier must be 1, 2 or 3, got {self.tier}")
        if not self.extract.strip():
            raise ValueError(
                f"{self.url} was archived with an empty extract. Storing the "
                f"URL alone is what this feature exists to stop."
            )
        if not self.content_hash:
            object.__setattr__(self, "content_hash", extract_hash(self.extract))
        if len(self.extract) > MAX_EXTRACT_CHARS:
            object.__setattr__(
                self, "extract", self.extract[:MAX_EXTRACT_CHARS] + " …[truncated]"
            )

    @property
    def may_drive_a_figure(self) -> bool:
        """Tier 3 — marketplaces, review sites, news — can add context but must
        never produce a number in a cost breakdown."""
        return self.tier <= 2

    def age_days(self, today: date) -> int:
        return (today - self.retrieved_at).days

    def as_of(self) -> str:
        """The phrase that goes next to every citation."""
        return f"as of {self.retrieved_at.strftime('%d %B %Y')}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title or None,
            "tier": self.tier,
            "may_drive_a_figure": self.may_drive_a_figure,
            "retrieved_at": self.retrieved_at.isoformat(),
            "as_of": self.as_of(),
            "content_hash": self.content_hash,
            "extract": self.extract,
        }


@dataclass(frozen=True, slots=True)
class ChangeReport:
    url: str
    changed: bool
    archived_hash: str
    current_hash: str
    checked_at: date
    affected_facts: tuple[str, ...] = ()

    def message(self) -> str:
        if not self.changed:
            return (
                f"{self.url} is unchanged since it was archived. The cached "
                f"figures stand."
            )
        return (
            f"⚠ {self.url} has changed since it was read. "
            f"{len(self.affected_facts)} cached fact(s) cite it and are flagged "
            f"for review. They have NOT been recomputed — a figure that moves "
            f"without explanation is worse than one that is stale and labelled."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "changed": self.changed,
            "archived_hash": self.archived_hash,
            "current_hash": self.current_hash,
            "checked_at": self.checked_at.isoformat(),
            "affected_facts": list(self.affected_facts),
            "message": self.message(),
        }


class ArchiveBackend(Protocol):
    def put(self, key: str, payload: dict[str, Any]) -> None: ...
    def get(self, key: str) -> dict[str, Any] | None: ...
    def all_keys(self) -> list[str]: ...


@dataclass(slots=True)
class MemoryArchive:
    """In-process backend. Not a production fallback — see `DocumentVault`."""

    records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def put(self, key: str, payload: dict[str, Any]) -> None:
        self.records[key] = payload

    def get(self, key: str) -> dict[str, Any] | None:
        return self.records.get(key)

    def all_keys(self) -> list[str]:
        return sorted(self.records)


@dataclass(slots=True)
class SourceArchive:
    """Archived extracts, and the facts that depend on them."""

    backend: ArchiveBackend
    _citing: dict[str, set[str]] = field(default_factory=dict)

    @staticmethod
    def key_for(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:32]

    def archive(
        self,
        url: str,
        extract: str,
        *,
        tier: int,
        retrieved_at: date | None = None,
        title: str = "",
        cited_by: str | None = None,
    ) -> ArchivedSource:
        source = ArchivedSource(
            url=url,
            extract=extract,
            retrieved_at=retrieved_at or datetime.now(timezone.utc).date(),
            tier=tier,
            title=title,
        )
        self.backend.put(self.key_for(url), source.to_dict())
        if cited_by:
            self._citing.setdefault(url, set()).add(cited_by)
        return source

    def get(self, url: str) -> ArchivedSource | None:
        raw = self.backend.get(self.key_for(url))
        if raw is None:
            return None
        return ArchivedSource(
            url=raw["url"],
            extract=raw["extract"],
            retrieved_at=date.fromisoformat(raw["retrieved_at"]),
            tier=raw["tier"],
            title=raw.get("title") or "",
            content_hash=raw["content_hash"],
        )

    def note_citation(self, url: str, fact: str) -> None:
        self._citing.setdefault(url, set()).add(fact)

    def facts_citing(self, url: str) -> tuple[str, ...]:
        return tuple(sorted(self._citing.get(url, ())))

    def check(self, url: str, current_text: str, *, today: date) -> ChangeReport:
        """Compare a fresh read against what was archived.

        Never recomputes. A changed source flags the facts that cite it and
        leaves them alone — the decision to revise is a human one, and a figure
        that moves between two readings with no explanation destroys the trust
        the whole evidence layer exists to build.
        """
        archived = self.get(url)
        if archived is None:
            raise KeyError(f"{url} has not been archived, so nothing to compare")
        current = extract_hash(current_text)
        changed = current != archived.content_hash
        return ChangeReport(
            url=url,
            changed=changed,
            archived_hash=archived.content_hash,
            current_hash=current,
            checked_at=today,
            affected_facts=self.facts_citing(url) if changed else (),
        )

    def stale(self, today: date, window_days: int = 180) -> list[ArchivedSource]:
        out = []
        for key in self.backend.all_keys():
            raw = self.backend.get(key)
            if raw and (today - date.fromisoformat(raw["retrieved_at"])).days > window_days:
                out.append(self.get(raw["url"]))
        return [s for s in out if s is not None]


__all__ = [
    "MAX_EXTRACT_CHARS",
    "ArchivedSource",
    "ChangeReport",
    "MemoryArchive",
    "SourceArchive",
    "UndatedSource",
    "extract_hash",
]
