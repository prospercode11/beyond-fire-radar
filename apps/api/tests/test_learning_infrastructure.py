from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db import get_db
from app.learning.service import (
    FEATURE_DEFINITIONS,
    FEATURE_NAMES,
    _build_splits,
    _evaluate_rows,
    _fit_logistic,
    _leakage_report,
)
from app.main import app
from app.models import (
    EvaluationManifest,
    LearningFeatureSet,
    LearningLabelSet,
    TrainingDatasetSnapshot,
    User,
)
from fastapi.testclient import TestClient


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _session():
    override = app.dependency_overrides[get_db]
    generator = override()
    return next(generator), generator


def _row(index: int, *, future_feature: bool = False, early_label: bool = False) -> dict:
    prediction = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    label = prediction + timedelta(days=2)
    available = prediction + timedelta(days=2) if future_feature else prediction
    if early_label:
        label = prediction - timedelta(minutes=1)
    return {
        "row_id": f"row-{index}",
        "incident_id": f"incident-{index}",
        "prediction_at": prediction.isoformat(),
        "label_at": label.isoformat(),
        "features": {"provisional_score": index / 10, "missing_feature_count": 0.0},
        "feature_available_at": {"provisional_score": available.isoformat()},
        "target": index % 2,
    }


def test_time_grouped_split_and_leakage_checks_are_deterministic() -> None:
    rows = [_row(index) for index in range(6)]
    assignments, report = _build_splits(rows)
    assert report["passed"] is True
    assert report["version"] == "time-grouped-split.v1"
    assert len({assignments[row["row_id"]] for row in rows}) == 3
    assert (
        len(
            {row["incident_id"] for row in rows if assignments[row["row_id"]] == "train"}
            & {row["incident_id"] for row in rows if assignments[row["row_id"]] == "test"}
        )
        == 0
    )

    invalid = [_row(0, future_feature=True), _row(1, early_label=True), _row(2)]
    invalid_assignments, _ = _build_splits(invalid)
    leakage = _leakage_report(invalid, invalid_assignments)
    assert leakage["passed"] is False
    assert any("future feature" in item for item in leakage["failures"])
    assert any("label is not after prediction" in item for item in leakage["failures"])


def test_logistic_baseline_metrics_include_uncertainty_and_no_claim() -> None:
    rows = [_row(index) for index in range(6)]
    assignments, split_report = _build_splits(rows)
    assert split_report["passed"] is True
    artifact = _fit_logistic(rows[:4], ["provisional_score", "missing_feature_count"])
    metrics = _evaluate_rows(rows, assignments, artifact)
    assert artifact["algorithm"] == "logistic_baseline"
    assert "test" in metrics["splits"]
    assert "precision_interval" in metrics["splits"]["test"]["thresholds"]["0.5"]
    assert "reliability_bins" in metrics["splits"]["test"]["calibration"]
    assert "thresholds" in metrics["splits"]["test"]["uncertainty"]
    assert metrics["accuracy_claim_allowed"] is False
    assert metrics["calibration"]["real_world_claim_allowed"] is False


def test_learning_api_keeps_fixture_data_inactive_and_supports_replay_and_drift(
    client: TestClient,
) -> None:
    headers = _auth(client)
    db, generator = _session()
    try:
        user = db.query(User).filter(User.email == "admin@example.com").one()
        manifest = EvaluationManifest(
            id=str(uuid4()),
            manifest_type="outcomes_analytics",
            manifest_version="evaluation-manifest.v1",
            as_of=datetime(2026, 8, 1, tzinfo=timezone.utc),
            filters={"mechanics": True},
            incident_ids=[],
            score_run_ids=[],
            label_ids=[],
            outcome_event_ids=[],
            source_acquisition_modes=["synthetic_fixture"],
            source_retrieval_ids=[],
            source_property_import_ids=[],
            source_provider_ids=["fixture.sarasota.dispatch"],
            source_authorization_bases=["fixture"],
            source_snapshot_hashes=["fixture-hash"],
            source_provenance={"retrievals": [], "property_imports": []},
            claim_status="directional_only",
            created_by=user.id,
        )
        comparison_manifest = EvaluationManifest(
            id=str(uuid4()),
            manifest_type="outcomes_analytics",
            manifest_version="evaluation-manifest.v1",
            as_of=manifest.as_of,
            filters={"mechanics": True, "comparison": True},
            incident_ids=[],
            score_run_ids=[],
            label_ids=[],
            outcome_event_ids=[],
            source_acquisition_modes=["synthetic_fixture"],
            source_retrieval_ids=[],
            source_property_import_ids=[],
            source_provider_ids=["fixture.sarasota.dispatch"],
            source_authorization_bases=["fixture"],
            source_snapshot_hashes=["fixture-hash-comparison"],
            source_provenance={"retrievals": [], "property_imports": []},
            claim_status="directional_only",
            created_by=user.id,
        )
        feature_set = LearningFeatureSet(
            id=str(uuid4()),
            version="learning-features.test.v1",
            status="active",
            feature_names=FEATURE_NAMES,
            definitions=FEATURE_DEFINITIONS,
            created_by=user.id,
        )
        label_set = LearningLabelSet(
            id=str(uuid4()),
            version="learning-labels-test.v1",
            label_type="review_relevance",
            positive_values=["relevant"],
            negative_values=["not_relevant"],
            excluded_values=["uncertain"],
            definition="Synthetic mechanics-only target.",
            created_by=user.id,
        )
        rows = []
        for index in range(6):
            item = _row(index)
            item["features"] = {name: 0.0 for name in FEATURE_NAMES}
            item["features"]["provisional_score"] = index / 10
            rows.append(item)
        assignments = {
            row["row_id"]: "train" if index < 4 else "validation" if index == 4 else "test"
            for index, row in enumerate(rows)
        }
        snapshot = TrainingDatasetSnapshot(
            id=str(uuid4()),
            idempotency_key="mechanics-dataset-seed",
            dataset_version="training-dataset.test.v1",
            feature_set_id=feature_set.id,
            label_set_id=label_set.id,
            source_manifest_id=manifest.id,
            as_of=manifest.as_of,
            status="mechanics_ready",
            mechanics_only=True,
            real_data_eligible=False,
            row_count=len(rows),
            incident_count=len(rows),
            filters={"mechanics": True},
            source_provenance=manifest.source_provenance,
            rows=rows,
            split_assignments=assignments,
            split_report={"version": "time-grouped-split.v1", "passed": True},
            leakage_report={"passed": True, "failures": []},
            blocked_reasons=["synthetic mechanics fixture"],
            created_by=user.id,
        )
        comparison = TrainingDatasetSnapshot(
            id=str(uuid4()),
            idempotency_key="mechanics-dataset-comparison",
            dataset_version="training-dataset.test.v1",
            feature_set_id=feature_set.id,
            label_set_id=label_set.id,
            source_manifest_id=comparison_manifest.id,
            as_of=manifest.as_of,
            status="mechanics_ready",
            mechanics_only=True,
            real_data_eligible=False,
            row_count=len(rows),
            incident_count=len(rows),
            filters={"mechanics": True},
            source_provenance=manifest.source_provenance,
            rows=[
                {**row, "features": {**row["features"], "provisional_score": 1.0}} for row in rows
            ],
            split_assignments=assignments,
            split_report={"version": "time-grouped-split.v1", "passed": True},
            leakage_report={"passed": True, "failures": []},
            blocked_reasons=["synthetic mechanics fixture"],
            created_by=user.id,
        )
        db.add_all([manifest, comparison_manifest, feature_set, label_set, snapshot, comparison])
        db.commit()
        snapshot_id = snapshot.id
        comparison_id = comparison.id
    finally:
        generator.close()

    db, generator = _session()
    try:
        blocked_snapshot = db.get(TrainingDatasetSnapshot, snapshot_id)
        assert blocked_snapshot is not None
        blocked_snapshot.status = "blocked"
        db.commit()
    finally:
        generator.close()
    blocked_training = client.post(
        "/api/v1/learning/models/train",
        headers=headers,
        json={
            "dataset_snapshot_id": snapshot_id,
            "algorithm": "logistic_baseline",
            "mechanics_only": True,
            "idempotency_key": "blocked-model-train-1",
        },
    )
    assert blocked_training.status_code == 422

    db, generator = _session()
    try:
        restored_snapshot = db.get(TrainingDatasetSnapshot, snapshot_id)
        assert restored_snapshot is not None
        restored_snapshot.status = "mechanics_ready"
        db.commit()
    finally:
        generator.close()

    trained = client.post(
        "/api/v1/learning/models/train",
        headers=headers,
        json={
            "dataset_snapshot_id": snapshot_id,
            "algorithm": "logistic_baseline",
            "mechanics_only": True,
            "idempotency_key": "mechanics-model-train-1",
        },
    )
    trained.raise_for_status()
    model = trained.json()
    assert model["status"] == "inactive"
    assert model["artifact"]["algorithm"] == "logistic_baseline"
    assert model["evaluation"]["accuracy_claim_allowed"] is False

    replay = client.post(
        f"/api/v1/learning/models/{model['id']}/replay",
        headers=headers,
        json={"idempotency_key": "mechanics-replay-1"},
    )
    replay.raise_for_status()
    assert replay.json()["accuracy_claim_allowed"] is False
    replay_again = client.post(
        f"/api/v1/learning/models/{model['id']}/replay",
        headers=headers,
        json={"idempotency_key": "mechanics-replay-1"},
    )
    replay_again.raise_for_status()
    assert replay_again.json()["id"] == replay.json()["id"]

    drift = client.post(
        "/api/v1/learning/drift",
        headers=headers,
        json={
            "baseline_snapshot_id": snapshot_id,
            "comparison_snapshot_id": comparison_id,
            "idempotency_key": "mechanics-drift-1",
        },
    )
    drift.raise_for_status()
    assert drift.json()["metrics"]["accuracy_claim_allowed"] is False

    policy = client.get("/api/v1/learning/policy", headers=headers)
    policy.raise_for_status()
    assert policy.json()["mode"] == "rule_based_fallback"
    assert policy.json()["learned_model_active"] is False

    promotion = client.post(
        f"/api/v1/learning/models/{model['id']}/promote",
        headers=headers,
        json={"idempotency_key": "mechanics-promote-1"},
    )
    assert promotion.status_code == 422


def test_dataset_api_blocks_directional_manifest_without_real_labels(client: TestClient) -> None:
    headers = _auth(client)
    db, generator = _session()
    try:
        user = db.query(User).filter(User.email == "admin@example.com").one()
        manifest = EvaluationManifest(
            id=str(uuid4()),
            manifest_type="outcomes_analytics",
            manifest_version="evaluation-manifest.v1",
            as_of=datetime.now(timezone.utc),
            filters={},
            incident_ids=[],
            score_run_ids=[],
            label_ids=[],
            outcome_event_ids=[],
            source_acquisition_modes=["synthetic_fixture"],
            source_retrieval_ids=[],
            source_property_import_ids=[],
            source_provider_ids=[],
            source_authorization_bases=[],
            source_snapshot_hashes=[],
            source_provenance={"retrievals": [], "property_imports": []},
            claim_status="directional_only",
            created_by=user.id,
        )
        db.add(manifest)
        db.commit()
        manifest_id = manifest.id
    finally:
        generator.close()
    response = client.post(
        "/api/v1/learning/datasets",
        headers=headers,
        json={
            "manifest_id": manifest_id,
            "target_label_type": "review_relevance",
            "mechanics_only": False,
            "idempotency_key": "blocked-dataset-1",
        },
    )
    response.raise_for_status()
    assert response.json()["status"] == "blocked"
    assert response.json()["real_data_eligible"] is False
    assert any(
        "real approved outcome evidence" in item for item in response.json()["blocked_reasons"]
    )
