"""Free text to a structured item and a buyer — PRC-001.

The one job, and the one thing it must not do
----------------------------------------------
A language model is good at reading "I'm a govt employee in Bangalore looking
at a 3kW rooftop solar setup" and producing structure. It is not permitted to
produce any figure that reaches a computation. This module is the boundary, and
the boundary is enforced three ways rather than asked for.

**`ResolvedItem` has no Money field.** Not a validated one, not an optional
one — the dataclass has no attribute of that type, so there is nowhere for a
rupee amount to land. A test asserts it over the annotations, because the
guarantee should survive someone adding a convenient `estimated_price` in a
hurry.

**The vocabulary is closed.** A family or a buyer profile outside the declared
set becomes a QUESTION, never the nearest match. A resolver that quietly maps
an unrecognised phrase onto a known category is how a tractor gets costed as a
car — silently, with a plausible number at the end of it.

**A numeric spec is a suggestion, never an answer.** Battery capacity
multiplies the per-kWh incentive; system capacity picks the PM-Surya Ghar tier.
A model that guesses "probably 3 kW" has produced a rupee figure by proxy. So
those come back as a question with the model's suggestion ATTACHED, for the
buyer to confirm off the spec sheet, and the suggestion never enters the
resolved item on its own.

Missing means ask, not assume
------------------------------
`state` is the sharpest case. Road tax and stamp duty are state levies, so a
defaulted state is not a small imprecision — it is a wrong answer that looks
right, and the buyer has no way to tell. Every critical field absent from the
extraction produces a targeted question naming what it is for.

The extractor is injected
--------------------------
Same shape as `SearchFn` in PRC-011. The model never appears in this module's
imports, so the resolver is testable without one and the choice of model stays
out of the costing path.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields
from typing import Any

# (free text) -> a flat dict of string values. Deliberately not typed as
# anything richer: whatever the model returns is untrusted input to be
# validated, and a typed return would imply it had already been checked.
ExtractFn = Callable[[str], Mapping[str, Any]]

_LOOKS_LIKE_MONEY = re.compile(
    r"(?:₹|\bRs\.?\b|\bINR\b)|(?:\b\d[\d,]*\s*(?:lakh|lac|crore|cr)\b)",
    re.IGNORECASE,
)
_LOOKS_LIKE_RATE = re.compile(r"\d\s*(?:%|per\s*cent|percent)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ResolvedItem:
    """What is being bought, by whom, where.

    Every field is a string or a mapping of strings. There is deliberately no
    price, no amount and no Money — see the module docstring. `specs` holds
    only values the buyer confirmed or that arrived from an admitted fact.
    """

    family: str
    category: str
    state: str
    buyer_profile: str
    use_case: str = ""
    specs: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "category": self.category,
            "state": self.state,
            "buyer_profile": self.buyer_profile,
            "use_case": self.use_case,
            "specs": dict(self.specs),
        }


@dataclass(frozen=True, slots=True)
class Question:
    """Something to ask, and what it is for.

    `why` is not decoration. A user asked for their battery capacity with no
    reason given will guess; told it decides the incentive amount, they go and
    look it up.
    """

    field_name: str
    ask: str
    why: str
    options: tuple[str, ...] = ()
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field_name,
            "ask": self.ask,
            "why": self.why,
            "options": list(self.options),
            "suggestion": self.suggestion or None,
        }


@dataclass(frozen=True, slots=True)
class Resolution:
    """What is known so far, and what is still needed.

    `known` carries the fields that DID validate on an incomplete pass. Without
    it, answering one question would throw away everything the first pass got
    right and the user would be asked the same things again — which is how a
    clarifying question becomes an interrogation.
    """

    item: ResolvedItem | None
    questions: tuple[Question, ...] = ()
    refused: tuple[str, ...] = ()
    known: Mapping[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.item is not None and not self.questions

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item.to_dict() if self.item else None,
            "complete": self.complete,
            "questions": [q.to_dict() for q in self.questions],
            "refused": list(self.refused),
            "known": dict(self.known),
        }


# ── validation ──────────────────────────────────────────────────────────────

def looks_like_a_figure(value: Any) -> bool:
    """Whether a model has slipped a rupee amount or a rate into a slot.

    Bare digits are NOT caught here and should not be: "3kW" and "5 seats" are
    legitimate structure. What is caught is the shape of a costing input — a
    currency mark, a scale word, a percentage — which has no business coming
    out of an extractor at all.
    """
    text = str(value)
    return bool(_LOOKS_LIKE_MONEY.search(text) or _LOOKS_LIKE_RATE.search(text))


def resolve(
    text: str,
    extract: ExtractFn,
    *,
    cfg: Mapping[str, Any],
    buyer_profiles: tuple[str, ...],
    known_categories: tuple[str, ...] = (),
) -> Resolution:
    """Structure from free text, with everything unproven turned into a question."""
    rules = cfg["item_resolver"]
    raw = dict(extract(text) or {})

    # ── 1. anything shaped like a figure is dropped, loudly ─────────────────
    refused: list[str] = []
    for key, value in list(raw.items()):
        if looks_like_a_figure(value):
            refused.append(
                f"{key}={value!r} — an extractor may produce structure, not "
                f"figures. A rupee amount or a rate arriving from a language "
                f"model has no provenance beyond the model, so it is dropped "
                f"rather than carried into a cost breakdown."
            )
            raw.pop(key)

    questions: list[Question] = []

    # ── 2. closed vocabularies ──────────────────────────────────────────────
    families = tuple(rules["families"])
    family = _checked(
        raw.get("family"), families, "family",
        "Which of these is it?",
        "The family decides which schemes and which cost lines apply at all.",
        questions,
    )
    profile = _checked(
        raw.get("buyer_profile"), buyer_profiles, "buyer_profile",
        "Who is buying?",
        "The same item gives a different answer to a government employee, a "
        "farmer and a GST-registered business.",
        questions,
    )

    category = raw.get("category")
    if category and known_categories and category not in known_categories:
        questions.append(Question(
            "category",
            f"We do not have a GST category for {category!r}. Which is closest?",
            "The GST rate is looked up by category, and mapping an unknown "
            "phrase onto the nearest known one is how a tractor gets costed "
            "as a car.",
            options=known_categories,
            suggestion=str(category),
        ))
        category = None
    elif not category:
        questions.append(Question(
            "category", "What exactly is being bought?",
            "The GST rate is looked up by category.",
            options=known_categories,
        ))

    state = raw.get("state")
    if not state:
        questions.append(Question(
            "state", "Which state will it be registered or bought in?",
            "Road tax and stamp duty are state levies. A defaulted state is "
            "not a small imprecision — it is a wrong answer that looks right.",
        ))

    # ── 3. numeric specs are suggestions ────────────────────────────────────
    specs: dict[str, str] = {}
    confirmable = rules["confirmable_specs"]
    for name, meta in confirmable.items():
        if name not in raw:
            continue
        questions.append(Question(
            name, str(meta["ask"]), " ".join(str(meta["why"]).split()),
            suggestion=str(raw[name]),
        ))

    for key, value in raw.items():
        if key in confirmable or key in (
            "family", "category", "state", "buyer_profile", "use_case",
        ):
            continue
        specs[key] = str(value)

    if questions:
        known = {
            k: str(v) for k, v in raw.items()
            if k not in {q.field_name for q in questions}
        }
        return Resolution(item=None, questions=tuple(questions),
                          refused=tuple(refused), known=known)

    return Resolution(
        item=ResolvedItem(
            family=str(family), category=str(category), state=str(state),
            buyer_profile=str(profile), use_case=str(raw.get("use_case", "")),
            specs=specs,
        ),
        refused=tuple(refused),
    )


def _checked(
    value: Any, allowed: tuple[str, ...], name: str, ask: str, why: str,
    questions: list[Question],
) -> Any:
    if value in allowed:
        return value
    questions.append(Question(
        name, ask, why, options=allowed,
        suggestion=str(value) if value else "",
    ))
    return None


def confirm(
    resolution: Resolution, answers: Mapping[str, str],
    *, cfg: Mapping[str, Any], buyer_profiles: tuple[str, ...],
    known_categories: tuple[str, ...] = (),
) -> Resolution:
    """Fold the buyer's answers back in.

    Runs the same validation as the first pass, so a confirmed value gets no
    special trust — a buyer who types "₹5 lakh" into the battery capacity box
    is refused exactly as a model would be.
    """
    merged: dict[str, Any] = dict(resolution.known)
    if resolution.item is not None:
        merged.update(resolution.item.to_dict())
        merged.update(merged.pop("specs", {}))
    merged.update(answers)

    confirmable = set(cfg["item_resolver"]["confirmable_specs"])
    answered_specs = {
        k: str(v) for k, v in answers.items()
        if k in confirmable and not looks_like_a_figure(v)
    }

    out = resolve(
        "", lambda _: {k: v for k, v in merged.items() if k not in confirmable},
        cfg=cfg, buyer_profiles=buyer_profiles,
        known_categories=known_categories,
    )
    if out.item is None:
        return Resolution(
            item=None, questions=out.questions,
            refused=(*resolution.refused, *out.refused),
            known={**dict(out.known), **answered_specs},
        )
    return Resolution(
        item=ResolvedItem(
            family=out.item.family, category=out.item.category,
            state=out.item.state, buyer_profile=out.item.buyer_profile,
            use_case=out.item.use_case,
            specs={**out.item.specs, **answered_specs},
        ),
        refused=(*resolution.refused, *out.refused),
    )


def money_typed_fields() -> list[str]:
    """For the test that guards the boundary. Should always be empty."""
    return [
        f.name for f in fields(ResolvedItem)
        if "Money" in str(f.type) or "money" in f.name.lower()
        or "price" in f.name.lower() or "amount" in f.name.lower()
        or "cost" in f.name.lower()
    ]


__all__ = [
    "ExtractFn",
    "Question",
    "Resolution",
    "ResolvedItem",
    "confirm",
    "looks_like_a_figure",
    "money_typed_fields",
    "resolve",
]
