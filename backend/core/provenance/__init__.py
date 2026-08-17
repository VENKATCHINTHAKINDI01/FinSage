"""Value objects that make every figure defensible.

Money           Decimal-backed; refuses float entirely.
Citation        both 1961 and 2025 Act numbering, because the transition is live
Trace           the actual computation, replayable to the same value
Confidence      COMPOSED from measurable signals, never authored

On Confidence: for a deterministic engine the arithmetic is certain. All the
uncertainty lives in the inputs. Complete official inputs against a fresh rule
pack report CERTAIN — not 87%. Fake precision is a trust leak.
"""

from backend.core.provenance.citation import Citation, SectionAlias, SourceRef
from backend.core.provenance.confidence import Confidence, Level, Provenance, Signal
from backend.core.provenance.evidence_pack import (
    ClosedWindow,
    InputRecord,
    PackContent,
    build_pack,
    closed_windows_from_outcomes,
)
from backend.core.provenance.ledger import (
    Ledger,
    LedgerEntry,
    UndatedFigure,
    entry_from_citation,
    ledger_from_trace,
)
from backend.core.provenance.money import (
    ZERO,
    Money,
    format_rate,
    maximum,
    minimum,
    pct_of,
    rate,
    rupees,
)
from backend.core.provenance.panel import (
    AssumptionRow,
    EvidencePanel,
    build_panel,
)
from backend.core.provenance.reproduce import (
    FigureChange,
    Pin,
    ReplayMismatch,
    RuleDiff,
    Verification,
    assert_reproduces,
    diff_under,
    pin_of,
    verify,
)
from backend.core.provenance.trace import Op, Step, Trace

__all__ = [
    "ZERO",
    "AssumptionRow",
    "Citation",
    "ClosedWindow",
    "Confidence",
    "EvidencePanel",
    "FigureChange",
    "InputRecord",
    "Ledger",
    "LedgerEntry",
    "Level",
    "Money",
    "Op",
    "PackContent",
    "Pin",
    "Provenance",
    "ReplayMismatch",
    "RuleDiff",
    "SectionAlias",
    "Signal",
    "SourceRef",
    "Step",
    "Trace",
    "UndatedFigure",
    "Verification",
    "assert_reproduces",
    "build_pack",
    "build_panel",
    "closed_windows_from_outcomes",
    "diff_under",
    "entry_from_citation",
    "format_rate",
    "ledger_from_trace",
    "maximum",
    "minimum",
    "pct_of",
    "pin_of",
    "rate",
    "rupees",
    "verify",
]
