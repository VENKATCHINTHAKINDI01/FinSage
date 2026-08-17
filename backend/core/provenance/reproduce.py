"""Reproducibility and integrity — EVD-007.

Three questions an Evidence Pack has to survive, and they are not the same
question:

    1. Is this pack intact?          → the content hash still matches
    2. Can I get this answer again?  → replay under the SAME pinned rule pack
    3. Is it still right today?      → recompute under the CURRENT pack and diff

The third is the one that matters
---------------------------------
A pack issued in August is read by a CA in January, by which time the rule pack
may have been corrected. The wrong thing to do is recompute and quietly show a
different number — the reader has no way to tell they are looking at a revision.
The right thing is to show BOTH, labelled, with the rule-pack versions that
produced each. `diff_under()` does that and refuses to collapse the two.

Why the pin is a file hash and not a date
-----------------------------------------
`meta.verified_on` is a claim written inside the rule pack. A hash of the file's
bytes is a fact about it. Pinning the date means editing a rate without bumping
the date replays clean — integrity resting on whoever edited the YAML
remembering to change something else, which is not integrity. `TaxRuleset.version`
carries the fingerprint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.core.provenance.money import ZERO, Money
from backend.core.rules.loader import TaxRuleset, load_ruleset


class ReplayMismatch(Exception):
    """A pinned computation did not reproduce.

    Raised rather than returned because a pack that does not replay is not a
    pack with a caveat — it is either tampered with or the engine has changed
    under it, and both need a human.
    """


@dataclass(frozen=True, slots=True)
class Pin:
    """Everything needed to reproduce one computation, and nothing else.

    Deliberately does not include the OUTPUT. A pin that carried the answer
    could be replayed against itself and always agree; the point is to recompute
    from inputs and see whether the same answer comes back.
    """

    fy: str
    rule_pack_version: str
    rule_pack_verified_on: date
    input_hash: str
    content_hash: str
    pack_format_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "rule_pack_version": self.rule_pack_version,
            "rule_pack_verified_on": self.rule_pack_verified_on.isoformat(),
            "input_hash": self.input_hash,
            "content_hash": self.content_hash,
            "pack_format_version": self.pack_format_version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Pin:
        return cls(
            fy=raw["fy"],
            rule_pack_version=raw["rule_pack_version"],
            rule_pack_verified_on=date.fromisoformat(raw["rule_pack_verified_on"]),
            input_hash=raw["input_hash"],
            content_hash=raw["content_hash"],
            pack_format_version=raw["pack_format_version"],
        )


def pin_of(pack: Any, *, ruleset: TaxRuleset | None = None) -> Pin:
    """Take the pin from a built pack."""
    rs = ruleset or load_ruleset(pack.fy)
    from backend.core.provenance.evidence_pack import PACK_FORMAT_VERSION

    return Pin(
        fy=pack.fy,
        rule_pack_version=rs.version,
        rule_pack_verified_on=rs.verified_on,
        input_hash=pack.input_hash(),
        content_hash=pack.content_hash(),
        pack_format_version=PACK_FORMAT_VERSION,
    )


# ── 1 & 2: integrity and replay ─────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Verification:
    intact: bool
    rule_pack_unchanged: bool
    detail: str

    @property
    def fully_reproduced(self) -> bool:
        return self.intact and self.rule_pack_unchanged

    def to_dict(self) -> dict[str, Any]:
        return {
            "intact": self.intact,
            "rule_pack_unchanged": self.rule_pack_unchanged,
            "fully_reproduced": self.fully_reproduced,
            "detail": self.detail,
        }


def verify(pin: Pin, regenerated: Any, *, ruleset: TaxRuleset | None = None) -> Verification:
    """Check a regenerated pack against its pin.

    Separates the two failure modes, because they mean different things. A
    content-hash mismatch under an UNCHANGED rule pack means the inputs or the
    engine moved — a bug or tampering. A mismatch because the rule pack itself
    changed is expected and is the subject of `diff_under()`.
    """
    rs = ruleset or load_ruleset(pin.fy)
    pack_same = rs.version == pin.rule_pack_version
    hash_same = regenerated.content_hash() == pin.content_hash

    if hash_same and pack_same:
        detail = "Reproduced exactly under the same rule pack."
    elif not pack_same:
        detail = (
            f"The rule pack has changed since this pack was issued: pinned "
            f"{pin.rule_pack_version}, current {rs.version}. Any difference in "
            f"the figures is explained by that, not by an error — see the diff."
        )
    else:
        detail = (
            f"The rule pack is unchanged ({pin.rule_pack_version}) but the "
            f"computation no longer reproduces. Pinned content hash "
            f"{pin.content_hash[:16]}, regenerated "
            f"{regenerated.content_hash()[:16]}. This is a bug or tampering, "
            f"not a rule change."
        )
    return Verification(
        intact=hash_same, rule_pack_unchanged=pack_same, detail=detail,
    )


def assert_reproduces(pin: Pin, regenerated: Any, *, ruleset: TaxRuleset | None = None) -> None:
    """Strict form, for the guarantee the pack itself asserts."""
    result = verify(pin, regenerated, ruleset=ruleset)
    if not result.fully_reproduced:
        raise ReplayMismatch(result.detail)


# ── 3: what changed, marked as a change ─────────────────────────────────────

@dataclass(frozen=True, slots=True)
class FigureChange:
    label: str
    was: Money
    now: Money

    @property
    def delta(self) -> Money:
        return self.now - self.was

    @property
    def direction(self) -> str:
        if self.delta > ZERO:
            return "increased"
        if self.delta < ZERO:
            return "decreased"
        return "unchanged"

    def sentence(self) -> str:
        return (
            f"{self.label}: was {self.was}, now {self.now} "
            f"({self.direction} by {abs(self.delta)})."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "was": self.was.to_json(),
            "now": self.now.to_json(),
            "delta": self.delta.to_json(),
            "direction": self.direction,
        }


@dataclass(slots=True)
class RuleDiff:
    """The answer as issued, and the answer today, kept apart."""

    pinned_version: str
    current_version: str
    pinned_verified_on: date
    current_verified_on: date
    changes: list[FigureChange] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def rule_pack_changed(self) -> bool:
        return self.pinned_version != self.current_version

    @property
    def figures_changed(self) -> bool:
        return bool(self.changes or self.added or self.removed)

    def headline(self) -> str:
        """What the reader must be told before they look at any number."""
        if not self.rule_pack_changed:
            return (
                "The rules have not changed since this pack was issued. The "
                "figures below are the figures you were given."
            )
        if not self.figures_changed:
            return (
                f"The rule pack has been updated since this pack was issued "
                f"({self.pinned_version} → {self.current_version}), but none of "
                f"your figures changed."
            )
        return (
            f"⚠ The rule pack has been updated since this pack was issued "
            f"({self.pinned_version} → {self.current_version}) and "
            f"{len(self.changes)} figure(s) would now be different. The pack you "
            f"hold is the record of what was computed AT THE TIME; the values "
            f"below are what the same inputs give today. Both are shown, "
            f"because replacing one with the other would hide that anything "
            f"moved."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_pack_changed": self.rule_pack_changed,
            "figures_changed": self.figures_changed,
            "pinned": {
                "version": self.pinned_version,
                "verified_on": self.pinned_verified_on.isoformat(),
            },
            "current": {
                "version": self.current_version,
                "verified_on": self.current_verified_on.isoformat(),
            },
            "headline": self.headline(),
            "changes": [c.to_dict() for c in self.changes],
            "added_figures": self.added,
            "removed_figures": self.removed,
        }


_RATE_IN_LABEL = re.compile(r"\s*@\s*[\d.]+\s*%")
_AMOUNT_IN_LABEL = re.compile(r"₹[\d,]+")


def _match_key(label: str) -> str:
    """Match figures across rule packs by what they ARE, not what they say.

    Step labels embed the parameter they applied — "Health & Education Cess
    @ 4%". Keying a diff on the raw label therefore reports a rate change as a
    REMOVED "Cess @ 4%" plus an ADDED "Cess @ 5%", which is strictly less useful
    than "Cess: was ₹3,750, now ₹4,688" and buries the very thing the reader
    needs. Found by the test that expected a change and got two orphans.

    Rates and rupee amounts are stripped for matching only; the displayed label
    is untouched.
    """
    stripped = _RATE_IN_LABEL.sub("", label)
    stripped = _AMOUNT_IN_LABEL.sub("", stripped)
    return " ".join(stripped.split()).rstrip("—- ").strip().lower()


def diff_under(
    pinned_pack: Any,
    current_pack: Any,
    pin: Pin,
    *,
    current_ruleset: TaxRuleset | None = None,
) -> RuleDiff:
    """Compare the pack as issued against the same inputs computed today.

    Both packs must have been built from the SAME inputs — that is what makes a
    difference attributable to the rules rather than to the facts. `verify()`
    checks the input hash; this function reports the consequence.
    """
    rs = current_ruleset or load_ruleset(current_pack.fy)

    if pinned_pack.input_hash() != current_pack.input_hash():
        raise ReplayMismatch(
            "These two packs were built from different inputs, so a difference "
            "in the figures says nothing about the rules. Rebuild the current "
            "pack from the pinned inputs first."
        )

    was = {_match_key(e.label): (e.label, e.value) for e in pinned_pack.figures()}
    now = {_match_key(e.label): (e.label, e.value) for e in current_pack.figures()}

    changes = [
        # The CURRENT label is shown, because it is the one that describes
        # today's rule ("Cess @ 5%"), while the values name both sides.
        FigureChange(now[key][0], was[key][1], now[key][1])
        for key in was
        if key in now and was[key][1] != now[key][1]
    ]
    return RuleDiff(
        pinned_version=pin.rule_pack_version,
        current_version=rs.version,
        pinned_verified_on=pin.rule_pack_verified_on,
        current_verified_on=rs.verified_on,
        changes=changes,
        added=[now[k][0] for k in now if k not in was],
        removed=[was[k][0] for k in was if k not in now],
    )


__all__ = [
    "FigureChange",
    "Pin",
    "ReplayMismatch",
    "RuleDiff",
    "Verification",
    "assert_reproduces",
    "diff_under",
    "pin_of",
    "verify",
]
