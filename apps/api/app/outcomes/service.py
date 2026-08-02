from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.models import (
    AnalyticsMetric,
    CanonicalIncident,
    DispatchObservation,
    EvaluationManifest,
    IncidentObservationLink,
    IncidentOutcomeEvent,
    IncidentPropertyCandidate,
    IncidentPropertyMatchRun,
    InternalAlert,
    OpportunityScoreRun,
    OutcomeLabel,
    PropertyImport,
    PropertyMatchDecision,
    ProviderRetrieval,
    RawDispatchRow,
    RawSnapshot,
)

LABEL_VALUES: dict[str, set[str]] = {
    "review_relevance": {"relevant", "not_relevant", "uncertain"},
    "classification": {"correct", "incorrect", "uncertain"},
    "property_match": {"correct", "incorrect", "unresolved"},
    "alert_usefulness": {"useful", "not_useful", "uncertain"},
    "client_status": {"existing", "not_existing", "unknown"},
}
ERROR_CATEGORIES = {
    "source_quality",
    "incident_classification",
    "incident_linkage",
    "property_match",
    "opportunity_ranking",
    "workflow",
    "other",
}
OUTCOME_EVENT_TYPES = {
    "review_started",
    "review_completed",
    "alert_acknowledged",
    "property_reviewed",
    "found_first",
    "existing_client_confirmed",
    "not_relevant",
    "closed",
}
METRIC_NAMES = {
    "funnel",
    "property_match_accuracy",
    "precision_at_k",
    "alert_usefulness",
    "found_first_rate",
    "reviewer_agreement",
    "error_taxonomy",
    "model_lab_readiness",
}
METRIC_VERSION = "outcomes-analytics.v1"
MANIFEST_VERSION = "evaluation-manifest.v1"
SMALL_SAMPLE_THRESHOLD = 20
MODEL_LAB_MIN_LABELS = 50
MODEL_LAB_MIN_INCIDENTS = 20
TAXONOMY_VERSION = "outcomes-taxonomy.v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _warning(denominator: int, *, source_modes: list[str]) -> Optional[str]:
    warnings: list[str] = []
    if denominator < SMALL_SAMPLE_THRESHOLD:
        warnings.append(
            f"small sample: denominator is {denominator}; {SMALL_SAMPLE_THRESHOLD} is the review threshold"
        )
    if "synthetic_fixture" in source_modes:
        warnings.append(
            "synthetic fixture evidence is present; this is not a real-world accuracy or conversion estimate"
        )
    if not source_modes:
        warnings.append("no dispatch acquisition mode is represented in this manifest")
    return "; ".join(warnings) or None


def _validate_incident(db: Session, incident_id: str) -> CanonicalIncident:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise ValueError("incident not found")
    return incident


def _validate_score(
    db: Session, incident_id: str, score_run_id: Optional[str]
) -> Optional[OpportunityScoreRun]:
    if score_run_id is None:
        return None
    score = db.get(OpportunityScoreRun, score_run_id)
    if score is None or score.incident_id != incident_id:
        raise ValueError("score_run_id does not belong to incident")
    return score


def create_outcome_label(
    db: Session,
    *,
    incident_id: str,
    score_run_id: Optional[str],
    property_match_run_id: Optional[str],
    property_candidate_id: Optional[str],
    property_decision_id: Optional[str],
    alert_id: Optional[str],
    label_type: str,
    label_value: str,
    error_category: Optional[str],
    rationale: str,
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> tuple[OutcomeLabel, bool]:
    if not idempotency_key:
        raise ValueError("an explicit idempotency key is required")
    _validate_incident(db, incident_id)
    score = _validate_score(db, incident_id, score_run_id)
    allowed = LABEL_VALUES.get(label_type)
    if allowed is None:
        raise ValueError(f"unsupported label_type: {label_type}")
    if label_value not in allowed:
        raise ValueError(f"unsupported label_value for {label_type}: {label_value}")
    if error_category is not None and error_category not in ERROR_CATEGORIES:
        raise ValueError(f"unsupported error_category: {error_category}")
    if label_value in {"incorrect", "not_relevant", "not_useful"} and error_category is None:
        raise ValueError("error_category is required for a negative label")
    property_fields = (property_match_run_id, property_candidate_id, property_decision_id)
    if label_type == "property_match":
        if (
            score is None
            or score.property_match_run_id is None
            or any(field is None for field in property_fields)
        ):
            raise ValueError(
                "property_match labels require a score, property match run, candidate, and decision"
            )
        if score.property_match_run_id != property_match_run_id:
            raise ValueError("property_match_run_id does not match the score run")
        match_run = db.get(IncidentPropertyMatchRun, property_match_run_id)
        candidate = db.get(IncidentPropertyCandidate, property_candidate_id)
        decision = db.get(PropertyMatchDecision, property_decision_id)
        if (
            match_run is None
            or match_run.incident_id != incident_id
            or candidate is None
            or candidate.incident_id != incident_id
            or candidate.match_run_id != property_match_run_id
            or decision is None
            or decision.incident_id != incident_id
            or decision.match_run_id != property_match_run_id
            or decision.candidate_id != property_candidate_id
        ):
            raise ValueError(
                "property_match label references do not belong to the incident prediction"
            )
        expected_decisions = {
            "correct": {"confirmed", "corrected"},
            "incorrect": {"rejected"},
            "unresolved": {"cleared", "rejected"},
        }
        if decision.decision not in expected_decisions[label_value]:
            raise ValueError(
                "property_match label does not agree with the recorded property decision"
            )
    elif any(field is not None for field in property_fields):
        raise ValueError("property-match references are only valid for property_match labels")

    alert = db.get(InternalAlert, alert_id) if alert_id else None
    if label_type == "alert_usefulness":
        if alert is None or alert.incident_id != incident_id:
            raise ValueError("alert_usefulness labels require an alert belonging to the incident")
        if score_run_id is None:
            score_run_id = alert.score_run_id
            score = _validate_score(db, incident_id, score_run_id)
        elif alert.score_run_id != score_run_id:
            raise ValueError("alert_id does not match the score run")
    elif alert_id is not None:
        raise ValueError("alert references are only valid for alert_usefulness labels")

    existing = db.scalar(
        select(OutcomeLabel).where(OutcomeLabel.idempotency_key == idempotency_key)
    )
    if existing is not None:
        same = (
            existing.incident_id == incident_id
            and existing.score_run_id == score_run_id
            and existing.property_match_run_id == property_match_run_id
            and existing.property_candidate_id == property_candidate_id
            and existing.property_decision_id == property_decision_id
            and existing.alert_id == alert_id
            and existing.label_type == label_type
            and existing.label_value == label_value
            and existing.error_category == error_category
            and existing.rationale == rationale
        )
        if not same:
            raise ValueError(
                "idempotency key already identifies a different outcome label"
            ) from None
        record_audit(
            db,
            action="outcome.label.replayed",
            resource_type="outcome_label",
            resource_id=existing.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={"idempotency_key": idempotency_key},
        )
        return existing, True

    label = OutcomeLabel(
        id=str(uuid4()),
        incident_id=incident_id,
        score_run_id=score_run_id,
        property_match_run_id=property_match_run_id,
        property_candidate_id=property_candidate_id,
        property_decision_id=property_decision_id,
        alert_id=alert_id,
        label_type=label_type,
        label_value=label_value,
        taxonomy_version=TAXONOMY_VERSION,
        error_category=error_category,
        rationale=rationale,
        provenance={
            "entry_mode": "manual_internal",
            "reviewer_user_id": actor_user_id,
            "source_scope": "internal reviewer label; not a source approval or legal conclusion",
            "metric_eligibility": "label is eligible only after the recorded created_at boundary",
        },
        idempotency_key=idempotency_key,
        reviewer_user_id=actor_user_id,
    )
    try:
        with db.begin_nested():
            db.add(label)
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(OutcomeLabel).where(OutcomeLabel.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        same = (
            existing.incident_id == incident_id
            and existing.score_run_id == score_run_id
            and existing.property_match_run_id == property_match_run_id
            and existing.property_candidate_id == property_candidate_id
            and existing.property_decision_id == property_decision_id
            and existing.alert_id == alert_id
            and existing.label_type == label_type
            and existing.label_value == label_value
            and existing.error_category == error_category
            and existing.rationale == rationale
        )
        if not same:
            raise ValueError(
                "idempotency key already identifies a different outcome label"
            ) from None
        record_audit(
            db,
            action="outcome.label.replayed",
            resource_type="outcome_label",
            resource_id=existing.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={"idempotency_key": idempotency_key, "concurrent": True},
        )
        return existing, True
    record_audit(
        db,
        action="outcome.label.created",
        resource_type="outcome_label",
        resource_id=label.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={
            "incident_id": incident_id,
            "label_type": label_type,
            "label_value": label_value,
            "error_category": error_category,
        },
    )
    return label, False


def create_outcome_event(
    db: Session,
    *,
    incident_id: str,
    score_run_id: Optional[str],
    event_type: str,
    occurred_at: datetime,
    details: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str,
    request_id: str,
) -> tuple[IncidentOutcomeEvent, bool]:
    if not idempotency_key:
        raise ValueError("an explicit idempotency key is required")
    _validate_incident(db, incident_id)
    _validate_score(db, incident_id, score_run_id)
    if event_type not in OUTCOME_EVENT_TYPES:
        raise ValueError(f"unsupported event_type: {event_type}")
    occurred = _utc(occurred_at)
    if occurred is None:
        raise ValueError("occurred_at is required")
    if occurred > _now():
        raise ValueError("outcome events cannot be recorded in the future")
    incident = db.get(CanonicalIncident, incident_id)
    if incident is not None and incident.first_event_time is not None:
        first_event_time = _utc(incident.first_event_time)
        if first_event_time is not None and occurred < first_event_time:
            raise ValueError("outcome event cannot precede the incident event window")
    existing = db.scalar(
        select(IncidentOutcomeEvent).where(IncidentOutcomeEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        same = (
            existing.incident_id == incident_id
            and existing.score_run_id == score_run_id
            and existing.event_type == event_type
            and existing.details == {**details, "provenance": "manual internal outcome event"}
            and _utc(existing.occurred_at) == occurred
        )
        if not same:
            raise ValueError(
                "idempotency key already identifies a different outcome event"
            ) from None
        record_audit(
            db,
            action="outcome.event.replayed",
            resource_type="incident_outcome_event",
            resource_id=existing.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={"idempotency_key": idempotency_key},
        )
        return existing, True

    event = IncidentOutcomeEvent(
        id=str(uuid4()),
        incident_id=incident_id,
        score_run_id=score_run_id,
        event_type=event_type,
        taxonomy_version=TAXONOMY_VERSION,
        occurred_at=occurred,
        source="manual_internal",
        details={**details, "provenance": "manual internal outcome event"},
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
    )
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(IncidentOutcomeEvent).where(
                IncidentOutcomeEvent.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise
        same = (
            existing.incident_id == incident_id
            and existing.score_run_id == score_run_id
            and existing.event_type == event_type
            and existing.details == {**details, "provenance": "manual internal outcome event"}
            and _utc(existing.occurred_at) == occurred
        )
        if not same:
            raise ValueError(
                "idempotency key already identifies a different outcome event"
            ) from None
        record_audit(
            db,
            action="outcome.event.replayed",
            resource_type="incident_outcome_event",
            resource_id=existing.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={"idempotency_key": idempotency_key, "concurrent": True},
        )
        return existing, True
    record_audit(
        db,
        action="outcome.event.created",
        resource_type="incident_outcome_event",
        resource_id=event.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"incident_id": incident_id, "event_type": event_type},
    )
    return event, False


def _source_modes(db: Session, incident_ids: list[str], as_of: datetime) -> list[str]:
    if not incident_ids:
        return []
    retrievals = db.scalars(
        select(ProviderRetrieval)
        .join(RawSnapshot, RawSnapshot.retrieval_id == ProviderRetrieval.id)
        .join(RawDispatchRow, RawDispatchRow.raw_snapshot_id == RawSnapshot.id)
        .join(DispatchObservation, DispatchObservation.raw_dispatch_row_id == RawDispatchRow.id)
        .join(
            IncidentObservationLink,
            IncidentObservationLink.observation_id == DispatchObservation.id,
        )
        .where(
            IncidentObservationLink.incident_id.in_(incident_ids),
            IncidentObservationLink.created_at <= as_of,
            or_(
                IncidentObservationLink.ended_at.is_(None),
                IncidentObservationLink.ended_at > as_of,
            ),
            ProviderRetrieval.retrieved_at <= as_of,
        )
        .distinct()
    ).all()
    return sorted({item.acquisition_mode for item in retrievals})


def _source_provenance(db: Session, incident_ids: list[str], as_of: datetime) -> dict[str, Any]:
    if not incident_ids:
        return {
            "retrievals": [],
            "property_imports": [],
            "acquisition_modes": [],
            "provider_ids": [],
            "authorization_basis": [],
            "snapshot_hashes": [],
        }
    retrievals = db.scalars(
        select(ProviderRetrieval)
        .join(RawSnapshot, RawSnapshot.retrieval_id == ProviderRetrieval.id)
        .join(RawDispatchRow, RawDispatchRow.raw_snapshot_id == RawSnapshot.id)
        .join(DispatchObservation, DispatchObservation.raw_dispatch_row_id == RawDispatchRow.id)
        .join(
            IncidentObservationLink,
            IncidentObservationLink.observation_id == DispatchObservation.id,
        )
        .where(
            IncidentObservationLink.incident_id.in_(incident_ids),
            IncidentObservationLink.created_at <= as_of,
            or_(
                IncidentObservationLink.ended_at.is_(None),
                IncidentObservationLink.ended_at > as_of,
            ),
            ProviderRetrieval.retrieved_at <= as_of,
        )
        .distinct()
    ).all()
    retrieval_ids = sorted(item.id for item in retrievals)
    snapshots = db.scalars(
        select(RawSnapshot).where(RawSnapshot.retrieval_id.in_(retrieval_ids))
    ).all()
    snapshot_by_retrieval = {item.retrieval_id: item for item in snapshots}
    records = [
        {
            "retrieval_id": item.id,
            "provider_id": item.provider_id,
            "acquisition_mode": item.acquisition_mode,
            "authorization_basis": item.authorization_basis,
            "snapshot_hash": (
                snapshot_by_retrieval[item.id].content_hash
                if item.id in snapshot_by_retrieval
                else None
            ),
        }
        for item in sorted(retrievals, key=lambda value: value.id)
    ]
    property_match_runs = db.scalars(
        select(IncidentPropertyMatchRun).where(
            IncidentPropertyMatchRun.incident_id.in_(incident_ids),
            IncidentPropertyMatchRun.created_at <= as_of,
        )
    ).all()
    property_import_ids = sorted(
        {item.property_import_id for item in property_match_runs if item.property_import_id}
    )
    property_imports = (
        db.scalars(
            select(PropertyImport).where(
                PropertyImport.id.in_(property_import_ids),
                PropertyImport.created_at <= as_of,
                PropertyImport.retrieved_at <= as_of,
            )
        ).all()
        if property_import_ids
        else []
    )
    property_records = [
        {
            "property_import_id": item.id,
            "provider_id": item.provider_id,
            "acquisition_mode": item.acquisition_mode,
            "authorization_basis": item.authorization_basis,
            "snapshot_hash": item.content_hash,
            "source_filename": item.source_filename,
        }
        for item in sorted(property_imports, key=lambda value: value.id)
    ]
    all_modes = sorted(
        {
            *(item.acquisition_mode for item in retrievals),
            *(str(item["acquisition_mode"]) for item in property_records),
        }
    )
    all_provider_ids = sorted(
        {
            *(str(item.provider_id) for item in retrievals),
            *(str(item["provider_id"]) for item in property_records),
        }
    )
    return {
        "retrievals": records,
        "property_imports": property_records,
        "acquisition_modes": all_modes,
        "provider_ids": all_provider_ids,
        "authorization_basis": sorted(
            {
                *(item.authorization_basis for item in retrievals if item.authorization_basis),
                *(
                    item["authorization_basis"]
                    for item in property_records
                    if item["authorization_basis"]
                ),
            }
        ),
        "snapshot_hashes": sorted(
            {
                *(
                    snapshot.content_hash
                    for snapshot in snapshot_by_retrieval.values()
                    if snapshot.content_hash
                ),
                *(item["snapshot_hash"] for item in property_records if item["snapshot_hash"]),
            }
        ),
    }


def _latest_labels(labels: list[OutcomeLabel], label_type: str) -> dict[str, OutcomeLabel]:
    latest: dict[str, OutcomeLabel] = {}
    for label in sorted(labels, key=lambda item: (_utc(item.created_at) or _now(), item.id)):
        if label.label_type != label_type:
            continue
        current = latest.get(label.incident_id)
        if current is None or (
            (_utc(label.created_at) or _now(), label.id)
            > (_utc(current.created_at) or _now(), current.id)
        ):
            latest[label.incident_id] = label
    return latest


def _metric_row(
    db: Session,
    manifest_id: str,
    *,
    name: str,
    numerator: Optional[float],
    denominator: int,
    value: Optional[float],
    status: str,
    warning: Optional[str],
    details: dict[str, Any],
) -> AnalyticsMetric:
    metric = AnalyticsMetric(
        id=str(uuid4()),
        manifest_id=manifest_id,
        metric_name=name,
        metric_version=METRIC_VERSION,
        numerator=numerator,
        denominator=denominator,
        value=value,
        status=status,
        warning=warning,
        details=details,
    )
    db.add(metric)
    return metric


def _report_sources_and_cases(
    db: Session, as_of: datetime
) -> tuple[
    list[CanonicalIncident],
    list[OpportunityScoreRun],
    list[OutcomeLabel],
    list[IncidentOutcomeEvent],
]:
    labels = list(
        db.scalars(
            select(OutcomeLabel)
            .where(OutcomeLabel.created_at <= as_of)
            .order_by(OutcomeLabel.created_at)
        ).all()
    )
    events = list(
        db.scalars(
            select(IncidentOutcomeEvent)
            .where(IncidentOutcomeEvent.created_at <= as_of)
            .order_by(IncidentOutcomeEvent.occurred_at, IncidentOutcomeEvent.id)
        ).all()
    )
    score_candidates = list(
        db.scalars(
            select(OpportunityScoreRun)
            .where(
                OpportunityScoreRun.created_at <= as_of,
                OpportunityScoreRun.as_of <= as_of,
            )
            .order_by(OpportunityScoreRun.provisional_score.desc(), OpportunityScoreRun.id)
        ).all()
    )
    scores_by_incident: dict[str, OpportunityScoreRun] = {}
    for score in score_candidates:
        current = scores_by_incident.get(score.incident_id)
        if current is None or (
            (_utc(score.created_at) or datetime.min.replace(tzinfo=timezone.utc), score.id)
            > (_utc(current.created_at) or datetime.min.replace(tzinfo=timezone.utc), current.id)
        ):
            scores_by_incident[score.incident_id] = score
    scores = sorted(
        scores_by_incident.values(),
        key=lambda item: (-float(item.provisional_score or 0), item.incident_id, item.id),
    )
    incident_ids = sorted(
        {
            *(label.incident_id for label in labels),
            *(event.incident_id for event in events),
            *(score.incident_id for score in scores),
        }
    )
    incidents = (
        list(
            db.scalars(
                select(CanonicalIncident).where(CanonicalIncident.id.in_(incident_ids))
            ).all()
        )
        if incident_ids
        else []
    )
    return incidents, scores, labels, events


def generate_analytics_report(
    db: Session,
    *,
    metrics: list[str],
    as_of: Optional[datetime],
    top_k: int,
    actor_user_id: str,
    request_id: str,
) -> tuple[EvaluationManifest, list[AnalyticsMetric]]:
    requested = list(dict.fromkeys(metrics or sorted(METRIC_NAMES)))
    unsupported = sorted(set(requested) - METRIC_NAMES)
    if unsupported:
        raise ValueError(f"unsupported metrics: {', '.join(unsupported)}")
    if top_k < 1 or top_k > 500:
        raise ValueError("top_k must be between 1 and 500")
    boundary = _utc(as_of) or _now()
    incidents, scores, labels, events = _report_sources_and_cases(db, boundary)
    incident_ids = sorted(item.id for item in incidents)
    score_ids = sorted(item.id for item in scores)
    label_ids = sorted(item.id for item in labels)
    event_ids = sorted(item.id for item in events)
    source_provenance = _source_provenance(db, incident_ids, boundary)
    modes = source_provenance["acquisition_modes"]
    source_records = source_provenance["retrievals"]
    property_records = source_provenance["property_imports"]
    manifest = EvaluationManifest(
        id=str(uuid4()),
        manifest_type="outcomes_analytics",
        manifest_version=MANIFEST_VERSION,
        as_of=boundary,
        filters={
            "metrics": requested,
            "top_k": top_k,
            "label_boundary": "created_at <= as_of",
            "score_boundary": "created_at <= as_of and score.as_of <= as_of",
            "outcome_boundary": "created_at <= as_of",
        },
        incident_ids=incident_ids,
        score_run_ids=score_ids,
        label_ids=label_ids,
        outcome_event_ids=event_ids,
        source_acquisition_modes=modes,
        source_retrieval_ids=sorted(item["retrieval_id"] for item in source_records),
        source_provider_ids=source_provenance["provider_ids"],
        source_authorization_bases=source_provenance["authorization_basis"],
        source_snapshot_hashes=source_provenance["snapshot_hashes"],
        source_property_import_ids=sorted(item["property_import_id"] for item in property_records),
        source_provenance=source_provenance,
        claim_status="directional_only" if incident_ids else "no_data",
        created_by=actor_user_id,
    )
    db.add(manifest)
    db.flush()
    generated: list[AnalyticsMetric] = []

    if "property_match_accuracy" in requested:
        raw_decisions = [
            label
            for label in labels
            if label.label_type == "property_match"
            and label.label_value in {"correct", "incorrect"}
        ]
        latest_decisions: dict[tuple[str, Optional[str]], OutcomeLabel] = {}
        for label in raw_decisions:
            key = (label.incident_id, label.property_decision_id)
            current = latest_decisions.get(key)
            if current is None or (
                (_utc(label.created_at) or _now(), label.id)
                > (_utc(current.created_at) or _now(), current.id)
            ):
                latest_decisions[key] = label
        decisions = list(latest_decisions.values())
        denominator = len(decisions)
        numerator = sum(label.label_value == "correct" for label in decisions)
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="property_match_accuracy",
                numerator=float(numerator),
                denominator=denominator,
                value=(numerator / denominator if denominator else None),
                status="available" if denominator else "unavailable",
                warning=_warning(denominator, source_modes=modes),
                details={
                    "denominator_definition": "distinct recorded property decisions with a correct or incorrect label",
                    "excluded_values": ["unresolved"],
                    "accuracy_claim_allowed": False,
                },
            )
        )

    if "precision_at_k" in requested:
        relevance = {
            incident_id: label
            for incident_id, label in _latest_labels(labels, "review_relevance").items()
            if label.label_value in {"relevant", "not_relevant"}
        }
        ranked = [
            score
            for score in scores
            if score.incident_id in relevance and score.provisional_score is not None
        ]
        ranked.sort(
            key=lambda item: (-float(item.provisional_score or 0), item.incident_id, item.id)
        )
        selected = ranked[:top_k]
        numerator = sum(relevance[item.incident_id].label_value == "relevant" for item in selected)
        denominator = len(selected)
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="precision_at_k",
                numerator=float(numerator),
                denominator=denominator,
                value=(numerator / denominator if denominator else None),
                status="available" if denominator else "unavailable",
                warning=_warning(denominator, source_modes=modes),
                details={
                    "k": top_k,
                    "denominator_definition": "top-k as-of score runs with a latest relevant/not_relevant review label",
                    "excluded_values": ["uncertain"],
                    "rank_order": "provisional_score descending, incident_id ascending, score_run_id ascending",
                    "accuracy_claim_allowed": False,
                },
            )
        )

    if "alert_usefulness" in requested:
        raw_decisions = [
            label
            for label in labels
            if label.label_type == "alert_usefulness"
            and label.label_value in {"useful", "not_useful"}
        ]
        alert_latest_decisions: dict[str, OutcomeLabel] = {}
        for label in raw_decisions:
            if label.alert_id is None:
                continue
            current = alert_latest_decisions.get(label.alert_id)
            if current is None or (
                (_utc(label.created_at) or _now(), label.id)
                > (_utc(current.created_at) or _now(), current.id)
            ):
                alert_latest_decisions[label.alert_id] = label
        decisions = list(alert_latest_decisions.values())
        denominator = len(decisions)
        numerator = sum(label.label_value == "useful" for label in decisions)
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="alert_usefulness",
                numerator=float(numerator),
                denominator=denominator,
                value=(numerator / denominator if denominator else None),
                status="available" if denominator else "unavailable",
                warning=_warning(denominator, source_modes=modes),
                details={
                    "denominator_definition": "distinct alerts with a latest useful or not_useful alert-usefulness label",
                    "excluded_values": ["uncertain"],
                    "conversion_separated": True,
                },
            )
        )

    if "found_first_rate" in requested:
        review_events = {
            event.incident_id
            for event in events
            if event.event_type in {"review_completed", "alert_acknowledged"}
        }
        found_first = {event.incident_id for event in events if event.event_type == "found_first"}
        denominator = len(review_events)
        numerator = len(found_first & review_events)
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="found_first_rate",
                numerator=float(numerator),
                denominator=denominator,
                value=(numerator / denominator if denominator else None),
                status="available" if denominator else "unavailable",
                warning=_warning(denominator, source_modes=modes),
                details={
                    "denominator_definition": "incidents with review_completed or alert_acknowledged exposure event",
                    "numerator_definition": "incidents with a manually recorded found_first event",
                    "manual_only": True,
                    "outreach_automation": False,
                },
            )
        )

    if "reviewer_agreement" in requested:
        grouped: dict[tuple[str, str], dict[str, OutcomeLabel]] = defaultdict(dict)
        for label in labels:
            grouped[(label.incident_id, label.label_type)][label.reviewer_user_id] = label
        pair_count = 0
        agreement_count = 0
        for reviewer_labels in grouped.values():
            if len(reviewer_labels) < 2:
                continue
            for left, right in combinations(reviewer_labels.values(), 2):
                pair_count += 1
                agreement_count += left.label_value == right.label_value
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="reviewer_agreement",
                numerator=float(agreement_count),
                denominator=pair_count,
                value=(agreement_count / pair_count if pair_count else None),
                status="available" if pair_count else "unavailable",
                warning=_warning(pair_count, source_modes=modes),
                details={
                    "denominator_definition": "reviewer pairs labeling the same incident and label type",
                    "agreement_definition": "exact label_value equality",
                    "pair_count": pair_count,
                },
            )
        )

    if "error_taxonomy" in requested:
        error_labels = [
            label
            for label in labels
            if label.error_category
            and label.label_value in {"incorrect", "not_relevant", "not_useful"}
        ]
        counts = Counter(label.error_category for label in error_labels)
        denominator = len(error_labels)
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="error_taxonomy",
                numerator=None,
                denominator=denominator,
                value=None,
                status="available" if denominator else "unavailable",
                warning=_warning(denominator, source_modes=modes),
                details={
                    "denominator_definition": "labels carrying an approved error category",
                    "counts": dict(sorted(counts.items())),
                    "categories": sorted(ERROR_CATEGORIES),
                },
            )
        )

    if "funnel" in requested:
        event_counts = Counter(event.event_type for event in events)
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="funnel",
                numerator=None,
                denominator=len(events),
                value=None,
                status="available" if events else "unavailable",
                warning=_warning(len(events), source_modes=modes),
                details={
                    "denominator_definition": "manual internal outcome events in the manifest",
                    "counts": dict(sorted(event_counts.items())),
                    "conversion_separated": True,
                },
            )
        )

    if "model_lab_readiness" in requested:
        relevance_labels = [label for label in labels if label.label_type == "review_relevance"]
        distinct_incidents = {label.incident_id for label in relevance_labels}
        blockers: list[str] = []
        if len(relevance_labels) < MODEL_LAB_MIN_LABELS:
            blockers.append(
                f"need at least {MODEL_LAB_MIN_LABELS} review_relevance labels; found {len(relevance_labels)}"
            )
        if len(distinct_incidents) < MODEL_LAB_MIN_INCIDENTS:
            blockers.append(
                f"need at least {MODEL_LAB_MIN_INCIDENTS} labeled incidents; found {len(distinct_incidents)}"
            )
        blockers.append("real held-out labels and source approval evidence are not established")
        generated.append(
            _metric_row(
                db,
                manifest.id,
                name="model_lab_readiness",
                numerator=0.0,
                denominator=len(relevance_labels),
                value=0.0,
                status="blocked",
                warning="Model Lab is a readiness contract only; no learned model was trained.",
                details={
                    "baseline_status": "not_trained",
                    "blockers": blockers,
                    "label_count": len(relevance_labels),
                    "distinct_incident_count": len(distinct_incidents),
                    "required_split": "time-aware and incident-grouped with leakage checks",
                    "accuracy_claim_allowed": False,
                },
            )
        )

    record_audit(
        db,
        action="analytics.report.created",
        resource_type="evaluation_manifest",
        resource_id=manifest.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={
            "metrics": requested,
            "as_of": boundary.isoformat(),
            "incident_count": len(incident_ids),
            "source_acquisition_modes": modes,
            "claim_status": manifest.claim_status,
        },
    )
    return manifest, sorted(generated, key=lambda item: (item.metric_name, item.id))


def manifest_metrics(
    db: Session, manifest_id: str
) -> tuple[EvaluationManifest, list[AnalyticsMetric]]:
    manifest = db.get(EvaluationManifest, manifest_id)
    if manifest is None:
        raise ValueError("analytics manifest not found")
    metrics = list(
        db.scalars(
            select(AnalyticsMetric)
            .where(AnalyticsMetric.manifest_id == manifest_id)
            .order_by(AnalyticsMetric.metric_name)
        ).all()
    )
    return manifest, metrics
