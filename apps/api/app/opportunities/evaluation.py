from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TemporalEvaluationCase:
    case_id: str
    group_id: str
    split: str
    prediction_at: datetime
    available_at: tuple[datetime, ...]


@dataclass(frozen=True)
class TemporalEvaluationReport:
    passed: bool
    failures: tuple[str, ...]
    accuracy_claim_allowed: bool
    metrics: dict[str, Any]


def validate_temporal_evaluation(
    cases: list[TemporalEvaluationCase], *, evaluation_split: str = "evaluation"
) -> TemporalEvaluationReport:
    failures: list[str] = []
    train = [case for case in cases if case.split == "train"]
    evaluation = [case for case in cases if case.split == evaluation_split]
    train_groups = {case.group_id for case in train}
    overlapping_groups = train_groups & {case.group_id for case in evaluation}
    if overlapping_groups:
        failures.append("incident/property groups overlap between train and evaluation splits")
    for case in cases:
        if any(available_at > case.prediction_at for available_at in case.available_at):
            failures.append(f"future feature availability in case {case.case_id}")
    if train and evaluation:
        latest_train = max(case.prediction_at for case in train)
        earliest_evaluation = min(case.prediction_at for case in evaluation)
        if latest_train >= earliest_evaluation:
            failures.append("evaluation prediction time is not after the training time window")
    return TemporalEvaluationReport(
        passed=not failures,
        failures=tuple(dict.fromkeys(failures)),
        # This Phase 5 harness validates leakage and reproducibility contracts only. It never
        # turns fixture or unlabeled data into an accuracy/calibration claim.
        accuracy_claim_allowed=False,
        metrics={},
    )
