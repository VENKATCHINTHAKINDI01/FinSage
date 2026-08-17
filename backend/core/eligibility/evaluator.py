"""Date-windowed eligibility evaluation — CORE-009.

Returns one of four outcomes, and the distinction between them is the point:

    ELIGIBLE            claim it
    INELIGIBLE          a condition fails, and we say which
    WINDOW_CLOSED       it existed, it doesn't now, here is the date
    INSUFFICIENT_DATA   we cannot tell, and here is exactly what is missing

Most systems collapse the last three into "nothing to show", which is how a
user ends up believing they have no options when really they were never asked
the right question. WINDOW_CLOSED in particular is surfaced to the user rather
than filtered out — it is the difference between a tool that looks empty and a
tool that looks like it knows what it is talking about.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.core.eligibility.benefit import BenefitAmount, compute_benefit
from backend.core.provenance.citation import Citation
from backend.core.provenance.money import ZERO, Money

RULES_FILE = Path(__file__).resolve().parent / "rules.yaml"


class Status(str, Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    WINDOW_CLOSED = "window_closed"
    INSUFFICIENT_DATA = "insufficient_data"

    @property
    def is_claimable(self) -> bool:
        return self is Status.ELIGIBLE

    @property
    def should_surface(self) -> bool:
        """Everything except a plain condition failure is worth telling the
        user about. A closed window is information; a missing field is a
        question we should have asked."""
        return self in (
            Status.ELIGIBLE,
            Status.WINDOW_CLOSED,
            Status.INSUFFICIENT_DATA,
        )


@dataclass(frozen=True, slots=True)
class Outcome:
    rule_id: str
    name: str
    status: Status
    max_benefit: Money = ZERO
    reason: str = ""
    closed_on: date | None = None
    missing_fields: tuple[str, ...] = ()
    citation: Citation | None = None
    benefit: BenefitAmount | None = None

    @property
    def amount_is_stated(self) -> bool:
        """False where the scheme exists but its amount is unconfirmed.

        Reported rather than defaulted. Rendering an unverified amount as ₹0
        reads as "this scheme is worth nothing to you", which is a false
        statement wearing the clothes of a computed one.
        """
        return self.benefit.stated if self.benefit else True

    @property
    def amount_missing_fields(self) -> tuple[str, ...]:
        """What we would need to ask to put a number on an entitlement the
        user already has. Separate from `missing_fields`, which is about
        whether they qualify at all."""
        return self.benefit.missing_fields if self.benefit else ()

    @property
    def amount_is_known(self) -> bool:
        return bool(self.benefit.computable) if self.benefit else True

    @property
    def message(self) -> str:
        phrase = self.benefit.phrase() if self.benefit else f"up to {self.max_benefit}"
        if self.status is Status.ELIGIBLE:
            return f"{self.name}: eligible, {phrase}."
        if self.status is Status.WINDOW_CLOSED:
            when = self.closed_on.strftime("%d %B %Y") if self.closed_on else "an earlier date"
            if not self.amount_is_stated:
                return (
                    f"{self.name}: the window closed on {when}. The amount is "
                    f"not stated because it has not been verified against an "
                    f"official source. {self.reason}".strip()
                )
            return (
                f"{self.name}: would have given you {phrase}, "
                f"but the window closed on {when}. {self.reason}".strip()
            )
        if self.status is Status.INSUFFICIENT_DATA:
            return (
                f"{self.name}: cannot be assessed without "
                f"{', '.join(self.missing_fields)}."
            )
        return f"{self.name}: not available — {self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "status": self.status.value,
            "max_benefit": self.max_benefit.to_json(),
            "reason": self.reason or None,
            "closed_on": self.closed_on.isoformat() if self.closed_on else None,
            "missing_fields": list(self.missing_fields),
            "citation": self.citation.to_dict() if self.citation else None,
            "amount_is_stated": self.amount_is_stated,
            "amount_is_known": self.amount_is_known,
            "amount_missing_fields": list(self.amount_missing_fields),
            "benefit": self.benefit.to_dict() if self.benefit else None,
            "message": self.message,
        }


@dataclass(slots=True)
class Facts:
    """What we know about the taxpayer and the transaction.

    A field that is absent is `None`, and absence produces INSUFFICIENT_DATA
    rather than a default. Defaulting `loan_sanction_date` to today would make
    every closed window silently reopen.
    """

    values: dict[str, Any] = field(default_factory=dict)
    as_of: date = field(default_factory=date.today)
    regime: str = "new"

    def get(self, name: str) -> Any:
        return self.values.get(name)

    def has(self, name: str) -> bool:
        return self.values.get(name) is not None


@lru_cache(maxsize=1)
def _load_rules() -> tuple[Mapping[str, Any], ...]:
    import yaml

    raw = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
    return tuple(raw.get("rules", []))


def _as_date(v: Any) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _check_conditions(
    rule: Mapping[str, Any], facts: Facts
) -> tuple[bool, str, list[str]]:
    """(passed, failure reason, missing field names)."""
    missing: list[str] = []
    for cond in rule.get("conditions", []):
        name = cond["field"]
        if not facts.has(name):
            missing.append(name)
            continue
        value = facts.get(name)

        if "equals" in cond and value != cond["equals"]:
            return False, f"{name} is {value}, must be {cond['equals']}", missing
        if "in" in cond and value not in cond["in"]:
            return False, f"{name} is {value}, must be one of {cond['in']}", missing
        if "at_least" in cond and value < cond["at_least"]:
            return False, f"{name} is {value}, must be at least {cond['at_least']}", missing
        if "at_most" in cond and value > cond["at_most"]:
            return False, f"{name} is {value}, must be at most {cond['at_most']}", missing

    return True, "", missing


def evaluate_rule(rule: Mapping[str, Any], facts: Facts) -> Outcome:
    rule_id = rule["id"]
    name = rule["name"]

    # Computed up front so every outcome carries it, including the closed and
    # ineligible ones — "would have given you ₹3,750" is the sentence that
    # makes a closed window land, and it needs the amount.
    benefit = compute_benefit(rule, facts)
    max_benefit = benefit.amount

    cit_raw = rule.get("citation", {})
    citation = (
        Citation(
            act="Income-tax Act, 2025",
            legacy_section=cit_raw.get("legacy_section"),
            section=cit_raw.get("section"),
            source_url=cit_raw.get("source_url"),
        )
        if (cit_raw.get("legacy_section") or cit_raw.get("section"))
        else None
    )

    # Structurally unavailable — e.g. PM E-DRIVE does not cover cars.
    if rule.get("always_ineligible"):
        ok, _reason, missing = _check_conditions(rule, facts)
        if missing:
            # A rule that can only ever say "no" is not worth asking the user a
            # question for. Absent facts mean it simply does not apply, rather
            # than INSUFFICIENT_DATA — otherwise a gold buyer gets prompted
            # about their vehicle category.
            return Outcome(rule_id, name, Status.INELIGIBLE, max_benefit,
                           reason="does not apply", citation=citation, benefit=benefit)
        if ok:
            return Outcome(rule_id, name, Status.INELIGIBLE, max_benefit,
                           reason=" ".join(rule.get("ineligible_reason", "").split()),
                           citation=citation, benefit=benefit)
        return Outcome(rule_id, name, Status.INELIGIBLE, max_benefit,
                       reason="does not apply", citation=citation, benefit=benefit)

    # Precedence matters, and the obvious orderings are both wrong.
    #
    #   Windows first  → a car buyer gets told the two-wheeler incentive expired.
    #   Regime first   → an EV buyer on the new regime is told "switch to old",
    #                    then discovers the 80EEB window shut in 2023 anyway.
    #
    # So: applicability first (does this rule concern me at all), then the
    # window (a permanent, terminal fact), then the regime (which the user can
    # actually change), then anything still unknown.
    ok, reason, missing = _check_conditions(rule, facts)
    if not ok:
        return Outcome(rule_id, name, Status.INELIGIBLE, max_benefit,
                       reason=reason, citation=citation, benefit=benefit)

    for window in rule.get("windows", []):
        field_name = window["field"]
        if not facts.has(field_name):
            return Outcome(
                rule_id, name, Status.INSUFFICIENT_DATA, max_benefit,
                missing_fields=(field_name,), citation=citation, benefit=benefit,
            )
        when = _as_date(facts.get(field_name))

        if "from" in window and when < _as_date(window["from"]):
            return Outcome(
                rule_id, name, Status.INELIGIBLE, max_benefit,
                reason=f"{field_name} {when} precedes the window opening on {window['from']}",
                citation=citation, benefit=benefit,
            )
        if "to" in window and when > _as_date(window["to"]):
            return Outcome(
                rule_id, name, Status.WINDOW_CLOSED, max_benefit,
                reason=" ".join(window.get("closed_message", "").split()),
                closed_on=_as_date(window["to"]),
                citation=citation, benefit=benefit,
            )

    regimes = rule.get("regimes")
    if regimes and facts.regime not in regimes:
        return Outcome(
            rule_id, name, Status.INELIGIBLE, max_benefit,
            reason=(
                f"available only under the {'/'.join(regimes)} regime; "
                f"you are on the {facts.regime} regime"
            ),
            citation=citation, benefit=benefit,
        )

    # A field the AMOUNT needs is deliberately NOT folded in here.
    #
    # Entitlement and quantum are different questions. "You qualify for the
    # two-wheeler incentive, and how much depends on your battery capacity" is
    # a true and useful sentence; collapsing it into INSUFFICIENT_DATA says
    # "we cannot tell whether you qualify", which is false. The missing field
    # still surfaces — through `benefit.missing_fields` and
    # `Outcome.amount_missing_fields` — so the targeted question still gets
    # asked, it is just asked about the right thing.
    if missing:
        return Outcome(rule_id, name, Status.INSUFFICIENT_DATA, max_benefit,
                       missing_fields=tuple(missing), citation=citation, benefit=benefit)

    return Outcome(rule_id, name, Status.ELIGIBLE, max_benefit, citation=citation, benefit=benefit)


def evaluate_all(facts: Facts, *, only: list[str] | None = None) -> list[Outcome]:
    """Evaluate every rule (or a named subset).

    Ordering puts what the user can act on first, then what they have lost,
    then what we need to ask about. Plain ineligibility comes last: it is the
    least useful and the most numerous.
    """
    rules = _load_rules()
    if only:
        wanted = {r.upper() for r in only}
        rules = tuple(r for r in rules if r["id"].upper() in wanted)

    outcomes = [evaluate_rule(r, facts) for r in rules]
    order = {
        Status.ELIGIBLE: 0,
        Status.WINDOW_CLOSED: 1,
        Status.INSUFFICIENT_DATA: 2,
        Status.INELIGIBLE: 3,
    }
    return sorted(outcomes, key=lambda o: (order[o.status], o.rule_id))


def claimable(facts: Facts) -> list[Outcome]:
    return [o for o in evaluate_all(facts) if o.status.is_claimable]


def closed_windows(facts: Facts) -> list[Outcome]:
    """What the user has missed. Shown deliberately — see the module docstring."""
    return [o for o in evaluate_all(facts) if o.status is Status.WINDOW_CLOSED]


def total_claimable(outcomes: list[Outcome]) -> tuple[Money, list[Outcome]]:
    """The sum, and everything the sum could not include.

    Returned as a pair for the same reason `facts_for_costing` is (PRC-010):
    a function returning only the total would let a caller print a confident
    figure that quietly omits every benefit whose amount is unverified or
    depends on a field nobody has supplied. Here the omission has to be handled
    at the call site, and the natural handling is to show it.
    """
    total = ZERO
    unquantified: list[Outcome] = []
    for o in outcomes:
        if o.status is not Status.ELIGIBLE:
            continue
        if o.amount_is_stated and o.amount_is_known:
            total = total + o.max_benefit
        else:
            unquantified.append(o)
    return total, unquantified
