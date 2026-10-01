"""Verify that committed benchmark summaries match their raw audit records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jevops.benchmark.runner import summarize_results


def _latest_results_dir(root: Path) -> Path:
    candidates = sorted(path for path in root.iterdir() if path.is_dir())
    if not candidates:
        raise SystemExit(f"no result directories found under {root}")
    return candidates[-1]


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _verify_benchmark(raw_path: Path, summary_path: Path) -> None:
    rows = _read_jsonl(raw_path)
    expected_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    actual_summary = summarize_results(rows)
    if actual_summary != expected_summary:
        raise SystemExit(f"summary does not match raw records: {summary_path}")

    evidence_by_case: dict[tuple[object, object, object], set[object]] = {}
    for row in rows:
        benchmark = row["benchmark"]
        truth = row["truth"]
        key = (benchmark["run"], truth["scenario"], benchmark["seed"])
        evidence_by_case.setdefault(key, set()).add(row["evidence_hash"])
    if any(len(hashes) != 1 for hashes in evidence_by_case.values()):
        raise SystemExit(f"engines did not share one evidence hash per case: {raw_path}")

    engines = {row["audit"]["decision"]["engine"] for row in rows}
    attempts = {item["total_attempts"] for item in actual_summary}
    print(
        f"verified {raw_path}: {len(rows)} decisions, "
        f"{len(evidence_by_case)} cases, {len(engines)} engines, attempts={sorted(attempts)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path)
    args = parser.parse_args()
    results_dir = args.results_dir or _latest_results_dir(Path("results"))

    for domain in ("streamguard", "payrecon"):
        stem = results_dir / f"benchmark-{domain}"
        _verify_benchmark(stem.with_suffix(".jsonl"), stem.with_suffix(".summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
