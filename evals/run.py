"""
Main eval runner for InboxSherpa cluster summarization.

Usage:
    python -m evals.run [--verbose] [--threshold FLOAT] [--output FILE]

This module:
1. Loads 100 test clusters from fixtures
2. Scores both "good" and "bad" summaries
3. Verifies that good summaries score higher than bad ones
4. Reports aggregate metrics and pass/fail status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from evals.scoring import (
    EvalReport,
    ScoreResult,
    aggregate_results,
    score_summary,
)


FIXTURES_PATH = Path(__file__).parent / "fixtures" / "test_clusters.json"

# Target thresholds for production readiness
THRESHOLDS = {
    "pass_rate": 0.90,           # 90% of good summaries should pass
    "avg_relevance": 0.50,       # Average relevance score
    "avg_brevity": 0.85,         # Average brevity score (structural)
    "avg_urgency": 0.70,         # Average urgency accuracy
    "good_vs_bad_margin": 0.20,  # Good should beat bad by at least this margin
}


def load_fixtures() -> List[dict]:
    """Load test cluster fixtures from JSON file."""
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


def evaluate_summary(
    test_id: str,
    messages: List[dict],
    summary: dict,
    pass_threshold: float,
) -> ScoreResult:
    """Evaluate a single summary against its messages."""
    subjects = [m.get("subject", "") for m in messages]
    bodies = [m.get("body", "") for m in messages]

    return score_summary(
        test_id=test_id,
        message_subjects=subjects,
        message_bodies=bodies,
        summary_title=summary.get("title", ""),
        summary_bullets=summary.get("bullets", []),
        declared_urgency=summary.get("urgency", "low"),
        pass_threshold=pass_threshold,
    )


def run_evaluation(
    pass_threshold: float = 0.6,
    verbose: bool = False,
) -> tuple[EvalReport, EvalReport, bool]:
    """
    Run full evaluation suite.

    Returns:
        (good_report, bad_report, overall_pass)
    """
    test_cases = load_fixtures()

    good_results: List[ScoreResult] = []
    bad_results: List[ScoreResult] = []

    for tc in test_cases:
        test_id = tc["id"]
        messages = tc["messages"]

        # Evaluate good summary
        good_result = evaluate_summary(
            test_id=f"{test_id}_good",
            messages=messages,
            summary=tc["good_summary"],
            pass_threshold=pass_threshold,
        )
        good_results.append(good_result)

        # Evaluate bad summary
        bad_result = evaluate_summary(
            test_id=f"{test_id}_bad",
            messages=messages,
            summary=tc["bad_summary"],
            pass_threshold=pass_threshold,
        )
        bad_results.append(bad_result)

        if verbose:
            print(f"\n{test_id} ({tc.get('category', 'unknown')}):")
            print(f"  Good: {good_result.overall_score:.3f} {'PASS' if good_result.passed else 'FAIL'}")
            print(f"  Bad:  {bad_result.overall_score:.3f} {'PASS' if bad_result.passed else 'FAIL'}")
            margin = good_result.overall_score - bad_result.overall_score
            print(f"  Margin: {margin:+.3f}")

    good_report = aggregate_results(good_results)
    bad_report = aggregate_results(bad_results)

    # Determine overall pass
    overall_pass = True
    checks = []

    # Check 1: Good summaries pass rate
    if good_report.pass_rate >= THRESHOLDS["pass_rate"]:
        checks.append(("Good pass rate", True, f"{good_report.pass_rate:.1%} >= {THRESHOLDS['pass_rate']:.1%}"))
    else:
        checks.append(("Good pass rate", False, f"{good_report.pass_rate:.1%} < {THRESHOLDS['pass_rate']:.1%}"))
        overall_pass = False

    # Check 2: Bad summaries should mostly fail
    bad_fail_rate = 1 - bad_report.pass_rate
    if bad_fail_rate >= THRESHOLDS["pass_rate"]:
        checks.append(("Bad fail rate", True, f"{bad_fail_rate:.1%} >= {THRESHOLDS['pass_rate']:.1%}"))
    else:
        checks.append(("Bad fail rate", False, f"{bad_fail_rate:.1%} < {THRESHOLDS['pass_rate']:.1%}"))
        overall_pass = False

    # Check 3: Good vs Bad margin
    margin = good_report.avg_overall - bad_report.avg_overall
    if margin >= THRESHOLDS["good_vs_bad_margin"]:
        checks.append(("Good vs Bad margin", True, f"{margin:.3f} >= {THRESHOLDS['good_vs_bad_margin']:.3f}"))
    else:
        checks.append(("Good vs Bad margin", False, f"{margin:.3f} < {THRESHOLDS['good_vs_bad_margin']:.3f}"))
        overall_pass = False

    # Check 4: Relevance threshold
    if good_report.avg_relevance >= THRESHOLDS["avg_relevance"]:
        checks.append(("Avg relevance", True, f"{good_report.avg_relevance:.3f} >= {THRESHOLDS['avg_relevance']:.3f}"))
    else:
        checks.append(("Avg relevance", False, f"{good_report.avg_relevance:.3f} < {THRESHOLDS['avg_relevance']:.3f}"))
        overall_pass = False

    # Check 5: Brevity threshold
    if good_report.avg_brevity >= THRESHOLDS["avg_brevity"]:
        checks.append(("Avg brevity", True, f"{good_report.avg_brevity:.3f} >= {THRESHOLDS['avg_brevity']:.3f}"))
    else:
        checks.append(("Avg brevity", False, f"{good_report.avg_brevity:.3f} < {THRESHOLDS['avg_brevity']:.3f}"))
        overall_pass = False

    # Check 6: Urgency threshold
    if good_report.avg_urgency >= THRESHOLDS["avg_urgency"]:
        checks.append(("Avg urgency", True, f"{good_report.avg_urgency:.3f} >= {THRESHOLDS['avg_urgency']:.3f}"))
    else:
        checks.append(("Avg urgency", False, f"{good_report.avg_urgency:.3f} < {THRESHOLDS['avg_urgency']:.3f}"))
        overall_pass = False

    return good_report, bad_report, overall_pass, checks


def print_report(
    good_report: EvalReport,
    bad_report: EvalReport,
    overall_pass: bool,
    checks: list,
) -> None:
    """Print formatted evaluation report."""
    print("\n" + "=" * 60)
    print("INBOXSHERPA AI EVAL HARNESS - SUMMARY SCORING REPORT")
    print("=" * 60)

    print("\n## GOOD SUMMARIES")
    print(f"  Total tests:    {good_report.total_tests}")
    print(f"  Passed:         {good_report.passed_tests}")
    print(f"  Failed:         {good_report.failed_tests}")
    print(f"  Pass rate:      {good_report.pass_rate:.1%}")
    print(f"  Avg relevance:  {good_report.avg_relevance:.3f}")
    print(f"  Avg brevity:    {good_report.avg_brevity:.3f}")
    print(f"  Avg urgency:    {good_report.avg_urgency:.3f}")
    print(f"  Avg overall:    {good_report.avg_overall:.3f}")

    print("\n## BAD SUMMARIES (should score lower)")
    print(f"  Total tests:    {bad_report.total_tests}")
    print(f"  Passed:         {bad_report.passed_tests}")
    print(f"  Failed:         {bad_report.failed_tests}")
    print(f"  Pass rate:      {bad_report.pass_rate:.1%}")
    print(f"  Avg relevance:  {bad_report.avg_relevance:.3f}")
    print(f"  Avg brevity:    {bad_report.avg_brevity:.3f}")
    print(f"  Avg urgency:    {bad_report.avg_urgency:.3f}")
    print(f"  Avg overall:    {bad_report.avg_overall:.3f}")

    margin = good_report.avg_overall - bad_report.avg_overall
    print("\n## DISCRIMINATION")
    print(f"  Good - Bad margin: {margin:.3f}")

    print("\n## THRESHOLD CHECKS")
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    print("\n" + "=" * 60)
    if overall_pass:
        print("OVERALL RESULT: PASS")
    else:
        print("OVERALL RESULT: FAIL")
    print("=" * 60)


def export_results(
    good_report: EvalReport,
    bad_report: EvalReport,
    output_path: str,
) -> None:
    """Export detailed results to JSON."""
    output = {
        "good_summaries": {
            "total_tests": good_report.total_tests,
            "passed_tests": good_report.passed_tests,
            "failed_tests": good_report.failed_tests,
            "pass_rate": good_report.pass_rate,
            "avg_relevance": good_report.avg_relevance,
            "avg_brevity": good_report.avg_brevity,
            "avg_urgency": good_report.avg_urgency,
            "avg_overall": good_report.avg_overall,
            "individual_results": [
                {
                    "test_id": r.test_id,
                    "relevance": r.relevance_score,
                    "brevity": r.brevity_score,
                    "urgency": r.urgency_score,
                    "overall": r.overall_score,
                    "passed": r.passed,
                    "details": r.details,
                }
                for r in good_report.individual_results
            ],
        },
        "bad_summaries": {
            "total_tests": bad_report.total_tests,
            "passed_tests": bad_report.passed_tests,
            "failed_tests": bad_report.failed_tests,
            "pass_rate": bad_report.pass_rate,
            "avg_relevance": bad_report.avg_relevance,
            "avg_brevity": bad_report.avg_brevity,
            "avg_urgency": bad_report.avg_urgency,
            "avg_overall": bad_report.avg_overall,
            "individual_results": [
                {
                    "test_id": r.test_id,
                    "relevance": r.relevance_score,
                    "brevity": r.brevity_score,
                    "urgency": r.urgency_score,
                    "overall": r.overall_score,
                    "passed": r.passed,
                    "details": r.details,
                }
                for r in bad_report.individual_results
            ],
        },
        "thresholds": THRESHOLDS,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nDetailed results exported to: {output_path}")


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Run AI eval harness for InboxSherpa cluster summarization"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed per-test results",
    )
    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=0.6,
        help="Pass threshold for individual tests (default: 0.6)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Export detailed results to JSON file",
    )

    args = parser.parse_args()

    print("Loading test fixtures...")
    print(f"Fixtures path: {FIXTURES_PATH}")

    good_report, bad_report, overall_pass, checks = run_evaluation(
        pass_threshold=args.threshold,
        verbose=args.verbose,
    )

    print_report(good_report, bad_report, overall_pass, checks)

    if args.output:
        export_results(good_report, bad_report, args.output)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
