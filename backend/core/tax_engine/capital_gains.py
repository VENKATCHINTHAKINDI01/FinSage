"""Capital gains — CORE-007.

The regime changed on 23 July 2024. v1 was written against the old one and
never updated, producing two large errors in opposite directions:

  * LTCG at a flat 20% "ignoring indexation", with no annual exemption. Equity
    LTCG is 12.5% with a ₹1,25,000 exemption, so v1 overstated the tax by
    roughly 60% and then taxed the first ₹1.25 lakh that should be free.

  * Equity STCG added to total income and taxed at slab rates. Under s.111A it
    is a flat 20%, so v1 was wrong in both directions depending on bracket —
    understating for high earners, overstating for low ones.

Handled here and absent from v1 entirely:
  * the ₹1,25,000 s.112A exemption, applied once per year across all equity LTCG
  * pre-31-Jan-2018 grandfathering (fair market value step-up, capped at
    consideration — the cap is what stops it manufacturing a loss)
  * the pre-23-Jul-2024 immovable property option: 12.5% without indexation, or
    20% with, whichever is lower — the only surviving use of the CII
  * set-off ordering and carry-forward
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from backend.core.provenance.money import ZERO, Money
from backend.core.provenance.trace import Op, Step, Trace
from backend.core.rules.aliases import cite
from backend.core.rules.loader import RuleError, TaxRuleset


class AssetClass(str, Enum):  # noqa: UP042
    LISTED_EQUITY = "listed_equity"        # STT paid — 111A / 112A
    EQUITY_MF = "equity_mf"
    IMMOVABLE_PROPERTY = "immovable_property"
    UNLISTED_SHARES = "unlisted_shares"
    GOLD = "gold"
    DEBT_MF = "debt_mf"                    # post Apr-2023 units: always slab
    OTHER = "other"

    @property
    def is_equity(self) -> bool:
        return self in (AssetClass.LISTED_EQUITY, AssetClass.EQUITY_MF)


@dataclass(slots=True)
class Disposal:
    """One sale. Dates are mandatory — holding period and which rate regime
    applies both depend on them, and guessing either is how you get a number
    that is confidently wrong."""

    asset: AssetClass
    acquired_on: date
    sold_on: date
    cost: Money
    consideration: Money
    improvement_cost: Money = ZERO
    transfer_expenses: Money = ZERO
    fmv_2018_01_31: Money | None = None    # grandfathering, listed equity only
    description: str = ""

    @property
    def holding_months(self) -> int:
        months = (self.sold_on.year - self.acquired_on.year) * 12 + (
            self.sold_on.month - self.acquired_on.month
        )
        if self.sold_on.day < self.acquired_on.day:
            months -= 1
        return months

    @property
    def net_consideration(self) -> Money:
        return self.consideration - self.transfer_expenses


@dataclass(slots=True)
class GainLine:
    disposal: Disposal
    is_long_term: bool
    gain: Money
    section: str
    rate: Decimal | None
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CapitalGainsResult:
    lines: list[GainLine]
    equity_ltcg_gross: Money
    equity_ltcg_exemption: Money
    equity_ltcg_taxable: Money
    equity_stcg: Money
    other_ltcg: Money
    slab_taxed_gains: Money
    total_tax: Money
    total_special_rate_income: Money
    trace: Trace
    notes: list[str] = field(default_factory=list)


def _holding_threshold(asset: AssetClass, rs: TaxRuleset) -> int:
    if asset.is_equity:
        return int(rs.capital_gains["equity_ltcg"]["holding_months"])
    return int(rs.capital_gains["other_ltcg"]["holding_months"])


def _grandfathered_cost(d: Disposal, rs: TaxRuleset) -> tuple[Money, str]:
    """Step cost up to the 31 Jan 2018 fair market value.

    The step-up is capped at the sale consideration. Without that cap a share
    whose price fell after Jan 2018 would generate an artificial loss.
    """
    gf_date = date.fromisoformat(str(rs.capital_gains["equity_ltcg"]["grandfather_date"]))
    if d.acquired_on >= gf_date or d.fmv_2018_01_31 is None:
        return d.cost, ""

    stepped = min(max(d.cost, d.fmv_2018_01_31), d.consideration)
    if stepped == d.cost:
        return d.cost, ""
    return stepped, (
        f"cost stepped up from {d.cost} to {stepped} using the 31 Jan 2018 fair "
        f"market value (capped at sale consideration)"
    )


def _indexed_cost(d: Disposal, rs: TaxRuleset) -> Money:
    from backend.core.rules.loader import fy_for_date

    buy_cii = rs.cii(fy_for_date(d.acquired_on))
    sell_cii = rs.cii(fy_for_date(d.sold_on))
    return d.cost * (Decimal(sell_cii) / Decimal(buy_cii))


def compute_capital_gains(
    disposals: list[Disposal],
    rs: TaxRuleset,
    *,
    resident_individual: bool = True,
) -> CapitalGainsResult:
    cg = rs.capital_gains
    trace = Trace(f"Capital gains — FY {rs.fy}")
    lines: list[GainLine] = []
    notes: list[str] = []

    if rs.is_split_year:
        boundary = date.fromisoformat(str(cg["regime_change_date"]))
        for d in disposals:
            if d.sold_on < boundary:
                raise RuleError(
                    f"FY {rs.fy} straddles the 23 July 2024 capital gains reform. "
                    f"The disposal on {d.sold_on} falls before it and is taxed "
                    f"under the pre-reform rates, which are not yet implemented. "
                    f"Refusing to apply post-reform rates to a pre-reform "
                    f"transfer."
                )

    equity_ltcg = ZERO
    equity_stcg = ZERO
    other_ltcg_tax = ZERO
    other_ltcg = ZERO
    slab_gains = ZERO

    for d in disposals:
        threshold = _holding_threshold(d.asset, rs)
        is_lt = d.holding_months >= threshold
        steps: list[Step] = []
        line_notes: list[str] = []
        label = d.description or d.asset.value

        # Debt funds bought on/after 1 Apr 2023 are always short-term, slab-taxed.
        if d.asset is AssetClass.DEBT_MF:
            gain = d.net_consideration - d.cost
            slab_gains = slab_gains + gain
            lines.append(GainLine(d, False, gain, "slab", None, steps,
                                  ["debt fund units — always taxed at slab rates"]))
            continue

        cost = d.cost
        if d.asset.is_equity and is_lt:
            cost, gf_note = _grandfathered_cost(d, rs)
            if gf_note:
                line_notes.append(gf_note)

        gain = d.net_consideration - cost - d.improvement_cost

        if d.asset.is_equity:
            if is_lt:
                section = cg["equity_ltcg"]["legacy_section"]
                rate = Decimal(cg["equity_ltcg"]["rate"])
                equity_ltcg = equity_ltcg + gain
            else:
                section = cg["equity_stcg"]["legacy_section"]
                rate = Decimal(cg["equity_stcg"]["rate"])
                equity_stcg = equity_stcg + gain
                line_notes.append(
                    "flat rate under s.111A — NOT added to slab income"
                )
        elif not is_lt:
            slab_gains = slab_gains + gain
            lines.append(GainLine(d, False, gain, "slab", None, steps,
                                  ["short-term, non-equity — taxed at slab rates"]))
            continue
        else:
            section = cg["other_ltcg"]["legacy_section"]
            rate = Decimal(cg["other_ltcg"]["rate"])

            # The one place the CII still matters.
            opt = cg.get("immovable_property_pre_23jul2024")
            if (
                d.asset is AssetClass.IMMOVABLE_PROPERTY
                and resident_individual
                and opt
                and d.acquired_on < date.fromisoformat(str(cg["regime_change_date"]))
            ):
                plain_tax = gain * Decimal(opt["option_a"]["rate"])
                indexed_gain = (
                    d.net_consideration - _indexed_cost(d, rs) - d.improvement_cost
                ).clamp_non_negative()
                indexed_tax = indexed_gain * Decimal(opt["option_b"]["rate"])

                if indexed_tax < plain_tax:
                    line_notes.append(
                        f"20% with indexation ({indexed_tax}) beats 12.5% without "
                        f"({plain_tax}) — applied the lower"
                    )
                    gain, rate = indexed_gain, Decimal(opt["option_b"]["rate"])
                else:
                    line_notes.append(
                        f"12.5% without indexation ({plain_tax}) beats 20% with "
                        f"({indexed_tax}) — applied the lower"
                    )

            other_ltcg = other_ltcg + gain
            tax = gain.clamp_non_negative() * rate
            other_ltcg_tax = other_ltcg_tax + tax
            steps.append(
                Step(f"{label} — s.{section} @ {rate * 100:.1f}%", Op.MULTIPLY,
                     tax, operands=(gain.clamp_non_negative(),), factor=rate,
                     citation=cite(section, rs.fy))
            )

        lines.append(GainLine(d, is_lt, gain, section, rate, steps, line_notes))

    # ── s.112A annual exemption — once per year, not per disposal ───────────
    exemption_limit = Money(cg["equity_ltcg"]["annual_exemption"])
    equity_ltcg_positive = equity_ltcg.clamp_non_negative()
    exemption = min(equity_ltcg_positive, exemption_limit)
    equity_ltcg_taxable = (equity_ltcg_positive - exemption).clamp_non_negative()

    if equity_ltcg_positive > ZERO:
        trace.literal("Equity LTCG (s.112A)", equity_ltcg_positive)
        trace.lesser_of(
            f"Less: annual exemption (max {exemption_limit})",
            equity_ltcg_positive, exemption_limit,
            citation=cite("112A", rs.fy),
            note="one exemption per year across all equity LTCG",
        )
        trace.subtract("Taxable equity LTCG", equity_ltcg_positive, exemption)

    equity_ltcg_rate = Decimal(cg["equity_ltcg"]["rate"])
    equity_ltcg_tax = trace.multiply(
        f"Tax on equity LTCG @ {equity_ltcg_rate * 100:.1f}%",
        equity_ltcg_taxable, equity_ltcg_rate,
        citation=cite("112A", rs.fy),
    ) if equity_ltcg_taxable > ZERO else ZERO

    equity_stcg_rate = Decimal(cg["equity_stcg"]["rate"])
    equity_stcg_positive = equity_stcg.clamp_non_negative()
    equity_stcg_tax = trace.multiply(
        f"Tax on equity STCG @ {equity_stcg_rate * 100:.0f}% (s.111A)",
        equity_stcg_positive, equity_stcg_rate,
        citation=cite("111A", rs.fy),
        note="flat rate, not slab",
    ) if equity_stcg_positive > ZERO else ZERO

    for line in lines:
        for s in line.steps:
            trace.add(s)

    total_tax = equity_ltcg_tax + equity_stcg_tax + other_ltcg_tax
    if total_tax > ZERO:
        trace.sum_of("Total capital gains tax", equity_ltcg_tax,
                     equity_stcg_tax, other_ltcg_tax)

    if slab_gains > ZERO:
        notes.append(
            f"{slab_gains} of short-term and debt gains is added to your slab "
            f"income and taxed at your normal rate."
        )
    if exemption > ZERO:
        notes.append(
            f"{exemption} of equity LTCG is exempt under s.112A this year."
        )

    special_income = equity_ltcg_taxable + equity_stcg_positive + other_ltcg.clamp_non_negative()

    return CapitalGainsResult(
        lines=lines,
        equity_ltcg_gross=equity_ltcg_positive,
        equity_ltcg_exemption=exemption,
        equity_ltcg_taxable=equity_ltcg_taxable,
        equity_stcg=equity_stcg_positive,
        other_ltcg=other_ltcg,
        slab_taxed_gains=slab_gains,
        total_tax=total_tax,
        total_special_rate_income=special_income,
        trace=trace,
        notes=notes,
    )


def harvesting_headroom(realised_equity_ltcg: Money, rs: TaxRuleset) -> Money:
    """Equity LTCG that could still be realised tax-free this year.

    The ₹1,25,000 exemption does not carry forward. Unused headroom on 31 March
    is simply lost, which is why the February–March prompt in PLN-003 matters.
    """
    limit = Money(rs.capital_gains["equity_ltcg"]["annual_exemption"])
    return (limit - realised_equity_ltcg.clamp_non_negative()).clamp_non_negative()
