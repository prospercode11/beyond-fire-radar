from __future__ import annotations

import math
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.incidents.evidence import (
    EVIDENCE_GROUPING_VERSION,
    ObservationEvidenceGroup,
    current_contradiction_count,
    group_observations,
)
from app.incidents.service import _classification
from app.models import (
    CanonicalIncident,
    DispatchObservation,
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
from app.providers.taxonomy import (
    BRUSH_OUTSIDE_FIRE,
    COMMERCIAL_STRUCTURE_FIRE,
    ELECTRICAL_STRUCTURAL_EXPOSURE,
    EXTINGUISHED_FIRE,
    GENERAL_FIRE,
    GENERAL_STRUCTURE_FIRE,
    ILLEGAL_BURNING,
    MULTIFAMILY_STRUCTURE_FIRE,
    PUBLIC_SERVICE_FIRE,
    RESIDENTIAL_STRUCTURE_FIRE,
    SMOKE_INSIDE_STRUCTURE,
    VEHICLE_FIRE,
    VEHICLE_STRUCTURAL_EXPOSURE,
    WORKING_FIRE,
)

LEGACY_SCORING_VERSION = "opportunity-scoring.v1"
SECOND_SCORING_VERSION = "opportunity-scoring.v2"
PREVIOUS_SCORING_VERSION = "opportunity-scoring.v3"
NO_PROXIMITY_SCORING_VERSION = "opportunity-scoring.v4"
PROXIMITY_SCORING_VERSION = "opportunity-scoring.v5"
PREVIOUS_CURRENT_SCORING_VERSION = "opportunity-scoring.v6"
FIRE_ONLY_SCORING_VERSION = "opportunity-scoring.v7"
ADDRESS_FIX_SCORING_VERSION = "opportunity-scoring.v8"
CONTRADICTION_FIX_SCORING_VERSION = "opportunity-scoring.v9"
SCORING_VERSION = "opportunity-scoring.v10"
LEGACY_FEATURE_VERSION = "opportunity-features.v1"
SECOND_FEATURE_VERSION = "opportunity-features.v2"
PREVIOUS_FEATURE_VERSION = "opportunity-features.v3"
NO_PROXIMITY_FEATURE_VERSION = "opportunity-features.v4"
PROXIMITY_FEATURE_VERSION = "opportunity-features.v5"
PREVIOUS_CURRENT_FEATURE_VERSION = "opportunity-features.v6"
FIRE_ONLY_FEATURE_VERSION = "opportunity-features.v7"
ADDRESS_FIX_FEATURE_VERSION = "opportunity-features.v8"
CONTRADICTION_FIX_FEATURE_VERSION = "opportunity-features.v9"
FEATURE_VERSION = "opportunity-features.v10"
PREVIOUS_FIT_PROFILE_VERSION = "beyondadjusting-fit.v1"
BASE_FIT_PROFILE_VERSION = "beyondadjusting-fit.v2"
FIT_PROFILE_VERSION = "beyondadjusting-fit.v4"
FIT_PROFILE_SOURCE_URL = "https://beyondadjusting.com/#claim"
FIT_PROFILE_RETRIEVED_ON = "2026-08-03"
PROPERTY_SEGMENT_NORMALIZATION_VERSION = "property-segment-normalization.v2"
PROPERTY_CODE_SOURCE_URL = "https://www.sc-pa.com/propertysearch/"
BOCA_RATON_ANCHOR_NAME = "Boca Raton public geographic anchor"
BEYOND_ADJUSTING_ANCHOR_LATITUDE = 26.3683
BEYOND_ADJUSTING_ANCHOR_LONGITUDE = -80.1289
BEYOND_ADJUSTING_PROXIMITY_WEIGHT = 0.20
BEYOND_ADJUSTING_PROXIMITY_RADIUS_KM = 250.0

BEYOND_ADJUSTING_FIT_PROFILE: dict[str, Any] = {
    "version": FIT_PROFILE_VERSION,
    "source_url": FIT_PROFILE_SOURCE_URL,
    "retrieved_on": FIT_PROFILE_RETRIEVED_ON,
    "published_property_segments": ["residential", "commercial", "condominium", "business"],
    "published_claim_types": [
        "hurricane_storm",
        "fire",
        "water",
        "roof",
        "sinkhole",
        "loss_of_income",
        "vandalism",
        "wind",
        "other",
    ],
    "property_use_code_rules": {
        "sarasota.property_appraiser": {
            "0100": "residential",
            "0200": "condominium",
            "0400": "commercial_or_business",
        }
    },
    "scope": "Public service profile only; not coverage, claim-validity, or hiring evidence.",
}

BEYOND_ADJUSTING_FIT_PROFILE_V2: dict[str, Any] = {
    **BEYOND_ADJUSTING_FIT_PROFILE,
    "version": BASE_FIT_PROFILE_VERSION,
}

BEYOND_ADJUSTING_FIT_PROFILE_V3: dict[str, Any] = {
    **BEYOND_ADJUSTING_FIT_PROFILE,
    "version": "beyondadjusting-fit.v3",
}

BEYOND_ADJUSTING_FIT_PROFILE_V1: dict[str, Any] = {
    **BEYOND_ADJUSTING_FIT_PROFILE,
    "version": PREVIOUS_FIT_PROFILE_VERSION,
}
BEYOND_ADJUSTING_FIT_PROFILE_V1.pop("property_use_code_rules", None)

FIT_FIRE_FAMILIES = {
    BRUSH_OUTSIDE_FIRE,
    COMMERCIAL_STRUCTURE_FIRE,
    ELECTRICAL_STRUCTURAL_EXPOSURE,
    EXTINGUISHED_FIRE,
    GENERAL_FIRE,
    GENERAL_STRUCTURE_FIRE,
    ILLEGAL_BURNING,
    MULTIFAMILY_STRUCTURE_FIRE,
    PUBLIC_SERVICE_FIRE,
    RESIDENTIAL_STRUCTURE_FIRE,
    SMOKE_INSIDE_STRUCTURE,
    VEHICLE_FIRE,
    VEHICLE_STRUCTURAL_EXPOSURE,
    WORKING_FIRE,
}

# Opportunity scoring is intentionally narrower than incident intake. These are the
# source classifications that positively identify a fire event; smoke investigations,
# alarms, unknown calls, crashes, medical calls, and other dispatch activity remain
# inspectable evidence but are never opportunities.
FIRE_SCOREABLE_FAMILIES = {
    BRUSH_OUTSIDE_FIRE,
    COMMERCIAL_STRUCTURE_FIRE,
    ELECTRICAL_STRUCTURAL_EXPOSURE,
    EXTINGUISHED_FIRE,
    GENERAL_FIRE,
    GENERAL_STRUCTURE_FIRE,
    ILLEGAL_BURNING,
    MULTIFAMILY_STRUCTURE_FIRE,
    PUBLIC_SERVICE_FIRE,
    RESIDENTIAL_STRUCTURE_FIRE,
    VEHICLE_FIRE,
    VEHICLE_STRUCTURAL_EXPOSURE,
    WORKING_FIRE,
}
FIRE_SCOREABILITY_VERSION = "fire-only-score-gate.v2"
PREVIOUS_FIRE_SCOREABILITY_VERSION = "fire-only-score-gate.v1"
PREVIOUS_FIRE_SCOREABLE_FAMILIES = FIRE_SCOREABLE_FAMILIES - {
    EXTINGUISHED_FIRE,
    ILLEGAL_BURNING,
    PUBLIC_SERVICE_FIRE,
}

PROPERTY_PROVIDER_BY_DISPATCH_PROVIDER = {
    "sarasota.official_dispatch": "sarasota.property_appraiser",
    "miami_dade.fire_calls": "miami_dade.property_appraiser",
    "broward.efirstalert_dispatch": "broward.property_tax_roll",
}

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

# A refresh can be initiated by the header, the stream, and the polling worker at
# nearly the same time in the local SQLite deployment. Serialize score writes in
# this process so two requests never both observe the same current run and then
# race the one-current partial index. PostgreSQL still enforces the row lock below.
_SCORE_WRITE_LOCK = threading.RLock()


def fire_score_eligibility(classification_family: str) -> tuple[bool, str]:
    if classification_family in FIRE_SCOREABLE_FAMILIES:
        return True, ""
    return False, f"non_fire_event:{classification_family}"


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
    property_provider_id: str
    property_use_code: Optional[str]
    property_use_category: Optional[str]
    number_of_units: Optional[int]
    number_of_buildings: Optional[int]
    effective_at: Optional[datetime]
    latitude: Optional[float] = None
    longitude: Optional[float] = None


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
    source_observation_ids: Optional[list[str]] = None,
    use_current_contradiction_projection: bool = False,
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
    observation_ids = source_observation_ids or [item.id for item in observations]
    if use_current_contradiction_projection:
        contradiction_count = current_contradiction_count(observations)
    else:
        from app.models import IncidentEvidence

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


def incident_score_eligibility(
    db: Session,
    incident: CanonicalIncident,
    *,
    as_of: Optional[datetime] = None,
) -> tuple[bool, str, IncidentScoreSnapshot]:
    """Return scoreability from current source evidence, not a stale incident label."""

    effective_as_of = as_of or datetime.now(timezone.utc)
    if effective_as_of.tzinfo is None:
        effective_as_of = effective_as_of.replace(tzinfo=timezone.utc)
    observations = _observations(db, incident.id, as_of=effective_as_of)
    evidence_groups = group_observations(observations)
    snapshot = _incident_snapshot(
        db,
        incident,
        [group.representative for group in evidence_groups],
        as_of=effective_as_of,
        source_observation_ids=[item.id for item in observations],
    )
    eligible, reason = fire_score_eligibility(snapshot.classification_family)
    return eligible, reason, snapshot


def _deactivate_current_non_fire_score(
    db: Session,
    run: OpportunityScoreRun,
    *,
    reason: str,
    actor_user_id: Optional[str],
) -> None:
    """Retire a stale current score while keeping its full historical evidence."""

    if not run.is_current:
        return
    run.is_current = False
    record_audit(
        db,
        action="opportunity.score_deactivated",
        resource_type="opportunity_score_run",
        resource_id=run.id,
        actor_user_id=actor_user_id,
        request_id=f"fire-scoreability-reconcile:{run.id}",
        metadata={
            "reason": reason,
            "policy_version": FIRE_SCOREABILITY_VERSION,
            "source_evidence_retained": True,
        },
    )


def _ensure_fire_score_runs(
    db: Session,
    *,
    actor_user_id: Optional[str],
    provider_id: Optional[str] = None,
    force: bool = False,
) -> int:
    """Materialize one current score run for every currently eligible fire incident.

    This is deliberately invoked after ingestion and at worker startup. A score run may be
    abstained/blocked when property evidence is missing, but the fire incident still remains
    visible in the opportunity queue with its reason instead of silently disappearing until a
    reviewer opens the detail page.
    """

    query = select(CanonicalIncident).where(CanonicalIncident.is_active.is_(True))
    if provider_id:
        query = query.where(CanonicalIncident.provider_id == provider_id)
    incidents = db.scalars(query.order_by(CanonicalIncident.created_at, CanonicalIncident.id)).all()
    changed = 0
    for incident in incidents:
        # Recompute stale projections before deciding whether an incident is fire-scoreable.
        # This repairs persisted crash/alarm labels after a taxonomy release without waiting
        # for a reviewer to open each incident.
        from app.incidents.service import incident_needs_classification_refresh, rescore_incident

        if incident_needs_classification_refresh(db, incident):
            rescore_incident(
                db,
                incident,
                actor_user_id=actor_user_id,
                request_id=f"opportunity-taxonomy-refresh:{incident.id}",
            )
        current = db.scalar(
            select(OpportunityScoreRun).where(
                OpportunityScoreRun.incident_id == incident.id,
                OpportunityScoreRun.is_current.is_(True),
            )
        )
        eligible, reason, _ = incident_score_eligibility(db, incident)
        if not eligible:
            if current is not None:
                _deactivate_current_non_fire_score(
                    db,
                    current,
                    reason=reason,
                    actor_user_id=actor_user_id,
                )
                changed += 1
            continue
        selected_property_provider = PROPERTY_PROVIDER_BY_DISPATCH_PROVIDER.get(
            incident.provider_id
        ) or (current.property_provider_id if current is not None else None)
        current_import = (
            db.scalar(
                select(PropertyImport).where(
                    PropertyImport.provider_id == selected_property_provider,
                    PropertyImport.is_current.is_(True),
                )
            )
            if selected_property_provider
            else None
        )
        current_match = (
            db.get(IncidentPropertyMatchRun, current.property_match_run_id)
            if current is not None and current.property_match_run_id
            else None
        )
        current_observation_ids = [
            item.id for item in _observations(db, incident.id, as_of=datetime.now(timezone.utc))
        ]
        from app.properties.address import ADDRESS_NORMALIZATION_VERSION
        from app.properties.resolution import MATCHER_VERSION

        current_is_complete = (
            current is not None
            and current.scoring_version == SCORING_VERSION
            and current.source_observation_ids == current_observation_ids
            and current.property_provider_id == selected_property_provider
            and (
                current_import is None
                or (
                    current_match is not None
                    and current_match.property_import_id == current_import.id
                    and current_match.matcher_version == MATCHER_VERSION
                    and current_match.address_normalization_version == ADDRESS_NORMALIZATION_VERSION
                )
            )
        )
        if not force and current_is_complete:
            continue
        if selected_property_provider:
            # A current property snapshot is sufficient to create the audited match run;
            # do that before scoring so a refresh can recover incidents that were previously
            # abstained only because no match had been materialized yet. The matcher itself
            # remains conservative and can still abstain on ambiguous or low-precision input.
            from app.properties.resolution import run_property_match

            if current_import is not None:
                try:
                    run_property_match(
                        db,
                        incident,
                        property_provider_id=selected_property_provider,
                        property_import_id=current_import.id,
                        actor_user_id=actor_user_id,
                        force=force,
                    )
                except ValueError:
                    # Scoring must retain the missing/abstained property boundary rather than
                    # converting a failed match into a guessed parcel.
                    pass
        score_incident(
            db,
            incident,
            property_provider_id=selected_property_provider,
            actor_user_id=actor_user_id,
        )
        changed += 1
    return changed


def ensure_fire_score_runs(
    db: Session,
    *,
    actor_user_id: Optional[str],
    provider_id: Optional[str] = None,
    force: bool = False,
) -> int:
    # Keep the whole refresh batch inside the same process lock. Locking only the
    # individual insert still allows two requests to create property matches in
    # separate uncommitted transactions before either request commits its score.
    with _SCORE_WRITE_LOCK:
        return _ensure_fire_score_runs(
            db,
            actor_user_id=actor_user_id,
            provider_id=provider_id,
            force=force,
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
    unit_count = fields.get("number_of_units")
    building_count = fields.get("number_of_buildings")
    if run.status == "site_matched":
        unit_count = max(int(unit_count or 0), run.candidate_count)
        building_count = max(int(building_count or 0), 1)
    return PropertyScoreSnapshot(
        property_provider_id=property_import.provider_id,
        property_use_code=fields.get("property_use_code"),
        property_use_category=fields.get("property_use_category"),
        number_of_units=unit_count,
        number_of_buildings=building_count,
        latitude=fields.get("latitude"),
        longitude=fields.get("longitude"),
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
    observations: list[DispatchObservation],
    retrievals: list[ProviderRetrieval],
    *,
    source_observation_ids: Optional[list[str]] = None,
) -> ScoreFeature:
    ids = source_observation_ids or [item.id for item in observations]
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
    snapshot: IncidentScoreSnapshot,
    observations: list[DispatchObservation],
    *,
    as_of: datetime,
    retained_observation_count: Optional[int] = None,
    source_observation_ids: Optional[list[str]] = None,
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
    if retained_observation_count is not None:
        evidence["retained_observation_count"] = retained_observation_count
    return _feature(
        "incident_validity",
        value,
        status=status,
        explanation=(
            "Incident validity reflects source-faithful classification confidence and applies a "
            "visible contradiction penalty; it does not assert damage or claim validity."
        ),
        evidence=evidence,
        source_observation_ids=source_observation_ids or [item.id for item in observations],
        available_at=_available_at(snapshot.last_event_time, as_of),
    )


def _material_loss_evidence(
    snapshot: IncidentScoreSnapshot,
    observations: list[DispatchObservation],
    *,
    negative_terms: tuple[str, ...],
    as_of: datetime,
    source_observation_ids: Optional[list[str]] = None,
) -> tuple[ScoreFeature, bool, str]:
    text = " ".join(
        [
            snapshot.classification_family or "",
            snapshot.canonical_event_type or "",
            *(item.original_event_type or "" for item in observations),
        ]
    ).lower()
    ids = source_observation_ids or [item.id for item in observations]
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
    elif run.status == "site_matched" and candidate is not None:
        parcel = db.get(Parcel, candidate.parcel_id)
        if parcel is None:
            return (
                _feature(
                    "property_match_quality",
                    0.0,
                    status="abstained",
                    explanation=(
                        "The representative site parcel is no longer available; ranking abstains."
                    ),
                    evidence={"match_run_status": run.status},
                ),
                candidate,
                None,
                True,
                "property_match_uncertain",
            )
        value = max(0.0, min(1.0, candidate.match_score * 0.70))
        status = "site_matched"
        reason = ""
        evidence = {
            "match_run_status": run.status,
            "match_scope": "site",
            "site_candidate_count": run.candidate_count,
            "owner_attribution": "not_available",
            "representative_parcel_id": parcel.parcel_id,
            "match_score": candidate.match_score,
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
    retained_observation_count: Optional[int] = None,
    source_observation_ids: Optional[list[str]] = None,
) -> ScoreFeature:
    value = min(1.0, 0.25 + min(len(observations), 5) * 0.08)
    evidence: dict[str, Any] = {
        "observation_count": len(observations),
        "retained_observation_count": retained_observation_count
        if retained_observation_count is not None
        else len(observations),
    }
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
        source_observation_ids=source_observation_ids or [item.id for item in observations],
        available_at=_available_at(snapshot.last_event_time, as_of),
    )


def _legacy_fit(parcel: Optional[PropertyScoreSnapshot]) -> ScoreFeature:
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


def _property_fit_segment(
    category: Optional[str],
    *,
    property_provider_id: str,
    property_use_code: Optional[str],
    profile: dict[str, Any],
) -> tuple[Optional[str], str]:
    normalized = " ".join((category or "").lower().replace("-", " ").split())
    if any(term in normalized for term in ("condominium", "condo")):
        return "condominium", "property_use_category"
    if any(term in normalized for term in ("residential", "single family", "dwelling")):
        return "residential", "property_use_category"
    if any(term in normalized for term in ("commercial", "business", "retail", "office")):
        return "commercial_or_business", "property_use_category"
    code_rules = profile.get("property_use_code_rules")
    provider_rules = code_rules.get(property_provider_id) if isinstance(code_rules, dict) else None
    mapped_segment = (
        provider_rules.get(str(property_use_code).strip())
        if isinstance(provider_rules, dict) and property_use_code
        else None
    )
    if mapped_segment in {"residential", "commercial_or_business", "condominium"}:
        return mapped_segment, "property_use_code"
    return None, "unmapped"


def _fit_feature(
    value: float,
    status: str,
    explanation: str,
    evidence: dict[str, Any],
    parcel: PropertyScoreSnapshot,
    rules: dict[str, Any],
) -> ScoreFeature:
    proximity_rules = rules.get("beyond_adjusting_proximity")
    if not isinstance(proximity_rules, dict) or not proximity_rules.get("enabled", False):
        return _feature(
            "beyond_adjusting_fit",
            value,
            status=status,
            explanation=explanation,
            evidence=evidence,
            available_at=parcel.effective_at,
        )

    latitude = parcel.latitude
    longitude = parcel.longitude
    proximity_evidence: dict[str, Any] = {
        "proximity_status": "missing",
        "anchor_name": BOCA_RATON_ANCHOR_NAME,
        "anchor_basis": "public city/service-area anchor; not a private residence",
        "anchor_latitude": BEYOND_ADJUSTING_ANCHOR_LATITUDE,
        "anchor_longitude": BEYOND_ADJUSTING_ANCHOR_LONGITUDE,
        "proximity_weight": BEYOND_ADJUSTING_PROXIMITY_WEIGHT,
        "proximity_radius_km": BEYOND_ADJUSTING_PROXIMITY_RADIUS_KM,
    }
    adjusted_value = value
    if latitude is not None and longitude is not None:
        lat1, lon1, lat2, lon2 = map(
            math.radians,
            (
                BEYOND_ADJUSTING_ANCHOR_LATITUDE,
                BEYOND_ADJUSTING_ANCHOR_LONGITUDE,
                float(latitude),
                float(longitude),
            ),
        )
        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1
        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        distance_km = 6371.0088 * 2 * math.asin(math.sqrt(max(0.0, min(1.0, haversine))))
        proximity_factor = max(
            0.0,
            min(1.0, 1.0 - distance_km / BEYOND_ADJUSTING_PROXIMITY_RADIUS_KM),
        )
        adjusted_value = value * (
            (1.0 - BEYOND_ADJUSTING_PROXIMITY_WEIGHT)
            + BEYOND_ADJUSTING_PROXIMITY_WEIGHT * proximity_factor
        )
        proximity_evidence.update(
            {
                "proximity_status": "available",
                "distance_km": round(distance_km, 3),
                "proximity_factor": round(proximity_factor, 6),
            }
        )
    else:
        proximity_evidence["reason"] = "parcel coordinates are unavailable"
    return _feature(
        "beyond_adjusting_fit",
        adjusted_value,
        status=status,
        explanation=(
            f"{explanation} A {BEYOND_ADJUSTING_PROXIMITY_WEIGHT:.0%} public Boca Raton service-area component "
            "decreases with parcel distance; it is not a claim about a person's residence."
        ),
        evidence={**evidence, "proximity": proximity_evidence},
        available_at=parcel.effective_at,
    )


def _fit(
    snapshot: IncidentScoreSnapshot,
    parcel: Optional[PropertyScoreSnapshot],
    *,
    rules: dict[str, Any],
    property_context: Optional[dict[str, Any]] = None,
    legacy: bool = False,
) -> ScoreFeature:
    if legacy:
        return _legacy_fit(parcel)

    profile = rules.get("beyond_adjusting_fit_profile")
    if not isinstance(profile, dict):
        profile = BEYOND_ADJUSTING_FIT_PROFILE
    profile_evidence = {
        "fit_profile_version": profile.get("version", FIT_PROFILE_VERSION),
        "fit_source_url": profile.get("source_url", FIT_PROFILE_SOURCE_URL),
        "fit_source_retrieved_on": profile.get("retrieved_on", FIT_PROFILE_RETRIEVED_ON),
        "fit_inference": False,
        "property_segment_normalization_version": PROPERTY_SEGMENT_NORMALIZATION_VERSION,
    }
    if property_context:
        profile_evidence["property_match_context"] = property_context
    category = parcel.property_use_category if parcel is not None else None
    property_use_code = parcel.property_use_code if parcel is not None else None
    if parcel is None:
        return _feature(
            "beyond_adjusting_fit",
            None,
            status="missing",
            explanation=(
                "No source-backed property segment is available to compare with Beyond Adjusting's "
                "published residential, commercial, condominium, and business service profile."
            ),
            evidence={
                **profile_evidence,
                "property_use_category": category,
                "property_use_code": property_use_code,
            },
            available_at=parcel.effective_at if parcel else None,
        )

    property_segment, property_segment_basis = _property_fit_segment(
        category,
        property_provider_id=parcel.property_provider_id,
        property_use_code=property_use_code,
        profile=profile,
    )
    claim_signal = "fire" if snapshot.classification_family in FIT_FIRE_FAMILIES else None
    evidence = {
        **profile_evidence,
        "property_use_category": category,
        "property_use_code": property_use_code,
        "property_segment": property_segment,
        "property_segment_basis": property_segment_basis,
        "property_code_source_url": (
            PROPERTY_CODE_SOURCE_URL if property_segment_basis == "property_use_code" else None
        ),
        "claim_signal": claim_signal,
    }
    if property_segment and claim_signal == "fire":
        return _fit_feature(
            1.0,
            "available",
            (
                "The source provides a recognized residential, commercial, condominium, or business "
                "property segment and a fire-related classification that matches Beyond Adjusting's "
                "published service profile. This is service-profile fit, not claim or coverage evidence."
            ),
            {**evidence, "fit_basis": ["published property segment", "published claim type: fire"]},
            parcel,
            rules,
        )
    if property_segment:
        return _fit_feature(
            0.50,
            "partial",
            (
                "The property segment matches Beyond Adjusting's published profile, but the source "
                "classification is not a specific published claim-type match. No damage or claim "
                "conclusion is made."
            ),
            {
                **evidence,
                "fit_basis": [
                    "published property segment",
                    "no specific published claim-type match",
                ],
            },
            parcel,
            rules,
        )
    return _fit_feature(
        0.25,
        "partial",
        (
            "The property-use category is present but does not map to a published Beyond Adjusting "
            "property segment. Human review is required; no service, claim, or coverage conclusion is made."
        ),
        {**evidence, "fit_basis": ["unmapped property-use category"]},
        parcel,
        rules,
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
    if version_name not in {
        LEGACY_SCORING_VERSION,
        SECOND_SCORING_VERSION,
        PREVIOUS_SCORING_VERSION,
        NO_PROXIMITY_SCORING_VERSION,
        PROXIMITY_SCORING_VERSION,
        PREVIOUS_CURRENT_SCORING_VERSION,
        FIRE_ONLY_SCORING_VERSION,
        ADDRESS_FIX_SCORING_VERSION,
        CONTRADICTION_FIX_SCORING_VERSION,
        SCORING_VERSION,
    }:
        raise ValueError(f"scoring version {version_name} is not registered")
    legacy = version_name == LEGACY_SCORING_VERSION
    previous_fit = version_name == SECOND_SCORING_VERSION
    previous_scoring = version_name == PREVIOUS_SCORING_VERSION
    no_proximity = version_name == NO_PROXIMITY_SCORING_VERSION
    proximity = version_name == PROXIMITY_SCORING_VERSION
    rules: dict[str, Any] = {
        "negative_source_terms": list(NEGATIVE_TERMS),
        "alert_requires_real_manual_source": True,
        "probability_display": False,
    }
    if not legacy:
        rules["beyond_adjusting_fit_profile"] = (
            BEYOND_ADJUSTING_FIT_PROFILE_V1
            if previous_fit
            else BEYOND_ADJUSTING_FIT_PROFILE_V2
            if previous_scoring or no_proximity
            else BEYOND_ADJUSTING_FIT_PROFILE_V3
            if version_name == PREVIOUS_CURRENT_SCORING_VERSION
            else BEYOND_ADJUSTING_FIT_PROFILE
        )
        if version_name in {
            PROXIMITY_SCORING_VERSION,
            PREVIOUS_CURRENT_SCORING_VERSION,
            FIRE_ONLY_SCORING_VERSION,
            ADDRESS_FIX_SCORING_VERSION,
            CONTRADICTION_FIX_SCORING_VERSION,
            SCORING_VERSION,
        }:
            rules["beyond_adjusting_proximity"] = {
                "enabled": True,
                "weight": BEYOND_ADJUSTING_PROXIMITY_WEIGHT,
                "radius_km": BEYOND_ADJUSTING_PROXIMITY_RADIUS_KM,
                "anchor_name": BOCA_RATON_ANCHOR_NAME,
            }
        if version_name == FIRE_ONLY_SCORING_VERSION:
            rules["fire_scoreability"] = {
                "enabled": True,
                "version": PREVIOUS_FIRE_SCOREABILITY_VERSION,
                "allowed_families": sorted(PREVIOUS_FIRE_SCOREABLE_FAMILIES),
            }
        elif version_name in {
            ADDRESS_FIX_SCORING_VERSION,
            CONTRADICTION_FIX_SCORING_VERSION,
            SCORING_VERSION,
        }:
            rules["fire_scoreability"] = {
                "enabled": True,
                "version": FIRE_SCOREABILITY_VERSION,
                "allowed_families": sorted(FIRE_SCOREABLE_FAMILIES),
            }
        if version_name in {CONTRADICTION_FIX_SCORING_VERSION, SCORING_VERSION}:
            rules["contradiction_projection"] = {
                "version": "incident-contradictions.v2",
                "current_grouped_evidence_only": True,
                "historical_evidence_retained": True,
            }
    version = ScoringVersion(
        id=str(uuid4()),
        version=version_name,
        status="active",
        component_versions={
            name: LEGACY_FEATURE_VERSION
            if legacy
            else SECOND_FEATURE_VERSION
            if previous_fit
            else PREVIOUS_FEATURE_VERSION
            if previous_scoring
            else NO_PROXIMITY_FEATURE_VERSION
            if no_proximity
            else PROXIMITY_FEATURE_VERSION
            if proximity
            else FIRE_ONLY_FEATURE_VERSION
            if version_name == FIRE_ONLY_SCORING_VERSION
            else ADDRESS_FIX_FEATURE_VERSION
            if version_name == ADDRESS_FIX_SCORING_VERSION
            else CONTRADICTION_FIX_FEATURE_VERSION
            if version_name == CONTRADICTION_FIX_SCORING_VERSION
            else FEATURE_VERSION
            if version_name == SCORING_VERSION
            else PREVIOUS_CURRENT_FEATURE_VERSION
            for name in COMPONENT_WEIGHTS
        },
        priors=COMPONENT_WEIGHTS,
        rules=rules,
        description=(
            "Versioned cold-start evidence ranking with published service-profile fit; "
            "not calibrated and not a probability."
            if not legacy and not previous_fit
            else "Versioned cold-start evidence ranking; not calibrated and not a probability."
        ),
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
    release_rules = dict(rules)
    release_rules.setdefault("beyond_adjusting_fit_profile", BEYOND_ADJUSTING_FIT_PROFILE)
    version = ScoringVersion(
        id=str(uuid4()),
        version=version_name,
        status="active",
        component_versions=component_versions,
        priors=numeric_priors,
        rules=release_rules,
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


def _score_incident(
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
    observations = _observations(db, incident.id, as_of=effective_as_of)
    use_grouped_evidence = version.version in {
        NO_PROXIMITY_SCORING_VERSION,
        PROXIMITY_SCORING_VERSION,
        PREVIOUS_CURRENT_SCORING_VERSION,
        FIRE_ONLY_SCORING_VERSION,
        ADDRESS_FIX_SCORING_VERSION,
        CONTRADICTION_FIX_SCORING_VERSION,
        SCORING_VERSION,
    }
    evidence_groups = (
        group_observations(observations)
        if use_grouped_evidence
        else [
            ObservationEvidenceGroup(fingerprint=(item.id,), observations=(item,))
            for item in observations
        ]
    )
    evidence_observations = [group.representative for group in evidence_groups]
    source_observation_ids = [item.id for item in observations]
    retrievals = _retrievals(db, observations)
    property_run = _latest_property_run(
        db, incident.id, property_provider_id, as_of=effective_as_of
    )
    incident_snapshot = _incident_snapshot(
        db,
        incident,
        evidence_observations,
        as_of=effective_as_of,
        source_observation_ids=source_observation_ids,
        use_current_contradiction_projection=version.version
        in {CONTRADICTION_FIX_SCORING_VERSION, SCORING_VERSION},
    )
    scoreable, scoreability_reason = fire_score_eligibility(incident_snapshot.classification_family)
    if not scoreable and observations:
        raise ValueError(
            "opportunity scoring is limited to explicit fire-related incidents "
            f"({scoreability_reason})"
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
    source = _source_quality(
        evidence_observations,
        retrievals,
        source_observation_ids=source_observation_ids,
    )
    validity = _incident_validity(
        incident_snapshot,
        evidence_observations,
        as_of=effective_as_of,
        retained_observation_count=len(observations),
        source_observation_ids=source_observation_ids,
    )
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
        incident_snapshot,
        observations,
        negative_terms=negative_terms,
        as_of=effective_as_of,
        source_observation_ids=source_observation_ids,
    )
    complexity = _loss_complexity(
        incident_snapshot,
        evidence_observations,
        property_snapshot,
        as_of=effective_as_of,
        retained_observation_count=len(observations),
        source_observation_ids=source_observation_ids,
    )
    fit_property_snapshot = property_snapshot
    fit_property_context = {
        "match_run_id": property_run.id if property_run else None,
        "match_run_status": property_run.status if property_run else None,
        "candidate_id": candidate.id if candidate else None,
        "candidate_match_score": candidate.match_score if candidate else None,
        "candidate_is_abstained": candidate.is_abstained if candidate else None,
        "human_decision_confirmed": match.status == "human_confirmed",
    }
    if (
        fit_property_snapshot is None
        and property_run is not None
        and candidate is not None
        and not candidate.is_abstained
    ):
        candidate_parcel = db.get(Parcel, candidate.parcel_id)
        fit_property_snapshot = _property_snapshot(
            db, property_run, candidate_parcel, as_of=effective_as_of
        )
    fit = _fit(
        incident_snapshot,
        fit_property_snapshot,
        rules=rules,
        property_context=fit_property_context,
        legacy=version.version == LEGACY_SCORING_VERSION,
    )
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
    source_ids = source_observation_ids
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
            "evidence_group_count": len(evidence_groups),
            "retained_source_observation_count": len(observations),
            "evidence_grouping_version": (
                EVIDENCE_GROUPING_VERSION if use_grouped_evidence else None
            ),
            "negative_evidence": material.evidence if material.status == "negative" else None,
            "property_candidate_id": candidate.id if candidate else None,
            "property_match_run_id": property_run.id if property_run else None,
            "fit_profile_version": fit.evidence.get("fit_profile_version"),
            "fit_profile_source_url": fit.evidence.get("fit_source_url"),
            "human_override_at_as_of": (
                {"decision": override.decision, "reason": override.reason} if override else None
            ),
            "alert_eligible": alert_eligible,
            "fire_scoreability": {
                "version": FIRE_SCOREABILITY_VERSION,
                "classification_family": incident_snapshot.classification_family,
                "allowed": True,
            },
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


def score_incident(
    db: Session,
    incident: CanonicalIncident,
    *,
    property_provider_id: Optional[str],
    actor_user_id: Optional[str] = None,
    scoring_version: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> OpportunityScoreRun:
    with _SCORE_WRITE_LOCK:
        return _score_incident(
            db,
            incident,
            property_provider_id=property_provider_id,
            actor_user_id=actor_user_id,
            scoring_version=scoring_version,
            as_of=as_of,
        )


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
