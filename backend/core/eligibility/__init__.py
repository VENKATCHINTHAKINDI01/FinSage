"""Date-windowed eligibility evaluation.

Returns ELIGIBLE / INELIGIBLE(reason) / WINDOW_CLOSED(closed_on) /
INSUFFICIENT_DATA(missing_fields).

WINDOW_CLOSED exists because the most damaging class of bug in Indian tax
software is a benefit that exists in the statute but is closed to this user on
this date. Section 80EEB is the canonical example: it requires the vehicle loan
to have been sanctioned between 2019-01-01 and 2023-03-31, and the section text
still reads "Rs 1,50,000".
"""

from backend.core.eligibility.evaluator import (
    Facts,
    Outcome,
    Status,
    claimable,
    closed_windows,
    evaluate_all,
    evaluate_rule,
)

__all__ = [
    "Facts",
    "Outcome",
    "Status",
    "claimable",
    "closed_windows",
    "evaluate_all",
    "evaluate_rule",
]
