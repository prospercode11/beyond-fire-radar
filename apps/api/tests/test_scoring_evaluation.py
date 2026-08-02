from __future__ import annotations

from datetime import datetime, timezone

from app.opportunities.evaluation import TemporalEvaluationCase, validate_temporal_evaluation


def test_temporal_evaluation_rejects_future_features_and_group_leakage() -> None:
    cases = [
        TemporalEvaluationCase(
            "train-1",
            "incident-a",
            "train",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            (datetime(2025, 12, 31, tzinfo=timezone.utc),),
        ),
        TemporalEvaluationCase(
            "eval-1",
            "incident-a",
            "evaluation",
            datetime(2026, 2, 1, tzinfo=timezone.utc),
            (datetime(2026, 1, 31, tzinfo=timezone.utc),),
        ),
    ]
    report = validate_temporal_evaluation(cases)
    assert report.passed is False
    assert "incident/property groups overlap between train and evaluation splits" in report.failures
    assert report.accuracy_claim_allowed is False


def test_temporal_evaluation_accepts_grouped_time_order_without_metrics() -> None:
    cases = [
        TemporalEvaluationCase(
            "train-1",
            "incident-a",
            "train",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            (datetime(2025, 12, 31, tzinfo=timezone.utc),),
        ),
        TemporalEvaluationCase(
            "eval-1",
            "incident-b",
            "evaluation",
            datetime(2026, 2, 1, tzinfo=timezone.utc),
            (datetime(2026, 1, 31, tzinfo=timezone.utc),),
        ),
    ]
    report = validate_temporal_evaluation(cases)
    assert report.passed is True
    assert report.metrics == {}
    assert report.accuracy_claim_allowed is False
