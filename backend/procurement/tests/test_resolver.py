"""Free text to a structured item — PRC-001."""

from __future__ import annotations

import yaml

from backend.core.costing.landed_cost import _load
from backend.core.eligibility.evaluator import RULES_FILE
from backend.procurement.resolver import (
    ResolvedItem,
    confirm,
    looks_like_a_figure,
    money_typed_fields,
    resolve,
)

CFG = _load("procurement.yaml")
PROFILES = tuple(
    yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))["meta"]["buyer_profiles"]
)
CATEGORIES = ("rooftop_solar", "electric_vehicle", "motor_vehicle", "tractor")


def run(extracted, text="whatever the user typed"):
    return resolve(text, lambda _: extracted, cfg=CFG,
                   buyer_profiles=PROFILES, known_categories=CATEGORIES)


COMPLETE = {
    "family": "home_and_durables",
    "category": "rooftop_solar",
    "state": "KA",
    "buyer_profile": "government_employee",
}


# ── the boundary, enforced by the type ──────────────────────────────────────

def test_the_resolved_item_has_nowhere_to_put_a_rupee_figure():
    """Not a validated field, not an optional one — no field of that kind
    exists, so the guarantee survives someone adding a convenient
    `estimated_price` in a hurry."""
    assert money_typed_fields() == []


def test_a_figure_from_the_extractor_is_dropped_and_named():
    got = run({**COMPLETE, "estimated_price": "₹2,50,000"})
    assert got.item is not None
    assert "estimated_price" not in got.item.specs
    assert any("estimated_price" in r for r in got.refused)
    assert any("no provenance beyond the model" in r for r in got.refused)


def test_a_rate_from_the_extractor_is_dropped_too():
    got = run({**COMPLETE, "gst_rate": "18%"})
    assert "gst_rate" not in got.item.specs
    assert got.refused


def test_scale_words_are_caught_even_without_a_currency_mark():
    assert looks_like_a_figure("2.5 lakh")
    assert looks_like_a_figure("1 crore")
    assert looks_like_a_figure("Rs 40,000")


def test_bare_structural_numbers_are_not_treated_as_figures():
    """"3kW" and "5 seats" are legitimate structure. A rule that caught every
    digit would leave the resolver unable to describe anything."""
    assert not looks_like_a_figure("3kW")
    assert not looks_like_a_figure("5")
    assert not looks_like_a_figure("BS6")


# ── closed vocabularies ─────────────────────────────────────────────────────

def test_an_unknown_family_becomes_a_question_not_the_nearest_match():
    """Quietly mapping an unrecognised phrase onto a known category is how a
    tractor gets costed as a car — silently, with a plausible number at the
    end of it."""
    got = run({**COMPLETE, "family": "farm_stuff"})
    assert got.item is None
    q = next(q for q in got.questions if q.field_name == "family")
    assert q.suggestion == "farm_stuff"
    assert "home_and_durables" in q.options


def test_an_unknown_category_is_asked_about_with_the_options():
    got = run({**COMPLETE, "category": "solar thingy"})
    assert got.item is None
    q = next(q for q in got.questions if q.field_name == "category")
    assert q.suggestion == "solar thingy"
    assert set(q.options) == set(CATEGORIES)


def test_an_unknown_buyer_profile_becomes_a_question():
    got = run({**COMPLETE, "buyer_profile": "engineer"})
    assert got.item is None
    q = next(q for q in got.questions if q.field_name == "buyer_profile")
    assert "government_employee" in q.options
    assert "different answer" in q.why


# ── missing means ask ───────────────────────────────────────────────────────

def test_a_missing_state_is_asked_for_rather_than_defaulted():
    """Road tax and stamp duty are state levies. A defaulted state is a wrong
    answer that looks right, and the buyer cannot tell."""
    got = run({k: v for k, v in COMPLETE.items() if k != "state"})
    assert got.item is None
    q = next(q for q in got.questions if q.field_name == "state")
    assert "state levies" in q.why


def test_every_question_says_what_it_is_for():
    """A user asked for a value with no reason given will guess."""
    got = run({})
    assert got.questions
    for q in got.questions:
        assert q.why.strip()
        assert q.ask.strip()


def test_a_complete_extraction_resolves_with_no_questions():
    got = run(COMPLETE)
    assert got.complete
    assert isinstance(got.item, ResolvedItem)
    assert got.item.state == "KA"
    assert got.item.buyer_profile == "government_employee"


# ── numeric specs are suggestions ───────────────────────────────────────────

def test_a_numeric_spec_from_the_model_is_a_question_not_an_answer():
    """Battery capacity multiplies the per-kWh incentive. A model that guesses
    "probably 3 kW" has produced a rupee figure by proxy."""
    got = run({**COMPLETE, "capacity_kw": "3"})
    assert got.item is None
    q = next(q for q in got.questions if q.field_name == "capacity_kw")
    assert q.suggestion == "3"
    assert "decides the amount" in q.why


def test_the_suggestion_never_enters_the_item_on_its_own():
    got = run({**COMPLETE, "battery_kwh": "2.5"})
    assert got.item is None


def test_a_confirmed_spec_is_accepted():
    first = run({**COMPLETE, "capacity_kw": "3"})
    got = confirm(first, {"capacity_kw": "3"}, cfg=CFG,
                  buyer_profiles=PROFILES, known_categories=CATEGORIES)
    assert got.complete
    assert got.item.specs["capacity_kw"] == "3"


def test_a_confirmed_value_gets_no_special_trust():
    """A buyer who types "₹5 lakh" into the capacity box is refused exactly as
    a model would be."""
    first = run({**COMPLETE, "capacity_kw": "3"})
    got = confirm(first, {"capacity_kw": "₹5 lakh"}, cfg=CFG,
                  buyer_profiles=PROFILES, known_categories=CATEGORIES)
    assert "capacity_kw" not in (got.item.specs if got.item else {})


def test_answers_resolve_the_outstanding_questions():
    first = run({"family": "vehicles"})
    assert first.item is None
    got = confirm(
        first,
        {"category": "electric_vehicle", "state": "MH",
         "buyer_profile": "salaried_private"},
        cfg=CFG, buyer_profiles=PROFILES, known_categories=CATEGORIES,
    )
    assert got.complete
    assert got.item.family == "vehicles"
    assert got.item.category == "electric_vehicle"


# ── the model stays out of the imports ──────────────────────────────────────

def test_the_resolver_names_no_model():
    import pathlib

    import backend.procurement.resolver as mod

    text = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    for name in ("openai", "anthropic", "groq", "langchain", "llm_client"):
        assert f"import {name}" not in text


def test_serialises_with_the_questions_and_the_refusals():
    d = run({**COMPLETE, "estimated_price": "₹2,50,000",
             "capacity_kw": "3"}).to_dict()
    assert d["complete"] is False
    assert d["refused"]
    assert any(q["field"] == "capacity_kw" for q in d["questions"])
