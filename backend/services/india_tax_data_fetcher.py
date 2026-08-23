"""Tax reference data — AGT-001 / DEM-006.

What was wrong with this file
------------------------------
It held a hardcoded `fy_2024_25_data` dict, was instantiated in `main.py`'s
lifespan, and was read by four production modules. Every rate in it was frozen
at FY 2024-25 and several were simply wrong:

    80D            ₹1,50,000  — that is 80C's limit. 80D is ₹25,000, or
                                ₹50,000 where the insured is a senior, in two
                                separate limbs capped at ₹1,00,000 together.
    80CCD          ₹1,50,000  — the additional NPS deduction under 80CCD(1B)
                                is ₹50,000.
    LTCG                  20% — 12.5% for transfers on or after 23 July 2024.
    standard ded.    ₹50,000  — ₹75,000 in the new regime for FY 2026-27.
    slabs         FY 2024-25  — three Budgets out of date.
    senior slabs     present  — the new regime has no age bands at all.

Nothing here moved when the year did, because nothing here knew what year it
was. `advanced_calculator.py` had already been patched *around* this file with
hardcoded stopgaps rather than trusting it — the shape of a module everyone
has quietly stopped believing.

What changed
------------
Every RATE now reads through to `backend.core.rules`, the same packs the
deterministic engine computes from, so an agent quoting a limit and the engine
applying one can no longer disagree. There is no default financial year: the
year is passed, or derived from the date, and an unknown one raises from the
loader rather than resolving to the nearest pack.

What deliberately did NOT change
---------------------------------
The ITR-form, GST-threshold and red-flag heuristics below are not tax rates and
are covered by their own tests. Replacing them is PLN-004's and a future GST
feature's scope, not this fix — an earlier attempt deleted them wholesale and
broke eleven passing tests for no gain.
"""

import logging
from typing import Any

from backend.core.rules.loader import TaxRuleset, fy_for_date, load_ruleset

logger = logging.getLogger(__name__)


def _plain(node: Any) -> Any:
    """Unwrap the loader's frozen mappings.

    `TaxRuleset` deep-freezes into `MappingProxyType` and tuples so one request
    cannot mutate the shared ruleset. Callers here serialise to JSON, which can
    encode neither.
    """
    if hasattr(node, "items"):
        return {k: _plain(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(v) for v in node]
    return node


class IndiaTaxDataFetcher:
    """
    Fetch India-specific tax data from official sources.

    Sources:
    • incometax.gov.in
    • cbdt.gov.in
    """

    def __init__(self):
        # `static_data` now holds ONLY the non-rate reference material: ITR
        # form descriptions, GST registration thresholds, red-flag heuristics
        # and common mistakes. Every rate, limit, slab and date is read from
        # the rule pack on demand — see `_rules()` and the accessors below.
        self.static_data = self._init_static_data()

    # Kept as an alias because four modules and a test suite read this name.
    # It no longer contains FY 2024-25 tax rates; the name is now a lie in a
    # harmless direction, and renaming it is a separate mechanical change.
    @property
    def fy_2024_25_data(self) -> dict[str, Any]:
        return self.static_data

    def _rules(self, fy: str | None = None) -> TaxRuleset:
        """The pack for a stated year, or the one in force today.

        No default year anywhere. That was this file's single largest defect:
        it had one, silently, forever.
        """
        from datetime import date

        return load_ruleset(fy) if fy else load_ruleset(fy_for_date(date.today()))

    def _init_static_data(self) -> dict[str, Any]:
        """Non-rate reference material only."""
        return {
            # GST Rules
            "gst": {
                "registration_threshold": 4000000,  # ₹40 lakh
                "composition_threshold": 1500000,  # ₹15 lakh
                "gst_rates": [0, 0.05, 0.12, 0.18, 0.28],
                "intra_state_threshold": 5000000  # ₹50 lakh
            },

            # ITR Forms Available
            "itr_forms": {
                "ITR-1": {
                    "name": "Individuals with total income < ₹50 lakh",
                    "applicable": "Salaried individuals, interest, rental income",
                    "income_types": ["salary", "interest", "rental"],
                    "capital_gains": False,
                    "business": False
                },
                "ITR-2": {
                    "name": "Individuals with capital gains or foreign assets",
                    "applicable": "Capital gains, foreign assets, speculation income",
                    "income_types": ["all"],
                    "capital_gains": True,
                    "business": False
                },
                "ITR-4": {
                    "name": "Self-employed individuals with turnover < ₹5 crore",
                    "applicable": "Business/Professional income < ₹5 crore",
                    "income_types": ["business", "professional"],
                    "capital_gains": True,
                    "business": True
                },
                "ITR-5": {
                    "name": "High income individuals (> ₹50 lakh)",
                    "applicable": "Total income > ₹50 lakh or capital gains",
                    "income_types": ["all"],
                    "capital_gains": True,
                    "business": True
                }
            },

            # Red Flag Patterns (India Tax Department)
            "red_flags": {
                "high_income_low_deductions": {
                    "flag": "High income with low deductions",
                    "severity": "Medium",
                    "trigger": "Income > ₹20L, deductions < 5%"
                },
                "cash_transaction_large": {
                    "flag": "Large cash transactions",
                    "severity": "High",
                    "trigger": "Cash deposit > ₹1 lakh without explanation"
                },
                "foreign_income_unreported": {
                    "flag": "Foreign income not reported",
                    "severity": "High",
                    "trigger": "Foreign travel/account detected"
                },
                "tds_mismatch": {
                    "flag": "TDS paid vs salary mismatch",
                    "severity": "High",
                    "trigger": "Form 16 TDS != 26AS TDS"
                },
                "year_to_year_variance": {
                    "flag": "Significant income variance",
                    "severity": "Low",
                    "trigger": "YoY change > 50%"
                },
                "multiple_pans": {
                    "flag": "Multiple PANs detected",
                    "severity": "High",
                    "trigger": "Multiple PAN filings"
                },
                "loss_carryforward_excess": {
                    "flag": "Loss carry forward exceeds limit",
                    "severity": "Medium",
                    "trigger": "Loss > 8 year limit"
                },
                "schedule_mismatch": {
                    "flag": "Schedule data inconsistency",
                    "severity": "Medium",
                    "trigger": "Income doesn't match schedules"
                },
                "gst_compliance_gap": {
                    "flag": "GST compliance issue",
                    "severity": "Medium",
                    "trigger": "Turnover > ₹40L without GST"
                },
                "advance_tax_default": {
                    "flag": "Advance tax not paid",
                    "severity": "High",
                    "trigger": "Expected liability > ₹10k, no advance tax"
                }
            },

            # Common Mistakes in ITR Filing
            "common_itr_mistakes": [
                "Selecting wrong ITR form for income profile",
                "Not reporting all income sources",
                "Claiming deductions without documents",
                "PAN entry errors or mismatch with Aadhaar",
                "Forgetting to attach required schedules",
                "Not verifying ITR within 30 days",
                "Incorrect bank account details",
                "Missing Form 16 data entry",
                "TDS mismatch with 26AS",
                "Claiming deductions beyond limits"
            ]
        }

    async def get_current_tax_data(self, fy: str | None = None) -> dict[str, Any]:
        """Rates for the year in force, from the rule pack."""
        rs = self._rules(fy)
        return {
            "financial_year": rs.fy,
            "assessment_year": rs.assessment_year,
            "governing_act": rs.governing_act,
            "rule_pack_version": rs.version,
            "verified_on": rs.verified_on.isoformat(),
            "start_date": rs.effective_from.isoformat(),
            "end_date": rs.effective_to.isoformat(),
            "cess_rate": str(rs.cess_rate),
            "surcharge": _plain(rs.surcharge),
            "capital_gains": _plain(rs.capital_gains),
            "deduction_limits": await self.get_deduction_limits(rs.fy),
            "important_dates": await self.get_important_dates(rs.fy),
            # The non-rate reference material, passed through unchanged. These
            # are heuristics and form descriptions, not figures the Finance Act
            # sets, so they do not belong in a rule pack.
            "itr_forms": self.static_data["itr_forms"],
            "gst": self.static_data["gst"],
            "red_flags": self.static_data["red_flags"],
            "common_mistakes": self.static_data.get("common_mistakes", []),
            # Named rather than silently absent. A caller reaching for
            # `senior_citizen_brackets` is asking the wrong question and should
            # find that out, not receive an empty list and carry on.
            "note": (
                "Rates come from the rule pack for this financial year. The "
                "new regime has no age-based slabs, so there is no "
                "'senior_citizen_brackets' key — age affects 80TTB and the "
                "old-regime basic exemption, not the new-regime bands."
            ),
        }

    async def get_itr_forms(self) -> dict[str, Any]:
        """Get all ITR forms information"""
        return self.fy_2024_25_data["itr_forms"]

    async def get_deduction_limits(self, fy: str | None = None) -> dict[str, Any]:
        """Every deduction the pack defines, with its real ceiling.

        Returns the pack's own structure rather than flattening each to a
        single `limit`. 80D genuinely has no single limit — self/family and
        parents are separate limbs with different amounts by age — and that
        flattening is exactly how it came to be recorded as ₹1,50,000.
        """
        rs = self._rules(fy)
        return {
            code: _plain(body)
            for code, body in rs.data.get("deductions", {}).items()
        }

    async def get_red_flags(self) -> dict[str, Any]:
        """Get all red flag patterns"""
        return self.fy_2024_25_data["red_flags"]

    async def get_important_dates(self, fy: str | None = None) -> dict[str, str]:
        """Statutory dates for the year, from the pack."""
        rs = self._rules(fy)
        out: dict[str, str] = {
            "fy_start": rs.effective_from.isoformat(),
            "fy_end": rs.effective_to.isoformat(),
        }

        # Every deadline the pack states, under the pack's own names.
        for key, value in _plain(rs.deadlines).items():
            if not isinstance(value, (dict, list)):
                out[key] = str(value)

        # Plus the legacy aliases four modules read by name. Aliases rather
        # than renames, because `itr_normal_deadline` flattens a distinction
        # the pack makes on purpose — a non-audit business return is due
        # 31 August where a salaried one is due 31 July, and the audit case is
        # 31 October. Callers that need the difference should read the specific
        # keys; these keep the existing ones working against real data instead
        # of against a hardcoded FY 2024-25 date.
        alias = {
            "itr_normal_deadline": "itr_non_audit",
            "itr_extended_deadline": "itr_business_non_audit",
        }
        for legacy, real in alias.items():
            if real in out:
                out[legacy] = out[real]

        # Advance-tax instalments are stored as MM-DD plus a cumulative
        # percentage, because the percentages are what s.234C charges on. The
        # calendar dates are derived here rather than duplicated in the pack.
        year = rs.effective_from.year
        for i, inst in enumerate(_plain(rs.advance_tax).get("instalments", []), 1):
            month, day = str(inst["due"]).split("-")
            # The fourth instalment falls in March, which is the SECOND
            # calendar year of the financial year.
            due_year = year + 1 if int(month) < 4 else year
            out[f"q{i}_advance_tax"] = f"{due_year}-{month}-{day}"

        out.setdefault("itr_verification", "30_days_from_filing")
        return out

    async def get_tax_brackets(
        self, is_senior: bool = False, regime: str = "new",
        age: int | None = None, fy: str | None = None,
    ) -> list[dict]:
        """Slabs for a regime and age, from the pack.

        `is_senior: bool` is kept for the existing callers but cannot express
        the old regime's TWO age bands (60 and 80), so `age` supersedes it.
        Passing `is_senior=True` alone resolves to 60, which is what the old
        boolean meant.
        """
        rs = self._rules(fy)
        effective_age = age if age is not None else (60 if is_senior else 0)

        # The pack stores bands as cumulative ceilings — {"upto": 400000,
        # "rate": "0.00"} — because that is how the Finance Act writes them and
        # how the engine consumes them. Callers here expect {min, max, rate},
        # so this translates rather than duplicating the data in a second
        # shape. `max: None` is the open-ended top band; the old dict used
        # float('inf'), which is not JSON-serialisable.
        out: list[dict] = []
        floor = 0
        for band in rs.slabs(regime, age=effective_age):
            ceiling = band.get("upto")
            out.append({
                "min": floor,
                "max": ceiling,
                "rate": float(band["rate"]),
            })
            if ceiling is None:
                break
            floor = ceiling
        return out

    async def get_gst_rules(self) -> dict[str, Any]:
        """Get GST rules for India"""
        return self.fy_2024_25_data["gst"]

    async def validate_itr_form(self, user_data: dict[str, Any]) -> str:
        """Validate and recommend ITR form based on user data"""
        annual_income = user_data.get("annual_income", 0)
        has_capital_gains = user_data.get("has_capital_gains", False)
        employment_type = user_data.get("employment_type", "salaried")

        # ITR-5: High income
        if annual_income > 5000000:
            return "ITR-5"

        # ITR-4: Self-employed
        if employment_type in ["self-employed", "business"]:
            return "ITR-4"

        # ITR-2: Capital gains
        if has_capital_gains:
            return "ITR-2"

        # ITR-1: Default
        return "ITR-1"

    async def check_gst_requirement(self, turnover: float) -> dict[str, Any]:
        """Check if GST registration required"""
        gst_threshold = self.fy_2024_25_data["gst"]["registration_threshold"]

        return {
            "gst_required": turnover > gst_threshold,
            "turnover": turnover,
            "threshold": gst_threshold,
            "message": "GST registration mandatory" if turnover > gst_threshold else "GST registration optional"
        }

    async def detect_red_flags(self, user_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect potential red flags in user data"""
        flags = []
        red_flag_patterns = self.fy_2024_25_data["red_flags"]

        # High income low deductions
        annual_income = user_data.get("annual_income", 0)
        deductions = user_data.get("deductions", {})
        total_deductions = sum(d.get("amount", 0) for d in deductions.values()) if isinstance(deductions, dict) else 0

        if annual_income > 2000000 and (total_deductions / annual_income) < 0.05:
            flags.append({
                "flag": red_flag_patterns["high_income_low_deductions"]["flag"],
                "severity": red_flag_patterns["high_income_low_deductions"]["severity"],
                "trigger": red_flag_patterns["high_income_low_deductions"]["trigger"]
            })

        # TDS mismatch
        tds_paid = user_data.get("tds_paid", 0)
        calculated_tax = user_data.get("calculated_tax", 0)

        if calculated_tax > 0 and abs(tds_paid - calculated_tax) > calculated_tax * 0.10:  # 10% variance
            flags.append({
                "flag": red_flag_patterns["tds_mismatch"]["flag"],
                "severity": red_flag_patterns["tds_mismatch"]["severity"],
                "trigger": red_flag_patterns["tds_mismatch"]["trigger"]
            })

        # GST compliance
        turnover = user_data.get("turnover", 0)
        gst_registered = user_data.get("gst_registered", False)

        if turnover > self.fy_2024_25_data["gst"]["registration_threshold"] and not gst_registered:
            flags.append({
                "flag": red_flag_patterns["gst_compliance_gap"]["flag"],
                "severity": red_flag_patterns["gst_compliance_gap"]["severity"],
                "trigger": red_flag_patterns["gst_compliance_gap"]["trigger"]
            })

        return flags

    async def get_common_mistakes(self) -> list[str]:
        """Get common ITR filing mistakes"""
        return self.fy_2024_25_data["common_itr_mistakes"]

    async def format_currency(self, amount: float) -> str:
        """Format amount in Indian Rupees with proper formatting"""
        # Indian number system: 10,00,000 instead of 1,000,000
        amount_str = f"{amount:,.2f}"
        parts = amount_str.split(".")

        # Convert to Indian numbering
        number = parts[0].replace(",", "")

        # Split into groups of 2 from right, except first group
        if len(number) <= 3:
            indian_format = number
        else:
            # Group by 2 from right
            groups = []
            n = number

            # First group (last 3 digits)
            if len(n) > 3:
                groups.append(n[-3:])
                n = n[:-3]
            else:
                groups.append(n)
                n = ""

            # Remaining groups by 2
            while len(n) > 0:
                if len(n) <= 2:
                    groups.append(n)
                    n = ""
                else:
                    groups.append(n[-2:])
                    n = n[:-2]

            # Reverse and join
            groups.reverse()
            indian_format = ",".join(groups)

        if len(parts) > 1:
            return f"₹{indian_format}.{parts[1]}"
        return f"₹{indian_format}"


# Global instance
india_tax_data = IndiaTaxDataFetcher()


async def get_india_tax_data() -> IndiaTaxDataFetcher:
    """Get India tax data fetcher instance"""
    return india_tax_data
