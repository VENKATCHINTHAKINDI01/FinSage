"""Cache at answer time, search on the sweep — PRC-011.

The latency answer, and why it is two functions rather than one
---------------------------------------------------------------
Opening web search to the agents fixes coverage and would, done naively, put
six government portals on the critical path of every reply. AGT-012 already
solved this for freshness by giving `FreshnessCache` no fetch method at all.
This module takes the same line, one level up:

    resolve(keys, cache)          answer time.  Reads the cache. Full stop.
    sweep(keys, cache, search)    background.   Searches, admits, fills cache.

`resolve` has no `search` parameter. Not a default of `None`, not a flag — the
parameter does not exist, so there is no call site at which someone under a
deadline can pass one "just for this one lookup". The only thing that can fail
at answer time is a dictionary lookup, and that is a property of the signature
rather than of anyone's discipline.

`sweep` is the only thing that touches the network, and it does not touch it
directly either: the search function is injected. That keeps this module
testable without a network and keeps the choice of search backend out of the
costing path entirely.

Stale serves, missing does not
------------------------------
A cached fact past its TTL is returned with its staleness badge. A user with a
labelled 40-day-old GST rate is better served than a user with an error page.

A fact that was never gathered is a `Gap`, not a guess. That is the asymmetry
the whole design rests on: an old figure is probably right and says how old it
is; an invented figure is a coin flip that says nothing.

What comes back is always two halves
-------------------------------------
`Gathered` carries the usable facts, the gaps, and the Tier-3 context
separately, because a caller that could accidentally take only the first would
produce a breakdown with lines silently missing. Splitting them means the
omission has to be handled somewhere, and the natural place is the UI, where a
named gap is useful to a human.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.core.provenance.admission import (
    Admission,
    CandidateFact,
    Gap,
    Verdict,
    admit,
    load_admission_rules,
)
from backend.core.provenance.sourcing import (
    SourceCache,
    SourcedFact,
    next_refresh_due,
)

# (key, query) -> whatever the extractors managed to lift from the results.
# Returning candidates rather than text is deliberate: the search layer is
# responsible for running a deterministic extractor over the page, so a search
# backend that can only produce prose cannot satisfy this signature.
SearchFn = Callable[[str, str], Sequence[CandidateFact]]


@dataclass(frozen=True, slots=True)
class Gathered:
    """Everything a costing run needs, with the holes named."""

    facts: dict[str, SourcedFact] = field(default_factory=dict)
    gaps: list[Gap] = field(default_factory=list)
    context: dict[str, SourcedFact] = field(default_factory=dict)
    stale: list[str] = field(default_factory=list)
    refresh_due: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.gaps

    def gap_sentences(self) -> list[str]:
        return [g.sentence() for g in self.gaps]

    def to_dict(self, today: date | None = None) -> dict[str, Any]:
        return {
            "facts": {k: v.to_dict(today) for k, v in self.facts.items()},
            "context": {k: v.to_dict(today) for k, v in self.context.items()},
            "gaps": [g.to_dict() for g in self.gaps],
            "stale": self.stale,
            "refresh_due": self.refresh_due,
            "complete": self.complete,
        }


def resolve(
    keys: Iterable[str],
    cache: SourceCache,
    *,
    today: date,
) -> Gathered:
    """Answer time. Reads the cache and nothing else.

    There is deliberately no `search` parameter. See the module docstring — the
    guarantee is in the signature, because a guarantee that depends on callers
    remembering is not a guarantee.
    """
    facts: dict[str, SourcedFact] = {}
    context: dict[str, SourcedFact] = {}
    gaps: list[Gap] = []
    stale: list[str] = []
    due: list[str] = []

    for key in keys:
        fact = cache.get(key)
        if fact is None:
            gaps.append(Gap(
                key=key,
                reason=(
                    "it has not been gathered yet, and this is answered from "
                    "verified sources only."
                ),
                what_would_fix_it=(
                    "The background sweep will look for it; it will appear in "
                    "a later run if an admissible source exists."
                ),
            ))
            continue

        if fact.tier.may_drive_a_cost_line:
            facts[key] = fact
        else:
            context[key] = fact
            gaps.append(Gap(
                key=key,
                reason=(
                    f"the only source held for it is {fact.source_url}, an "
                    f"unverified aggregator. It is shown as context and is not "
                    f"included in any total."
                ),
                what_would_fix_it=(
                    "An official or manufacturer source carrying the same "
                    "figure."
                ),
                candidates_seen=1,
            ))

        if fact.is_stale(today):
            stale.append(key)
        if next_refresh_due(fact) <= today:
            due.append(key)

    return Gathered(
        facts=facts, gaps=gaps, context=context, stale=stale, refresh_due=due,
    )


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What the background run did, for the log a human actually reads."""

    admitted: list[str] = field(default_factory=list)
    context_only: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    admissions: dict[str, Admission] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return not self.rejected

    def summary(self) -> str:
        if self.healthy:
            return (
                f"{len(self.admitted)} fact(s) admitted, "
                f"{len(self.unchanged)} still fresh."
            )
        return (
            f"{len(self.admitted)} admitted, {len(self.rejected)} could not be "
            f"admitted from any source found. Those figures will be reported "
            f"as gaps rather than estimated: "
            f"{', '.join(sorted(self.rejected))}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "context_only": self.context_only,
            "rejected": self.rejected,
            "unchanged": self.unchanged,
            "healthy": self.healthy,
            "summary": self.summary(),
            "admissions": {k: v.to_dict() for k, v in self.admissions.items()},
        }


def sweep(
    queries: dict[str, str],
    cache: SourceCache,
    search: SearchFn,
    *,
    today: date,
    force: bool = False,
    cfg: dict[str, Any] | None = None,
) -> SweepReport:
    """Background. The only place in the costing path that reaches the network.

    A key whose cached fact is not yet due for refresh is skipped, so the sweep
    costs one request per fact per TTL rather than one per answer. `force`
    exists for a re-verification run after a Budget, where the point is to
    re-read everything regardless of age.

    A failed admission does NOT evict the cached fact. If a page moved and this
    morning's search found nothing admissible, yesterday's Tier-1 figure with
    its date on it is still the best thing available, and replacing it with
    nothing would turn a working answer into a gap on the strength of one bad
    fetch.
    """
    cfg = cfg or load_admission_rules()
    report_admitted: list[str] = []
    report_context: list[str] = []
    report_rejected: list[str] = []
    report_unchanged: list[str] = []
    admissions: dict[str, Admission] = {}

    for key, query in queries.items():
        held = cache.get(key)
        if held is not None and not force and next_refresh_due(held) > today:
            report_unchanged.append(key)
            continue

        candidates = list(search(key, query))
        verdict = admit(key, candidates, cfg=cfg)
        admissions[key] = verdict

        if verdict.verdict is Verdict.ADMITTED:
            cache.put(verdict.fact)          # type: ignore[arg-type]
            report_admitted.append(key)
        elif verdict.verdict is Verdict.CONTEXT_ONLY:
            # Only cached where nothing better is held. Overwriting a Tier-1
            # fact with a marketplace listing would silently demote a costable
            # line to context.
            if held is None or not held.tier.may_drive_a_cost_line:
                cache.put(verdict.fact)      # type: ignore[arg-type]
            report_context.append(key)
        else:
            report_rejected.append(key)

    return SweepReport(
        admitted=report_admitted,
        context_only=report_context,
        rejected=report_rejected,
        unchanged=report_unchanged,
        admissions=admissions,
    )


__all__ = [
    "Gathered",
    "SearchFn",
    "SweepReport",
    "resolve",
    "sweep",
]
