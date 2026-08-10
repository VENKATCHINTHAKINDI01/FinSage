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
from backend.core.provenance.trace import Op, Step, Trace

__all__ = [
    "ZERO",
    "Citation",
    "Confidence",
    "Level",
    "Money",
    "Op",
    "Provenance",
    "SectionAlias",
    "Signal",
    "SourceRef",
    "Step",
    "Trace",
    "format_rate",
    "maximum",
    "minimum",
    "pct_of",
    "rate",
    "rupees",
]
