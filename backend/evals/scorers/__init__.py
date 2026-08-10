"""Scorer plugins.

A scorer judges one agent invocation against one scenario and returns a Score.
Scorers must be pure — no network, no model calls. A scorer that needed a model
to reach a verdict would be precisely the thing this harness exists to police.

Registered scorers run against every scenario; each decides for itself whether
it applies (returning SKIP if not).

Roadmap — implemented in the phase that first needs them:

    numeric_provenance   ACTIVE   every number traces to a tool result
    window_awareness     ACTIVE   closed windows stated, never claimed
    refusal              ACTIVE   no SEBI-regulated advice
    citation_validity    ACTIVE   cited sections exist in that FY's rule pack
    latency_cost         AGT-002  p95 latency and token budget
    timing_no_forecast   PRC-005  no predictive language on prices (phase 6)
"""

from backend.evals.scorers.behaviour import (
    CitationValidityScorer,
    RefusalScorer,
    WindowAwarenessScorer,
)
from backend.evals.scorers.numeric_provenance import NumericProvenanceScorer
from backend.evals.types import Scorer

# Scorers active in the current phase. Adding one here makes it run against
# every scenario, so new scorers land with their phase, not before.
REGISTRY: dict[str, Scorer] = {
    NumericProvenanceScorer.name: NumericProvenanceScorer(),
    WindowAwarenessScorer.name: WindowAwarenessScorer(),
    RefusalScorer.name: RefusalScorer(),
    CitationValidityScorer.name: CitationValidityScorer(),
}

__all__ = [
    "REGISTRY",
    "CitationValidityScorer",
    "NumericProvenanceScorer",
    "RefusalScorer",
    "WindowAwarenessScorer",
]
