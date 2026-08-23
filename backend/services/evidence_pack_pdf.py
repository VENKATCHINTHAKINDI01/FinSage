"""Rendering an Evidence Pack to PDF — EVD-006.

Why this is not in core
-----------------------
reportlab is I/O and core is forbidden I/O by the import-linter contract. The
content model (`backend.core.provenance.evidence_pack`) is pure and testable;
this module only draws it. The split also means the page and the machine-readable
appendix come from one `PackContent`, so they cannot disagree about a figure.

Why it never touches local disk
-------------------------------
v1 wrote generated financial PDFs to `exports/tax_report_user-123_20260707.pdf`
— unencrypted, on the application's own filesystem, forty-one of them sitting in
the repository. This renders to `bytes` and hands them to the vault. There is no
filename parameter, because a filename parameter is how the old behaviour comes
back.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from backend.core.provenance.evidence_pack import PackContent

if TYPE_CHECKING:  # pragma: no cover
    from backend.vault.store import DocumentVault

# Solid black boxes are what you get for Unicode sub/superscripts in reportlab's
# built-in fonts, so nothing here uses them.
_PAGE_MARGIN = 40


def render_pack_pdf(pack: PackContent) -> bytes:
    """Draw the pack and return the bytes. No path, no file, no disk."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=_PAGE_MARGIN, rightMargin=_PAGE_MARGIN,
        topMargin=_PAGE_MARGIN, bottomMargin=_PAGE_MARGIN,
        title=pack.title, author="FinSage AI",
        subject=f"Tax computation evidence pack — FY {pack.fy}",
    )

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Heading1"], fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, spaceBefore=14,
                        spaceAfter=4)
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=12,
                          alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10,
                           textColor=colors.HexColor("#555555"))
    mono = ParagraphStyle("mono", parent=body, fontName="Courier", fontSize=7,
                          leading=9)

    story: list[Any] = []

    cell_style = ParagraphStyle(
        "cell", parent=base["Normal"], fontSize=7.5, leading=9,
        spaceBefore=0, spaceAfter=0,
    )

    def table(rows: list[list[str]], widths: list[float]) -> Table:
        # Cells WRAP rather than overflow.
        #
        # A plain string in a reportlab cell does not wrap: it runs straight
        # over the next column and the two overlap on the page. That surfaced
        # when CORE-002 verified the section concordance and citations grew a
        # 2025 section number — "FY 2026-27" in the Provision column collided
        # with "2026-08-09" in Last checked, and the text extracted as
        # "2026-272026-08-09". A reader sees overlapping glyphs; a parser sees
        # a number that is on no line of the document.
        #
        # Wrapping every non-header cell in a Paragraph is the fix, and it is
        # width-independent — the next long citation cannot reintroduce it.
        wrapped = [rows[0]] + [
            [
                cell if isinstance(cell, Paragraph)
                else Paragraph(str(cell).replace("&", "&amp;")
                               .replace("<", "&lt;"), cell_style)
                for cell in row
            ]
            for row in rows[1:]
        ]
        t = Table(wrapped, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#333333")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f6f6f6")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    # ── cover ───────────────────────────────────────────────────────────────
    story.append(Paragraph(pack.title, h1))
    story.append(Paragraph(
        f"Financial year {pack.fy} · Assessment year {pack.assessment_year} · "
        f"{pack.governing_act}", body,
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Generated {pack.generated_on.isoformat()}. Rules last verified "
        f"{pack.rule_pack_verified_on.isoformat()} against the sources listed "
        f"at the end of this document. Rule pack "
        f"<b>{pack.rule_pack_version or pack.rule_pack_id}</b>, content hash "
        f"<b>{pack.content_hash()[:16]}</b>. Regenerating from the same inputs "
        f"under the same rule pack reproduces this hash exactly; a different "
        f"rule pack version means the rules moved, not that the figures were "
        f"wrong.", small,
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Every figure in this document was computed by a deterministic rules "
        "engine from the inputs recorded below. None was produced by a language "
        "model. The arithmetic is shown in full so it can be checked line by "
        "line, and the appendix carries the same data in machine-readable form "
        "so the computation can be re-run independently.", body,
    ))

    # ── 1. inputs ───────────────────────────────────────────────────────────
    if pack.inputs:
        story.append(Paragraph("1. What this is based on", h2))
        rows = [["Item", "Value", "Where it came from"]]
        rows += [
            [i.label, i.value,
             ("ASSUMED — " + i.provenance) if i.is_assumption else i.provenance]
            for i in pack.inputs
        ]
        story.append(table(rows, [150, 110, 250]))
        if pack.assumptions:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                f"{len(pack.assumptions)} of these are assumptions rather than "
                f"facts you supplied. Each is marked ASSUMED. If any is wrong, "
                f"the figures below change — correct it and regenerate rather "
                f"than adjusting the result by hand.", small,
            ))

    # ── 2. the arithmetic ───────────────────────────────────────────────────
    story.append(Paragraph("2. The calculation, in full", h2))
    for trace in pack.worksheets:
        story.append(Paragraph(trace.title, ParagraphStyle(
            "ws", parent=body, fontName="Helvetica-Bold", spaceBefore=8,
        )))
        for line in trace.render().splitlines():
            story.append(Paragraph(line.replace("&", "&amp;"), mono))
        story.append(Spacer(1, 4))

    # ── 3. closed windows ───────────────────────────────────────────────────
    if pack.closed_windows:
        story.append(PageBreak())
        story.append(Paragraph("3. Benefits that are no longer available", h2))
        story.append(Paragraph(
            "These would have applied to you but their windows have closed. "
            "They are listed because guidance still circulating online "
            "describes several of them as current.", body,
        ))
        story.append(Spacer(1, 6))
        rows = [["Benefit", "Section", "Closed on", "Would have been worth"]]
        rows += [
            [w.name, w.legacy_section or "—",
             w.closed_on.strftime("%d %B %Y") if w.closed_on else "—",
             str(w.would_have_been_worth)]
            for w in pack.closed_windows
        ]
        story.append(table(rows, [180, 60, 100, 120]))

    # ── 4. authority for every figure ───────────────────────────────────────
    figures = pack.figures()
    if figures:
        story.append(Paragraph("4. Authority for each figure", h2))
        rows = [["Figure", "Amount", "Provision", "Last checked"]]
        rows += [
            [e.label, str(e.value), e.citation_display,
             e.verified_on.isoformat()]
            for e in figures
        ]
        story.append(table(rows, [150, 80, 200, 70]))

    # ── 5. confidence ───────────────────────────────────────────────────────
    if pack.confidence is not None:
        story.append(Paragraph("5. How much to trust this", h2))
        conf = pack.confidence.to_dict()
        story.append(Paragraph(
            f"Overall: <b>{conf.get('level', 'unknown')}</b>", body,
        ))
        for signal in conf.get("signals", []):
            story.append(Paragraph(
                f"— {signal.get('what', '')}: {signal.get('detail', '')}", small,
            ))

    # ── 6. sources ──────────────────────────────────────────────────────────
    story.append(Paragraph("6. Sources", h2))
    for url in pack.rule_pack_sources:
        story.append(Paragraph(url, small))

    if pack.notes:
        story.append(Paragraph("7. Notes and caveats", h2))
        for note in pack.notes:
            story.append(Paragraph(f"— {note}", body))

    # ── appendix ────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Appendix — machine-readable record", h2))
    story.append(Paragraph(
        "The complete computation in JSON, so this pack can be re-verified "
        "without retyping anything. `content_hash` covers the inputs, rules and "
        "arithmetic but NOT the generation date, so regenerating from the same "
        "inputs under the same rule pack produces the same hash.", small,
    ))
    story.append(Spacer(1, 6))
    blob = json.dumps(pack.appendix(), indent=1, ensure_ascii=False, default=str)
    for line in blob.splitlines():
        story.append(Paragraph(
            line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
            mono,
        ))

    story.append(Spacer(1, 6 * mm))
    story.append(KeepTogether(Paragraph(
        "This pack is a record of a computation, not tax advice. Confirm any "
        "position with a qualified professional before acting on it.", small,
    )))

    doc.build(story)
    return buf.getvalue()


def store_pack(
    pack: PackContent,
    owner_id: str,
    vault: DocumentVault,
    *,
    url_ttl: timedelta | None = None,
) -> dict[str, Any]:
    """Render into the vault and return a short-lived signed URL.

    The bytes never touch local disk. There is deliberately no variant of this
    function that takes a path — v1's `exports/` directory existed because such
    a variant existed.
    """
    from backend.vault.store import DocumentKind

    document = vault.store(
        owner_id=owner_id,
        data=render_pack_pdf(pack),
        filename=f"evidence-pack-{pack.fy}-{pack.content_hash()[:12]}.pdf",
        content_type="application/pdf",
        kind=DocumentKind.EVIDENCE_PACK,
    )
    return {
        "document": document.to_dict(),
        "download_url": vault.download_url(document.document_id, owner_id, url_ttl),
        "content_hash": pack.content_hash(),
        "input_hash": pack.input_hash(),
        "rule_pack_id": pack.rule_pack_id,
    }


__all__ = ["render_pack_pdf", "store_pack"]
