"""Which ITR form to file — PLN-004.

What this replaces
------------------
v1 shipped a table that was not stale but invented:

    ITR-5   "high income individuals > 50 lakh"   — it is for firms, LLPs,
                                                    AOPs and BOIs, and no
                                                    individual may ever file it
    ITR-3    absent from the table entirely       — the form most people with
                                                    business income need
    ITR-4   "turnover < 5 crore"                  — a figure lifted from the
                                                    audit provisions; the form
                                                    is conditioned on total
                                                    income of ₹50 lakh

Filing the wrong form is not a cosmetic error. The return is treated as
defective under s.139(9), and if it is not corrected in time it is treated as
never having been filed at all — losses forfeited, belated-filing fee, interest
running.

Why it explains the exclusions
------------------------------
"You should file ITR-2" is an instruction. "You cannot use ITR-1 because you
held unlisted shares during the year, and ITR-2 is the next form that permits
that" is something a person can check, disagree with, and act on. Every
`Exclusion` carries the fact that triggered it, so a user who thinks the
profile is wrong knows precisely which answer to correct.

The vintage problem, stated rather than hidden
-----------------------------------------------
Forms for an assessment year are notified around March of that year. For a
return being planned during FY 2026-27, the AY 2027-28 forms do not exist yet.
This selector applies the most recently notified scoping and says which year
that came from on every answer. Presenting last year's rules as this year's is
how a form selector becomes confidently wrong the moment CBDT moves a
threshold — which it did twice for ITR-1 in two years.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.core.provenance.money import ZERO, Money
from backend.core.rules.loader import TaxRuleset, load_ruleset


class EntityType(str, Enum):
    INDIVIDUAL = "individual"
    HUF = "huf"
    FIRM = "firm"
    LLP = "llp"
    AOP = "aop"
    BOI = "boi"
    AJP = "ajp"
    COMPANY = "company"
    TRUST = "trust"
    POLITICAL_PARTY = "political_party"
    RESEARCH_INSTITUTION = "research_institution"


class Residency(str, Enum):
    ORDINARILY_RESIDENT = "ordinarily_resident"
    NOT_ORDINARILY_RESIDENT = "not_ordinarily_resident"
    NON_RESIDENT = "non_resident"


@dataclass(slots=True)
class FilerProfile:
    """Everything the choice turns on, and nothing else.

    Deliberately flat and explicit. A profile assembled from a half-filled form
    should fail a check rather than default its way into ITR-1, so every flag
    that could disqualify defaults to the *permissive* value only where absence
    genuinely means absence (you either held unlisted shares or you did not).
    """

    entity: EntityType = EntityType.INDIVIDUAL
    residency: Residency = Residency.ORDINARILY_RESIDENT
    total_income: Money = ZERO

    # income composition
    has_salary: bool = False
    house_properties: int = 0
    has_business_income: bool = False
    uses_presumptive_scheme: bool = False
    has_short_term_capital_gains: bool = False
    ltcg_112a: Money = ZERO
    has_other_capital_gains: bool = False
    agricultural_income: Money = ZERO
    has_lottery_or_racehorse_income: bool = False
    has_special_rate_income: bool = False
    has_retirement_benefit_account_relief: bool = False
    has_section_5a_apportionment: bool = False

    # status flags — each one of these alone forces a bigger form
    is_company_director: bool = False
    holds_unlisted_equity_shares: bool = False
    has_foreign_assets_or_signing_authority: bool = False
    has_foreign_income: bool = False
    tds_under_194n: bool = False
    has_deferred_esop_tax: bool = False
    has_carry_forward_loss: bool = False

    claims_section_11_exemption: bool = False


@dataclass(frozen=True, slots=True)
class Exclusion:
    form: str
    reason: str
    fact: str

    def __str__(self) -> str:
        return f"{self.form}: {self.reason} ({self.fact})"

    def to_dict(self) -> dict[str, str]:
        return {"form": self.form, "reason": self.reason, "fact": self.fact}


@dataclass(slots=True)
class FormRecommendation:
    fy: str
    form: str
    entity: EntityType
    excluded: list[Exclusion]
    notified_for_ay: str
    applies_to_ay: str
    needs_form_10iea: bool
    notes: list[str] = field(default_factory=list)

    @property
    def scoping_is_provisional(self) -> bool:
        """True where the forms for the year in question are not yet notified,
        which is the normal state of affairs for most of any financial year."""
        return self.notified_for_ay != self.applies_to_ay

    def blocking_reasons(self) -> list[dict[str, Any]]:
        """The distinct reasons, each with the forms it ruled out.

        `excluded` is per-form and correct, but a flat rendering of it repeats
        "you were a director in a company" once for ITR-1 and again for ITR-4,
        which reads like a bug. What a user needs is the list of things about
        them that constrain the choice — each said once.
        """
        merged: dict[tuple[str, str], list[str]] = {}
        for e in self.excluded:
            merged.setdefault((e.reason, e.fact), []).append(e.form)
        return [
            {"reason": reason, "fact": fact, "rules_out": forms}
            for (reason, fact), forms in merged.items()
        ]

    def summary(self) -> str:
        line = f"File {self.form} for AY {self.applies_to_ay}."
        reasons = self.blocking_reasons()
        if reasons:
            line += (
                f" {len(reasons)} thing(s) about your situation rule out the "
                f"simpler forms."
            )
        return line

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "form": self.form,
            "entity": self.entity.value,
            "applies_to_ay": self.applies_to_ay,
            "notified_for_ay": self.notified_for_ay,
            "scoping_is_provisional": self.scoping_is_provisional,
            "needs_form_10iea": self.needs_form_10iea,
            "excluded": [e.to_dict() for e in self.excluded],
            "blocking_reasons": self.blocking_reasons(),
            "summary": self.summary(),
            "notes": self.notes,
        }


# Each disqualifier maps to a predicate on the profile and the sentence a user
# should read. Kept as data rather than a chain of ifs so the same table drives
# ITR-1 and ITR-4, which share most of their exclusions but not all.
_CHECKS: dict[str, tuple[str, Any]] = {
    "business_or_professional_income": (
        "you have income from business or profession",
        lambda p, rs: p.has_business_income,
    ),
    "short_term_capital_gains": (
        "you have short-term capital gains",
        lambda p, rs: p.has_short_term_capital_gains,
    ),
    "ltcg_112a_over_limit": (
        "your equity LTCG exceeds the amount this form permits",
        lambda p, rs: p.ltcg_112a > Money(
            rs.itr_forms["ITR-1"].get("allows_ltcg_112a_upto", 0)
        ),
    ),
    "other_capital_gains": (
        "you have capital gains other than equity LTCG under s.112A",
        lambda p, rs: p.has_other_capital_gains,
    ),
    "more_than_two_house_properties": (
        "you have income from more than two house properties",
        lambda p, rs: p.house_properties > int(
            rs.itr_forms["ITR-1"].get("max_house_properties", 2)
        ),
    ),
    "lottery_or_racehorse_income": (
        "you have winnings from lottery or income from racehorses",
        lambda p, rs: p.has_lottery_or_racehorse_income,
    ),
    "special_rate_income_115bbda_or_115bbe": (
        "you have income taxed at special rates under s.115BBDA or s.115BBE",
        lambda p, rs: p.has_special_rate_income,
    ),
    "retirement_benefit_account_relief": (
        "you are claiming relief on a foreign retirement benefit account",
        lambda p, rs: p.has_retirement_benefit_account_relief,
    ),
    "section_5a_apportionment": (
        "your income must be apportioned under s.5A",
        lambda p, rs: p.has_section_5a_apportionment,
    ),
    "agricultural_income_over_5000": (
        "your agricultural income exceeds ₹5,000",
        lambda p, rs: p.agricultural_income > Money(5000),
    ),
    "is_company_director": (
        "you were a director in a company during the year",
        lambda p, rs: p.is_company_director,
    ),
    "holds_unlisted_equity_shares": (
        "you held unlisted equity shares at some point during the year",
        lambda p, rs: p.holds_unlisted_equity_shares,
    ),
    "foreign_assets_or_signing_authority": (
        "you hold assets outside India or have signing authority on a foreign "
        "account",
        lambda p, rs: p.has_foreign_assets_or_signing_authority,
    ),
    "foreign_income": (
        "you have income from a source outside India",
        lambda p, rs: p.has_foreign_income,
    ),
    "tds_under_194n": (
        "tax was deducted from your cash withdrawals under s.194N",
        lambda p, rs: p.tds_under_194n,
    ),
    "deferred_esop_tax": (
        "tax on your ESOPs has been deferred",
        lambda p, rs: p.has_deferred_esop_tax,
    ),
    "brought_forward_or_carry_forward_loss": (
        "you have a loss brought forward or to be carried forward",
        lambda p, rs: p.has_carry_forward_loss,
    ),
    "not_ordinarily_resident_or_non_resident": (
        "this form is only for taxpayers who are ordinarily resident",
        lambda p, rs: p.residency is not Residency.ORDINARILY_RESIDENT,
    ),
    "not_an_individual": (
        "only an individual may use this form",
        lambda p, rs: p.entity is not EntityType.INDIVIDUAL,
    ),
    "is_llp": (
        "an LLP cannot use this form, even on a presumptive basis",
        lambda p, rs: p.entity is EntityType.LLP,
    ),
}


def _facts(profile: FilerProfile, key: str) -> str:
    """The specific value behind an exclusion, so a user can check it."""
    return {
        "more_than_two_house_properties": f"{profile.house_properties} properties",
        "ltcg_112a_over_limit": f"{profile.ltcg_112a} of equity LTCG",
        "agricultural_income_over_5000": f"{profile.agricultural_income}",
        "not_ordinarily_resident_or_non_resident": profile.residency.value,
        "not_an_individual": f"you are filing as a {profile.entity.value}",
        "is_llp": "an LLP",
    }.get(key, "from your profile")


def _check_form(
    form: str, profile: FilerProfile, rs: TaxRuleset
) -> list[Exclusion]:
    """Everything about this profile that rules the form out. All of it, not
    the first one — a user fixing one answer should not have to come back and
    discover a second problem."""
    cfg = rs.itr_forms[form]
    found: list[Exclusion] = []

    limit = cfg.get("total_income_limit")
    if limit is not None and profile.total_income > Money(limit):
        found.append(Exclusion(
            form,
            f"your total income is over the {Money(limit)} limit for this form",
            f"{profile.total_income}",
        ))

    if cfg.get("requires_presumptive") and not profile.uses_presumptive_scheme:
        found.append(Exclusion(
            form,
            "this form is only for taxpayers declaring income on a presumptive "
            "basis under s.44AD, s.44ADA or s.44AE",
            "presumptive scheme not in use",
        ))

    for key in cfg.get("disqualifiers", []):
        reason, predicate = _CHECKS[key]
        if predicate(profile, rs):
            found.append(Exclusion(form, reason, _facts(profile, key)))

    return found


def select_itr_form(
    profile: FilerProfile,
    fy: str,
    *,
    ruleset: TaxRuleset | None = None,
) -> FormRecommendation:
    """Pick the simplest form the taxpayer actually qualifies for."""
    rs = ruleset or load_ruleset(fy)
    cfg = rs.itr_forms
    notes: list[str] = []
    excluded: list[Exclusion] = []

    # Non-individual entities are decided by what they ARE, not by income
    # composition. This is the branch v1 got backwards.
    entity_form = _entity_form(profile, cfg)
    if entity_form:
        return _finish(rs, entity_form, profile, [], notes)

    # ITR-1 and ITR-4 are the two simple forms; neither is a subset of the
    # other, so both are tested and the surviving one is preferred.
    for candidate in ("ITR-1", "ITR-4"):
        problems = _check_form(candidate, profile, rs)
        if not problems:
            return _finish(rs, candidate, profile, excluded, notes)
        excluded.extend(problems)

    # ITR-2 is for individuals and HUFs WITHOUT business income; ITR-3 is the
    # catch-all with it.
    if profile.has_business_income:
        return _finish(rs, "ITR-3", profile, excluded, notes)

    excluded.extend(_check_form("ITR-2", profile, rs))
    return _finish(rs, "ITR-2", profile, excluded, notes)


def _entity_form(profile: FilerProfile, cfg: Any) -> str | None:
    """Forms determined by entity type rather than income.

    A company files ITR-6 whatever its income looks like — unless it claims
    s.11 exemption, in which case ITR-7. No individual may ever file ITR-5,
    ITR-6 or ITR-7, which is precisely the error v1's table encoded.
    """
    if profile.entity in (EntityType.INDIVIDUAL, EntityType.HUF):
        return None
    if profile.entity is EntityType.COMPANY:
        return "ITR-7" if profile.claims_section_11_exemption else "ITR-6"
    if profile.entity in (
        EntityType.TRUST, EntityType.POLITICAL_PARTY,
        EntityType.RESEARCH_INSTITUTION,
    ):
        return "ITR-7"

    # Firms, LLPs, AOPs, BOIs and AJPs. A firm using the presumptive scheme may
    # use ITR-4 instead — but an LLP may not, which is why the entity check
    # cannot simply route every firm-like entity to ITR-5.
    if profile.entity is EntityType.FIRM and profile.uses_presumptive_scheme:
        return None
    return "ITR-5"


def _finish(
    rs: TaxRuleset,
    form: str,
    profile: FilerProfile,
    excluded: list[Exclusion],
    notes: list[str],
) -> FormRecommendation:
    cfg = rs.itr_forms
    needs_10iea = (
        form in cfg.get("form_10iea_required_for", [])
        and profile.has_business_income
    )
    if needs_10iea:
        notes.append(
            f"To use the old regime with business income you must file Form "
            f"10-IEA BEFORE filing {form}. Filers of ITR-1 and ITR-2 just tick "
            f"a box; you do not."
        )

    notified, applies = cfg["notified_for_ay"], cfg["applies_to_ay"]
    if notified != applies:
        notes.append(
            f"This is the AY {notified} form scoping, which is the most recent "
            f"notified. The AY {applies} forms are usually notified around "
            f"March {applies.split('-')[0]} — re-check then, because CBDT "
            f"moved the ITR-1 thresholds in each of the last two years."
        )

    if profile.has_carry_forward_loss:
        notes.append(
            "Carrying a loss forward requires the return to be filed by the "
            "due date. Filing late forfeits it entirely."
        )

    return FormRecommendation(
        fy=rs.fy, form=form, entity=profile.entity, excluded=excluded,
        notified_for_ay=notified, applies_to_ay=applies,
        needs_form_10iea=needs_10iea, notes=notes,
    )
