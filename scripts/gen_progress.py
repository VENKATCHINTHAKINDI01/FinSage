#!/usr/bin/env python3
"""
Generate PROGRESS.md from feature.json.

PROGRESS.md is a build artefact — never hand-edit it. CI fails if the committed
file differs from this script's output.

Usage:
    python scripts/gen_progress.py            # write PROGRESS.md
    python scripts/gen_progress.py --check    # exit 1 if PROGRESS.md is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURE_FILE = ROOT / "feature.json"
SCHEMA_FILE = ROOT / "docs" / "feature.schema.json"
PROGRESS_FILE = ROOT / "PROGRESS.md"

# Only 'verified' counts toward completion. Everything else is work in flight.
COMPLETE_STATUSES = {"verified"}

STATUS_ICON = {
    "not_started": "○",
    "in_progress": "◐",
    "blocked": "⊘",
    "implemented": "◑",
    "tested": "◕",
    "verified": "●",
}

TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def load() -> dict:
    with FEATURE_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def bar(done: int, total: int, width: int = 24) -> str:
    if total == 0:
        return "─" * width
    filled = round(width * done / total)
    return "█" * filled + "░" * (width - filled)


def pct(done: int, total: int) -> str:
    return "0%" if total == 0 else f"{round(100 * done / total)}%"


def validate_schema(data: dict) -> list[str]:
    """Structural validation against docs/feature.schema.json.

    jsonschema is optional so the generator still runs in a bare environment;
    CI installs it, so the schema gate is always enforced there.
    """
    try:
        import jsonschema
    except ImportError:
        print("  note: jsonschema not installed — structural validation skipped",
              file=sys.stderr)
        return []

    with SCHEMA_FILE.open(encoding="utf-8") as fh:
        schema = json.load(fh)

    validator = jsonschema.Draft7Validator(schema)
    problems = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in err.path) or "<root>"
        problems.append(f"schema: {where}: {err.message}")
    return problems


def validate(data: dict) -> list[str]:
    """Semantic invariants declared in feature.json.conventions.

    These are the rules a JSON schema cannot express: cross-references,
    dependency cycles, the deterministic/llm contradiction, and the
    freshness gate that stops v1's staleness from recurring.
    """
    problems: list[str] = []
    features = data["features"]
    ids = {f["id"] for f in features}
    valid_statuses = set(data["conventions"]["status_vocabulary"])
    freshness_days = data["conventions"]["freshness_policy_days"]
    today = date.today()

    seen: set[str] = set()
    for f in features:
        fid = f["id"]

        if fid in seen:
            problems.append(f"{fid}: duplicate feature id")
        seen.add(fid)

        if f["status"] not in valid_statuses:
            problems.append(f"{fid}: unknown status '{f['status']}'")

        for dep in f.get("depends_on", []):
            if dep not in ids:
                problems.append(f"{fid}: depends_on unknown feature '{dep}'")

        if f.get("deterministic") and f.get("llm_involved"):
            problems.append(f"{fid}: cannot be both deterministic and llm_involved")

        # A feature claiming to encode tax rules must cite an official source
        # and must be proven by a test, not by assertion.
        if f.get("rules_refs"):
            if not f.get("sources"):
                problems.append(f"{fid}: has rules_refs but no source")
            tests = f.get("tests", {})
            if not (tests.get("golden") or tests.get("unit")):
                problems.append(f"{fid}: encodes tax rules but has no golden or unit test")

        # Anything an LLM touches needs an eval scenario, or the numeric
        # provenance gate has nothing to run against.
        if f.get("llm_involved") and not f.get("tests", {}).get("eval"):
            problems.append(f"{fid}: llm_involved but has no eval scenario")

        # Freshness gate — the control that stops v1's staleness recurring.
        lv = f.get("last_verified")
        if f.get("rules_refs") and lv:
            age = (today - datetime.strptime(lv, "%Y-%m-%d").date()).days
            if age > freshness_days:
                problems.append(
                    f"{fid}: last_verified is {age}d old (limit {freshness_days}d)"
                )

    # Dependency cycles.
    graph = {f["id"]: list(f.get("depends_on", [])) for f in features}
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            cycle = " → ".join([*trail[trail.index(node):], node])
            problems.append(f"dependency cycle: {cycle}")
            return
        state[node] = 1
        for nxt in graph.get(node, []):
            visit(nxt, [*trail, node])
        state[node] = 2

    for fid in graph:
        visit(fid, [])

    return problems


def render(data: dict) -> str:
    features = data["features"]
    phases = data["phases"]
    total = len(features)
    done = sum(1 for f in features if f["status"] in COMPLETE_STATUSES)

    by_phase: dict[int, list[dict]] = defaultdict(list)
    for f in features:
        by_phase[f["phase"]].append(f)

    status_counts = Counter(f["status"] for f in features)
    tier_counts = Counter(f["tier"] for f in features)
    p0 = [f for f in features if f["tier"] == "P0"]
    p0_done = sum(1 for f in p0 if f["status"] in COMPLETE_STATUSES)

    L: list[str] = []
    add = L.append

    add("<!-- GENERATED FILE — do not edit. Source: feature.json -->")
    add("<!-- Regenerate: python scripts/gen_progress.py -->")
    add("")
    add("# FinSage AI — Progress")
    add("")
    add(f"**Generated** {date.today().isoformat()} · "
        f"**Plan** [{data['plan_ref']}]({data['plan_ref']}) · "
        f"**Review** [{data['review_ref']}]({data['review_ref']})")
    add("")
    add(f"`{bar(done, total)}` **{pct(done, total)}** — {done}/{total} features verified")
    add("")
    add(f"P0 (release-blocking): **{p0_done}/{len(p0)}** verified")
    add("")
    add("> Only `verified` — legal basis confirmed against an official source — counts")
    add("> toward completion. Nothing user-facing ships below `verified`.")
    add("")

    add("## Phases")
    add("")
    add("| # | Phase | Progress | Features | Gate |")
    add("|---|---|---|---|---|")
    for ph in phases:
        items = by_phase.get(ph["id"], [])
        d = sum(1 for f in items if f["status"] in COMPLETE_STATUSES)
        add(f"| {ph['id']} | **{ph['name']}** | `{bar(d, len(items), 14)}` {pct(d, len(items))} "
            f"| {d}/{len(items)} | {ph['gate']} |")
    add("")

    add("## Status")
    add("")
    add("| Status | Count | | Tier | Count |")
    add("|---|---|---|---|---|")
    order = data["conventions"]["status_vocabulary"]
    tiers = sorted(tier_counts, key=lambda t: TIER_ORDER.get(t, 9))
    for i in range(max(len(order), len(tiers))):
        left = (f"{STATUS_ICON.get(order[i], '·')} `{order[i]}` | {status_counts.get(order[i], 0)}"
                if i < len(order) else " | ")
        right = (f"`{tiers[i]}` | {tier_counts[tiers[i]]}"
                 if i < len(tiers) else " | ")
        add(f"| {left} | | {right} |")
    add("")

    add("## Features")
    add("")
    for ph in phases:
        items = sorted(
            by_phase.get(ph["id"], []),
            key=lambda f: (TIER_ORDER.get(f["tier"], 9), f["id"]),
        )
        if not items:
            continue
        d = sum(1 for f in items if f["status"] in COMPLETE_STATUSES)
        add(f"### Phase {ph['id']} — {ph['name']}  ·  {d}/{len(items)}")
        add("")
        add(f"**Gate:** {ph['gate']}")
        add("")
        add("| | ID | Feature | Tier | Deps | Verified |")
        add("|---|---|---|---|---|---|")
        for f in items:
            icon = STATUS_ICON.get(f["status"], "·")
            deps = ", ".join(f.get("depends_on", [])) or "—"
            lv = f.get("last_verified") or "—"
            add(f"| {icon} | `{f['id']}` | {f['name']} | {f['tier']} | {deps} | {lv} |")
        add("")

    add("## Ready to start")
    add("")
    add("Not started, with every dependency already verified:")
    add("")
    done_ids = {f["id"] for f in features if f["status"] in COMPLETE_STATUSES}
    ready = [
        f for f in features
        if f["status"] == "not_started"
        and all(d in done_ids for d in f.get("depends_on", []))
    ]
    ready.sort(key=lambda f: (f["phase"], TIER_ORDER.get(f["tier"], 9), f["id"]))
    if ready:
        for f in ready[:12]:
            add(f"- `{f['id']}` **{f['name']}** — phase {f['phase']}, {f['tier']}")
    else:
        add("- _None — every unstarted feature is still blocked by a dependency._")
    add("")

    blocked = [f for f in features if f["status"] == "blocked"]
    if blocked:
        add("## Blocked")
        add("")
        for f in blocked:
            add(f"- `{f['id']}` **{f['name']}** — {f.get('risk', 'no detail')}")
        add("")

    add("---")
    add("")
    add(f"_FYs supported: {', '.join(data['fy_supported'])} · {data['governing_act']}_")
    add("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if PROGRESS.md is stale or the registry is invalid")
    args = ap.parse_args()

    data = load()

    problems = validate_schema(data) + validate(data)
    if problems:
        print("feature.json validation failed:", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1

    out = render(data)

    if args.check:
        current = PROGRESS_FILE.read_text(encoding="utf-8") if PROGRESS_FILE.exists() else ""
        if current != out:
            print("PROGRESS.md is stale — run: python scripts/gen_progress.py",
                  file=sys.stderr)
            return 1
        print("PROGRESS.md up to date; registry valid.")
        return 0

    PROGRESS_FILE.write_text(out, encoding="utf-8")
    total = len(data["features"])
    print(f"Wrote {PROGRESS_FILE.relative_to(ROOT)} — {total} features, registry valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
