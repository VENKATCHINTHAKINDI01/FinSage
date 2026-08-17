#!/usr/bin/env python3
"""Fail the build when a shipped tax rule has gone stale.

Why this exists
---------------
v1's defining failure was not a bug. It was decay. The slabs were correct for
FY 2023-24 and simply stopped being correct, in seven files at once, with
nothing anywhere in the system objecting.

Correctness in a tax product is perishable. Every Budget invalidates part of
it, and there is no test that catches "this was true two years ago". The only
defence is to make staleness fail loudly on a clock.

What it checks
--------------
1. Any feature with `rules_refs` whose `last_verified` is older than
   `conventions.freshness_policy_days`, or is null while the feature is
   shipped (status `verified`).
2. Any rule pack whose `meta.verified_on` is older than the same window.
3. Rule packs whose financial year has ended without a successor pack — the
   Budget landed and nobody added the new year.

Usage
-----
    python scripts/verify_freshness.py            # fail on stale
    python scripts/verify_freshness.py --warn     # report, exit 0
    python scripts/verify_freshness.py --days 90  # tighter window
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURE_FILE = ROOT / "feature.json"
RULES_DIR = ROOT / "backend" / "core" / "rules"

SHIPPED = {"verified"}


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _age(d: str, today: date) -> int:
    return (today - _parse(d)).days


def check_features(data: dict, limit: int, today: date) -> list[str]:
    problems = []
    for f in data["features"]:
        if not f.get("rules_refs"):
            continue

        lv = f.get("last_verified")
        if lv is None:
            if f["status"] in SHIPPED:
                problems.append(
                    f"{f['id']} ({f['name']}): status is '{f['status']}' but "
                    f"last_verified is null — a shipped tax rule nobody has "
                    f"confirmed against an official source"
                )
            continue

        age = _age(lv, today)
        if age > limit:
            srcs = ", ".join(f.get("sources", [])[:2]) or "no source listed"
            problems.append(
                f"{f['id']} ({f['name']}): last verified {age} days ago "
                f"(limit {limit}). Re-check against: {srcs}"
            )
    return problems


def check_rule_packs(limit: int, today: date) -> list[str]:
    if not RULES_DIR.exists():
        return []

    try:
        import yaml
    except ImportError:
        return ["PyYAML not installed — rule pack freshness not checked"]

    problems: list[str] = []
    covered_years: set[str] = set()

    for path in sorted(RULES_DIR.glob("fy_*.y*ml")):
        pack = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        meta = pack.get("meta", {})

        fy = meta.get("financial_year")
        if fy:
            covered_years.add(fy)

        verified_on = meta.get("verified_on")
        if not verified_on:
            problems.append(f"{path.name}: meta.verified_on is missing")
            continue

        age = _age(str(verified_on), today)
        if age > limit:
            problems.append(
                f"{path.name}: verified {age} days ago (limit {limit}) — "
                f"re-check slabs, limits and thresholds against incometax.gov.in"
            )

        # A pack whose year has ended and which has no successor means a Budget
        # went by unnoticed.
        end = meta.get("effective_to")
        if end and _parse(str(end)) < today:
            successor = _next_fy(str(fy)) if fy else None
            if successor and successor not in _all_years():
                problems.append(
                    f"{path.name}: FY {fy} ended on {end} and there is no "
                    f"rule pack for FY {successor}. The Budget has landed."
                )

    # The non-year packs — gst.yaml, procurement.yaml, admission.yaml — age
    # exactly like the FY packs and were previously not checked at all. GST 2.0
    # restructured every slab on one day in September 2025; a procurement pack
    # nobody re-reads is how a stale road tax rate survives a state Budget.
    for path in sorted(RULES_DIR.glob("*.y*ml")):
        if path.name.startswith("fy_"):
            continue
        pack = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        verified_on = (pack.get("meta") or {}).get("verified_on")
        if not verified_on:
            problems.append(f"{path.name}: meta.verified_on is missing")
            continue
        age = _age(str(verified_on), today)
        if age > limit:
            problems.append(
                f"{path.name}: verified {age} days ago (limit {limit}) — "
                f"re-check against the sources listed in the pack"
            )

    return problems


def _all_years() -> set[str]:
    years = set()
    for p in RULES_DIR.glob("fy_*.y*ml"):
        stem = p.stem.removeprefix("fy_")          # 2026_27
        parts = stem.split("_")
        if len(parts) == 2:
            years.add(f"{parts[0]}-{parts[1]}")
    return years


def _next_fy(fy: str) -> str | None:
    try:
        start = int(fy.split("-")[0])
    except (ValueError, IndexError):
        return None
    return f"{start + 1}-{str(start + 2)[-2:]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None,
                    help="override conventions.freshness_policy_days")
    ap.add_argument("--warn", action="store_true",
                    help="report but exit 0")
    args = ap.parse_args()

    data = json.loads(FEATURE_FILE.read_text(encoding="utf-8"))
    limit = args.days or data["conventions"]["freshness_policy_days"]
    today = date.today()

    problems = check_features(data, limit, today) + check_rule_packs(limit, today)

    if not problems:
        tracked = sum(1 for f in data["features"] if f.get("rules_refs"))
        print(f"Freshness OK — {tracked} rule-backed features, "
              f"{len(_all_years()) if RULES_DIR.exists() else 0} rule packs, "
              f"{limit}-day window.")
        return 0

    stream = sys.stdout if args.warn else sys.stderr
    print(f"{'WARNING' if args.warn else 'STALE TAX RULES'} "
          f"({len(problems)}):", file=stream)
    for p in problems:
        print(f"  {'!' if args.warn else '✗'} {p}", file=stream)

    if args.warn:
        return 0

    print(
        "\nTax rules are perishable. Re-verify against the official source, "
        "then update last_verified in feature.json / meta.verified_on in the "
        "rule pack.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
