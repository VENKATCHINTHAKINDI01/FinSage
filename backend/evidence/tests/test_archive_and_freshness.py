"""Source archival (EVD-004) and answer-time freshness (AGT-012).

Paired because they are two halves of one guarantee: the archive knows what a
source SAID when it was read, and the freshness check reports whether anyone has
looked since — without ever touching the network at answer time.
"""

from __future__ import annotations

import time
from datetime import date

import pytest

from backend.agents.freshness import (
    AnswerFreshness,
    Freshness,
    FreshnessCache,
    check_answer,
    check_freshness,
)
from backend.evidence.archive import (
    MAX_EXTRACT_CHARS,
    ArchivedSource,
    MemoryArchive,
    SourceArchive,
    UndatedSource,
    extract_hash,
)

WHEN = date(2026, 8, 12)
URL = "https://www.incometax.gov.in/rebate-87a"
EXTRACT = "A resident individual may claim a rebate of up to Rs 60,000 under section 87A."


@pytest.fixture
def archive() -> SourceArchive:
    return SourceArchive(backend=MemoryArchive())


# ══ EVD-004: the extract is stored, not just the URL ════════════════════════

class TestArchivingTheExtract:
    def test_the_text_is_kept_not_only_the_link(self, archive) -> None:
        """A URL rots. "We read this on 9 August" is only checkable if what was
        read was kept."""
        archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN)
        assert archive.get(URL).extract == EXTRACT

    def test_an_empty_extract_is_refused(self, archive) -> None:
        """Storing the URL alone is the behaviour this feature replaces."""
        with pytest.raises(ValueError, match="empty extract"):
            archive.archive(URL, "   ", tier=1, retrieved_at=WHEN)

    def test_a_long_extract_is_truncated_rather_than_stored_whole(self) -> None:
        """The extract, not the page. Archiving whole portals grows without
        bound and most of the bytes are navigation."""
        s = ArchivedSource(URL, "x" * (MAX_EXTRACT_CHARS + 500), WHEN, 1)
        assert len(s.extract) <= MAX_EXTRACT_CHARS + 20
        assert s.extract.endswith("…[truncated]")

    def test_an_unarchived_url_returns_none_rather_than_guessing(self, archive) -> None:
        assert archive.get("https://example.gov.in/never-read") is None


class TestNoUndatedSource:
    def test_construction_without_a_date_raises(self) -> None:
        """Same invariant as `LedgerEntry`: a figure whose provenance is
        unknown must fail in the engine, not render as a plausible number."""
        with pytest.raises(UndatedSource, match="without a retrieval date"):
            ArchivedSource(URL, EXTRACT, None, 1)

    def test_every_source_renders_an_as_of_date(self, archive) -> None:
        s = archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN)
        assert s.as_of() == "as of 12 August 2026"
        assert s.to_dict()["as_of"] == "as of 12 August 2026"

    def test_a_tier_three_source_may_not_drive_a_figure(self, archive) -> None:
        """Marketplaces, review sites and news can add context. They must never
        produce a number in a cost breakdown."""
        assert archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN).may_drive_a_figure
        assert archive.archive(URL, EXTRACT, tier=2, retrieved_at=WHEN).may_drive_a_figure
        assert not archive.archive(
            URL, EXTRACT, tier=3, retrieved_at=WHEN
        ).may_drive_a_figure

    def test_an_invalid_tier_is_refused(self) -> None:
        with pytest.raises(ValueError, match="tier must be"):
            ArchivedSource(URL, EXTRACT, WHEN, 4)


class TestChangeDetection:
    def test_an_unchanged_source_reports_no_change(self, archive) -> None:
        archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN)
        report = archive.check(URL, EXTRACT, today=date(2027, 1, 1))
        assert not report.changed
        assert "cached figures stand" in report.message()

    def test_reflowed_whitespace_is_not_a_policy_change(self, archive) -> None:
        """Only substance is fingerprinted. A tripwire that fires on HTML
        reflow stops being watched."""
        archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN)
        noisy = "  " + EXTRACT.replace(" ", "\n  ").upper() + "\t"
        assert not archive.check(URL, noisy, today=WHEN).changed

    def test_a_changed_figure_is_detected(self, archive) -> None:
        archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN)
        moved = EXTRACT.replace("60,000", "75,000")
        assert archive.check(URL, moved, today=WHEN).changed

    def test_it_flags_the_facts_that_cite_it_rather_than_recomputing(
        self, archive
    ) -> None:
        """The load-bearing behaviour. A figure that moves between two readings
        with no explanation destroys the trust the evidence layer exists to
        build."""
        archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN,
                        cited_by="rebate_87a_ceiling")
        archive.note_citation(URL, "rebate_87a_marginal_relief")

        report = archive.check(URL, EXTRACT.replace("60,000", "75,000"), today=WHEN)
        assert set(report.affected_facts) == {
            "rebate_87a_ceiling", "rebate_87a_marginal_relief",
        }
        assert "NOT been recomputed" in report.message()
        assert "⚠" in report.message()

    def test_an_unchanged_source_flags_nothing(self, archive) -> None:
        archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN, cited_by="a_rule")
        assert archive.check(URL, EXTRACT, today=WHEN).affected_facts == ()

    def test_checking_an_unarchived_url_raises(self, archive) -> None:
        with pytest.raises(KeyError, match="has not been archived"):
            archive.check(URL, EXTRACT, today=WHEN)

    def test_the_hash_is_stable_across_calls(self) -> None:
        assert extract_hash(EXTRACT) == extract_hash(EXTRACT)


def test_stale_sources_can_be_listed(archive) -> None:
    archive.archive(URL, EXTRACT, tier=1, retrieved_at=date(2026, 1, 1))
    archive.archive("https://a.gov.in/b", EXTRACT, tier=1, retrieved_at=date(2026, 8, 1))
    stale = archive.stale(date(2026, 9, 1), window_days=180)
    assert [s.url for s in stale] == [URL]


# ══ AGT-012: answer time never touches the network ══════════════════════════

class TestNoNetworkAtAnswerTime:
    def test_the_cache_has_no_fetch_method(self) -> None:
        """A cache that could fetch would eventually be asked to, and the
        network would be back on the critical path of every response."""
        for name in ("fetch", "refresh", "get_url", "download", "request"):
            assert not hasattr(FreshnessCache, name)

    def test_a_lookup_is_far_under_the_fifty_millisecond_budget(self) -> None:
        """The acceptance criterion. Measured over 1,000 lookups so a single
        slow one cannot pass by luck."""
        cache = FreshnessCache()
        for i in range(200):
            cache.record(f"https://a.gov.in/{i}", checked_on=WHEN)

        start = time.perf_counter()
        for _ in range(1_000):
            check_freshness("https://a.gov.in/7", cache, today=WHEN)
        per_call_ms = (time.perf_counter() - start) * 1000 / 1_000
        assert per_call_ms < 5, f"{per_call_ms:.3f}ms per lookup"

    def test_a_verdict_never_blocks_an_answer(self) -> None:
        """Whatever the state. A user with a stale-but-labelled figure is
        better served than a user with an error page."""
        cache = FreshnessCache()
        cache.record(URL, checked_on=date(2020, 1, 1), changed=True)
        for state_url in (URL, "https://never.seen/x"):
            assert not check_freshness(state_url, cache, today=WHEN).blocks_answer
        assert check_answer([URL], cache, today=WHEN).to_dict()["blocks_answer"] is False


class TestVerdicts:
    def _cache(self, **kw) -> FreshnessCache:
        c = FreshnessCache()
        c.record(URL, **kw)
        return c

    def test_recently_checked_and_unchanged_is_fresh(self) -> None:
        c = self._cache(checked_on=date(2026, 8, 1))
        assert check_freshness(URL, c, today=WHEN).state is Freshness.FRESH

    def test_beyond_the_fresh_window_is_stale(self) -> None:
        c = self._cache(checked_on=date(2026, 6, 1))
        assert check_freshness(URL, c, today=WHEN).state is Freshness.STALE

    def test_never_checked_is_unknown_not_fresh(self) -> None:
        """Silence must not read as confirmation."""
        v = check_freshness(URL, FreshnessCache(), today=WHEN)
        assert v.state is Freshness.UNKNOWN
        assert "never been re-checked" in v.detail

    def test_a_changed_source_outranks_its_age(self) -> None:
        c = self._cache(checked_on=WHEN, changed=True, affects_rules=("87A",))
        v = check_freshness(URL, c, today=WHEN)
        assert v.state is Freshness.CHANGED
        assert v.affects_rules == ("87A",)
        assert "NOT been recomputed" in v.detail

    def test_every_non_fresh_state_downgrades_confidence(self) -> None:
        assert not Freshness.FRESH.downgrades_confidence
        for s in (Freshness.STALE, Freshness.CHANGED, Freshness.UNKNOWN):
            assert s.downgrades_confidence
            assert s.badge


class TestAnswerLevelFreshness:
    def test_the_worst_source_decides_the_badge(self) -> None:
        c = FreshnessCache()
        c.record("https://a/1", checked_on=WHEN)
        c.record("https://a/2", checked_on=date(2026, 1, 1))
        c.record("https://a/3", checked_on=WHEN, changed=True)
        assert check_answer(
            ["https://a/1", "https://a/2", "https://a/3"], c, today=WHEN
        ).worst is Freshness.CHANGED

    def test_a_changed_source_costs_the_most_confidence(self) -> None:
        """It is the only state where the fact may actually be WRONG rather
        than merely unconfirmed."""
        def penalty(**kw):
            c = FreshnessCache()
            c.record(URL, **kw)
            return check_answer([URL], c, today=WHEN).confidence_penalty

        assert penalty(checked_on=WHEN) == "0.00"
        assert penalty(checked_on=date(2026, 6, 1)) == "0.05"
        assert penalty(checked_on=WHEN, changed=True) == "0.25"
        assert AnswerFreshness([]).confidence_penalty == "0.00"

    def test_an_unchecked_source_costs_more_than_a_merely_old_one(self) -> None:
        c = FreshnessCache()
        assert check_answer(["https://never/seen"], c, today=WHEN).confidence_penalty == "0.10"

    def test_the_changed_sources_are_listed_for_the_badge(self) -> None:
        c = FreshnessCache()
        c.record("https://a/1", checked_on=WHEN)
        c.record("https://a/2", checked_on=WHEN, changed=True, affects_rules=("87A",))
        answer = check_answer(["https://a/1", "https://a/2"], c, today=WHEN)
        assert [v.url for v in answer.changed] == ["https://a/2"]

    def test_an_answer_with_no_sources_is_fresh_and_free(self) -> None:
        assert check_answer([], FreshnessCache(), today=WHEN).worst is Freshness.FRESH


def test_the_archive_feeds_the_freshness_cache() -> None:
    """The two halves joined: archive detects the change, cache carries it to
    answer time without a network call."""
    archive = SourceArchive(backend=MemoryArchive())
    archive.archive(URL, EXTRACT, tier=1, retrieved_at=WHEN, cited_by="87A ceiling")
    report = archive.check(URL, EXTRACT.replace("60,000", "75,000"), today=WHEN)

    cache = FreshnessCache()
    cache.record(URL, checked_on=report.checked_at, changed=report.changed,
                 affects_rules=report.affected_facts)

    verdict = check_freshness(URL, cache, today=WHEN)
    assert verdict.state is Freshness.CHANGED
    assert verdict.affects_rules == ("87A ceiling",)
