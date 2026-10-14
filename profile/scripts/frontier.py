"""Build profile/results/frontier.csv from the saved development runs (Homework 9 Part E).

Usage: uv run python profile/scripts/frontier.py

A configuration is dominated when another has an equal or higher development
score and an equal or lower cost, with at least one strict improvement.
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS = REPO_ROOT / "optimize" / "results"
OUTPUT = REPO_ROOT / "profile" / "results" / "frontier.csv"
RUNS = [  # (candidate label, saved result glob)
    ("hw8-final", "development-final-*.json"),
    ("fewer-tokens", "development-fewer-tokens-*.json"),
    ("cache-before", "development-cache-before-*.json"),
    ("cache-after", "development-cache-after-*.json"),
]


def main() -> None:
    rows = []
    for label, pattern in RUNS:
        path = sorted(glob.glob(str(RESULTS / pattern)))[-1]
        result = json.loads(Path(path).read_text())
        rows.append({
            "candidate": label,
            "model": result["model"],
            "development_score": result["score"],
            "write_pass_5": result["write_pass_5"],
            "cost_per_100_conversations_usd": result["cost_per_100_conversations_usd"],
            "median_latency_seconds": result["median_latency_seconds"],
        })
    for row in rows:
        dominated = any(
            other is not row
            and other["development_score"] >= row["development_score"]
            and other["cost_per_100_conversations_usd"] <= row["cost_per_100_conversations_usd"]
            and (other["development_score"] > row["development_score"]
                 or other["cost_per_100_conversations_usd"] < row["cost_per_100_conversations_usd"])
            for other in rows
        )
        row["frontier_status"] = "dominated" if dominated else "frontier"
    with OUTPUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
