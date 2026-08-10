"""Citations that survive the 1961 → 2025 Act transition.

The Income-tax Act, 2025 came into force on 1 April 2026 and renumbered
essentially every section — 819 sections became 536. Policy barely moved; the
citations all did.

So for FY 2026-27 onward the product must speak the new numbering, while users,
CAs, every article written before 2026 and decades of muscle memory all speak
the old one. A citation therefore carries both, and renders both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class Citation:
    """Where a number's authority comes from.

    `section` is the Income-tax Act 2025 reference where known.
    `legacy_section` is the 1961 Act equivalent. At least one must be present.
    """

    act: str = "Income-tax Act, 2025"
    section: str | None = None
    legacy_section: str | None = None
    fy: str | None = None
    source_url: str | None = None
    retrieved_at: date | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.section and not self.legacy_section:
            raise ValueError("a citation needs at least one section reference")

    @property
    def display(self) -> str:
        """Both numbering schemes, because during the transition the reader
        may know either one and will not thank you for guessing."""
        if self.section and self.legacy_section:
            body = f"s.{self.section} (formerly s.{self.legacy_section})"
        else:
            body = f"s.{self.section or self.legacy_section}"

        parts = [self.act, body]
        if self.fy:
            parts.append(f"FY {self.fy}")
        return " · ".join(parts)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "act": self.act,
            "section": self.section,
            "legacy_section": self.legacy_section,
            "fy": self.fy,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "note": self.note or None,
            "display": self.display,
        }


@dataclass(frozen=True, slots=True)
class SourceRef:
    """A non-statutory source — a government portal, a notification, a circular.

    `retrieved_at` is mandatory. An undated figure cannot be shown to a user:
    "GST is 5%" is only true as of a date, and the whole GST schedule was
    restructured in September 2025.
    """

    url: str
    tier: int                      # 1 official · 2 primary commercial · 3 aggregator
    retrieved_at: date
    title: str = ""
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if self.tier not in (1, 2, 3):
            raise ValueError(f"source tier must be 1, 2 or 3, got {self.tier}")

    @property
    def may_drive_a_figure(self) -> bool:
        """Tier 3 (marketplaces, review sites, news) can add context but must
        never produce a number in a cost breakdown."""
        return self.tier <= 2

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "tier": self.tier,
            "title": self.title,
            "retrieved_at": self.retrieved_at.isoformat(),
            "content_hash": self.content_hash,
            "may_drive_a_figure": self.may_drive_a_figure,
        }


@dataclass(frozen=True, slots=True)
class SectionAlias:
    """One entry in the 1961 ↔ 2025 mapping."""

    legacy: str
    current: str
    description: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
