"""Lifting a figure off a page — PRC-012.

The admission gate (PRC-010) will only accept a number that a deterministic
extractor produced. This is that extractor. It is the half of search-and-verify
that decides whether the whole idea works, because everything upstream can be
correct and still be worthless if the thing reading the page is a model with a
regex bolted on for appearances.

Four rules, and each one is a refusal
--------------------------------------
**The extractor names itself.** `extracted_by` is set inside these functions
and is never a parameter. A caller cannot label its own output `html_table_cell`
while actually eyeballing prose — the only way to get that label is to have gone
through the table reader. This is what makes the admission check meaningful
rather than a string comparison against a promise.

**Anchored, never positional.** A cell is found by its row and column HEADERS,
not by index. `rows[3][2]` is correct until someone upstream inserts a column,
at which point it silently starts reading the wrong number off a page that still
parses cleanly. There is no error to notice. Header text at least fails loudly
when the page is restructured.

**Ambiguity is refused, never resolved.** If a label appears twice on a page
with two different figures beside it, this returns nothing. Taking the first is
a guess wearing a deterministic costume, and it is the more dangerous kind of
guess because it comes with a provenance trail attesting that a parser did it.

**The raw text is preserved.** `raw_value` is the literal substring from the
page — "5%", "₹1,50,000" — not a normalised Decimal. Admission re-parses it, so
the parse is visible and re-checkable, and a human auditing the fact sees what
was actually written rather than what someone's parser concluded.

Why every function returns a reason
------------------------------------
An extractor that returns `None` tells the sweep nothing, and the resulting Gap
says only "nothing was found". But "the label was on the page twice with
different figures" and "the page does not mention this at all" call for
completely different fixes. `Extraction` carries the note so the sweep log is
useful to whoever has to go and look.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any

from backend.core.provenance.admission import CandidateFact

# Kept in step with `extractors.deterministic` in admission.yaml. A name here
# that is not there means the extraction is rejected downstream, which is the
# right failure — the pack is the authority, this is the implementation.
RATE_EXTRACTOR = "regex_rate"
RUPEE_EXTRACTOR = "regex_rupee"
TABLE_EXTRACTOR = "html_table_cell"
PDF_TABLE_EXTRACTOR = "pdf_table_cell"
JSON_EXTRACTOR = "json_field"
CSV_EXTRACTOR = "csv_column"

DEFAULT_WINDOW = 200


@dataclass(frozen=True, slots=True)
class Extraction:
    """What was lifted, or why nothing was."""

    candidate: CandidateFact | None
    note: str

    @property
    def ok(self) -> bool:
        return self.candidate is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "note": self.note,
            "raw_value": self.candidate.raw_value if self.candidate else None,
        }


def found(extractions: list[Extraction]) -> list[CandidateFact]:
    """The candidates, for handing to `admit`. Notes stay behind in the log."""
    return [e.candidate for e in extractions if e.candidate is not None]


# ── patterns ────────────────────────────────────────────────────────────────
# Deliberately narrow. A pattern that matches more finds more wrong numbers.

_RATE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|per\s*cent\b|percent\b)", re.IGNORECASE,
)
_RUPEE = re.compile(
    r"(?:₹|Rs\.?\s*|INR\s*)\s?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:lakhs?|lacs?|crores?|cr)\b)?",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def _rate_value(raw: str) -> Decimal | None:
    m = re.search(r"\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        return Decimal(m.group(0)) / Decimal(100)
    except InvalidOperation:
        return None


def _rupee_value(raw: str) -> Decimal | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        value = Decimal(m.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    lowered = raw.lower()
    if "crore" in lowered or re.search(r"\bcr\b", lowered):
        value *= Decimal(10_000_000)
    elif "lakh" in lowered or "lac" in lowered:
        value *= Decimal(100_000)
    return value


# ── anchored text extraction ────────────────────────────────────────────────

def _near(
    text: str,
    *,
    label: str,
    pattern: re.Pattern[str],
    valuer,
    kind: str,
    extractor: str,
    key: str,
    source_url: str,
    fetched_on: date,
    window: int,
    source_kind: str,
    title: str,
) -> Extraction:
    haystack = _WS.sub(" ", text)
    needle = _norm(label)
    if not needle:
        return Extraction(None, "no label was given to anchor the search on.")

    lowered = haystack.lower()
    starts = [m.start() for m in re.finditer(re.escape(needle), lowered)]
    if not starts:
        return Extraction(
            None,
            f"the page does not mention {label!r}, so there is nothing to read "
            f"a figure next to.",
        )

    hits: list[tuple[str, Decimal, str]] = []
    for start in starts:
        segment = haystack[start:start + len(needle) + window]
        for m in pattern.finditer(segment):
            value = valuer(m.group(0))
            if value is None:
                continue
            hits.append((m.group(0), value, segment.strip()))
            break            # nearest figure to this occurrence of the label

    if not hits:
        return Extraction(
            None,
            f"{label!r} appears on the page but no {kind} follows it within "
            f"{window} characters.",
        )

    distinct = {v for _, v, _ in hits}
    if len(distinct) > 1:
        return Extraction(
            None,
            f"{label!r} appears {len(hits)} times with different figures "
            f"({sorted(str(v) for v in distinct)}). Refusing rather than "
            f"taking the first: a page that says two things needs a human to "
            f"say which one applies.",
        )

    raw, _, snippet = hits[0]
    return Extraction(
        CandidateFact(
            key=key,
            raw_value=raw,
            value_kind="rate" if kind == "rate" else "money",
            extracted_by=extractor,
            source_url=source_url,
            fetched_on=fetched_on,
            title=title,
            snippet=snippet[:400],
            source_kind=source_kind,
        ),
        f"read {raw!r} next to {label!r}.",
    )


def rate_near(
    text: str,
    *,
    label: str,
    key: str,
    source_url: str,
    fetched_on: date,
    window: int = DEFAULT_WINDOW,
    source_kind: str = "",
    title: str = "",
) -> Extraction:
    """A percentage sitting next to a named label in prose."""
    return _near(
        text, label=label, pattern=_RATE, valuer=_rate_value, kind="rate",
        extractor=RATE_EXTRACTOR, key=key, source_url=source_url,
        fetched_on=fetched_on, window=window, source_kind=source_kind,
        title=title,
    )


def rupees_near(
    text: str,
    *,
    label: str,
    key: str,
    source_url: str,
    fetched_on: date,
    window: int = DEFAULT_WINDOW,
    source_kind: str = "",
    title: str = "",
) -> Extraction:
    """An amount sitting next to a named label in prose."""
    return _near(
        text, label=label, pattern=_RUPEE, valuer=_rupee_value, kind="amount",
        extractor=RUPEE_EXTRACTOR, key=key, source_url=source_url,
        fetched_on=fetched_on, window=window, source_kind=source_kind,
        title=title,
    )


# ── tables ──────────────────────────────────────────────────────────────────

class _TableReader(HTMLParser):
    """A table reader on the standard library.

    No BeautifulSoup: this runs in the costing path and the dependency is not
    declared in requirements.txt, so relying on it would work in development
    and fail in a clean install.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append(_WS.sub(" ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._stack:
                self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def close(self) -> None:
        super().close()
        # An unclosed <table> is common in hand-written government HTML. Keep
        # what was parsed rather than discarding the page.
        while self._stack:
            self.tables.append(self._stack.pop())


def tables_from_html(html: str) -> list[list[list[str]]]:
    reader = _TableReader()
    reader.feed(html)
    reader.close()
    return reader.tables


def cell_from_rows(
    rows: list[list[str]],
    *,
    row_label: str,
    column_label: str,
    key: str,
    source_url: str,
    fetched_on: date,
    value_kind: str = "rate",
    source_kind: str = "",
    title: str = "",
    extractor: str = TABLE_EXTRACTOR,
) -> Extraction:
    """A cell located by its headers.

    Not by index. `rows[3][2]` keeps parsing cleanly after someone inserts a
    column and starts returning a different number with no error anywhere.
    """
    if not rows:
        return Extraction(None, "the page has no table in it.")

    header = [_norm(c) for c in rows[0]]
    want_col = _norm(column_label)
    matches = [i for i, h in enumerate(header) if want_col and want_col in h]
    if not matches:
        return Extraction(
            None,
            f"no column headed {column_label!r} — the table has {rows[0]}.",
        )
    if len(matches) > 1:
        return Extraction(
            None,
            f"{column_label!r} matches {len(matches)} columns "
            f"({[rows[0][i] for i in matches]}); the header is too vague to "
            f"read a figure from safely.",
        )
    col = matches[0]

    want_row = _norm(row_label)
    hits = [
        r for r in rows[1:]
        if r and want_row and want_row in _norm(r[0]) and len(r) > col
    ]
    if not hits:
        return Extraction(
            None, f"no row labelled {row_label!r} in that table.",
        )
    values = {_norm(r[col]) for r in hits}
    if len(values) > 1:
        return Extraction(
            None,
            f"{row_label!r} appears in {len(hits)} rows with different values "
            f"({sorted(values)}). Refusing rather than picking one.",
        )

    raw = hits[0][col].strip()
    if not raw:
        return Extraction(
            None,
            f"the cell at {row_label!r} × {column_label!r} is empty. An empty "
            f"cell is not a zero — a blank means the page did not say.",
        )
    return Extraction(
        CandidateFact(
            key=key, raw_value=raw, value_kind=value_kind,
            extracted_by=extractor, source_url=source_url,
            fetched_on=fetched_on, title=title, source_kind=source_kind,
            snippet=f"{hits[0][0]} | {rows[0][col]} | {raw}",
        ),
        f"read {raw!r} from {row_label!r} × {column_label!r}.",
    )


def cell_from_html(
    html: str,
    *,
    row_label: str,
    column_label: str,
    key: str,
    source_url: str,
    fetched_on: date,
    value_kind: str = "rate",
    source_kind: str = "",
    title: str = "",
) -> Extraction:
    """The first table on the page that has both headers.

    Scanning for the right table rather than taking `tables[0]` because a
    government page routinely wraps its content in a layout table.
    """
    tables = tables_from_html(html)
    if not tables:
        return Extraction(None, "the page has no table in it.")
    notes: list[str] = []
    for rows in tables:
        got = cell_from_rows(
            rows, row_label=row_label, column_label=column_label, key=key,
            source_url=source_url, fetched_on=fetched_on,
            value_kind=value_kind, source_kind=source_kind, title=title,
        )
        if got.ok:
            return got
        notes.append(got.note)
    return Extraction(
        None,
        f"none of the {len(tables)} table(s) on the page carried "
        f"{row_label!r} × {column_label!r}. Last: {notes[-1]}",
    )


def cell_from_pdf_rows(rows: list[list[str]], **kw) -> Extraction:
    """Same reader, labelled as having come from a PDF.

    The label matters because it travels with the fact into the evidence pack,
    and "read from a PDF table" and "read from an HTML table" are different
    claims about how re-checkable the figure is.
    """
    kw.setdefault("extractor", PDF_TABLE_EXTRACTOR)
    return cell_from_rows(rows, **kw)


# ── structured formats ──────────────────────────────────────────────────────

def field_from_json(
    payload: Any,
    *,
    path: str,
    key: str,
    source_url: str,
    fetched_on: date,
    value_kind: str = "rate",
    source_kind: str = "",
    title: str = "",
) -> Extraction:
    """A dotted path into a published data file. `a.b.0.c`."""
    node = payload
    walked: list[str] = []
    for part in path.split("."):
        walked.append(part)
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return Extraction(
                None,
                f"the document has nothing at {'.'.join(walked)} (looked for "
                f"{path!r}).",
            )
    if isinstance(node, dict | list):
        return Extraction(
            None,
            f"{path!r} points at a {type(node).__name__}, not a figure.",
        )
    return Extraction(
        CandidateFact(
            key=key, raw_value=str(node), value_kind=value_kind,
            extracted_by=JSON_EXTRACTOR, source_url=source_url,
            fetched_on=fetched_on, title=title, source_kind=source_kind,
            snippet=f"{path} = {node}",
        ),
        f"read {node!r} from {path}.",
    )


def column_from_csv(
    text: str,
    *,
    row_label: str,
    column_label: str,
    key: str,
    source_url: str,
    fetched_on: date,
    value_kind: str = "rate",
    source_kind: str = "",
    title: str = "",
) -> Extraction:
    rows = [r for r in csv.reader(io.StringIO(text)) if r]
    got = cell_from_rows(
        rows, row_label=row_label, column_label=column_label, key=key,
        source_url=source_url, fetched_on=fetched_on, value_kind=value_kind,
        source_kind=source_kind, title=title, extractor=CSV_EXTRACTOR,
    )
    return got


__all__ = [
    "CSV_EXTRACTOR",
    "DEFAULT_WINDOW",
    "JSON_EXTRACTOR",
    "PDF_TABLE_EXTRACTOR",
    "RATE_EXTRACTOR",
    "RUPEE_EXTRACTOR",
    "TABLE_EXTRACTOR",
    "Extraction",
    "cell_from_html",
    "cell_from_pdf_rows",
    "cell_from_rows",
    "column_from_csv",
    "field_from_json",
    "found",
    "rate_near",
    "rupees_near",
    "tables_from_html",
]
