from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.incidents.service import _classification
from app.models import (
    CanonicalIncident,
    DispatchObservation,
    IncidentEvidence,
    IncidentObservationLink,
    IncidentPropertyCandidate,
    IncidentPropertyMatchRun,
    OpportunityScoreFeature,
    OpportunityScoreOverride,
    OpportunityScoreRun,
    Parcel,
    PropertyImport,
    PropertyMatchDecision,
    PropertySourceRow,
    ProviderRetrieval,
    RawSnapshot,
    ScoringVersion,
)

SCORING_VERSION = "opportunity-scoring.v1"
FEATURE_VERSION = "opportunity-features.v1"

COMPONENT_WEIGHTS: dict[str, float] = {
    "source_quality": 0.15,
    "incident_validity": 0.20,
    "property_match_quality": 0.20,
    "material_loss_evidence": 0.15,
    "loss_complexity": 0.10,
    "beyond_adjusting_fit": 0.10,
    "data_sufficiency": 0.10,
}

NEGATIVE_TERMS = (
    "alarm",
    "vehicle",
    "brush",
    "cancel",
    "false",
    "minor",
)


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _available_at(value: Optional[datetime], as_of: datetime) -> datetime:
    return min(_utc(value) or as_of, as_of)


@dataclass(frozen=True)
class ScoreFeature:
    name: str
    value: Optional[float]
    status: str
    evidence: dict[str, Any]
    source_observation_ids: list[str]
    available_at: Optional[datetime]
    explanation: str


@dataclass(frozen=True)
class IncidentScoreSnapshot:
    classification_family: str
    classification_version: str
    classification_confidence: float
    canonical_event_type: Optional[str]
    last_event_time: Optional[datetime]
    contradiction_count: int


@dataclass(frozen=True)
class PropertyScoreSnapshot:
    property_use_category: Optional[str]
    number_of_units: Optional[int]
    number_of_buildings: Optional[int]
    effective_at: Optional[datetime]


def _feature(
    name: str,
    value: Optional[float],
    *,
    status: str,
    explanation: str,
    evidence: Optional[dict[str, Any]] = None,
    source_observation_ids: Optional[list[str]] = None,
    available_at: Optional[datetime] = None,
) -> ScoreFeature:
    return ScoreFeature(
        name=name,
        value=None if value is None else max(0.0, min(1.0, value)),
        status=status,
        evidence=evidence or {},
        source_observation_ids=source_observation_ids or [],
        available_at=available_at,
        explanation=explanation,
    )


def _observations(db: Session, incident_id: str, *, as_of: datetime) -> list[DispatchObservation]:
    return list(
        db.scalars(
            select(DispatchObservation)
            .join(
                IncidentObservationLink,
                IncidentObservationLink.observation_id == DispatchObservation.id,
            )
            .where(
                IncidentObservationLink.incident_id == incident_id,
                IncidentObservationLink.created_at <= as_of,
                or_(
                    and_(
                        IncidentObservationLink.ended_at.is_(None),
                        IncidentObservationLink.is_current.is_(True),
                    ),
                    IncidentObservationLink.ended_at > as_of,
                ),
                DispatchObservation.retrieved_at <= as_of,
                DispatchObservation.event_time <= as_of,
            )
            .order_by(DispatchObservation.event_time, DispatchObservation.id)
        ).all()
    )


def _incident_snapshot(
    db: Session,
    incident: CanonicalIncident,
    observations: list[DispatchObservation],
    *,
    as_of: datetime,
) -> IncidentScoreSnapshot:
    if not observations:
        return IncidentScoreSnapshot(
            classification_family="Unknown fire situation",
            classification_version="none-at-boundary",
            classification_confidence=0.0,
            canonical_event_type=None,
            last_event_time=None,
            contradiction_count=0,
        )
    family, confidence, _, explanation = _classification(observations)
    event_types = Counter(
        item.original_event_type for item in observations if item.original_event_type
    )
    event_times: list[datetime] = []
    for item in observations:
        normalized_event_time = _utc(item.event_time)
        if normalized_event_time is not None:
            event_times.append(normalized_event_time)
    observation_ids = [item.id for item in observations]
    persisted_contradictions = db.scalar(
        select(IncidentEvidence.id)
        .where(
            IncidentEvidence.incident_id == incident.id,
            IncidentEvidence.observation_id.in_(observation_ids),
            IncidentEvidence.evidence_type == "contradictory",
            IncidentEvidence.created_at <= as_of,
        )
        .limit(1)
    )
    contradiction_count = max(
        int(len({item.normalized_event_family for item in observations}) > 1),
        int(persisted_contradictions is not None),
    )
    return IncidentScoreSnapshot(
        classification_family=family,
        classification_version=str(explanation.get("classification_version", "unknown")),
        classification_confidence=confidence,
        canonical_event_type=event_types.most_common(1)[0][0] if event_types else None,
        last_event_time=max(event_times) if event_times else None,
        contradiction_count=contradiction_count,
    )


def _latest_property_run(
    db: Session,
    incident_id: str,
    property_provider_id: Optional[str],
    *,
    as_of: datetime,
) -> Optional[IncidentPropertyMatchRun]:
    query = select(IncidentPropertyMatchRun).where(
        IncidentPropertyMatchRun.incident_id == incident_id
    )
    if property_provider_id:
        query = query.where(IncidentPropertyMatchRun.property_provider_id == property_provider_id)
    else:
        provider_ids = set(
            db.scalars(
                select(IncidentPropertyMatchRun.property_provider_id)
                .where(
                    IncidentPropertyMatchRun.incident_id == incident_id,
                    IncidentPropertyMatchRun.created_at <= as_of,
                )
                .distinct()
            ).all()
        )
        if len(provider_ids) > 1:
            raise ValueError(
                "property_provider_id is required when multiple property providers are available"
            )
    query = query.where(IncidentPropertyMatchRun.created_at <= as_of)
    return db.scalar(query.order_by(IncidentPropertyMatchRun.created_at.desc()))


def _property_snapshot(
    db: Session,
    run: Optional[IncidentPropertyMatchRun],
    parcel: Optional[Parcel],
    *,
    as_of: datetime,
) -> Optional[PropertyScoreSnapshot]:
    if run is None or parcel is None or run.property_import_id is None:
        return None
    property_import = db.get(PropertyImport, run.property_import_id)
    if property_import is None:
        return None
    retrieved_at = _utc(property_import.retrieved_at)
    effective_at = _utc(property_import.effective_at)
    if retrieved_at is None or retrieved_at > as_of or (effective_at and effective_at > as_of):
        return None
    source_row = db.scalar(
        select(PropertySourceRow).where(
            PropertySourceRow.property_import_id == property_import.id,
            PropertySourceRow.source_parcel_id == parcel.parcel_id,
        )
    )
    if source_row is None:
        return None
    fields = source_row.normalized_fields or {}
    return PropertyScoreSnapshot(
        property_use_category=fields.get("property_use_category"),
        number_of_units=fields.get("number_of_units"),
        number_of_buildings=fields.get("number_of_buildings"),
        effective_at=min(effective_at or retrieved_at, as_of),
    )


def _retrievals(db: Session, observations: list[DispatchObservation]) -> list[ProviderRetrieval]:
    snapshot_ids = {item.raw_snapshot_id for item in observations}
    if not snapshot_ids:
        return []
    return list(
        db.scalars(
            select(ProviderRetrieval)
            .join(RawSnapshot, RawSnapshot.retrieval_id == ProviderRetrieval.id)
            .where(RawSnapshot.id.in_(snapshot_ids))
        ).all()
    )


def _source_quality(
    observations: list[DispatchObservation], retrievals: list[ProviderRetrieval]
) -> ScoreFeature:
    ids = [item.id for item in observations]
    if not observations:
        return _feature(
            "source_quality",
            None,
            status="missing",
            explanation="No current dispatch observations are available.",
        )
    parser_confidence = sum(item.parser_confidence for item in observations) / len(observations)
    modes = {item.acquisition_mode for item in retrievals}
    acquisition_factor = 0.75
    if "synthetic_fixture" in modes:
        acquisition_factor = 0.50
    elif "manual_snapshot" in modes:
        acquisition_factor = 0.80
    value = parser_confidence * acquisition_factor
    retrieved_times: list[datetime] = []
    for item in observations:
        normalized_retrieved_at = _utc(item.retrieved_at)
        if normalized_retrieved_at is not None:
            retrieved_times.append(normalized_retrieved_at)
    latest = max(retrieved_times) if retrieved_times else None
    return _feature(
        "source_quality",
        value,
        status="available",
        explanation=(
            "Source quality combines parser confidence with an explicit acquisition-mode factor; "
            "synthetic fixtures are never eligible for operational alerts."
        ),
        evidence={
            "parser_confidence_mean": parser_confidence,
            "acquisition_modes": sorted(modes),
            "acquisition_factor": acquisition_factor,
        },
        source_observation_ids=ids,
        available_at=latest,
    )


def _incident_validity(
    snapshot: IncidentScoreSnapshot, observations: list[DispatchObservation], *, as_of: datetime
) -> ScoreFeature:
    confidence = snapshot.classification_confidence
    contradiction_penalty = min(0.60, snapshot.contradiction_count * 0.15)
    value = max(0.0, confidence - contradiction_penalty)
    status = "contradicted" if snapshot.contradiction_count else "available"
    evidence: dict[str, Any] = {
        "classification_family": snapshot.classification_family,
        "classification_version": snapshot.classification_version,
        "classification_confidence": confidence,
        "contradiction_count": snapshot.contradiction_count,
        "observation_count": len(observations),
    }
    return _feature(
        "incident_validity",
        value,
        status=status,
        explanation=(
            "Incident validity reflects source-faithful classification confidence and applies a "
            "visible contradiction penalty; it does not assert damage or claim validity."
        ),
        evidence=evidence,
        source_observation_ids=[item.id for item in observations],
        available_at=_available_at(snapshot.last_event_time, as_of),
    )


def _material_loss_evidence(
    snapshot: IncidentScoreSnapshot,
    observations: list[DispatchObservation],
    *,
    negative_terms: tuple[str, ...],
    as_of: datetime,
) -> tuple[ScoreFeature, bool, str]:
    text = " ".join(
        [
            snapshot.classification_family or "",
            snapshot.canonical_event_type or "",
            *(item.original_event_type or "" for item in observations),
        ]
    ).lower()
    ids = [item.id for item in observations]
    if any(term in text for term in negative_terms):
        return (
            _feature(
                "material_loss_evidence",
                0.10,
                status="negative",
                explanation=(
                    "The source wording is a negative relevance signal for this ranking baseline; "
                    "it is not a statement that no damage occurred."
                ),
                evidence={
                    "matched_negative_terms": [term for term in negative_terms if term in text]
                },
                source_observation_ids=ids,
                available_at=_available_at(snapshot.last_event_time, as_of),
            ),
            True,
            "negative_source_relevance",
        )
    if "structure" in text or "building" in text:
        value = 0.90 if "fire" in text else 0.70
        return (
            _feature(
                "material_loss_evidence",
                value,
                status="available",
                explanation=(
                    "Structure-related dispatch wording supplies a provisional evidence signal; "
                    "it is not proof of material loss."
                ),
                evidence={"matched_structure_terms": True},
                source_observation_ids=ids,
                available_at=_available_at(snapshot.last_event_time, as_of),
            ),
            False,
            "",
        )
    return (
        _feature(
            "material_loss_evidence",
            0.25,
            status="weak",
            explanation="No structure-related source wording is available for this provisional rank.",
            evidence={"matched_structure_terms": False},
            source_observation_ids=ids,
            available_at=_available_at(snapshot.last_event_time, as_of),
        ),
        False,
        "",
    )


def _property_match_quality(
    db: Session,
    incident_id: str,
    run: Optional[IncidentPropertyMatchRun],
    *,
    property_provider_id: Optional[str],
    as_of: datetime,
) -> tuple[ScoreFeature, Optional[IncidentPropertyCandidate], Optional[Parcel], bool, str]:
    if run is None:
        return (
            _feature(
                "property_match_quality",
                None,
                status="missing",
                explanation="No property match run is available; ranking abstains.",
            ),
            None,
            None,
            True,
            "property_match_missing",
        )
    candidate = db.scalar(
        select(IncidentPropertyCandidate).where(
            IncidentPropertyCandidate.match_run_id == run.id,
            IncidentPropertyCandidate.rank == 1,
        )
    )
    decision = db.scalar(
        select(PropertyMatchDecision)
        .where(
            PropertyMatchDecision.incident_id == incident_id,
            PropertyMatchDecision.created_at <= as_of,
        )
        .order_by(PropertyMatchDecision.created_at.desc(), PropertyMatchDecision.id.desc())
    )
    decision_candidate = (
        db.get(IncidentPropertyCandidate, decision.candidate_id)
        if decision and decision.candidate_id
        else None
    )
    decision_matches_run = bool(
        decision
        and decision.match_run_id == run.id
        and (decision_candidate is None or decision_candidate.match_run_id == run.id)
        and (property_provider_id is None or run.property_provider_id == property_provider_id)
    )
    parcel = (
        db.get(Parcel, decision.parcel_id)
        if decision and decision.parcel_id and decision_matches_run
        else None
    )
    if decision and decision_matches_run and decision.decision in {"rejected", "cleared"}:
        return (
            _feature(
                "property_match_quality",
                0.0,
                status="negative",
                explanation="The latest human property decision cleared or rejected the match.",
                evidence={"human_decision": decision.decision},
            ),
            candidate,
            parcel,
            True,
            "human_property_decision",
        )
    evidence: dict[str, Any]
    if (
        decision
        and decision_matches_run
        and decision.decision == "confirmed"
        and parcel is not None
    ):
        value = 1.0
        status = "human_confirmed"
        reason = ""
        evidence = {"human_decision": "confirmed", "parcel_id": parcel.parcel_id}
    elif run.status == "matched" and candidate is not None and not candidate.is_abstained:
        value = max(0.0, min(1.0, candidate.match_score * 0.80 + (candidate.score_margin or 0.0)))
        status = "available"
        reason = ""
        evidence = {
            "match_run_status": run.status,
            "classification": candidate.classification,
            "match_score": candidate.match_score,
            "score_margin": candidate.score_margin,
        }
    else:
        return (
            _feature(
                "property_match_quality",
                0.0,
                status="abstained",
                explanation="Property evidence is unresolved or explicitly abstained; ranking abstains.",
                evidence={
                    "match_run_status": run.status,
                    "abstention_reason": run.abstention_reason,
                },
            ),
            candidate,
            parcel,
            True,
            "property_match_uncertain",
        )
    return (
        _feature(
            "property_match_quality",
            value,
            status=status,
            explanation="Property match quality preserves the current run, candidate margin, and human decision.",
            evidence=evidence,
        ),
        candidate,
        parcel,
        False,
        reason,
    )


def _loss_complexity(
    snapshot: IncidentScoreSnapshot,
    observations: list[DispatchObservation],
    parcel: Optional[PropertyScoreSnapshot],
    *,
    as_of: datetime,
) -> ScoreFeature:
    value = min(1.0, 0.25 + min(len(observations), 5) * 0.08)
    evidence: dict[str, Any] = {"observation_count": len(observations)}
    if parcel is not None:
        units = parcel.number_of_units or 0
        buildings = parcel.number_of_buildings or 0
        if units > 1:
            value += 0.20
        if buildings > 1:
            value += 0.15
        evidence.update({"number_of_units": units, "number_of_buildings": buildings})
    return _feature(
        "loss_complexity",
        min(1.0, value),
        status="available" if parcel is not None else "partial",
        explanation=(
            "Complexity is an evidence dimension based on observed incident updates and known "
            "property structure; it does not estimate damage severity."
        ),
        evidence=evidence,
        source_observation_ids=[item.id for item in observations],
        available_at=_available_at(snapshot.last_event_time, as_of),
    )


def _fit(
    parcel: Optional[PropertyScoreSnapshot],
) -> ScoreFeature:
    category = parcel.property_use_category if parcel is not None else None
    return _feature(
        "beyond_adjusting_fit",
        0.50 if category else None,
        status="missing",
        explanation=(
            "No Beyond Adjusting portfolio/client-fit evidence is currently available. A neutral "
            "expert prior is retained for transparent ranking only; this feature cannot enable an alert."
        ),
        evidence={"property_use_category": category, "fit_inference": False},
        available_at=parcel.effective_at if parcel else None,
    )


def _freshness(snapshot: IncidentScoreSnapshot, *, as_of: datetime) -> ScoreFeature:
    now = as_of
    event_time = snapshot.last_event_time or now
    age_days = max(0.0, (now - event_time).total_seconds() / 86400)
    value = max(0.10, 1.0 - min(age_days, 14.0) / 14.0)
    return _feature(
        "evidence_freshness",
        value,
        status="available",
        explanation="Freshness decays with time since the latest incident observation.",
        evidence={"age_days": round(age_days, 3), "decay_window_days": 14},
        available_at=_available_at(snapshot.last_event_time, as_of),
    )


def _data_sufficiency(features: list[ScoreFeature]) -> ScoreFeature:
    required = [item for item in features if item.name != "data_sufficiency"]
    available = sum(item.status in {"available", "human_confirmed", "partial"} for item in required)
    value = available / len(required) if required else 0.0
    return _feature(
        "data_sufficiency",
        value,
        status="available" if value >= 0.70 else "partial",
        explanation="Data sufficiency records which independent evidence dimensions are available.",
        evidence={"available_dimensions": available, "total_dimensions": len(required)},
    )


def _current_override(
    db: Session, incident_id: str, *, as_of: Optional[datetime] = None
) -> Optional[OpportunityScoreOverride]:
    query = select(OpportunityScoreOverride).where(
        OpportunityScoreOverride.incident_id == incident_id
    )
    if as_of is not None:
        query = query.where(OpportunityScoreOverride.created_at <= as_of)
    override = db.scalar(
        query.order_by(
            OpportunityScoreOverride.created_at.desc(), OpportunityScoreOverride.id.desc()
        )
    )
    return None if override is None or override.decision == "clear" else override


def register_scoring_version(
    db: Session,
    actor_user_id: Optional[str] = None,
    version_name: str = SCORING_VERSION,
) -> ScoringVersion:
    existing = db.scalar(select(ScoringVersion).where(ScoringVersion.version == version_name))
    if existing is not None:
        return existing
    if version_name != SCORING_VERSION:
        raise ValueError(f"scoring version {version_name} is not registered")
    version = ScoringVersion(
        id=str(uuid4()),
        version=version_name,
        status="active",
        component_versions={name: FEATURE_VERSION for name in COMPONENT_WEIGHTS},
        priors=COMPONENT_WEIGHTS,
        rules={
            "negative_source_terms": list(NEGATIVE_TERMS),
            "alert_requires_real_manual_source": True,
            "probability_display": False,
        },
        description="Versioned cold-start evidence ranking; not calibrated and not a probability.",
        created_by=actor_user_id,
    )
    db.add(version)
    db.flush()
    return version


def create_scoring_version(
    db: Session,
    *,
    version_name: str,
    component_versions: dict[str, Any],
    priors: dict[str, Any],
    rules: dict[str, Any],
    description: str,
    actor_user_id: str,
    request_id: str,
) -> ScoringVersion:
    if db.scalar(select(ScoringVersion).where(ScoringVersion.version == version_name)) is not None:
        raise ValueError(f"scoring version {version_name} already exists")
    expected_components = set(COMPONENT_WEIGHTS)
    if set(priors) != expected_components or set(component_versions) != expected_components:
        raise ValueError(
            "scoring release must define every registered scoring component exactly once"
        )
    numeric_priors = {name: float(value) for name, value in priors.items()}
    if any(value < 0 for value in numeric_priors.values()) or not math.isclose(
        sum(numeric_priors.values()), 1.0, abs_tol=0.0001
    ):
        raise ValueError("scoring release priors must be non-negative and sum to 1")
    if rules.get("probability_display") is not False:
        raise ValueError("scoring releases must explicitly disable probability display")
    version = ScoringVersion(
        id=str(uuid4()),
        version=version_name,
        status="active",
        component_versions=component_versions,
        priors=numeric_priors,
        rules=rules,
        description=description,
        created_by=actor_user_id,
    )
    db.add(version)
    db.flush()
    record_audit(
        db,
        action="opportunity.scoring_version_created",
        resource_type="scoring_version",
        resource_id=version.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"version": version.version, "component_versions": component_versions},
    )
    return version


def score_incident(
    db: Session,
    incident: CanonicalIncident,
    *,
    property_provider_id: Optional[str],
    actor_user_id: Optional[str] = None,
    scoring_version: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> OpportunityScoreRun:
    effective_as_of = as_of or datetime.now(timezone.utc)
    if effective_as_of.tzinfo is None:
        effective_as_of = effective_as_of.replace(tzinfo=timezone.utc)
    version = register_scoring_version(db, actor_user_id, scoring_version or SCORING_VERSION)
    weights = {name: float(value) for name, value in version.priors.items()}
    rules = version.rules or {}
    negative_terms = tuple(str(item) for item in rules.get("negative_source_terms", NEGATIVE_TERMS))
    component_versions = version.component_versions or {}
    # PostgreSQL serializes concurrent rescoring on the incident row. SQLite relies on its
    # database write lock plus the one-current partial index and remains explicitly non-production.
    db.execute(
        select(CanonicalIncident).where(CanonicalIncident.id == incident.id).with_for_update()
    )
    current = db.scalar(
        select(OpportunityScoreRun).where(
            OpportunityScoreRun.incident_id == incident.id,
            OpportunityScoreRun.is_current.is_(True),
        )
    )
    if current is not None:
        current.is_current = False
        db.flush()
    observations = _observations(db, incident.id, as_of=effective_as_of)
    retrievals = _retrievals(db, observations)
    property_run = _latest_property_run(
        db, incident.id, property_provider_id, as_of=effective_as_of
    )
    incident_snapshot = _incident_snapshot(db, incident, observations, as_of=effective_as_of)
    source = _source_quality(observations, retrievals)
    validity = _incident_validity(incident_snapshot, observations, as_of=effective_as_of)
    match, candidate, parcel, _match_blocked, match_reason = _property_match_quality(
        db,
        incident.id,
        property_run,
        property_provider_id=property_provider_id,
        as_of=effective_as_of,
    )
    property_snapshot = _property_snapshot(db, property_run, parcel, as_of=effective_as_of)
    if (
        property_run is not None
        and candidate is not None
        and parcel is not None
        and property_snapshot is None
    ):
        match = _feature(
            "property_match_quality",
            None,
            status="abstained",
            explanation="The selected property evidence is not available at the score as-of boundary.",
            evidence={"property_match_run_id": property_run.id},
        )
        match_reason = "property_match_temporal_unavailable"
    material, negative, negative_reason = _material_loss_evidence(
        incident_snapshot, observations, negative_terms=negative_terms, as_of=effective_as_of
    )
    complexity = _loss_complexity(
        incident_snapshot, observations, property_snapshot, as_of=effective_as_of
    )
    fit = _fit(property_snapshot)
    freshness = _freshness(incident_snapshot, as_of=effective_as_of)
    features = [source, validity, match, material, complexity, fit, freshness]
    sufficiency = _data_sufficiency(features)
    features.append(sufficiency)
    hard_reason = negative_reason or match_reason
    if not hard_reason and incident_snapshot.contradiction_count:
        hard_reason = "contradictory_incident_evidence"
    if hard_reason:
        status = "suppressed" if negative else "abstained"
        score: Optional[float] = None
        tier = "suppressed" if negative else "research"
        hard_gate = "blocked"
    else:
        log_score = sum(
            weights.get(item.name, 0.0) * math.log(max(item.value or 0.01, 0.01))
            for item in features
            if item.name in weights
        )
        score = round(max(0.0, min(100.0, math.exp(log_score) * 100)), 2)
        if score >= 80 and sufficiency.value is not None and sufficiency.value >= 0.70:
            tier = "elite"
        elif score >= 60:
            tier = "priority_review"
        else:
            tier = "research"
        status = "scored"
        hard_gate = "review_only" if fit.status == "missing" else "eligible_for_review"
    modes = {item.acquisition_mode for item in retrievals}
    manually_authorized = bool(
        retrievals
        and all(
            item.acquisition_mode == "manual_snapshot" and bool(item.authorization_basis)
            for item in retrievals
        )
    )
    alert_eligible = bool(
        score is not None
        and score >= 80
        and tier == "elite"
        and hard_gate == "eligible_for_review"
        and not negative
        and not incident_snapshot.contradiction_count
        and manually_authorized
        and modes == {"manual_snapshot"}
        and match.status in {"available", "human_confirmed"}
        and fit.status == "available"
    )
    override = _current_override(db, incident.id, as_of=effective_as_of)
    source_ids = [item.id for item in observations]
    feature_available_times = [
        item.available_at for item in features if item.available_at is not None
    ]
    run = OpportunityScoreRun(
        id=str(uuid4()),
        incident_id=incident.id,
        property_match_run_id=property_run.id if property_run else None,
        property_provider_id=property_provider_id,
        scoring_version=version.version,
        previous_score_run_id=current.id if current else None,
        as_of=effective_as_of,
        status=status,
        provisional_score=score,
        evidence_tier=tier,
        alert_eligibility=alert_eligible,
        abstention_reason=hard_reason
        or ("fit_evidence_missing" if fit.status == "missing" else None),
        hard_gate_status=hard_gate,
        explanation={
            "semantics": "provisional evidence ranking, not an empirical probability",
            "formula": "weighted geometric mean of versioned components with hard gates",
            "component_weights": weights,
            "negative_evidence": material.evidence if material.status == "negative" else None,
            "property_candidate_id": candidate.id if candidate else None,
            "property_match_run_id": property_run.id if property_run else None,
            "human_override_at_as_of": (
                {"decision": override.decision, "reason": override.reason} if override else None
            ),
            "alert_eligible": alert_eligible,
        },
        source_observation_ids=source_ids,
        available_at=max(feature_available_times) if feature_available_times else None,
        created_by=actor_user_id,
        completed_at=datetime.now(timezone.utc),
        is_current=True,
    )
    db.add(run)
    db.flush()
    for item in features:
        weight = weights.get(item.name, 0.0)
        score_contribution = (
            round(weight * math.log(max(item.value or 0.01, 0.01)), 6)
            if item.value is not None and item.name in weights
            else None
        )
        db.add(
            OpportunityScoreFeature(
                id=str(uuid4()),
                score_run_id=run.id,
                feature_name=item.name,
                value=item.value,
                status=item.status,
                contribution=score_contribution,
                evidence=item.evidence,
                source_observation_ids=item.source_observation_ids,
                available_at=item.available_at,
                feature_version=str(component_versions.get(item.name, FEATURE_VERSION)),
                explanation=item.explanation,
            )
        )
    record_audit(
        db,
        action="opportunity.score_created",
        resource_type="opportunity_score_run",
        resource_id=run.id,
        actor_user_id=actor_user_id,
        request_id="opportunity-score:" + run.id,
        metadata={
            "incident_id": incident.id,
            "scoring_version": version.version,
            "status": status,
            "evidence_tier": tier,
            "provisional_score": score,
            "alert_eligibility": alert_eligible,
            "abstention_reason": run.abstention_reason,
        },
    )
    return run


def rollback_score(
    db: Session,
    run: OpportunityScoreRun,
    *,
    actor_user_id: str,
    request_id: str,
) -> OpportunityScoreRun:
    db.execute(
        select(CanonicalIncident).where(CanonicalIncident.id == run.incident_id).with_for_update()
    )
    current = db.scalar(
        select(OpportunityScoreRun).where(
            OpportunityScoreRun.incident_id == run.incident_id,
            OpportunityScoreRun.is_current.is_(True),
        )
    )
    if current is None or current.id != run.id or not run.is_current:
        raise ValueError("only the current opportunity score can be rolled back")
    run.is_current = False
    run.status = "rolled_back"
    db.flush()
    prior = (
        db.get(OpportunityScoreRun, run.previous_score_run_id)
        if run.previous_score_run_id
        else None
    )
    if prior is not None:
        prior.is_current = True
    record_audit(
        db,
        action="opportunity.score_rolled_back",
        resource_type="opportunity_score_run",
        resource_id=run.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={
            "incident_id": run.incident_id,
            "restored_score_run_id": prior.id if prior else None,
        },
    )
    return prior or run


def record_override(
    db: Session,
    incident: CanonicalIncident,
    *,
    score_run: Optional[OpportunityScoreRun],
    decision: str,
    reason: str,
    actor_user_id: str,
    request_id: str,
) -> OpportunityScoreOverride:
    if decision not in {"suppress", "promote_review", "hold", "clear"}:
        raise ValueError("decision must be suppress, promote_review, hold, or clear")
    override = OpportunityScoreOverride(
        id=str(uuid4()),
        incident_id=incident.id,
        score_run_id=score_run.id if score_run else None,
        decision=decision,
        reason=reason,
        actor_user_id=actor_user_id,
    )
    db.add(override)
    record_audit(
        db,
        action="opportunity.override_recorded",
        resource_type="canonical_incident",
        resource_id=incident.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={
            "decision": decision,
            "reason": reason,
            "score_run_id": score_run.id if score_run else None,
        },
    )
    return override
