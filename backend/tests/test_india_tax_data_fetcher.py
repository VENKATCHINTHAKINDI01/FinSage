from itertools import pairwise

import pytest

from backend.services.india_tax_data_fetcher import get_india_tax_data


@pytest.mark.asyncio
async def test_get_current_tax_data():
    fetcher = await get_india_tax_data()
    data = await fetcher.get_current_tax_data()
    assert isinstance(data, dict)

    # AGT-001: this asserted "2024-25" against a hardcoded dict, so it passed
    # for three Budgets after the figures behind it went stale. It now asserts
    # that the data tracks the REAL current year and carries the rule pack it
    # came from — a claim that cannot rot the same way.
    from datetime import date

    from backend.core.rules.loader import fy_for_date

    assert data["financial_year"] == fy_for_date(date.today())
    assert data["rule_pack_version"].startswith("fy_")
    assert data["verified_on"]

    # The wrong figures this feature existed to remove.
    limits = data["deduction_limits"]
    assert limits["80C"]["limit"] == 150000
    assert limits["80D"].get("limit") != 150000, "80D is not 80C's ceiling"
    assert limits["80CCD_1B"]["limit"] == 50000, "80CCD(1B) is 50,000, not 1.5L"

    # No `tax_brackets` key: they depend on regime and age, so a single list
    # cannot be correct for everyone. get_tax_brackets(regime, age) instead.
    assert "tax_brackets" not in data
    assert "senior_citizen_brackets" not in data
    assert "no age-based slabs" in data["note"]

@pytest.mark.asyncio
async def test_get_itr_forms():
    fetcher = await get_india_tax_data()
    forms = await fetcher.get_itr_forms()
    assert isinstance(forms, dict)
    assert "ITR-1" in forms
    assert "ITR-2" in forms

@pytest.mark.asyncio
async def test_get_deduction_limits():
    fetcher = await get_india_tax_data()
    limits = await fetcher.get_deduction_limits()
    assert isinstance(limits, dict)
    assert limits["80C"]["limit"] == 150000

@pytest.mark.asyncio
async def test_get_red_flags():
    fetcher = await get_india_tax_data()
    flags = await fetcher.get_red_flags()
    assert isinstance(flags, dict)
    assert "high_income_low_deductions" in flags

@pytest.mark.asyncio
async def test_get_important_dates():
    fetcher = await get_india_tax_data()
    dates = await fetcher.get_important_dates()
    assert isinstance(dates, dict)
    assert "fy_start" in dates

@pytest.mark.asyncio
async def test_get_tax_brackets():
    fetcher = await get_india_tax_data()
    # AGT-001: these came from a hardcoded FY 2024-25 dict. They now come from
    # the rule pack, so the assertions are about SHAPE and ordering rather than
    # about frozen amounts that go stale every Budget — the specific figures
    # are golden-tested in backend/core/tests.
    normal_brackets = await fetcher.get_tax_brackets(is_senior=False)
    assert normal_brackets[0]["min"] == 0
    assert normal_brackets[0]["rate"] == 0.0
    assert normal_brackets[-1]["max"] is None, "the top band is open-ended"
    for lower, upper in pairwise(normal_brackets):
        assert lower["max"] == upper["min"], "bands must be contiguous"
        assert upper["rate"] >= lower["rate"], "rates must be progressive"

    # The NEW regime has no age bands at all, which the old boolean could not
    # express. Age only moves the OLD regime's basic exemption.
    assert await fetcher.get_tax_brackets(is_senior=True) == normal_brackets
    old_senior = await fetcher.get_tax_brackets(is_senior=True, regime="old")
    old_normal = await fetcher.get_tax_brackets(is_senior=False, regime="old")
    assert old_senior[0]["max"] > old_normal[0]["max"]

@pytest.mark.asyncio
async def test_get_gst_rules():
    fetcher = await get_india_tax_data()
    gst = await fetcher.get_gst_rules()
    assert gst["registration_threshold"] == 4000000

@pytest.mark.asyncio
async def test_validate_itr_form():
    fetcher = await get_india_tax_data()

    # Salaried, simple
    form1 = await fetcher.validate_itr_form({
        "annual_income": 1200000,
        "has_capital_gains": False,
        "employment_type": "salaried"
    })
    assert form1 == "ITR-1"

    # Capital gains
    form2 = await fetcher.validate_itr_form({
        "annual_income": 1200000,
        "has_capital_gains": True,
        "employment_type": "salaried"
    })
    assert form2 == "ITR-2"

    # Self-employed
    form3 = await fetcher.validate_itr_form({
        "annual_income": 1200000,
        "has_capital_gains": False,
        "employment_type": "business"
    })
    assert form3 == "ITR-4"

    # High income
    form4 = await fetcher.validate_itr_form({
        "annual_income": 6000000,
        "has_capital_gains": False,
        "employment_type": "salaried"
    })
    assert form4 == "ITR-5"

@pytest.mark.asyncio
async def test_check_gst_requirement():
    fetcher = await get_india_tax_data()

    res1 = await fetcher.check_gst_requirement(3500000)
    assert res1["gst_required"] is False

    res2 = await fetcher.check_gst_requirement(4500000)
    assert res2["gst_required"] is True

@pytest.mark.asyncio
async def test_detect_red_flags():
    fetcher = await get_india_tax_data()

    # Test high income low deductions
    user_data = {
        "annual_income": 2500000,
        "deductions": {
            "80C": {"amount": 50000}
        }
    }
    flags = await fetcher.detect_red_flags(user_data)
    assert any(f["flag"] == "High income with low deductions" for f in flags)

    # Test TDS mismatch
    user_data_tds = {
        "calculated_tax": 200000,
        "tds_paid": 150000
    }
    flags_tds = await fetcher.detect_red_flags(user_data_tds)
    assert any(f["flag"] == "TDS paid vs salary mismatch" for f in flags_tds)

    # Test GST compliance gap
    user_data_gst = {
        "turnover": 5000000,
        "gst_registered": False
    }
    flags_gst = await fetcher.detect_red_flags(user_data_gst)
    assert any(f["flag"] == "GST compliance issue" for f in flags_gst)

@pytest.mark.asyncio
async def test_format_currency():
    fetcher = await get_india_tax_data()

    assert await fetcher.format_currency(1000) == "₹1,000.00"
    assert await fetcher.format_currency(100000) == "₹1,00,000.00"
    assert await fetcher.format_currency(10000000) == "₹1,00,00,000.00"
    assert await fetcher.format_currency(1234567.89) == "₹12,34,567.89"


# ── AGT-001: the regression guard ───────────────────────────────────────────

def test_no_hardcoded_rate_table_survives_in_this_module():
    """The defect was structural, not arithmetic.

    A dict of rates inside this file cannot know what year it is, so it went
    stale silently for three Budgets while four production modules read it. The
    check is therefore "is there a rate table here at all", not "are the
    numbers right" — right numbers in a frozen table are next year's wrong
    numbers.
    """
    import ast
    import pathlib
    import re

    import backend.services.india_tax_data_fetcher as mod

    tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))

    # The precise shape of what was removed: a dict literal mapping a SECTION
    # CODE to a figure. Checking for the key names alone was too blunt — those
    # still appear as output keys built from live pack data, which is the fix
    # rather than the defect.
    section = re.compile(r"^(?:80[A-Z]{0,4}(?:\(\d[A-Z]?\))?|24\(?b\)?|10\(13A\))$")
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if not section.match(key.value):
                continue
            if isinstance(value, (ast.Constant, ast.Dict)):
                offenders.append(f"{key.value} -> {ast.unparse(value)[:40]}")
    assert not offenders, f"section-keyed figures back in the module: {offenders}"


@pytest.mark.asyncio
async def test_the_year_follows_the_calendar_not_a_constant():
    from datetime import date

    from backend.core.rules.loader import fy_for_date

    fetcher = await get_india_tax_data()
    for fy in ("2024-25", "2025-26", "2026-27"):
        data = await fetcher.get_current_tax_data(fy)
        assert data["financial_year"] == fy
    assert (await fetcher.get_current_tax_data())["financial_year"] == fy_for_date(
        date.today(),
    )


@pytest.mark.asyncio
async def test_an_unknown_year_raises_rather_than_resolving_to_the_nearest():
    from backend.core.rules.loader import RuleError

    fetcher = await get_india_tax_data()
    with pytest.raises(RuleError):
        await fetcher.get_current_tax_data("2031-32")


@pytest.mark.asyncio
async def test_advance_tax_dates_land_in_the_right_calendar_year():
    """The fourth instalment falls in March, which is the SECOND calendar year
    of the financial year — an off-by-one here dates it twelve months early."""
    fetcher = await get_india_tax_data()
    dates = await fetcher.get_important_dates("2026-27")
    assert dates["q1_advance_tax"] == "2026-06-15"
    assert dates["q4_advance_tax"] == "2027-03-15"


@pytest.mark.asyncio
async def test_deadline_aliases_track_the_pack_rather_than_a_frozen_date():
    fetcher = await get_india_tax_data()
    dates = await fetcher.get_important_dates("2026-27")
    assert dates["itr_normal_deadline"] == dates["itr_non_audit"]
    assert dates["itr_extended_deadline"] == dates["itr_business_non_audit"]
    assert dates["itr_normal_deadline"].startswith("2027-")
