#!/usr/bin/env python3
"""Validate the Phase 5 temporal/leakage contract without making an accuracy claim."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))

from app.opportunities.evaluation import TemporalEvaluationCase, validate_temporal_evaluation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text())
    cases = [
        TemporalEvaluationCase(
            case_id=item["case_id"],
            group_id=item["group_id"],
            split=item["split"],
            prediction_at=datetime.fromisoformat(item["prediction_at"]),
            available_at=tuple(datetime.fromisoformat(value) for value in item["available_at"]),
        )
        for item in payload["cases"]
    ]
    report = validate_temporal_evaluation(cases)
    print(
        json.dumps(
            {
                "passed": report.passed,
                "failures": report.failures,
                "accuracy_claim_allowed": report.accuracy_claim_allowed,
            }
        )
    )
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
