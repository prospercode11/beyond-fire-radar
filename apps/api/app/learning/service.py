from __future__ import annotations

import importlib.util
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import get_settings
from app.models import (
    EvaluationManifest,
    LearningFeatureSet,
    LearningLabelSet,
    ModelControlAction,
    ModelDriftReport,
    ModelRelease,
    ModelReplayRun,
    OpportunityScoreFeature,
    OpportunityScoreRun,
    OutcomeLabel,
    PropertyImport,
    ProviderRetrieval,
    RawSnapshot,
    TrainingDatasetSnapshot,
)

FEATURE_SET_VERSION = "learning-features.v1"
LABEL_SET_VERSION = "learning-labels-review-relevance.v1"
DATASET_VERSION = "training-dataset.v1"
SPLIT_VERSION = "time-grouped-split.v1"
MODEL_CARD_VERSION = "model-card.v1"
DRIFT_THRESHOLD = 0.2

FEATURE_NAMES = [
    "provisional_score",
    "score_source_quality",
    "score_incident_validity",
    "score_property_match_quality",
    "score_material_loss_evidence",
    "score_loss_complexity",
    "score_beyond_adjusting_fit",
    "score_data_sufficiency",
    "alert_eligibility",
    "missing_feature_count",
]
FEATURE_DEFINITIONS: dict[str, str] = {
    "provisional_score": "Phase 5 provisional score divided by 100; it is not a probability.",
    "score_source_quality": "Versioned Phase 5 source-quality component; missing values are imputed to 0.",
    "score_incident_validity": "Versioned Phase 5 incident-validity component; missing values are imputed to 0.",
    "score_property_match_quality": "Versioned Phase 5 property-match component; missing values are imputed to 0.",
    "score_material_loss_evidence": "Versioned Phase 5 material-loss component; missing values are imputed to 0.",
    "score_loss_complexity": "Versioned Phase 5 loss-complexity component; missing values are imputed to 0.",
    "score_beyond_adjusting_fit": "Versioned Phase 5 fit component; missing values are imputed to 0.",
    "score_data_sufficiency": "Versioned Phase 5 data-sufficiency component; missing values are imputed to 0.",
    "alert_eligibility": "Binary Phase 5 hard-gate output, not an outreach or loss conclusion.",
    "missing_feature_count": "Count of missing Phase 5 component values, available at the score boundary.",
}
LABEL_CONTRACTS: dict[str, dict[str, Any]] = {
    "review_relevance": {
        "version": LABEL_SET_VERSION,
        "positive_values": ["relevant"],
        "negative_values": ["not_relevant"],
        "excluded_values": ["uncertain"],
        "definition": "Manual internal review-relevance labels; not a damage, claim, coverage, or conversion label.",
    },
    "classification": {
        "version": "learning-labels-classification.v1",
        "positive_values": ["correct"],
        "negative_values": ["incorrect"],
        "excluded_values": ["uncertain"],
        "definition": "Manual source-faithful incident-classification labels.",
    },
}
SUPPORTED_ALGORITHMS = {"logistic_baseline", "gradient_boosted"}
REAL_SOURCE_MODES = {"manual_snapshot"}
REAL_DISPATCH_PROVIDER = "sarasota.official_dispatch"
REAL_PROPERTY_PROVIDER = "sarasota.property_appraiser"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _iso(value: Optional[datetime]) -> Optional[str]:
    normalized = _utc(value)
    return normalized.isoformat() if normalized else None


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed) or _now()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def ensure_learning_contracts(
    db: Session,
    *,
    actor_user_id: str,
    target_label_type: str = "review_relevance",
    request_id: str,
) -> tuple[LearningFeatureSet, LearningLabelSet]:
    contract = LABEL_CONTRACTS.get(target_label_type)
    if contract is None:
        raise ValueError(f"unsupported learning label type: {target_label_type}")
    feature_set = db.scalar(
        select(LearningFeatureSet).where(LearningFeatureSet.version == FEATURE_SET_VERSION)
    )
    if feature_set is None:
        feature_set = LearningFeatureSet(
            id=str(uuid4()),
            version=FEATURE_SET_VERSION,
            status="active",
            feature_names=FEATURE_NAMES,
            definitions=FEATURE_DEFINITIONS,
            created_by=actor_user_id,
        )
        db.add(feature_set)
        db.flush()
        record_audit(
            db,
            action="learning.feature_set.created",
            resource_type="learning_feature_set",
            resource_id=feature_set.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={"version": feature_set.version},
        )
    label_version = str(contract["version"])
    label_set = db.scalar(select(LearningLabelSet).where(LearningLabelSet.version == label_version))
    if label_set is None:
        label_set = LearningLabelSet(
            id=str(uuid4()),
            version=label_version,
            label_type=target_label_type,
            positive_values=list(contract["positive_values"]),
            negative_values=list(contract["negative_values"]),
            excluded_values=list(contract["excluded_values"]),
            definition=str(contract["definition"]),
            created_by=actor_user_id,
        )
        db.add(label_set)
        db.flush()
        record_audit(
            db,
            action="learning.label_set.created",
            resource_type="learning_label_set",
            resource_id=label_set.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={"version": label_set.version, "label_type": target_label_type},
        )
    return feature_set, label_set


def _manifest_is_real_eligible(db: Session, manifest: EvaluationManifest) -> bool:
    modes = set(manifest.source_acquisition_modes or [])
    if manifest.claim_status != "real_world_approved" or modes != REAL_SOURCE_MODES:
        return False
    if not manifest.source_provenance or not manifest.source_retrieval_ids:
        return False
    retrievals = db.scalars(
        select(ProviderRetrieval).where(ProviderRetrieval.id.in_(manifest.source_retrieval_ids))
    ).all()
    if len(retrievals) != len(set(manifest.source_retrieval_ids)):
        return False
    for retrieval in retrievals:
        if (
            retrieval.provider_id != REAL_DISPATCH_PROVIDER
            or retrieval.status != "imported"
            or retrieval.acquisition_mode not in REAL_SOURCE_MODES
            or retrieval.authorization_basis != "manual_attestation"
        ):
            return False
        if not retrieval.snapshot_hash:
            return False
    snapshots = db.scalars(
        select(RawSnapshot).where(RawSnapshot.retrieval_id.in_(manifest.source_retrieval_ids))
    ).all()
    if len(snapshots) != len(retrievals):
        return False
    property_ids = set(manifest.source_property_import_ids or [])
    if property_ids:
        imports = db.scalars(
            select(PropertyImport).where(PropertyImport.id.in_(property_ids))
        ).all()
        if len(imports) != len(property_ids):
            return False
        if any(
            item.provider_id != REAL_PROPERTY_PROVIDER
            or item.acquisition_mode not in REAL_SOURCE_MODES
            or item.authorization_basis != "manual_attestation"
            or item.status not in {"imported", "completed"}
            for item in imports
        ):
            return False
    declared_providers = set(manifest.source_provider_ids or [])
    actual_providers = {item.provider_id for item in retrievals} | {
        item.provider_id for item in (imports if property_ids else [])
    }
    actual_modes = {item.acquisition_mode for item in retrievals} | {
        item.acquisition_mode for item in (imports if property_ids else [])
    }
    actual_authorization = {
        item.authorization_basis for item in retrievals if item.authorization_basis
    } | {
        item.authorization_basis
        for item in (imports if property_ids else [])
        if item.authorization_basis
    }
    actual_hashes = {item.snapshot_hash for item in retrievals if item.snapshot_hash} | {
        item.content_hash for item in (imports if property_ids else [])
    }
    return bool(
        declared_providers == actual_providers
        and set(manifest.source_acquisition_modes or []) == actual_modes
        and set(manifest.source_authorization_bases or []) == actual_authorization
        and set(manifest.source_snapshot_hashes or []) == actual_hashes
    )


def _component_values(
    score: OpportunityScoreRun, score_features: list[OpportunityScoreFeature]
) -> tuple[dict[str, float], dict[str, Optional[datetime]]]:
    values: dict[str, float] = {}
    availability: dict[str, Optional[datetime]] = {}
    raw = {item.feature_name: item for item in score_features}
    missing = 0
    for name in FEATURE_NAMES:
        if name == "provisional_score":
            values[name] = max(0.0, min(1.0, float(score.provisional_score or 0.0) / 100.0))
            availability[name] = _utc(score.as_of)
        elif name == "alert_eligibility":
            values[name] = 1.0 if score.alert_eligibility else 0.0
            availability[name] = _utc(score.as_of)
        elif name == "missing_feature_count":
            continue
        else:
            component_name = name.removeprefix("score_")
            item = raw.get(component_name)
            if item is None or item.value is None:
                values[name] = 0.0
                availability[name] = _utc(score.as_of)
                missing += 1
            else:
                values[name] = max(0.0, min(1.0, float(item.value)))
                availability[name] = _utc(item.available_at) or _utc(score.as_of)
    values["missing_feature_count"] = min(1.0, missing / 7.0)
    availability["missing_feature_count"] = _utc(score.as_of)
    return values, availability


def _build_splits(rows: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, Any]]:
    groups: dict[str, datetime] = {}
    for row in rows:
        prediction_at = _parse_iso(str(row["prediction_at"]))
        group = str(row["incident_id"])
        groups[group] = max(groups.get(group, prediction_at), prediction_at)
    ordered_groups = sorted(groups, key=lambda group: (groups[group], group))
    if len(ordered_groups) < 3:
        return (
            {str(row["row_id"]): "train" for row in rows},
            {
                "version": SPLIT_VERSION,
                "passed": False,
                "failures": [
                    "at least three incident groups are required for train/validation/test"
                ],
                "group_counts": {"train": len(ordered_groups), "validation": 0, "test": 0},
            },
        )
    train_end = max(1, int(len(ordered_groups) * 0.6))
    validation_end = max(train_end + 1, int(len(ordered_groups) * 0.8))
    validation_end = min(validation_end, len(ordered_groups) - 1)
    split_by_group: dict[str, str] = {}
    for index, group in enumerate(ordered_groups):
        split_by_group[group] = (
            "train" if index < train_end else "validation" if index < validation_end else "test"
        )
    assignments = {str(row["row_id"]): split_by_group[str(row["incident_id"])] for row in rows}
    group_counts = {
        split: sum(value == split for value in split_by_group.values())
        for split in ("train", "validation", "test")
    }
    train_times = [groups[group] for group, split in split_by_group.items() if split == "train"]
    evaluation_times = [
        groups[group] for group, split in split_by_group.items() if split in {"validation", "test"}
    ]
    failures = []
    if train_times and evaluation_times and max(train_times) >= min(evaluation_times):
        failures.append("training predictions are not strictly earlier than held-out predictions")
    return (
        assignments,
        {
            "version": SPLIT_VERSION,
            "passed": not failures,
            "failures": failures,
            "group_counts": group_counts,
            "train_latest_prediction_at": _iso(max(train_times)) if train_times else None,
            "held_out_earliest_prediction_at": _iso(min(evaluation_times))
            if evaluation_times
            else None,
            "group_overlap": False,
        },
    )


def _leakage_report(rows: list[dict[str, Any]], assignments: dict[str, str]) -> dict[str, Any]:
    failures: list[str] = []
    seen_groups: dict[str, str] = {}
    for row in rows:
        row_id = str(row["row_id"])
        prediction_at = _parse_iso(str(row["prediction_at"]))
        label_at = _parse_iso(str(row["label_at"]))
        if label_at <= prediction_at:
            failures.append(f"label is not after prediction for row {row_id}")
        for name, available_at in (row.get("feature_available_at") or {}).items():
            if available_at and _parse_iso(str(available_at)) > prediction_at:
                failures.append(
                    f"future feature {name} is available after prediction for row {row_id}"
                )
        group = str(row["incident_id"])
        split = assignments.get(row_id)
        if group in seen_groups and seen_groups[group] != split:
            failures.append(f"incident group {group} appears in multiple splits")
        seen_groups[group] = str(split)
    return {"passed": not failures, "failures": _unique(failures)}


def _make_dataset_rows(
    db: Session,
    manifest: EvaluationManifest,
    label_set: LearningLabelSet,
) -> tuple[list[dict[str, Any]], list[str]]:
    manifest_incident_ids = set(manifest.incident_ids or [])
    if not manifest_incident_ids:
        return [], ["manifest has no incident IDs"]
    labels = db.scalars(
        select(OutcomeLabel)
        .where(OutcomeLabel.id.in_(manifest.label_ids))
        .order_by(OutcomeLabel.created_at, OutcomeLabel.id)
    ).all()
    score_ids = set(manifest.score_run_ids or [])
    scores = {
        score.id: score
        for score in db.scalars(
            select(OpportunityScoreRun).where(OpportunityScoreRun.id.in_(score_ids))
        ).all()
    }
    feature_rows: dict[str, list[OpportunityScoreFeature]] = defaultdict(list)
    score_features = db.scalars(
        select(OpportunityScoreFeature).where(OpportunityScoreFeature.score_run_id.in_(score_ids))
    ).all()
    for item in score_features:
        feature_rows[item.score_run_id].append(item)
    positive = set(label_set.positive_values)
    negative = set(label_set.negative_values)
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for label in labels:
        if label.label_type != label_set.label_type or label.label_value not in positive | negative:
            continue
        if label.incident_id not in manifest_incident_ids:
            failures.append(f"label {label.id} incident is not in the source manifest")
            continue
        if label.score_run_id is None:
            failures.append(f"label {label.id} has no bound score run")
            continue
        score = scores.get(label.score_run_id)
        if score is None:
            failures.append(f"score run {label.score_run_id} is not in the source manifest")
            continue
        if score.incident_id != label.incident_id:
            failures.append(
                f"score run {score.id} and label {label.id} reference different incidents"
            )
            continue
        prediction_at = _utc(score.as_of) or _utc(score.created_at) or _now()
        label_at = _utc(label.created_at) or _now()
        manifest_as_of = _utc(manifest.as_of) or _now()
        score_created_at = _utc(score.created_at)
        if score_created_at is not None and score_created_at > manifest_as_of:
            failures.append(f"score run {score.id} is after the manifest boundary")
            continue
        if prediction_at > manifest_as_of or label_at > manifest_as_of:
            failures.append(f"label {label.id} or score {score.id} is after the manifest boundary")
            continue
        values, available = _component_values(score, feature_rows[label.score_run_id])
        raw_features = {item.feature_name: item for item in feature_rows[label.score_run_id]}
        feature_provenance = {
            name: {
                "score_run_id": score.id,
                "feature_version": (
                    raw_features[name].feature_version if name in raw_features else "score.as_of"
                ),
                "source_observation_ids": (
                    list(raw_features[name].source_observation_ids)
                    if name in raw_features
                    else list(score.source_observation_ids)
                ),
                "available_at": _iso(available.get(name)),
                "status": "observed" if name in raw_features else "missing_or_derived",
            }
            for name in values
        }
        rows.append(
            {
                "row_id": f"{label.id}:{score.id}",
                "incident_id": label.incident_id,
                "score_run_id": score.id,
                "label_id": label.id,
                "prediction_at": prediction_at.isoformat(),
                "label_at": label_at.isoformat(),
                "features": values,
                "feature_available_at": {key: _iso(value) for key, value in available.items()},
                "feature_provenance": feature_provenance,
                "target": 1 if label.label_value in positive else 0,
            }
        )
    return rows, _unique(failures)


def create_dataset_snapshot(
    db: Session,
    *,
    manifest_id: str,
    target_label_type: str,
    mechanics_only: bool,
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> TrainingDatasetSnapshot:
    manifest = db.get(EvaluationManifest, manifest_id)
    if manifest is None:
        raise ValueError("evaluation manifest not found")
    feature_set, label_set = ensure_learning_contracts(
        db,
        actor_user_id=actor_user_id,
        target_label_type=target_label_type,
        request_id=request_id,
    )
    existing_by_key = db.scalar(
        select(TrainingDatasetSnapshot).where(
            TrainingDatasetSnapshot.idempotency_key == idempotency_key
        )
    )
    if existing_by_key is not None:
        return existing_by_key
    existing = db.scalar(
        select(TrainingDatasetSnapshot).where(
            TrainingDatasetSnapshot.source_manifest_id == manifest_id,
            TrainingDatasetSnapshot.feature_set_id == feature_set.id,
            TrainingDatasetSnapshot.label_set_id == label_set.id,
        )
    )
    if existing is not None:
        return existing
    rows, row_failures = _make_dataset_rows(db, manifest, label_set)
    assignments, split_report = _build_splits(rows)
    leakage_report = _leakage_report(rows, assignments)
    real_data_eligible = _manifest_is_real_eligible(db, manifest)
    blocked_reasons = list(row_failures)
    if not rows:
        blocked_reasons.append(
            "no bound, non-uncertain labels are available for the selected target"
        )
    if not split_report["passed"]:
        blocked_reasons.extend(str(item) for item in split_report["failures"])
    if not leakage_report["passed"]:
        blocked_reasons.extend(str(item) for item in leakage_report["failures"])
    if not real_data_eligible:
        blocked_reasons.append(
            "real approved outcome evidence is required; fixture or directional manifests remain mechanics-only"
        )
    status = (
        "ready"
        if rows and real_data_eligible and split_report["passed"] and leakage_report["passed"]
        else "blocked"
    )
    if (
        status == "blocked"
        and mechanics_only
        and rows
        and split_report["passed"]
        and leakage_report["passed"]
    ):
        status = "mechanics_ready"
    snapshot = TrainingDatasetSnapshot(
        id=str(uuid4()),
        idempotency_key=idempotency_key,
        dataset_version=DATASET_VERSION,
        feature_set_id=feature_set.id,
        label_set_id=label_set.id,
        source_manifest_id=manifest.id,
        as_of=_utc(manifest.as_of) or _now(),
        status=status,
        mechanics_only=mechanics_only,
        real_data_eligible=real_data_eligible,
        row_count=len(rows),
        incident_count=len({str(row["incident_id"]) for row in rows}),
        filters={
            "target_label_type": target_label_type,
            "positive_values": list(label_set.positive_values),
            "negative_values": list(label_set.negative_values),
            "excluded_values": list(label_set.excluded_values),
            "prediction_boundary": "score.as_of <= label.created_at and score id is in manifest",
        },
        source_provenance=manifest.source_provenance,
        rows=rows,
        split_assignments=assignments,
        split_report=split_report,
        leakage_report=leakage_report,
        blocked_reasons=_unique(blocked_reasons),
        created_by=actor_user_id,
    )
    db.add(snapshot)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replayed = db.scalar(
            select(TrainingDatasetSnapshot).where(
                TrainingDatasetSnapshot.idempotency_key == idempotency_key
            )
        )
        if replayed is not None:
            return replayed
        raise
    record_audit(
        db,
        action="learning.dataset_snapshot.created",
        resource_type="training_dataset_snapshot",
        resource_id=snapshot.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={
            "manifest_id": manifest.id,
            "status": snapshot.status,
            "mechanics_only": mechanics_only,
            "row_count": snapshot.row_count,
            "real_data_eligible": real_data_eligible,
        },
    )
    return snapshot


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 60.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -60.0))
    return z / (1.0 + z)


def _fit_logistic(rows: list[dict[str, Any]], feature_names: list[str]) -> dict[str, Any]:
    weights = [0.0 for _ in feature_names]
    intercept = 0.0
    learning_rate = 0.25
    regularization = 0.01
    for _ in range(600):
        gradients = [0.0 for _ in feature_names]
        intercept_gradient = 0.0
        for row in rows:
            vector = [float((row.get("features") or {}).get(name, 0.0)) for name in feature_names]
            target = float(row["target"])
            probability = _sigmoid(
                intercept + sum(weight * value for weight, value in zip(weights, vector))
            )
            error = probability - target
            intercept_gradient += error
            for index, value in enumerate(vector):
                gradients[index] += error * value
        count = max(1, len(rows))
        intercept -= learning_rate * intercept_gradient / count
        for index, gradient in enumerate(gradients):
            weights[index] -= learning_rate * (gradient / count + regularization * weights[index])
    return {
        "algorithm": "logistic_baseline",
        "feature_names": feature_names,
        "weights": [round(value, 12) for value in weights],
        "intercept": round(intercept, 12),
        "optimizer": {"iterations": 600, "learning_rate": learning_rate, "l2": regularization},
    }


def _predict(artifact: dict[str, Any], row: dict[str, Any]) -> float:
    features = artifact.get("feature_names") or []
    values = row.get("features") or {}
    weights = artifact.get("weights") or []
    raw = float(artifact.get("intercept", 0.0))
    raw += sum(
        float(weight) * float(values.get(name, 0.0)) for name, weight in zip(features, weights)
    )
    return _sigmoid(raw)


def _wilson(successes: int, total: int) -> dict[str, Optional[float]]:
    if total == 0:
        return {"low": None, "high": None}
    proportion = successes / total
    z = 1.96
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    )
    return {"low": max(0.0, center - margin), "high": min(1.0, center + margin)}


def _reliability_bins(split_rows: list[dict[str, Any]], bin_count: int = 5) -> list[dict[str, Any]]:
    bins: list[list[dict[str, Any]]] = [[] for _ in range(bin_count)]
    for item in split_rows:
        index = min(bin_count - 1, int(float(item["prediction"]) * bin_count))
        bins[index].append(item)
    result: list[dict[str, Any]] = []
    for index, members in enumerate(bins):
        predictions = [float(item["prediction"]) for item in members]
        observed = [int(item["target"]) for item in members]
        result.append(
            {
                "lower": index / bin_count,
                "upper": (index + 1) / bin_count,
                "count": len(members),
                "mean_prediction": sum(predictions) / len(predictions) if predictions else None,
                "observed_rate": sum(observed) / len(observed) if observed else None,
            }
        )
    return result


def _selective_prediction_metrics(
    split_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    thresholds: dict[str, Any] = {}
    for confidence in (0.55, 0.65, 0.75, 0.85):
        selected = [
            item
            for item in split_rows
            if max(float(item["prediction"]), 1.0 - float(item["prediction"])) >= confidence
        ]
        errors = sum(
            (float(item["prediction"]) >= 0.5) != bool(item["target"]) for item in selected
        )
        thresholds[str(confidence)] = {
            "selected_count": len(selected),
            "abstained_count": len(split_rows) - len(selected),
            "coverage": len(selected) / len(split_rows) if split_rows else None,
            "risk": errors / len(selected) if selected else None,
            "risk_interval": _wilson(errors, len(selected)),
        }
    entropy = []
    for item in split_rows:
        probability = min(1.0 - 1e-12, max(1e-12, float(item["prediction"])))
        entropy.append(
            -(
                probability * math.log(probability)
                + (1.0 - probability) * math.log(1.0 - probability)
            )
        )
    entropy.sort()
    return {
        "policy": "abstain when max(prediction, 1-prediction) is below the selected confidence",
        "thresholds": thresholds,
        "mean_entropy": sum(entropy) / len(entropy) if entropy else None,
        "p95_entropy": entropy[min(len(entropy) - 1, int(len(entropy) * 0.95))]
        if entropy
        else None,
        "accuracy_claim_allowed": False,
    }


def _evaluate_rows(
    rows: list[dict[str, Any]], assignments: dict[str, str], artifact: dict[str, Any]
) -> dict[str, Any]:
    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        item["prediction"] = _predict(artifact, row)
        by_split[assignments.get(str(row["row_id"]), "unassigned")].append(item)
    split_metrics: dict[str, Any] = {}
    for split, split_rows in by_split.items():
        if split == "unassigned":
            continue
        threshold_metrics: dict[str, Any] = {}
        for threshold in (0.25, 0.5, 0.75):
            predicted_positive = [item for item in split_rows if item["prediction"] >= threshold]
            true_positive = sum(item["target"] == 1 for item in predicted_positive)
            actual_positive = sum(item["target"] == 1 for item in split_rows)
            precision = true_positive / len(predicted_positive) if predicted_positive else None
            recall = true_positive / actual_positive if actual_positive else None
            threshold_metrics[str(threshold)] = {
                "precision": precision,
                "recall": recall,
                "predicted_positive": len(predicted_positive),
                "actual_positive": actual_positive,
                "precision_interval": _wilson(true_positive, len(predicted_positive)),
            }
        brier = (
            sum((item["prediction"] - item["target"]) ** 2 for item in split_rows) / len(split_rows)
            if split_rows
            else None
        )
        ranked = sorted(
            split_rows, key=lambda item: (-item["prediction"], item["incident_id"], item["row_id"])
        )
        k = min(10, len(ranked))
        top_precision = sum(item["target"] == 1 for item in ranked[:k]) / k if k else None
        split_metrics[split] = {
            "row_count": len(split_rows),
            "thresholds": threshold_metrics,
            "brier_score": brier,
            "precision_at_k": {"k": k, "value": top_precision},
            "target_positive_count": sum(item["target"] == 1 for item in split_rows),
            "calibration": {
                "reliability_bins": _reliability_bins(split_rows),
                "brier_score": brier,
                "status": "directional_only",
            },
            "uncertainty": _selective_prediction_metrics(split_rows),
        }
    return {
        "version": "learning-evaluation.v1",
        "splits": split_metrics,
        "accuracy_claim_allowed": False,
        "calibration": {
            "status": "directional_only",
            "method": "reliability bins and Brier score",
            "real_world_claim_allowed": False,
        },
        "uncertainty": {
            "method": "confidence-threshold selective prediction and predictive entropy",
            "real_world_claim_allowed": False,
        },
    }


def _model_card(
    *,
    feature_set: LearningFeatureSet,
    label_set: LearningLabelSet,
    snapshot: TrainingDatasetSnapshot,
) -> dict[str, Any]:
    return {
        "version": MODEL_CARD_VERSION,
        "model_purpose": "Internal research ranking support only; never a damage, coverage, claim, or outreach conclusion.",
        "target": label_set.definition,
        "feature_contract": {
            "version": feature_set.version,
            "features": feature_set.feature_names,
            "missing_data": "numeric missing components are imputed to 0 and counted by missing_feature_count",
            "available_at": "every feature timestamp must be at or before score.as_of",
        },
        "dataset_snapshot_id": snapshot.id,
        "source_provenance": snapshot.source_provenance,
        "limitations": [
            "No model is active by default.",
            "Synthetic or directional labels are mechanics evidence only.",
            "Promotion requires real held-out improvement, calibration, error analysis, approval, and rollback readiness.",
        ],
    }


def train_model(
    db: Session,
    *,
    snapshot_id: str,
    algorithm: str,
    mechanics_only: bool,
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> ModelRelease:
    snapshot = db.get(TrainingDatasetSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError("training dataset snapshot not found")
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"unsupported learning algorithm: {algorithm}")
    existing_by_key = db.scalar(
        select(ModelRelease).where(ModelRelease.idempotency_key == idempotency_key)
    )
    if existing_by_key is not None:
        return existing_by_key
    if snapshot.status not in {"ready", "mechanics_ready"}:
        raise ValueError("training requires a ready or mechanics_ready dataset snapshot")
    if snapshot.status == "mechanics_ready" and not mechanics_only:
        raise ValueError("mechanics_ready snapshots require mechanics_only training")
    feature_set = db.get(LearningFeatureSet, snapshot.feature_set_id)
    label_set = db.get(LearningLabelSet, snapshot.label_set_id)
    if feature_set is None or label_set is None:
        raise ValueError("learning contract is missing")
    model_version = f"{algorithm}.v1.{str(uuid4())[:8]}"
    base_kwargs = dict(
        id=str(uuid4()),
        idempotency_key=idempotency_key,
        model_version=model_version,
        algorithm=algorithm,
        status="blocked",
        feature_set_id=feature_set.id,
        label_set_id=label_set.id,
        dataset_snapshot_id=snapshot.id,
        predecessor_id=None,
        artifact={},
        evaluation={"accuracy_claim_allowed": False},
        training_report={},
        model_card=_model_card(feature_set=feature_set, label_set=label_set, snapshot=snapshot),
        approval_required=True,
        inactive_reason=None,
        created_by=actor_user_id,
    )
    release = ModelRelease(**base_kwargs)
    reasons: list[str] = []
    if algorithm == "gradient_boosted":
        if (
            importlib.util.find_spec("sklearn") is None
            and importlib.util.find_spec("xgboost") is None
        ):
            reasons.append("no approved gradient-boosting dependency is installed")
        else:
            reasons.append(
                "gradient-boosted adapter is not activated in this dependency-light build"
            )
    if not snapshot.rows:
        reasons.append("training dataset has no eligible rows")
    if not snapshot.leakage_report.get("passed", False):
        reasons.append("leakage checks did not pass")
    if not snapshot.split_report.get("passed", False):
        reasons.append("time/group split checks did not pass")
    if not snapshot.real_data_eligible and not mechanics_only:
        reasons.append("real approved labels are required before training outside mechanics mode")
    targets = {int(row["target"]) for row in snapshot.rows}
    if len(targets) < 2:
        reasons.append("both positive and negative labels are required")
    if not reasons and algorithm == "logistic_baseline":
        train_rows = [
            row
            for row in snapshot.rows
            if snapshot.split_assignments.get(str(row["row_id"])) == "train"
        ]
        if len({int(row["target"]) for row in train_rows}) < 2:
            reasons.append("training split requires both positive and negative labels")
        else:
            artifact = _fit_logistic(train_rows, list(feature_set.feature_names))
            release.artifact = artifact
            release.evaluation = _evaluate_rows(snapshot.rows, snapshot.split_assignments, artifact)
            release.evaluation["gates"] = {
                "split_valid": bool(snapshot.split_report.get("passed")),
                "leakage_free": bool(snapshot.leakage_report.get("passed")),
                "held_out_improvement": False,
                "calibration_valid": False,
                "top_alert_precision_improved": False,
                "error_analysis_complete": False,
                "real_data_eligible": snapshot.real_data_eligible,
                "administrator_approval": False,
            }
            release.training_report = {
                "status": "mechanics_only" if mechanics_only else "candidate",
                "trained_rows": len(train_rows),
                "algorithm": algorithm,
                "source_claim_status": "synthetic_or_directional"
                if not snapshot.real_data_eligible
                else "real_pending_gate",
                "reproducibility": {
                    "dataset_snapshot_id": snapshot.id,
                    "feature_set_version": feature_set.version,
                    "label_set_version": label_set.version,
                    "split_version": SPLIT_VERSION,
                },
            }
            release.status = "inactive" if mechanics_only else "challenger"
            release.inactive_reason = (
                "mechanics-only model; synthetic/directional evidence cannot be promoted"
                if mechanics_only
                else "challenger requires independent review and administrator approval"
            )
    if reasons:
        release.status = "blocked"
        release.inactive_reason = "; ".join(_unique(reasons))
        release.training_report = {
            "status": "blocked",
            "reasons": _unique(reasons),
            "algorithm": algorithm,
            "accuracy_claim_allowed": False,
        }
    db.add(release)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replayed = db.scalar(
            select(ModelRelease).where(ModelRelease.idempotency_key == idempotency_key)
        )
        if replayed is not None:
            return replayed
        raise
    record_audit(
        db,
        action="learning.model_release.created",
        resource_type="model_release",
        resource_id=release.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={
            "model_version": release.model_version,
            "algorithm": algorithm,
            "status": release.status,
            "mechanics_only": mechanics_only,
        },
    )
    return release


def _control_replay(
    db: Session,
    *,
    action: str,
    model_release_id: str,
    idempotency_key: str,
) -> Optional[ModelRelease]:
    existing = db.scalar(
        select(ModelControlAction)
        .where(ModelControlAction.idempotency_key == idempotency_key)
        .with_for_update()
    )
    if existing is None:
        return None
    if existing.action != action or existing.model_release_id != model_release_id:
        raise ValueError("idempotency key is already bound to a different model control action")
    result = db.get(ModelRelease, existing.result_model_release_id)
    if result is None:
        raise ValueError("model control action result is missing")
    return result


def promote_model(
    db: Session,
    *,
    model_release_id: str,
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> ModelRelease:
    replayed = _control_replay(
        db,
        action="promote",
        model_release_id=model_release_id,
        idempotency_key=idempotency_key,
    )
    if replayed is not None:
        return replayed
    release = db.scalar(
        select(ModelRelease).where(ModelRelease.id == model_release_id).with_for_update()
    )
    if release is None:
        raise ValueError("model release not found")
    if release.status not in {"candidate", "challenger"}:
        raise ValueError("only candidate or challenger model releases can be promoted")
    gates = release.evaluation.get("gates") or {}
    required = (
        "split_valid",
        "leakage_free",
        "held_out_improvement",
        "calibration_valid",
        "top_alert_precision_improved",
        "error_analysis_complete",
        "real_data_eligible",
    )
    failures = [name for name in required if not gates.get(name, False)]
    if failures:
        raise ValueError("model promotion gates failed: " + ", ".join(failures))
    if not get_settings().enable_learned_model_serving:
        raise ValueError("learned model serving is disabled by configuration")
    champion = db.scalar(
        select(ModelRelease).where(ModelRelease.status == "champion").with_for_update()
    )
    if champion is not None:
        champion.status = "retired"
        db.flush()
    release.status = "champion"
    release.approved_by = actor_user_id
    release.approved_at = _now()
    release.deployed_at = _now()
    release.predecessor_id = champion.id if champion else release.predecessor_id
    record_audit(
        db,
        action="learning.model_release.promoted",
        resource_type="model_release",
        resource_id=release.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"model_version": release.model_version, "predecessor_id": release.predecessor_id},
    )
    db.add(
        ModelControlAction(
            id=str(uuid4()),
            idempotency_key=idempotency_key,
            action="promote",
            model_release_id=release.id,
            result_model_release_id=release.id,
            actor_user_id=actor_user_id,
            action_metadata={"predecessor_id": release.predecessor_id},
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replayed = _control_replay(
            db,
            action="promote",
            model_release_id=model_release_id,
            idempotency_key=idempotency_key,
        )
        if replayed is not None:
            return replayed
        raise ValueError("model promotion conflicted with another control action") from None
    return release


def rollback_model(
    db: Session,
    *,
    model_release_id: str,
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> ModelRelease:
    replayed = _control_replay(
        db,
        action="rollback",
        model_release_id=model_release_id,
        idempotency_key=idempotency_key,
    )
    if replayed is not None:
        return replayed
    release = db.scalar(
        select(ModelRelease).where(ModelRelease.id == model_release_id).with_for_update()
    )
    if release is None:
        raise ValueError("model release not found")
    if release.status != "champion":
        raise ValueError("only the champion model can be rolled back")
    release.status = "rolled_back"
    release.rolled_back_at = _now()
    db.flush()
    predecessor = (
        db.scalar(
            select(ModelRelease).where(ModelRelease.id == release.predecessor_id).with_for_update()
        )
        if release.predecessor_id
        else None
    )
    if predecessor is not None:
        predecessor.status = "champion"
        predecessor.approved_by = actor_user_id
        predecessor.approved_at = _now()
        predecessor.deployed_at = _now()
    record_audit(
        db,
        action="learning.model_release.rolled_back",
        resource_type="model_release",
        resource_id=release.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"predecessor_id": release.predecessor_id},
    )
    db.add(
        ModelControlAction(
            id=str(uuid4()),
            idempotency_key=idempotency_key,
            action="rollback",
            model_release_id=release.id,
            result_model_release_id=release.id,
            actor_user_id=actor_user_id,
            action_metadata={"predecessor_id": release.predecessor_id},
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replayed = _control_replay(
            db,
            action="rollback",
            model_release_id=model_release_id,
            idempotency_key=idempotency_key,
        )
        if replayed is not None:
            return replayed
        raise ValueError("model rollback conflicted with another control action") from None
    return release


def replay_model(
    db: Session,
    *,
    model_release_id: str,
    dataset_snapshot_id: Optional[str],
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> ModelReplayRun:
    release = db.get(ModelRelease, model_release_id)
    if release is None:
        raise ValueError("model release not found")
    existing_by_key = db.scalar(
        select(ModelReplayRun).where(ModelReplayRun.idempotency_key == idempotency_key)
    )
    if existing_by_key is not None:
        return existing_by_key
    snapshot = db.get(TrainingDatasetSnapshot, dataset_snapshot_id or release.dataset_snapshot_id)
    if snapshot is None:
        raise ValueError("training dataset snapshot not found")
    if snapshot.feature_set_id != release.feature_set_id:
        raise ValueError("replay snapshot must use the model feature contract")
    if snapshot.label_set_id != release.label_set_id:
        raise ValueError("replay snapshot must use the model label contract")
    if not release.artifact:
        metrics = {
            "status": "unavailable",
            "reason": "model release has no reproducible artifact",
            "accuracy_claim_allowed": False,
        }
    else:
        metrics = _evaluate_rows(snapshot.rows, snapshot.split_assignments, release.artifact)
        metrics["status"] = "replayed_frozen_snapshot"
        metrics["accuracy_claim_allowed"] = False
    replay = ModelReplayRun(
        id=str(uuid4()),
        idempotency_key=idempotency_key,
        model_release_id=release.id,
        dataset_snapshot_id=snapshot.id,
        metrics=metrics,
        accuracy_claim_allowed=False,
        created_by=actor_user_id,
    )
    db.add(replay)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replayed = db.scalar(
            select(ModelReplayRun).where(ModelReplayRun.idempotency_key == idempotency_key)
        )
        if replayed is not None:
            return replayed
        raise
    record_audit(
        db,
        action="learning.model_replay.created",
        resource_type="model_replay_run",
        resource_id=replay.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"model_release_id": release.id, "dataset_snapshot_id": snapshot.id},
    )
    return replay


def _psi(baseline: list[float], comparison: list[float]) -> float:
    if not baseline or not comparison:
        return 0.0
    bins = (0.0, 0.33, 0.66, 1.0)

    def counts(values: list[float]) -> list[float]:
        result = [0.0, 0.0, 0.0]
        for value in values:
            index = 0 if value < bins[1] else 1 if value < bins[2] else 2
            result[index] += 1.0
        total = max(1.0, len(values))
        return [(item + 0.5) / (total + 1.5) for item in result]

    left = counts(baseline)
    right = counts(comparison)
    return sum(
        (current - original) * math.log(current / original)
        for original, current in zip(left, right)
    )


def create_drift_report(
    db: Session,
    *,
    baseline_snapshot_id: str,
    comparison_snapshot_id: str,
    model_release_id: Optional[str],
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> ModelDriftReport:
    baseline = db.get(TrainingDatasetSnapshot, baseline_snapshot_id)
    comparison = db.get(TrainingDatasetSnapshot, comparison_snapshot_id)
    if baseline is None or comparison is None:
        raise ValueError("drift snapshots not found")
    existing_by_key = db.scalar(
        select(ModelDriftReport).where(ModelDriftReport.idempotency_key == idempotency_key)
    )
    if existing_by_key is not None:
        return existing_by_key
    if baseline.feature_set_id != comparison.feature_set_id:
        raise ValueError("drift snapshots must use the same feature contract")
    feature_set = db.get(LearningFeatureSet, baseline.feature_set_id)
    if feature_set is None:
        raise ValueError("drift feature contract not found")
    metrics: dict[str, Any] = {}
    maximum = 0.0
    for name in feature_set.feature_names:
        left = [float((row.get("features") or {}).get(name, 0.0)) for row in baseline.rows]
        right = [float((row.get("features") or {}).get(name, 0.0)) for row in comparison.rows]
        value = _psi(left, right)
        maximum = max(maximum, value)
        metrics[name] = {
            "population_stability_index": value,
            "baseline_count": len(left),
            "comparison_count": len(right),
            "status": "drift" if value >= DRIFT_THRESHOLD else "stable",
        }
    status = "drift" if maximum >= DRIFT_THRESHOLD else "stable"
    report = ModelDriftReport(
        id=str(uuid4()),
        idempotency_key=idempotency_key,
        model_release_id=model_release_id,
        baseline_snapshot_id=baseline.id,
        comparison_snapshot_id=comparison.id,
        feature_version=feature_set.version,
        status=status,
        threshold=DRIFT_THRESHOLD,
        metrics={"features": metrics, "maximum_psi": maximum, "accuracy_claim_allowed": False},
        created_by=actor_user_id,
    )
    db.add(report)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replayed = db.scalar(
            select(ModelDriftReport).where(ModelDriftReport.idempotency_key == idempotency_key)
        )
        if replayed is not None:
            return replayed
        raise
    record_audit(
        db,
        action="learning.drift_report.created",
        resource_type="model_drift_report",
        resource_id=report.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"status": status, "maximum_psi": maximum},
    )
    return report


def learning_policy(db: Session) -> dict[str, Any]:
    champion = db.scalar(select(ModelRelease).where(ModelRelease.status == "champion"))
    enabled = get_settings().enable_learned_model_serving
    if champion is None or not enabled:
        return {
            "mode": "rule_based_fallback",
            "model_release_id": None,
            "learned_model_active": False,
            "reason": "no approved active learned model and/or serving feature flag is disabled",
            "probability_display": False,
        }
    return {
        "mode": "learned_candidate_approved",
        "model_release_id": champion.id,
        "learned_model_active": True,
        "reason": "approved champion is eligible under the explicit serving feature flag",
        "probability_display": False,
    }
