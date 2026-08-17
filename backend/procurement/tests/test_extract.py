"""Lifting a figure off a page — PRC-012.

The point of an extractor is that it can be wrong in a way you notice. Most of
these tests are about the wrong answers it refuses to give.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from backend.core.provenance.admission import Verdict, admit
from backend.core.provenance.sourcing import Tier
from backend.procurement.extract import (
    RATE_EXTRACTOR,
    TABLE_EXTRACTOR,
    cell_from_html,
    cell_from_pdf_rows,
    cell_from_rows,
    column_from_csv,
    field_from_json,
    found,
    rate_near,
    rupees_near,
    tables_from_html,
)

SEEN = date(2026, 8, 13)
URL = "https://cbic.gov.in/rates"

COMMON = {
    "key": "gst.electric_vehicle",
    "source_url": URL,
    "fetched_on": SEEN,
    "source_kind": "gst",
}


# ── the label the extractor gives itself ────────────────────────────────────

def test_the_extractor_names_itself_and_the_name_is_not_a_parameter():
    """The load-bearing property of this module.

    If `extracted_by` were a parameter, a caller could label a model's guess
    `html_table_cell` and the admission gate would wave it through — the gate
    checks a string, and the string would be a lie. The only way to obtain the
    label is to have gone through the code that earns it.
    """
    import inspect

    from backend.procurement import extract

    for name in ("rate_near", "rupees_near", "cell_from_html",
                 "field_from_json", "column_from_csv"):
        params = inspect.signature(getattr(extract, name)).parameters
        assert "extracted_by" not in params, name


def test_every_extractor_label_is_one_the_rule_pack_accepts():
    """These two lists drift apart silently otherwise.

    An extractor whose label is missing from `extractors.deterministic` builds
    candidates that are always rejected — a working parser that produces
    nothing, with the failure looking like 'no source found'.
    """
    from backend.core.provenance.admission import load_admission_rules
    from backend.procurement import extract

    allowed = set(load_admission_rules()["extractors"]["deterministic"])
    ours = {
        getattr(extract, n) for n in dir(extract) if n.endswith("_EXTRACTOR")
    }
    assert ours <= allowed, f"not in admission.yaml: {sorted(ours - allowed)}"


def test_an_extracted_candidate_survives_admission_end_to_end():
    """The seam that matters: what comes out here is admissible there."""
    got = rate_near(
        "GST on electric vehicles is levied at 5% with effect from 2025.",
        label="electric vehicles", **COMMON,
    )
    assert got.ok
    assert got.candidate.extracted_by == RATE_EXTRACTOR
    verdict = admit("gst.electric_vehicle", found([got]))
    assert verdict.verdict is Verdict.ADMITTED
    assert verdict.fact.tier is Tier.OFFICIAL


# ── anchored prose ──────────────────────────────────────────────────────────

def test_a_rate_is_read_next_to_its_label():
    got = rate_near("Road tax in Karnataka: 13% for petrol vehicles.",
                    label="Karnataka", key="road_tax.KA",
                    source_url=URL, fetched_on=SEEN)
    assert got.candidate.raw_value == "13%"


def test_the_raw_page_text_is_preserved_not_a_normalised_number():
    """A human auditing the fact should see what the page actually said."""
    got = rate_near("Levy: 5 per cent.", label="Levy", **COMMON)
    assert got.candidate.raw_value == "5 per cent"


def test_a_label_that_is_not_on_the_page_reads_nothing():
    got = rate_near("Nothing relevant here.", label="stamp duty",
                    key="stamp_duty.MH", source_url=URL, fetched_on=SEEN)
    assert not got.ok
    assert "does not mention" in got.note


def test_a_label_with_no_figure_near_it_reads_nothing():
    got = rate_near(
        "Electric vehicles are covered by a separate notification. " + "x" * 500
        + " 5%",
        label="Electric vehicles", **COMMON,
    )
    assert not got.ok
    assert "within" in got.note


def test_two_different_figures_under_one_label_are_refused():
    """Taking the first is a guess wearing a deterministic costume, and it is
    the more dangerous kind because it arrives with a provenance trail."""
    got = rate_near(
        "Stamp duty is 6%. Elsewhere: stamp duty is 5% for women buyers.",
        label="stamp duty", key="stamp_duty.MH", source_url=URL,
        fetched_on=SEEN,
    )
    assert not got.ok
    assert "Refusing rather than taking the first" in got.note
    assert "0.05" in got.note and "0.06" in got.note


def test_the_same_figure_repeated_is_not_ambiguous():
    got = rate_near("GST is 5%. As noted, GST is 5.0% on these.",
                    label="GST", **COMMON)
    assert got.ok
    assert got.candidate.raw_value == "5%"


def test_amounts_read_with_indian_scale_words():
    for text, expected in [
        ("Subsidy cap: ₹1,50,000 per unit.", "₹1,50,000"),
        ("Subsidy cap: Rs. 1.5 lakh per unit.", "Rs. 1.5 lakh"),
    ]:
        got = rupees_near(text, label="Subsidy cap", key="price.cap",
                          source_url=URL, fetched_on=SEEN)
        assert got.candidate.raw_value == expected


def test_scale_words_are_compared_by_value_not_by_text():
    """'₹1,50,000' and '1.5 lakh' are the same figure written two ways, so a
    page carrying both is not contradicting itself."""
    got = rupees_near(
        "Cap is ₹1,50,000. The cap is Rs. 1.5 lakh in all states.",
        label="cap", key="price.cap", source_url=URL, fetched_on=SEEN,
    )
    assert got.ok

    # And the same for crore, which is the scale where dropping the multiplier
    # is worth a factor of ten million rather than a rounding argument.
    crore = rupees_near(
        "Turnover limit is ₹2,00,00,000. The limit is Rs. 2 crore.",
        label="limit", key="price.limit", source_url=URL, fetched_on=SEEN,
    )
    assert crore.ok


def test_extraction_is_deterministic_over_the_same_bytes():
    """The whole claim of 'deterministic extractor' in one assertion."""
    text = "GST on electric vehicles is 5% and on petrol cars is 40%."
    runs = {
        rate_near(text, label="electric vehicles", **COMMON).candidate.raw_value
        for _ in range(20)
    }
    assert runs == {"5%"}


# ── tables ──────────────────────────────────────────────────────────────────

HTML = """
<html><body>
<table><tr><td>site navigation</td></tr></table>
<table>
  <tr><th>State</th><th>EV rate</th><th>Petrol rate</th></tr>
  <tr><td>Karnataka</td><td>0%</td><td>13%</td></tr>
  <tr><td>Maharashtra</td><td>0%</td><td>11%</td></tr>
</table>
</body></html>
"""


def test_a_cell_is_found_by_its_headers():
    got = cell_from_html(HTML, row_label="Karnataka", column_label="Petrol",
                         key="road_tax.KA", source_url=URL, fetched_on=SEEN)
    assert got.candidate.raw_value == "13%"


def test_the_layout_table_is_skipped_to_reach_the_real_one():
    """Government pages routinely wrap content in a layout table, so taking
    tables[0] reads the navigation bar."""
    assert len(tables_from_html(HTML)) == 2
    got = cell_from_html(HTML, row_label="Maharashtra", column_label="EV rate",
                         key="road_tax.MH", source_url=URL, fetched_on=SEEN)
    assert got.candidate.raw_value == "0%"


def test_an_inserted_column_does_not_silently_shift_the_answer():
    """The case that positional indexing gets wrong with no error anywhere.

    `rows[1][2]` is 13% before the insert and 13% after only by luck; here the
    header is what is asked for, so the right cell is still found.
    """
    shifted = HTML.replace(
        "<th>State</th>", "<th>State</th><th>Region</th>",
    ).replace(
        "<td>Karnataka</td>", "<td>Karnataka</td><td>South</td>",
    ).replace(
        "<td>Maharashtra</td>", "<td>Maharashtra</td><td>West</td>",
    )
    got = cell_from_html(shifted, row_label="Karnataka",
                         column_label="Petrol", key="road_tax.KA",
                         source_url=URL, fetched_on=SEEN)
    assert got.candidate.raw_value == "13%"


def test_a_vague_column_header_is_refused_rather_than_guessed():
    got = cell_from_html(HTML, row_label="Karnataka", column_label="rate",
                         key="road_tax.KA", source_url=URL, fetched_on=SEEN)
    assert not got.ok


def test_an_empty_cell_is_not_a_zero():
    """A blank means the page did not say. Reading it as 0% would produce a
    road-tax-exempt state out of a formatting artefact."""
    rows = [["State", "EV rate"], ["Kerala", ""]]
    got = cell_from_rows(rows, row_label="Kerala", column_label="EV rate",
                         key="road_tax.KL", source_url=URL, fetched_on=SEEN)
    assert not got.ok
    assert "not a zero" in got.note


def test_a_duplicated_row_with_conflicting_values_is_refused():
    rows = [["State", "EV rate"], ["Kerala", "0%"], ["Kerala", "5%"]]
    got = cell_from_rows(rows, row_label="Kerala", column_label="EV rate",
                         key="road_tax.KL", source_url=URL, fetched_on=SEEN)
    assert not got.ok
    assert "Refusing rather than picking one" in got.note


def test_a_missing_header_says_what_the_table_actually_had():
    got = cell_from_html(HTML, row_label="Karnataka", column_label="Diesel",
                         key="road_tax.KA", source_url=URL, fetched_on=SEEN)
    assert not got.ok
    assert "Diesel" in got.note


def test_an_unclosed_table_still_parses():
    """Hand-written government HTML routinely omits the closing tag; throwing
    the page away over it would lose a Tier-1 source to a typo."""
    broken = "<table><tr><th>State</th><th>EV rate</th></tr>" \
             "<tr><td>Goa</td><td>0%</td></tr>"
    got = cell_from_html(broken, row_label="Goa", column_label="EV rate",
                         key="road_tax.GA", source_url=URL, fetched_on=SEEN)
    assert got.candidate.raw_value == "0%"


def test_a_pdf_table_carries_a_different_label():
    """'Read from a PDF table' and 'read from an HTML table' are different
    claims about how re-checkable the figure is, and the label travels into the
    evidence pack."""
    rows = [["State", "EV rate"], ["Goa", "0%"]]
    got = cell_from_pdf_rows(rows, row_label="Goa", column_label="EV rate",
                             key="road_tax.GA", source_url=URL,
                             fetched_on=SEEN)
    assert got.candidate.extracted_by == "pdf_table_cell"
    assert cell_from_rows(rows, row_label="Goa", column_label="EV rate",
                          key="road_tax.GA", source_url=URL,
                          fetched_on=SEEN).candidate.extracted_by \
        == TABLE_EXTRACTOR


# ── structured formats ──────────────────────────────────────────────────────

def test_a_json_path_is_walked_through_lists_and_dicts():
    payload = {"rates": [{"category": "ev", "gst": "5%"}]}
    got = field_from_json(payload, path="rates.0.gst", key="gst.ev",
                          source_url=URL, fetched_on=SEEN)
    assert got.candidate.raw_value == "5%"


def test_a_json_path_that_misses_says_how_far_it_got():
    payload = {"rates": [{"category": "ev"}]}
    got = field_from_json(payload, path="rates.0.gst", key="gst.ev",
                          source_url=URL, fetched_on=SEEN)
    assert not got.ok
    assert "rates.0.gst" in got.note


def test_a_json_path_pointing_at_a_container_is_not_a_figure():
    got = field_from_json({"rates": {"ev": {}}}, path="rates.ev",
                          key="gst.ev", source_url=URL, fetched_on=SEEN)
    assert not got.ok
    assert "not a figure" in got.note


def test_csv_reads_by_header_too():
    text = "State,EV rate,Petrol rate\nKarnataka,0%,13%\n"
    got = column_from_csv(text, row_label="Karnataka",
                          column_label="Petrol rate", key="road_tax.KA",
                          source_url=URL, fetched_on=SEEN)
    assert got.candidate.raw_value == "13%"
    assert got.candidate.extracted_by == "csv_column"


# ── the boundary ────────────────────────────────────────────────────────────

AGENT_DIRS = ["backend/agents", "backend/tools", "backend/orchestrator"]


def test_no_agent_or_tool_module_constructs_a_candidate_directly():
    """A ratchet, in the shape of the one AGT-001 uses.

    `CandidateFact` is an ordinary dataclass, so nothing at the language level
    stops an agent module from building one with `extracted_by='regex_rate'`
    and a number the model produced. That would defeat the admission gate
    completely while passing every one of its checks. Agents must call an
    extractor; this is what says so.
    """
    root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []
    for directory in AGENT_DIRS:
        base = root / directory
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "/tests/" in str(path) or path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "CandidateFact"):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == [], (
        "these modules build a CandidateFact by hand instead of calling an "
        f"extractor, which bypasses the admission gate: {offenders}"
    )
