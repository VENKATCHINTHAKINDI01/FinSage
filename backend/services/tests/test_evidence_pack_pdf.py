"""Evidence Pack rendering — EVD-006.

Lives here rather than in `backend/core/tests/` because the purity contract
forbids core from importing `backend.services`, and reportlab is I/O.

The keystone test is `test_every_figure_on_the_rendered_page_traces_to_the_engine`:
`numeric_provenance`, the same scorer that guards agent output, is run over the
text extracted from the FINISHED PDF with the pack's own appendix as ground
truth. A positive control immediately after it proves the check has teeth.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.provenance.evidence_pack import (
    ClosedWindow,
    InputRecord,
    build_pack,
)
from backend.core.provenance.money import rupees
from backend.core.tax_engine import TaxInput, compute_tax

FY = "2026-27"
WHEN = date(2026, 8, 12)


def _result(**kw):
    kw.setdefault("salary", rupees(1_500_000))
    kw.setdefault("deductions", {"80C": rupees(150_000)})
    return compute_tax(TaxInput(fy=FY, regime=kw.pop("regime", "new"), **kw))


def _pack(**kw):
    r = _result()
    base = {
        "title": "Tax computation",
        "fy": FY,
        "worksheets": [r.trace],
        "confidence": r.confidence,
        "generated_on": WHEN,
    }
    base.update(kw)
    return build_pack(**base)


class TestNoFigureComesFromProse:
    def test_every_figure_on_the_rendered_page_traces_to_the_engine(self) -> None:
        """The acceptance criterion, run for real.

        `numeric_provenance` is the same scorer that guards agent output: it
        extracts every numeric claim from prose and fails on any that no tool
        result produced. Here the "prose" is the text actually extracted from
        the finished PDF and the "tool results" are the pack's own appendix.
        A pass means no number reached the page from anywhere but the engine.
        """
        pdfplumber = pytest.importorskip("pdfplumber")

        import io

        from backend.evals.scorers.numeric_provenance import (
            NumericProvenanceScorer,
        )
        from backend.evals.types import AgentInvocation
        from backend.services.evidence_pack_pdf import render_pack_pdf

        pack = _pack(inputs=[
            InputRecord("Salary", "₹15,00,000", "Form 16"),
            InputRecord("80C investments", "₹1,50,000", "you stated"),
        ])
        with pdfplumber.open(io.BytesIO(render_pack_pdf(pack))) as pdf:
            page_text = "\n".join(p.extract_text() or "" for p in pdf.pages)

        invocation = AgentInvocation(
            agent="evidence_pack",
            query="render the pack",
            profile={i.label: i.value for i in pack.inputs},
            tool_results=[{"result": pack.appendix()}],
            output_text=page_text,
        )
        score = NumericProvenanceScorer().score({}, invocation)
        assert score.verdict.name == "PASS", score.detail

    def test_the_check_above_would_catch_a_fabricated_figure(self) -> None:
        """The positive control. Without this, the test above could be passing
        because the scorer finds nothing rather than because the pack is clean.

        A note containing an invented rupee amount — the exact shape of an LLM
        slipping a number into a document — must fail.
        """
        from backend.evals.scorers.numeric_provenance import (
            NumericProvenanceScorer,
        )
        from backend.evals.types import AgentInvocation

        pack = _pack()
        invocation = AgentInvocation(
            agent="evidence_pack",
            query="render the pack",
            profile={},
            tool_results=[{"result": pack.appendix()}],
            output_text="Your tax works out to ₹46,800 on these figures.",
        )
        score = NumericProvenanceScorer().score({}, invocation)
        assert score.verdict.name == "FAIL", (
            "the scorer did not catch an invented figure, so the clean result "
            "above proves nothing"
        )
        # The offending figure is quoted in `evidence`, with surrounding
        # context, so a developer reading a CI failure can see what was
        # invented and where.
        assert any("46,800" in e for e in score.evidence)


# ══ rendering, and never to disk ════════════════════════════════════════════

class TestRendering:
    def test_it_renders_to_bytes(self) -> None:
        from backend.services.evidence_pack_pdf import render_pack_pdf

        pdf = render_pack_pdf(_pack(
            inputs=[InputRecord("Salary", "₹15,00,000", "Form 16")],
            closed_windows=[ClosedWindow(
                "EV loan interest", date(2023, 3, 31), rupees(150_000),
                "Window closed.", "80EEB",
            )],
        ))
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 5_000

    def test_the_renderer_takes_no_path_argument(self) -> None:
        """v1's `exports/` directory existed because a path parameter existed.
        A function that cannot be told where to write cannot write there."""
        import inspect

        from backend.services import evidence_pack_pdf

        params = inspect.signature(evidence_pack_pdf.render_pack_pdf).parameters
        assert list(params) == ["pack"]
        assert not any(
            n in params for n in ("path", "filename", "output", "dest", "file_path")
        )

    def test_the_source_has_no_open_call(self) -> None:
        import pathlib

        src = pathlib.Path(
            "backend/services/evidence_pack_pdf.py"
        ).read_text(encoding="utf-8")
        assert "open(" not in src.replace("SimpleDocTemplate", "")
        assert '"wb"' not in src and "'wb'" not in src

    def test_stored_packs_go_to_the_vault_with_a_short_lived_url(self) -> None:
        from backend.services.evidence_pack_pdf import store_pack
        from backend.vault.store import DocumentVault, MemoryVault

        vault = DocumentVault(backend=MemoryVault())
        out = store_pack(_pack(), "alice", vault)

        assert out["content_hash"]
        assert "expires_in=" in out["download_url"]
        assert out["document"]["kind"] == "evidence_pack"
        assert "owner_id" not in out["document"]

    def test_another_user_cannot_fetch_it(self) -> None:
        from backend.services.evidence_pack_pdf import store_pack
        from backend.vault.store import AccessDenied, DocumentVault, MemoryVault

        vault = DocumentVault(backend=MemoryVault())
        out = store_pack(_pack(), "alice", vault)
        with pytest.raises(AccessDenied):
            vault.fetch(out["document"]["document_id"], "mallory")


def test_the_pdf_text_contains_the_computed_figures_and_the_citations() -> None:
    """End-to-end: what is actually on the page, read back out of the PDF."""
    pdfplumber = pytest.importorskip("pdfplumber")

    import io

    from backend.services.evidence_pack_pdf import render_pack_pdf

    pack = _pack(inputs=[InputRecord("Salary", "₹15,00,000", "Form 16")])
    with pdfplumber.open(io.BytesIO(render_pack_pdf(pack))) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    assert "97,500" in text                       # the computed liability
    assert "s.115BAC" in text or "115BAC" in text  # a citation
    assert pack.rule_pack_verified_on.isoformat() in text
    assert pack.content_hash()[:16] in text
