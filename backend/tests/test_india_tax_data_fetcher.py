import pytest
from backend.services.india_tax_data_fetcher import get_india_tax_data

@pytest.mark.asyncio
async def test_get_current_tax_data():
    fetcher = await get_india_tax_data()
    data = await fetcher.get_current_tax_data()
    assert isinstance(data, dict)
    assert data["financial_year"] == "2024-25"
    assert "tax_brackets" in data

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
    normal_brackets = await fetcher.get_tax_brackets(is_senior=False)
    senior_brackets = await fetcher.get_tax_brackets(is_senior=True)
    assert normal_brackets[0]["min"] == 0
    assert senior_brackets[0]["max"] == 500000

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
