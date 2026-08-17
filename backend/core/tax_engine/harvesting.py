"""Capital loss set-off and tax-loss harvesting — PLN-003.

The idea worth having
---------------------
The ₹1,25,000 exemption under s.112A is not a discount. It is a **0% tax
bucket**, and once you see it that way the whole feature follows:

    other STCG          slab, up to 30%
    equity STCG 111A    20%
    LTCG above 1.25L    12.5%
    LTCG within 1.25L   0%   ← setting a loss off here achieves nothing

A rupee of loss set off against equity STCG saves 20 paise. The same rupee set
off against the exempt slice of LTCG saves nothing at all and is gone for good.
Most tooling treats "set off the losses" as one undifferentiated step and
silently destroys value doing it.

Two orderings, two different reasons
------------------------------------
**Constrained losses first.** A long-term loss can only go against long-term
gains; a short-term loss can go against either. So LTCL is allocated first,
leaving the flexible STCL for whatever remains. That is better on both counts:
it maximises what gets used this year, and what carries forward is the loss
with the most future options.

**Highest rate first, within what the constraint allows.** Obvious once the
exemption is modelled as a rate rather than a deduction.

What this module deliberately does not decide
----------------------------------------------
Whether the assessee may *choose* which gain a loss lands on is not settled in
any source this codebase could find, and that is a finding rather than a gap.
What is established either way:

  * the CONSTRAINTS are statutory and are enforced here without qualification —
    STCL against STCG or LTCG, LTCL against LTCG only (s.74), and capital
    losses never against another head (s.71(3))
  * inter-head set-off under s.71 has been held to be at the assessee's option
    rather than mandatory, which supports reading s.70's "shall be entitled to
    have" the same way
  * the ORDER within the capital-gains head is unaddressed by the section, and
    ITR utilities have historically differed from the statutory reading

So the ordering here is the taxpayer-favourable one, and `ORDERING_CAVEAT`
travels with every result saying so. That is the honest position: the saving is
real and defensible, and the user should know it rests on a reading rather than
on settled law before they rely on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.core.provenance.money import ZERO, Money, pct_of
from backend.core.provenance.trace import Trace
from backend.core.rules.aliases import cite
from backend.core.rules.loader import TaxRuleset, load_ruleset

ORDERING_CAVEAT = (
    "Which gains a loss may be set off against is fixed by statute and is "
    "applied here exactly. The ORDER — most heavily taxed gains first — is not "
    "specified by s.70, and this is the reading most favourable to you. "
    "Inter-head set-off under s.71 has been held to be optional rather than "
    "mandatory, which supports it, but ITR utilities have applied their own "
    "sequence. Confirm the order with your return preparer before relying on "
    "the saving."
)


class GainBucket(str, Enum):
    """Capital gains sorted by how they are taxed, not by what they are.

    Two assets in the same bucket are interchangeable for set-off purposes;
    two in different buckets are not, and the difference is worth real money.
    """

    OTHER_STCG_SLAB = "other_stcg_slab"
    EQUITY_STCG_111A = "equity_stcg_111a"
    EQUITY_LTCG_112A = "equity_ltcg_112a"
    OTHER_LTCG_112 = "other_ltcg_112"

    @property
    def is_long_term(self) -> bool:
        return self in (GainBucket.EQUITY_LTCG_112A, GainBucket.OTHER_LTCG_112)

    @property
    def label(self) -> str:
        return {
            GainBucket.OTHER_STCG_SLAB: "Short-term gains taxed at slab rates",
            GainBucket.EQUITY_STCG_111A: "Equity STCG (s.111A)",
            GainBucket.EQUITY_LTCG_112A: "Equity LTCG (s.112A)",
            GainBucket.OTHER_LTCG_112: "Other LTCG (s.112)",
        }[self]


def bucket_rate(
    bucket: GainBucket, rs: TaxRuleset, *, slab_rate: Decimal = Decimal("0.30")
) -> Decimal:
    """The rate a marginal rupee in this bucket attracts.

    `slab_rate` is the taxpayer's actual marginal rate, which the caller knows
    and this module does not. Defaulting it to 30% would overstate the benefit
    of offsetting slab-taxed gains for everyone below the top bracket, so
    callers that know better should say so.
    """
    cg = rs.capital_gains
    return {
        GainBucket.OTHER_STCG_SLAB: slab_rate,
        GainBucket.EQUITY_STCG_111A: Decimal(str(cg["equity_stcg"]["rate"])),
        GainBucket.EQUITY_LTCG_112A: Decimal(str(cg["equity_ltcg"]["rate"])),
        GainBucket.OTHER_LTCG_112: Decimal(str(cg["other_ltcg"]["rate"])),
    }[bucket]


def exempt_floor(bucket: GainBucket, rs: TaxRuleset) -> Money:
    """How much of this bucket is taxed at nothing.

    Only s.112A has one. Modelling it here rather than as a deduction applied
    later is the whole point: it makes the exempt slice visible to the
    allocator as a 0% bucket it should refuse to spend losses on.
    """
    if bucket is GainBucket.EQUITY_LTCG_112A:
        return Money(rs.capital_gains["equity_ltcg"]["annual_exemption"])
    return ZERO


# ── set-off ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Allocation:
    loss_kind: str           # "STCL" or "LTCL"
    bucket: GainBucket
    amount: Money
    rate: Decimal
    tax_saved: Money
    from_brought_forward: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "loss": self.loss_kind,
            "against": self.bucket.label,
            "amount": self.amount.to_json(),
            "rate": f"{self.rate * 100:.2f}%",
            "tax_saved": self.tax_saved.to_json(),
            "from_brought_forward": self.from_brought_forward,
        }


@dataclass(slots=True)
class SetOffResult:
    fy: str
    gains_before: dict[GainBucket, Money]
    gains_after: dict[GainBucket, Money]
    allocations: list[Allocation]
    tax_saved: Money
    unused_stcl: Money
    unused_ltcl: Money
    exempt_slice_preserved: Money
    trace: Trace
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "allocations": [a.to_dict() for a in self.allocations],
            "tax_saved": self.tax_saved.to_json(),
            "gains_after": {b.value: v.to_json() for b, v in self.gains_after.items()},
            "carried_forward_stcl": self.unused_stcl.to_json(),
            "carried_forward_ltcl": self.unused_ltcl.to_json(),
            "notes": self.notes,
            "worksheet": self.trace.render(),
            "citations": [c.to_dict() for c in (cite("70", self.fy), cite("74", self.fy))],
        }


def set_off_losses(
    gains: dict[GainBucket, Money | int],
    fy: str,
    *,
    stcl: Money | int = 0,
    ltcl: Money | int = 0,
    brought_forward_stcl: Money | int = 0,
    brought_forward_ltcl: Money | int = 0,
    slab_rate: Decimal = Decimal("0.30"),
    ruleset: TaxRuleset | None = None,
) -> SetOffResult:
    """Allocate losses across gain buckets to minimise tax.

    Current-year losses are consumed before brought-forward ones. That is not
    an optimisation, it is the statutory order — and it matters because
    brought-forward losses expire after eight assessment years while
    current-year ones have the full window ahead of them.
    """
    rs = ruleset or load_ruleset(fy)
    trace = Trace(f"Capital loss set-off — FY {rs.fy}")
    notes = [ORDERING_CAVEAT]

    remaining = {b: Money(v) for b, v in gains.items() if Money(v) > ZERO}
    for bucket, amount in remaining.items():
        trace.literal(bucket.label, amount)

    # Each pool is (kind, amount, from_brought_forward). Two orderings stacked:
    # every current-year loss before any brought-forward one (ss.70/71 run
    # before s.74), and within each of those, the constrained LTCL before the
    # flexible STCL.
    pools: list[tuple[str, Money, bool]] = [
        ("LTCL", Money(ltcl), False),
        ("STCL", Money(stcl), False),
        ("LTCL", Money(brought_forward_ltcl), True),
        ("STCL", Money(brought_forward_stcl), True),
    ]

    allocations: list[Allocation] = []
    tax_saved = ZERO

    for kind, pool, is_bf in pools:
        available = pool
        if available <= ZERO:
            continue

        # LTCL is confined to long-term gains; STCL may go anywhere. Ordering
        # the eligible buckets by rate is what stops a loss being spent on the
        # exempt slice while a 20% gain sits untouched.
        eligible = [
            b for b in remaining
            if (b.is_long_term if kind == "LTCL" else True)
        ]
        eligible.sort(key=lambda b: bucket_rate(b, rs, slab_rate=slab_rate), reverse=True)

        for bucket in eligible:
            if available <= ZERO:
                break
            headroom = _taxable_headroom(bucket, remaining[bucket], rs)
            if headroom <= ZERO:
                continue

            used = min(available, headroom)
            rate = bucket_rate(bucket, rs, slab_rate=slab_rate)
            saved = pct_of(used, rate)

            allocations.append(
                Allocation(kind, bucket, used, rate, saved, from_brought_forward=is_bf)
            )
            tax_saved = tax_saved + saved
            remaining[bucket] = remaining[bucket] - used
            available = available - used

    unused_stcl = _unused("STCL", pools, allocations)
    unused_ltcl = _unused("LTCL", pools, allocations)

    if allocations:
        trace.sum_of("Total tax saved by set-off", *[a.tax_saved for a in allocations])

    preserved = _exempt_slice_left(remaining, rs)
    _append_notes(notes, remaining, unused_stcl, unused_ltcl, rs)

    return SetOffResult(
        fy=rs.fy,
        gains_before={b: Money(v) for b, v in gains.items()},
        gains_after=remaining,
        allocations=allocations,
        tax_saved=tax_saved,
        unused_stcl=unused_stcl,
        unused_ltcl=unused_ltcl,
        exempt_slice_preserved=preserved,
        trace=trace,
        notes=notes,
    )


def _taxable_headroom(bucket: GainBucket, gain: Money, rs: TaxRuleset) -> Money:
    """How much of this gain is actually worth offsetting.

    The exempt floor is subtracted, so a ₹2,00,000 equity LTCG offers ₹75,000
    of headroom, not ₹2,00,000. Offsetting the remaining ₹1,25,000 would spend
    real losses to reduce a tax of zero.
    """
    return (gain - exempt_floor(bucket, rs)).clamp_non_negative()


def _unused(kind: str, pools: list[tuple[str, Money, bool]],
            allocations: list[Allocation]) -> Money:
    total = ZERO
    for pool_kind, amount, _ in pools:
        if pool_kind == kind:
            total = total + amount
    for a in allocations:
        if a.loss_kind == kind:
            total = total - a.amount
    return total.clamp_non_negative()


def _exempt_slice_left(remaining: dict[GainBucket, Money], rs: TaxRuleset) -> Money:
    """Equity LTCG left standing inside the exemption — a good outcome, not a
    residue. It is the measure of how much loss the allocator declined to
    spend on a 0% bucket."""
    gain = remaining.get(GainBucket.EQUITY_LTCG_112A, ZERO)
    return min(gain, exempt_floor(GainBucket.EQUITY_LTCG_112A, rs))


def _append_notes(
    notes: list[str],
    remaining: dict[GainBucket, Money],
    unused_stcl: Money,
    unused_ltcl: Money,
    rs: TaxRuleset,
) -> None:
    floor = exempt_floor(GainBucket.EQUITY_LTCG_112A, rs)
    left = remaining.get(GainBucket.EQUITY_LTCG_112A, ZERO)
    if left > ZERO and left <= floor and (unused_stcl > ZERO or unused_ltcl > ZERO):
        notes.append(
            f"{left} of equity LTCG is left unoffset, and that is deliberate: "
            f"the first {floor} is exempt under s.112A, so a loss set off "
            f"against it would save nothing and be gone."
        )

    years = rs.capital_gains["set_off"]["carry_forward_years"]
    if unused_stcl > ZERO or unused_ltcl > ZERO:
        notes.append(
            f"Unused losses carry forward for {years} assessment years — "
            f"{unused_stcl} short-term and {unused_ltcl} long-term. They are "
            f"forfeited entirely unless the return is filed by the due date, "
            f"which is the single most expensive filing deadline there is."
        )
    if unused_ltcl > ZERO:
        notes.append(
            "Carried-forward long-term losses can only ever be set off against "
            "long-term gains. Short-term losses are the more useful ones to be "
            "left holding."
        )


# ── harvesting ──────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Position:
    """An open holding. Dates are mandatory for the same reason they are on a
    `Disposal`: whether a gain is long-term decides the rate, and guessing is
    how you get a number that is confidently wrong."""

    name: str
    acquired_on: date
    cost: Money
    market_value: Money
    asset: str = "listed_equity"

    def unrealised(self) -> Money:
        return self.market_value - self.cost

    def is_long_term_on(self, when: date, holding_months: int) -> bool:
        months = (when.year - self.acquired_on.year) * 12 + (
            when.month - self.acquired_on.month
        )
        if when.day < self.acquired_on.day:
            months -= 1
        return months >= holding_months

    def days_to_long_term(self, from_date: date, holding_months: int) -> int:
        """How much longer to hold. Selling an equity holding one day short of
        twelve months moves it from 12.5% to 20% — the single most expensive
        day in retail investing."""
        year = self.acquired_on.year + (self.acquired_on.month + holding_months - 1) // 12
        month = (self.acquired_on.month + holding_months - 1) % 12 + 1
        try:
            qualifies = date(year, month, self.acquired_on.day)
        except ValueError:                      # 31st into a shorter month
            qualifies = date(year, month, 28)
        return max(0, (qualifies - from_date).days)


@dataclass(frozen=True, slots=True)
class Opportunity:
    kind: str                # "harvest_loss" | "harvest_gain" | "wait"
    position: str
    amount: Money            # gain or loss to realise
    tax_effect: Money        # saved (positive) or avoided
    rationale: str
    act_by: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "position": self.position,
            "amount": self.amount.to_json(),
            "tax_effect": self.tax_effect.to_json(),
            "rationale": self.rationale,
            "act_by": self.act_by.isoformat() if self.act_by else None,
        }


@dataclass(slots=True)
class HarvestPlan:
    fy: str
    as_of: date
    exemption_remaining: Money
    opportunities: list[Opportunity]
    total_tax_effect: Money
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "as_of": self.as_of.isoformat(),
            "exemption_remaining": self.exemption_remaining.to_json(),
            "opportunities": [o.to_dict() for o in self.opportunities],
            "total_tax_effect": self.total_tax_effect.to_json(),
            "notes": self.notes,
        }


def harvest(
    positions: list[Position],
    fy: str,
    *,
    as_of: date,
    realised_equity_ltcg: Money | int = 0,
    realised_equity_stcg: Money | int = 0,
    slab_rate: Decimal = Decimal("0.30"),
    ruleset: TaxRuleset | None = None,
) -> HarvestPlan:
    """What to do before 31 March, quantified.

    Two opposite moves, and the reason they are in one function is that they
    compete for the same ₹1,25,000:

    **Harvest a gain.** Equity LTCG within the annual exemption is taxed at
    nothing. Selling and immediately rebuying resets your cost base upward at
    zero tax cost, so the gain never accumulates into a future taxable year.
    Unused exemption does not carry forward — it is genuinely use-it-or-lose-it
    every 31 March.

    **Harvest a loss.** Realising an unrealised loss creates a set-off against
    gains you have already booked.
    """
    rs = ruleset or load_ruleset(fy)
    cg = rs.capital_gains
    holding_months = int(cg["equity_ltcg"]["holding_months"])
    exemption = Money(cg["equity_ltcg"]["annual_exemption"])
    ltcg_rate = Decimal(str(cg["equity_ltcg"]["rate"]))
    stcg_rate = Decimal(str(cg["equity_stcg"]["rate"]))

    used = Money(realised_equity_ltcg).clamp_non_negative()
    remaining_exemption = (exemption - used).clamp_non_negative()
    booked_gains = Money(realised_equity_ltcg) + Money(realised_equity_stcg)

    opportunities: list[Opportunity] = []
    notes: list[str] = []
    year_end = date(_fy_end_year(rs.fy), 3, 31)

    for p in positions:
        pnl = p.unrealised()
        long_term = p.is_long_term_on(as_of, holding_months)

        if pnl < ZERO:
            # A loss is only worth realising if there is something to set it
            # against. Suggesting it into an empty year is advice to pay
            # brokerage for nothing.
            if booked_gains <= ZERO:
                continue
            rate = ltcg_rate if long_term else stcg_rate
            usable = min(-pnl, booked_gains)
            opportunities.append(Opportunity(
                kind="harvest_loss", position=p.name, amount=-pnl,
                tax_effect=pct_of(usable, rate),
                act_by=year_end,
                rationale=(
                    f"Realising this {-pnl} loss sets off against gains you have "
                    f"already booked this year, at {rate * 100:.1f}%."
                ),
            ))

        elif pnl > ZERO and long_term and p.asset in ("listed_equity", "equity_mf"):
            if remaining_exemption <= ZERO:
                continue
            take = min(pnl, remaining_exemption)
            opportunities.append(Opportunity(
                kind="harvest_gain", position=p.name, amount=take,
                tax_effect=pct_of(take, ltcg_rate),
                act_by=year_end,
                rationale=(
                    f"Selling and rebuying realises {take} of gain at zero tax "
                    f"under the s.112A exemption and resets your cost base "
                    f"upward, so that gain is never taxed later."
                ),
            ))
            remaining_exemption = remaining_exemption - take

        elif pnl > ZERO and not long_term:
            days = p.days_to_long_term(as_of, holding_months)
            if 0 < days <= 90:
                opportunities.append(Opportunity(
                    kind="wait", position=p.name, amount=pnl,
                    tax_effect=pct_of(pnl, stcg_rate - ltcg_rate),
                    act_by=None,
                    rationale=(
                        f"{days} more days of holding moves this from 20% "
                        f"short-term to 12.5% long-term."
                    ),
                ))

    total = ZERO
    for o in opportunities:
        total = total + o.tax_effect

    if remaining_exemption > ZERO:
        notes.append(
            f"{remaining_exemption} of your ₹{exemption.amount:,.0f} s.112A "
            f"exemption is unused. It does not carry forward — whatever is left "
            f"on 31 March is gone."
        )

    # The criterion the feature registry asks for, and the one most likely to
    # get a user into trouble if it is left out.
    notes.append(
        "On repurchasing: India has no wash-sale rule. Unlike the United "
        "States, nothing in the Act disallows a loss because you bought the "
        "same security straight back. The limit is the General Anti-Avoidance "
        "Rules, which can disallow a transaction whose main purpose is a tax "
        "benefit and which lacks commercial substance — in practice applied "
        "very rarely to individual share transactions on a recognised exchange "
        "at market prices. Repeated round-tripping purely to manufacture "
        "losses is what draws scrutiny; take advice before doing this at scale."
    )
    notes.append(
        "Every figure here is a tax effect, not a return. Harvesting changes "
        "when you pay tax, not whether the underlying investment is any good."
    )

    return HarvestPlan(
        fy=rs.fy, as_of=as_of, exemption_remaining=remaining_exemption,
        opportunities=sorted(opportunities, key=lambda o: o.tax_effect, reverse=True),
        total_tax_effect=total, notes=notes,
    )


def _fy_end_year(fy: str) -> int:
    return int(fy.split("-")[0]) + 1
