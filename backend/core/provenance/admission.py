"""Search proposes, rules admit — PRC-010.

Why this module exists
----------------------
Pre-storing every rate this product could need — thirty-odd states of stamp
duty and road tax, every solar and agri and MSME scheme, every OEM price list —
is a maintenance treadmill nobody keeps current. The road tax table in
`procurement.yaml` covers four states and is already a liability. Letting an
agent search the open web fixes coverage.

It also breaks three guarantees, unless something sits in between:

  1. **Provenance.** If an agent reads "6%" off a page and states it, the
     provenance of that figure is *a language model read it*. The whole product
     rests on the opposite.
  2. **Reproducibility.** EVD-007 promises a pack replays under a pinned rule
     version. A figure that comes from whatever the search engine returned that
     morning drifts day to day with no rule change and nothing to pin.
  3. **Latency.** AGT-012 exists so the network is never on the critical path
     of an answer.

So search does not answer the question. Search proposes a CANDIDATE, and the
rules decide whether it is admitted as a fact.

The shape of it
---------------
    web search  →  CandidateFact  →  admit()  →  SourcedFact  →  CostLine
                   (cannot cost)     (rules)     (can cost)

`CandidateFact` is deliberately a different type from `SourcedFact`, not a flag
on it. There is no way to hand a candidate to `CostLine`, because the
constructor takes a `SourcedFact` and a candidate is not one. Promotion is the
only route across, and promotion goes through the checks. That is the same
argument as `Tier3CannotCost`: a rule enforced by a code review survives until
the first deadline; a rule enforced by the type system does not need anyone to
remember it.

The four checks, and why each one is not a model's judgement
------------------------------------------------------------
**Tier comes from the domain**, looked up in a table, not from the model's read
of how official a page looks. "This appears to be a government source" is
precisely the judgement a language model makes confidently and wrongly.

**The extractor must be deterministic.** A model may find the page and say
where to look. It may not be the thing that reports the number. The test is
whether the same bytes yield the same figure tomorrow.

**The value must fall in a plausibility band** for its key. This catches the
extractor that grabbed the phone number, the page count or the year. It does
not make the figure right, and the docstring on `_plausible` says so.

**Independent corroboration**, by host, for the keys that need it. Two pages on
one site are one source.

What happens when a check fails
-------------------------------
The line is omitted and the gap is named. Not a national average, not a badged
guess in the total — a `Gap` that says which figure is missing, why it could
not be admitted, and what would fix it. A missing line the user can see is
recoverable. A confidently wrong line is the failure mode this whole codebase
is built to avoid, and falling back to an average reintroduces it at exactly
the moment the system already knows it is on thin ice.

The one exception is a Tier-3 candidate that is otherwise clean: a marketplace
listing that a deterministic extractor pulled and that is plausible. That is
admitted as CONTEXT_ONLY — a real `SourcedFact` at `Tier.AGGREGATOR`, which
`CostLine` will still refuse by type. It can be shown, badged, beside the
breakdown. It cannot be added up.

A model-authored figure is never CONTEXT_ONLY. Badging does not cure a
hallucinated rupee figure; it only gives it a place on the page.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from backend.core.provenance.money import Money
from backend.core.provenance.sourcing import SourcedFact, Tier
from backend.core.rules.loader import RULES_DIR, RuleError


class NotAdmitted(Exception):
    """A candidate was promoted without passing. Raised by `Admission.fact`
    only if something bypasses `verdict`, so it should never be seen."""


class Verdict(str, Enum):
    ADMITTED = "admitted"          # may drive a cost line
    CONTEXT_ONLY = "context_only"  # may be shown, badged; never totalled
    REJECTED = "rejected"          # produces a Gap


# ── what search hands back ──────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class CandidateFact:
    """Something seen on a page. Not yet a fact, and structurally unable to
    become one without going through `admit`.

    `raw_value` is a string on purpose. It is what the extractor lifted, before
    anyone decided what type it is — keeping it unparsed means the parse
    failure is itself an admission check rather than an exception thrown
    somewhere upstream with no verdict attached.
    """

    key: str                # "gst.electric_vehicle", "stamp_duty.MH.female"
    raw_value: str
    value_kind: str         # "rate" | "money"
    extracted_by: str       # keys extractors.deterministic / .model_authored
    source_url: str
    fetched_on: date
    title: str = ""
    snippet: str = ""       # the surrounding text, for a human to audit
    source_kind: str = ""   # keys sourcing.TTL_DAYS

    def __post_init__(self) -> None:
        if not self.fetched_on:
            raise ValueError(
                f"candidate {self.key} has no fetch date. A searched figure "
                f"without the day it was seen cannot be aged, cached or "
                f"re-checked, so it cannot be admitted under any rule."
            )

    @property
    def host(self) -> str:
        return _host(self.source_url)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class Gap:
    """A figure the system could not stand behind, named rather than filled.

    This is the deliverable of a failed admission. It exists so that the
    absence appears in the output — a breakdown that quietly drops a line looks
    identical to one where the line is genuinely zero.
    """

    key: str
    reason: str
    what_would_fix_it: str
    candidates_seen: int = 0

    def sentence(self) -> str:
        return (
            f"{self.key} is not included: {self.reason} "
            f"{self.what_would_fix_it}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "reason": self.reason,
            "what_would_fix_it": self.what_would_fix_it,
            "candidates_seen": self.candidates_seen,
            "sentence": self.sentence(),
        }


@dataclass(frozen=True, slots=True)
class Admission:
    """The verdict on one key, with the working shown."""

    key: str
    verdict: Verdict
    checks: tuple[Check, ...]
    _fact: SourcedFact | None = None
    gap: Gap | None = None

    @property
    def fact(self) -> SourcedFact | None:
        if self._fact is None:
            return None
        if self.verdict is Verdict.REJECTED:
            raise NotAdmitted(f"{self.key} was rejected but carried a fact")
        return self._fact

    @property
    def may_cost(self) -> bool:
        return self.verdict is Verdict.ADMITTED

    def failed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "verdict": self.verdict.value,
            "may_cost": self.may_cost,
            "checks": [c.to_dict() for c in self.checks],
            "fact": self._fact.to_dict() if self._fact else None,
            "gap": self.gap.to_dict() if self.gap else None,
        }


# ── parsing ─────────────────────────────────────────────────────────────────

_RATE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)", re.IGNORECASE,
)
_RUPEE = re.compile(
    r"(?:₹|Rs\.?|INR)?\s*(?P<num>\d[\d,]*(?:\.\d+)?)"
    r"\s*(?P<scale>lakhs?|lacs?|crores?|cr|k)?",
    re.IGNORECASE,
)
_SCALE = {
    "lakh": Decimal(100_000), "lakhs": Decimal(100_000),
    "lac": Decimal(100_000), "lacs": Decimal(100_000),
    "crore": Decimal(10_000_000), "crores": Decimal(10_000_000),
    "cr": Decimal(10_000_000), "k": Decimal(1_000),
}


def parse_rate(raw: str) -> Decimal | None:
    """A percentage on a page becomes a fraction.

    Returns None rather than raising: a parse failure is a verdict, not an
    accident. `0.05` and `5%` both mean five per cent, and a page may write
    either — but a bare `5` is ambiguous between the two and is refused.
    """
    text = raw.strip()
    m = _RATE.search(text)
    if m:
        try:
            return Decimal(m.group("num")) / Decimal(100)
        except InvalidOperation:
            return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if value >= 1:
        # "5" with no per-cent sign. Five, or five per cent? Refusing is the
        # only honest answer, and a rate of 1.0 or more is in any case outside
        # every band in the pack.
        return None
    return value


def parse_money(raw: str) -> Money | None:
    m = _RUPEE.search(raw.strip())
    if not m:
        return None
    try:
        value = Decimal(m.group("num").replace(",", ""))
    except InvalidOperation:
        return None
    scale = (m.group("scale") or "").lower()
    if scale:
        value = value * _SCALE[scale]
    return Money(value)


# ── the rules ───────────────────────────────────────────────────────────────

def _host(url: str) -> str:
    """The registrable host, lowercased, with any leading www. removed.

    Independence is by host. `www.x.gov.in` and `x.gov.in` are one source, and
    counting them as two would let a single page satisfy a quorum of two by
    being linked twice.
    """
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _suffix_match(host: str, listed: str) -> bool:
    return host == listed or host.endswith("." + listed)


def tier_for(url: str, cfg: dict[str, Any]) -> Tier:
    """Tier from the domain table. Unknown is Tier-3, never Tier-1.

    The default direction matters more than the table. An unrecognised domain
    defaulting upward would mean every new source is trusted until someone
    notices; defaulting down means every new source is context until someone
    verifies it.
    """
    host = _host(url)
    if not host:
        return Tier.AGGREGATOR
    domains = cfg["domains"]
    for listed in domains["tier_1"]:
        if _suffix_match(host, listed):
            return Tier.OFFICIAL
    for listed in domains["tier_2"]:
        if _suffix_match(host, listed):
            return Tier.OEM_OR_BANK
    return Tier.AGGREGATOR


def _as_decimal(value: Decimal | Money) -> Decimal:
    """Never `Decimal(str(money))` — `str(Money)` is the Indian-formatted
    display string ("₹1,50,000.00"), which does not parse back."""
    return value.amount if isinstance(value, Money) else Decimal(str(value))


def _plausibility_rule(key: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Longest matching prefix of the dotted key.

    `gst.electric_vehicle` matches `gst`. `road_tax.KA.ev` matches `road_tax`.
    No match returns None, and no match means not admissible for costing —
    unscreened is quarantined, not waved through.
    """
    rules = cfg["plausibility"]
    parts = key.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in rules:
            return dict(rules[prefix])
    return None


def _plausible(
    key: str, value: Decimal | Money, kind: str, cfg: dict[str, Any],
) -> Check:
    """Is this number in the range a number of this sort lives in?

    A pass here is NOT evidence the figure is correct. It means an extractor
    did not obviously lift the wrong thing off the page — a phone number, a
    page count, a year, an interest rate where a stamp duty was wanted. The
    evidence that a figure is right is the Tier-1 URL and the date beside it.
    Widening a band to let a figure through is therefore always the wrong fix.
    """
    rule = _plausibility_rule(key, cfg)
    if rule is None:
        return Check(
            "plausible", False,
            f"no plausibility rule covers {key!r}. A figure nobody has "
            f"declared a sane range for is quarantined rather than trusted; "
            f"add a rule to admission.yaml before this key can be costed.",
        )
    if rule["kind"] != kind:
        return Check(
            "plausible", False,
            f"{key} is declared as {rule['kind']} in the rules but arrived "
            f"as {kind}.",
        )

    if "allowed" in rule:
        allowed = [Decimal(str(a)) for a in rule["allowed"]]
        if _as_decimal(value) not in allowed:
            return Check(
                "plausible", False,
                f"{value} is not one of the permitted values "
                f"{[str(a) for a in allowed]}. {rule.get('note', '')}".strip(),
            )
        return Check("plausible", True, f"{value} is a permitted value.")

    low = Decimal(str(rule["min"]))
    high = Decimal(str(rule["max"]))
    got = _as_decimal(value)
    if not (low <= got <= high):
        return Check(
            "plausible", False,
            f"{got} is outside the plausible range {low}–{high} for {key}. "
            f"{rule.get('note', '')}".strip(),
        )
    return Check("plausible", True, f"{got} is within {low}–{high}.")


def _agrees(a: Decimal | Money, b: Decimal | Money, kind: str,
            cfg: dict[str, Any]) -> bool:
    q = cfg["quorum"]
    lhs, rhs = _as_decimal(a), _as_decimal(b)
    if kind == "rate":
        return abs(lhs - rhs) <= Decimal(str(q["rate_tolerance"]))
    if lhs == 0 and rhs == 0:
        return True
    pct = Decimal(str(q["money_tolerance_pct"]))
    largest = max(abs(lhs), abs(rhs))
    return abs(lhs - rhs) <= largest * pct


def _hosts_required(key: str, cfg: dict[str, Any]) -> int:
    q = cfg["quorum"]
    parts = key.split(".")
    for i in range(len(parts), 0, -1):
        if ".".join(parts[:i]) in set(q["single_source_sufficient"]):
            return 1
    return int(q["default_required_hosts"])


# ── the gate ────────────────────────────────────────────────────────────────

def admit(
    key: str,
    candidates: Sequence[CandidateFact],
    *,
    cfg: dict[str, Any] | None = None,
) -> Admission:
    """Decide whether anything here may become a fact.

    Order is deliberate. The extractor check runs first and is fatal at every
    tier, because a model-authored number should not be shown even as badged
    context. Everything after it is about how much weight a real extraction
    carries.
    """
    cfg = cfg or load_admission_rules()
    checks: list[Check] = []
    seen = len(candidates)

    if not candidates:
        return _reject(
            key, checks,
            "nothing was found for it.",
            "A source that publishes this figure, with a date.",
            seen,
        )

    for c in candidates:
        if c.key != key:
            raise ValueError(
                f"candidate for {c.key!r} passed to admit({key!r}). Mixing "
                f"keys would let a road tax figure corroborate a stamp duty."
            )
    kinds = {c.value_kind for c in candidates}
    if len(kinds) > 1:
        raise ValueError(
            f"candidates for {key!r} disagree on what they are: {sorted(kinds)}. "
            f"A rate and an amount cannot corroborate each other, and deciding "
            f"which one the key 'really' is would be a guess."
        )

    # ── 1. who lifted the number ────────────────────────────────────────────
    deterministic = set(cfg["extractors"]["deterministic"])
    model_authored = set(cfg["extractors"]["model_authored"])
    clean = [c for c in candidates if c.extracted_by in deterministic]
    if not clean:
        offenders = sorted({c.extracted_by for c in candidates})
        by_model = [o for o in offenders if o in model_authored]
        checks.append(Check(
            "deterministic_extractor", False,
            f"every candidate was produced by {offenders}. "
            + (
                "A language model may find the page and say where to look, but "
                "the number itself has to be lifted by an extractor that yields "
                "the same result from the same bytes tomorrow. A figure a model "
                "read and reported has no provenance beyond the model."
                if by_model else
                "That extractor is not on the deterministic list."
            ),
        ))
        return _reject(
            key, checks,
            "the only figures available were reported by a language model "
            "rather than lifted from the page by a deterministic extractor.",
            "The same page, re-read with a parser that targets the cell or the "
            "pattern the figure sits in.",
            seen,
        )
    checks.append(Check(
        "deterministic_extractor", True,
        f"{len(clean)} of {seen} candidate(s) came from "
        f"{sorted({c.extracted_by for c in clean})}.",
    ))

    # ── 2. parse ────────────────────────────────────────────────────────────
    parsed: list[tuple[CandidateFact, Decimal | Money]] = []
    for c in clean:
        value = parse_rate(c.raw_value) if c.value_kind == "rate" \
            else parse_money(c.raw_value) if c.value_kind == "money" else None
        if value is not None:
            parsed.append((c, value))
    if not parsed:
        checks.append(Check(
            "parsed", False,
            f"none of {[c.raw_value for c in clean]} parsed as "
            f"{clean[0].value_kind}.",
        ))
        return _reject(
            key, checks,
            "the extracted text did not parse as a number of the expected "
            "kind.",
            "A page where the figure is written unambiguously — a bare '5' is "
            "refused because it may mean five or five per cent.",
            seen,
        )
    checks.append(Check("parsed", True, f"{len(parsed)} value(s) parsed."))

    # ── 3. plausibility ─────────────────────────────────────────────────────
    kind = parsed[0][0].value_kind
    survivors = []
    last_failure: Check | None = None
    for c, value in parsed:
        check = _plausible(key, value, c.value_kind, cfg)
        if check.passed:
            survivors.append((c, value))
        else:
            last_failure = check
    if not survivors:
        checks.append(last_failure or Check("plausible", False, "implausible"))
        return _reject(
            key, checks,
            f"every figure found was outside the range a {key} figure lives "
            f"in, which usually means the extractor picked up the wrong number "
            f"on the page.",
            "A page where the figure is in a labelled table cell rather than "
            "loose prose.",
            seen,
        )
    checks.append(Check(
        "plausible", True,
        f"{len(survivors)} of {len(parsed)} value(s) within range.",
    ))

    # ── 4. tier ─────────────────────────────────────────────────────────────
    tiered = [(c, v, tier_for(c.source_url, cfg)) for c, v in survivors]
    costable = [t for t in tiered if t[2].may_drive_a_cost_line]
    if not costable:
        best = min(tiered, key=lambda t: (t[2], t[0].fetched_on))
        checks.append(Check(
            "tier", False,
            f"the best source available is {best[0].host}, which is tier "
            f"{int(best[2])} ({best[2].label}). Shown as context; it cannot "
            f"enter a total.",
        ))
        return Admission(
            key=key, verdict=Verdict.CONTEXT_ONLY, checks=tuple(checks),
            _fact=_promote(best[0], best[1], best[2]),
            gap=Gap(
                key=key,
                reason=(
                    f"the only sources found were unverified aggregators "
                    f"({sorted({c.host for c, _, _ in tiered})}), which may "
                    f"add context to a decision but must never produce a "
                    f"figure in a cost breakdown."
                ),
                what_would_fix_it=(
                    "An official or manufacturer page carrying the same "
                    "figure."
                ),
                candidates_seen=seen,
            ),
        )
    checks.append(Check(
        "tier", True,
        f"{len(costable)} source(s) at tier "
        f"{sorted({int(t[2]) for t in costable})}.",
    ))

    # ── 5. corroboration ────────────────────────────────────────────────────
    needed = _hosts_required(key, cfg)
    # Prefer the most authoritative, then the most recently fetched.
    costable.sort(key=lambda t: (t[2], -t[0].fetched_on.toordinal()))
    chosen_c, chosen_v, chosen_tier = costable[0]
    agreeing_hosts = {
        c.host for c, v, _ in costable if _agrees(v, chosen_v, kind, cfg)
    }
    if len(agreeing_hosts) < needed:
        disagreeing = {
            c.host: str(v) for c, v, _ in costable
            if not _agrees(v, chosen_v, kind, cfg)
        }
        checks.append(Check(
            "corroborated", False,
            f"{key} needs {needed} independent host(s) in agreement and has "
            f"{len(agreeing_hosts)} ({sorted(agreeing_hosts)})."
            + (f" Disagreeing: {disagreeing}." if disagreeing else ""),
        ))
        return _reject(
            key, checks,
            (
                f"the sources found do not agree "
                f"({ {c.host: str(v) for c, v, _ in costable} })."
                if len(costable) > 1 else
                f"it appeared on only {len(agreeing_hosts)} source and this "
                f"figure varies enough by locality that one is not enough."
            ),
            f"{needed} independent sources carrying the same figure.",
            seen,
        )
    checks.append(Check(
        "corroborated", True,
        f"{len(agreeing_hosts)} independent host(s) agree "
        f"(needed {needed}): {sorted(agreeing_hosts)}.",
    ))

    return Admission(
        key=key, verdict=Verdict.ADMITTED, checks=tuple(checks),
        _fact=_promote(chosen_c, chosen_v, chosen_tier),
    )


def _promote(
    candidate: CandidateFact, value: Decimal | Money, tier: Tier,
) -> SourcedFact:
    """The one crossing from candidate to fact.

    Every route into `SourcedFact` from search goes through here, which is why
    it is private and why `admit` is the only caller.
    """
    return SourcedFact(
        key=candidate.key,
        value=value,
        source_url=candidate.source_url,
        tier=tier,
        fetched_on=candidate.fetched_on,
        source_kind=candidate.source_kind,
        title=candidate.title,
    )


def _reject(
    key: str, checks: list[Check], reason: str, fix: str, seen: int,
) -> Admission:
    return Admission(
        key=key, verdict=Verdict.REJECTED, checks=tuple(checks),
        gap=Gap(key=key, reason=reason, what_would_fix_it=fix,
                candidates_seen=seen),
    )


def admit_all(
    proposals: dict[str, Sequence[CandidateFact]],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Admission]:
    cfg = cfg or load_admission_rules()
    return {k: admit(k, v, cfg=cfg) for k, v in proposals.items()}


def facts_for_costing(
    admissions: dict[str, Admission],
) -> tuple[dict[str, SourcedFact], list[Gap]]:
    """Split the verdicts into what may be used and what must be declared.

    Returns both halves because a caller that only takes the first half would
    silently drop the gaps, which is the exact behaviour the design refuses.
    """
    usable: dict[str, SourcedFact] = {}
    gaps: list[Gap] = []
    for key, a in admissions.items():
        if a.verdict is Verdict.ADMITTED and a.fact is not None:
            usable[key] = a.fact
        elif a.gap is not None:
            gaps.append(a.gap)
    return usable, gaps


def load_admission_rules() -> dict[str, Any]:
    import yaml

    path = Path(RULES_DIR) / "admission.yaml"
    if not path.exists():
        raise RuleError("rule pack admission.yaml is missing")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


__all__ = [
    "Admission",
    "CandidateFact",
    "Check",
    "Gap",
    "NotAdmitted",
    "Verdict",
    "admit",
    "admit_all",
    "facts_for_costing",
    "load_admission_rules",
    "parse_money",
    "parse_rate",
    "tier_for",
]
