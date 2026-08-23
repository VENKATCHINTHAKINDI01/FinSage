"""Section alias resolution — CORE-002.

The Income-tax Act, 2025 renumbered essentially every section on 1 April 2026.
Users know the old numbers; the department now uses the new ones. So citations
carry both.

Where the mapping has not yet been verified line by line against the published
concordance, `cite()` keeps the legacy number as primary and marks the new one
provisional. Confidently printing a section number we have not checked is the
exact failure this project exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.core.provenance.citation import Citation

ALIAS_FILE = Path(__file__).resolve().parent / "aliases_1961_to_2025.yaml"


@dataclass(frozen=True, slots=True)
class Alias:
    legacy: str
    current: str
    description: str
    verified: bool


@dataclass(frozen=True, slots=True)
class AliasMap:
    applies_from_fy: str
    by_legacy: dict[str, Alias]
    by_current: dict[str, Alias]

    def resolve(self, section: str) -> Alias | None:
        return self.by_legacy.get(section) or self.by_current.get(section)

    def applies_to(self, fy: str) -> bool:
        """Only translate for years actually governed by the 2025 Act."""
        return fy >= self.applies_from_fy


@lru_cache(maxsize=1)
def load_aliases() -> AliasMap:
    import yaml

    raw = yaml.safe_load(ALIAS_FILE.read_text(encoding="utf-8"))
    by_legacy: dict[str, Alias] = {}
    by_current: dict[str, Alias] = {}

    for entry in raw.get("aliases", []):
        alias = Alias(
            legacy=str(entry["legacy"]),
            current=str(entry["current"]),
            description=entry.get("description", ""),
            verified=entry.get("confidence") == "verified",
        )
        by_legacy[alias.legacy] = alias
        if alias.current != "singular":
            by_current[alias.current] = alias

    return AliasMap(
        applies_from_fy=str(raw.get("applies_from_fy", "2026-27")),
        by_legacy=by_legacy,
        by_current=by_current,
    )


def cite(
    legacy_section: str,
    fy: str,
    *,
    source_url: str | None = None,
    note: str = "",
) -> Citation:
    """Build a citation from a 1961-Act section number.

    For FY 2026-27 onward this attaches the 2025-Act number too, so the
    rendered citation reads "s.156 (formerly s.87A)". For earlier years, and
    for entries not yet verified, the legacy number stands alone.
    """
    amap = load_aliases()
    alias = amap.by_legacy.get(legacy_section)

    current: str | None = None
    extra = note
    if alias and amap.applies_to(fy) and alias.current != "singular":
        if alias.verified and alias.current == "OMITTED":
            # The official navigator records no 2025 counterpart. Rendering
            # "s.OMITTED" would be worse than rendering nothing, so the legacy
            # number stands alone and the absence is stated in words.
            extra = (
                f"{note + ' ' if note else ''}"
                f"The CBDT concordance records no Income-tax Act 2025 "
                f"counterpart for s.{legacy_section}. It is cited under the "
                f"1961 numbering until the position is confirmed against the "
                f"2025 Act itself."
            ).strip()
        elif alias.verified and not alias.current.isdigit():
            # Not a section at all — 10(13A) (HRA) moved to Schedule III. A
            # renderer that prefixes "s." to this produces a citation to a
            # provision that does not exist.
            extra = (
                f"{note + ' ' if note else ''}"
                f"Under the Income-tax Act 2025 this is not a section: it is "
                f"{alias.current}."
            ).strip()
        elif alias.verified:
            current = alias.current
        else:
            # Provisional: surfaced as a note, never presented as fact.
            extra = (
                f"{note + ' ' if note else ''}"
                f"Income-tax Act 2025 equivalent is provisionally s.{alias.current}; "
                f"mapping not yet verified against the published concordance."
            ).strip()

    return Citation(
        act="Income-tax Act, 2025" if amap.applies_to(fy) else "Income-tax Act, 1961",
        section=current,
        legacy_section=legacy_section,
        fy=fy,
        source_url=source_url,
        note=extra,
    )


def unverified_aliases() -> list[str]:
    """Feeds the CORE-002 acceptance criteria: the feature cannot move to
    `verified` while this is non-empty."""
    return sorted(a.legacy for a in load_aliases().by_legacy.values() if not a.verified)
