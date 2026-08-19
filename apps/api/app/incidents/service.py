from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import Settings
from app.incidents.evidence import (
    EVIDENCE_GROUPING_VERSION,
    current_contradiction_count,
    group_observations,
)
from app.incidents.linkage import (
    CLASSIFICATION_VERSION,
    LINKAGE_VERSION,
    STATE_AWAITING,
    STATE_CLOSED,
    STATE_CONFIRMED,
    STATE_DOWNGRADED,
    STATE_FALSE_ALARM,
    STATE_HIGH_STRUCTURE,
    STATE_LIKELY_STRUCTURE,
    STATE_NEW,
    STATE_PROPERTY_UNRESOLVED,
    STATE_SUPPRESSED,
    VALID_STATES,
    LinkageDecision,
    choose_linkage,
    normalize_location,
    utc_datetime,
)
from app.models import (
    CanonicalIncident,
    DispatchObservation,
    IncidentAlias,
    IncidentEvidence,
    IncidentMatchDecision,
    IncidentMerge,
    IncidentObservationLink,
    IncidentProcessingRun,
    IncidentRespondingAgency,
    IncidentRespondingStation,
    IncidentSplit,
    IncidentTimelineEvent,
    Provider,
    ProviderRetrieval,
    RawSnapshot,
)
from app.providers.approval import live_polling_is_authorized
from app.providers.taxonomy import (
    COMMERCIAL_STRUCTURE_FIRE,
    ELECTRICAL_STRUCTURAL_EXPOSURE,
    GENERAL_STRUCTURE_FIRE,
    MULTIFAMILY_STRUCTURE_FIRE,
    RESIDENTIAL_STRUCTURE_FIRE,
    ROUTINE_FIRE_ALARM,
    SMOKE_INSIDE_STRUCTURE,
    TAXONOMY_VERSION,
    TRAFFIC_CRASH_STRUCTURE,
    VEHICLE_STRUCTURAL_EXPOSURE,
    WORKING_FIRE,
    classify_event,
)

PROCESSABLE_ACQUISITION_MODES = {"manual_snapshot", "synthetic_fixture", "live_poll"}
STRUCTURE_FAMILIES = {
    COMMERCIAL_STRUCTURE_FIRE,
    GENERAL_STRUCTURE_FIRE,
    MULTIFAMILY_STRUCTURE_FIRE,
    RESIDENTIAL_STRUCTURE_FIRE,
    WORKING_FIRE,
    SMOKE_INSIDE_STRUCTURE,
    ELECTRICAL_STRUCTURAL_EXPOSURE,
    VEHICLE_STRUCTURAL_EXPOSURE,
    TRAFFIC_CRASH_STRUCTURE,
}
TERMINAL_STATES = {STATE_CLOSED, STATE_SUPPRESSED, STATE_FALSE_ALARM, STATE_DOWNGRADED}
STATE_DISPOSITION_PENDING = "Disposition pending"

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATE_NEW: {
        STATE_AWAITING,
        STATE_PROPERTY_UNRESOLVED,
        STATE_LIKELY_STRUCTURE,
        STATE_HIGH_STRUCTURE,
        STATE_CLOSED,
        STATE_SUPPRESSED,
    },
    STATE_AWAITING: {
        STATE_PROPERTY_UNRESOLVED,
        STATE_LIKELY_STRUCTURE,
        STATE_HIGH_STRUCTURE,
        STATE_CONFIRMED,
        STATE_AWAITING,
        STATE_DOWNGRADED,
        STATE_FALSE_ALARM,
        STATE_CLOSED,
        STATE_SUPPRESSED,
    },
    STATE_PROPERTY_UNRESOLVED: {
        STATE_AWAITING,
        STATE_LIKELY_STRUCTURE,
        STATE_HIGH_STRUCTURE,
        STATE_CONFIRMED,
        STATE_DOWNGRADED,
        STATE_FALSE_ALARM,
        STATE_CLOSED,
        STATE_SUPPRESSED,
    },
    STATE_LIKELY_STRUCTURE: {
        STATE_AWAITING,
        STATE_HIGH_STRUCTURE,
        STATE_CONFIRMED,
        STATE_DOWNGRADED,
        STATE_FALSE_ALARM,
        STATE_CLOSED,
        STATE_SUPPRESSED,
    },
    STATE_HIGH_STRUCTURE: {
        STATE_AWAITING,
        STATE_LIKELY_STRUCTURE,
        STATE_CONFIRMED,
        STATE_DOWNGRADED,
        STATE_FALSE_ALARM,
        STATE_CLOSED,
        STATE_SUPPRESSED,
    },
    STATE_CONFIRMED: {STATE_AWAITING, STATE_DOWNGRADED, STATE_CLOSED, STATE_SUPPRESSED},
    STATE_DOWNGRADED: {STATE_CLOSED, STATE_SUPPRESSED},
    STATE_FALSE_ALARM: {STATE_CLOSED, STATE_SUPPRESSED},
    STATE_CLOSED: {STATE_SUPPRESSED},
    STATE_SUPPRESSED: set(),
}
# The public state name is part of the specification. Keep this alias local so the transition
# map stays readable without introducing a second status vocabulary.
ALLOWED_TRANSITIONS[STATE_AWAITING].add(STATE_DISPOSITION_PENDING)
ALLOWED_TRANSITIONS[STATE_PROPERTY_UNRESOLVED].add(STATE_DISPOSITION_PENDING)
ALLOWED_TRANSITIONS[STATE_LIKELY_STRUCTURE].add(STATE_DISPOSITION_PENDING)
ALLOWED_TRANSITIONS[STATE_HIGH_STRUCTURE].add(STATE_DISPOSITION_PENDING)
ALLOWED_TRANSITIONS[STATE_DISPOSITION_PENDING] = {
    STATE_CONFIRMED,
    STATE_DOWNGRADED,
    STATE_FALSE_ALARM,
    STATE_CLOSED,
    STATE_SUPPRESSED,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event_time(observation: DispatchObservation) -> datetime:
    return utc_datetime(observation.event_time) or utc_datetime(observation.retrieved_at) or _now()


def _current_links(db: Session, incident_id: str) -> list[IncidentObservationLink]:
    return list(
        db.scalars(
            select(IncidentObservationLink)
            .where(
                IncidentObservationLink.incident_id == incident_id,
                IncidentObservationLink.is_current.is_(True),
            )
            .order_by(IncidentObservationLink.created_at, IncidentObservationLink.id)
        ).all()
    )


def _current_link_for_observation(
    db: Session, observation_id: str
) -> Optional[IncidentObservationLink]:
    return db.scalar(
        select(IncidentObservationLink).where(
            IncidentObservationLink.observation_id == observation_id,
            IncidentObservationLink.is_current.is_(True),
        )
    )


def _observations_for_links(
    db: Session, links: Iterable[IncidentObservationLink]
) -> list[DispatchObservation]:
    ids = [link.observation_id for link in links]
    if not ids:
        return []
    return list(
        db.scalars(select(DispatchObservation).where(DispatchObservation.id.in_(ids))).all()
    )


def _classification(
    observations: list[DispatchObservation],
) -> tuple[str, float, str, dict[str, Any]]:
    # Re-derive this field from preserved source wording so taxonomy fixes also correct
    # already-retained observations on the next incident recomputation.
    families = [classify_event(item.original_event_type) for item in observations]
    counts = Counter(families)
    family = max(counts, key=lambda value: (value in STRUCTURE_FAMILIES, counts[value], value))
    parser_confidence = sum(item.parser_confidence for item in observations) / max(
        1, len(observations)
    )
    conflicting_families = sorted(set(families))
    mixed_structure_and_alarm = (
        bool(set(families) & STRUCTURE_FAMILIES) and ROUTINE_FIRE_ALARM in families
    )
    agreement = counts[family] / max(1, len(families))
    confidence = round(min(0.99, max(0.25, parser_confidence * (0.55 + 0.45 * agreement))), 4)
    if mixed_structure_and_alarm or len(conflicting_families) > 1:
        confidence = min(confidence, 0.60)
    band = (
        "high_confidence"
        if confidence >= 0.85
        else "human_review"
        if confidence >= 0.62
        else "insufficient_evidence"
    )
    return (
        family,
        confidence,
        band,
        {
            "classification_version": CLASSIFICATION_VERSION,
            "family_counts": dict(counts),
            "source_event_families": conflicting_families,
            "contradictory_family_mix": mixed_structure_and_alarm,
            "method": "source-faithful taxonomy aggregation; no working-fire inference",
        },
    )


def incident_needs_classification_refresh(db: Session, incident: CanonicalIncident) -> bool:
    """Detect incidents persisted before the current source-taxonomy rules."""

    observations = _observations_for_links(db, _current_links(db, incident.id))
    return incident.classification_version != CLASSIFICATION_VERSION or any(
        item.taxonomy_version != TAXONOMY_VERSION
        or item.normalized_event_family != classify_event(item.original_event_type)
        for item in observations
    )


def _state_for(
    incident: CanonicalIncident, family: str, confidence: float, contradictions: int
) -> str:
    if contradictions and incident.state in {
        STATE_CLOSED,
        STATE_FALSE_ALARM,
        STATE_DOWNGRADED,
    }:
        return STATE_AWAITING
    if incident.state in TERMINAL_STATES:
        return incident.state
    if contradictions:
        return STATE_AWAITING
    if family in STRUCTURE_FAMILIES and confidence >= 0.85:
        return STATE_HIGH_STRUCTURE
    if family in STRUCTURE_FAMILIES and confidence >= 0.62:
        return STATE_LIKELY_STRUCTURE
    if incident.state == STATE_NEW:
        return STATE_NEW
    return STATE_AWAITING


def _add_timeline(
    db: Session,
    incident_id: str,
    event_type: str,
    *,
    source_observation_id: Optional[str] = None,
    prior_state: Optional[str] = None,
    new_state: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    actor_user_id: Optional[str] = None,
) -> IncidentTimelineEvent:
    event = IncidentTimelineEvent(
        id=str(uuid4()),
        incident_id=incident_id,
        event_type=event_type,
        occurred_at=_now(),
        prior_state=prior_state,
        new_state=new_state,
        source_observation_id=source_observation_id,
        details=details or {},
        actor_user_id=actor_user_id,
    )
    db.add(event)
    return event


def _add_evidence(
    db: Session,
    incident_id: str,
    observation_id: str,
    evidence_type: str,
    code: str,
    summary: str,
    details: dict[str, Any],
) -> None:
    exists = db.scalar(
        select(IncidentEvidence.id).where(
            IncidentEvidence.incident_id == incident_id,
            IncidentEvidence.observation_id == observation_id,
            IncidentEvidence.evidence_type == evidence_type,
            IncidentEvidence.code == code,
        )
    )
    if exists is None:
        db.add(
            IncidentEvidence(
                id=str(uuid4()),
                incident_id=incident_id,
                observation_id=observation_id,
                evidence_type=evidence_type,
                code=code,
                summary=summary,
                details=details,
            )
        )


def _create_incident_record(db: Session, observation: DispatchObservation) -> CanonicalIncident:
    family, confidence, band, explanation = _classification([observation])
    incident = CanonicalIncident(
        id=str(uuid4()),
        provider_id=observation.provider_id,
        state=STATE_NEW,
        classification_family=family,
        classification_version=CLASSIFICATION_VERSION,
        classification_confidence=confidence,
        confidence_band=band,
        review_band="human_review" if band != "high_confidence" else "auto_linked",
        canonical_event_type=observation.original_event_type,
        first_event_time=observation.event_time,
        last_event_time=observation.event_time,
        first_seen_at=observation.retrieved_at,
        last_seen_at=observation.retrieved_at,
        canonical_location=observation.original_location,
        canonical_grid=observation.grid,
        canonical_agency=observation.agency,
        canonical_station=observation.station,
        contradiction_count=0,
        classification_explanation=explanation,
        current_explanation={"created_from_observation_id": observation.id},
        is_active=True,
    )
    db.add(incident)
    db.flush()
    _add_timeline(
        db,
        incident.id,
        "created",
        source_observation_id=observation.id,
        details={
            "classification_version": CLASSIFICATION_VERSION,
            "acquisition_mode": "manual_or_fixture",
        },
    )
    return incident


def _add_aliases(
    db: Session, incident: CanonicalIncident, observation: DispatchObservation
) -> None:
    aliases = (
        ("source_record_id", observation.source_record_id),
        ("source_event_id", observation.source_event_id),
        ("source_case_number", observation.source_case_number),
    )
    for alias_type, value in aliases:
        if not value:
            continue
        existing = db.scalar(
            select(IncidentAlias).where(
                IncidentAlias.provider_id == incident.provider_id,
                IncidentAlias.alias_type == alias_type,
                IncidentAlias.alias_value == value,
            )
        )
        if existing is not None and existing.incident_id == incident.id:
            continue
        if existing is not None and alias_type == "source_record_id":
            # A stable source-record identity is globally unique. The source observation link
            # still preserves this row when a concurrent writer won the identity race.
            continue
        collision = existing is not None
        db.add(
            IncidentAlias(
                id=str(uuid4()),
                provider_id=incident.provider_id,
                incident_id=incident.id,
                observation_id=observation.id,
                alias_type=alias_type,
                alias_value=value,
                collision=collision,
            )
        )


def _link_observation(
    db: Session,
    incident: CanonicalIncident,
    observation: DispatchObservation,
    *,
    link_type: str,
    decision_id: Optional[str],
    actor_user_id: Optional[str],
) -> IncidentObservationLink:
    if incident.provider_id != observation.provider_id:
        raise ValueError("incident and source observation providers must match")
    existing = _current_link_for_observation(db, observation.id)
    if existing is not None:
        if existing.incident_id == incident.id:
            return existing
        raise ValueError("source observation is already assigned to another active incident")
    link = IncidentObservationLink(
        id=str(uuid4()),
        incident_id=incident.id,
        observation_id=observation.id,
        raw_dispatch_row_id=observation.raw_dispatch_row_id,
        link_type=link_type,
        is_current=True,
        assignment_key=observation.id,
        decision_id=decision_id,
        created_by=actor_user_id,
        ended_at=None,
    )
    db.add(link)
    _add_aliases(db, incident, observation)
    _add_evidence(
        db,
        incident.id,
        observation.id,
        "supporting",
        "source_row_linked",
        "Immutable parsed observation linked to the canonical incident.",
        {
            "raw_dispatch_row_id": observation.raw_dispatch_row_id,
            "raw_snapshot_id": observation.raw_snapshot_id,
        },
    )
    _add_timeline(
        db,
        incident.id,
        "observation_linked",
        source_observation_id=observation.id,
        details={"link_type": link_type, "decision_id": decision_id},
        actor_user_id=actor_user_id,
    )
    return link


def _record_decision(
    db: Session,
    observation: DispatchObservation,
    decision: str,
    stage: str,
    score: float,
    confidence_band: str,
    features: dict[str, Any],
    explanation: dict[str, Any],
    *,
    candidate_incident_id: Optional[str] = None,
    reference_observation_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> IncidentMatchDecision:
    row = IncidentMatchDecision(
        id=str(uuid4()),
        observation_id=observation.id,
        candidate_incident_id=candidate_incident_id,
        reference_observation_id=reference_observation_id,
        decision=decision,
        stage=stage,
        score=score,
        confidence_band=confidence_band,
        model_version=LINKAGE_VERSION,
        features=features,
        explanation=explanation,
        created_by=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def recompute_incident(
    db: Session, incident: CanonicalIncident, *, actor_user_id: Optional[str] = None
) -> int:
    observations = _observations_for_links(db, _current_links(db, incident.id))
    if not observations:
        incident.contradiction_count = 0
        return 0
    for item in observations:
        item.normalized_event_family = classify_event(item.original_event_type)
        item.taxonomy_version = TAXONOMY_VERSION
    evidence_groups = group_observations(observations)
    evidence_observations = [group.representative for group in evidence_groups]
    prior_family = incident.classification_family
    prior_confidence = incident.classification_confidence
    prior_band = incident.confidence_band
    family, confidence, band, explanation = _classification(evidence_observations)
    event_types = Counter(item.original_event_type for item in evidence_observations)
    incident.classification_family = family
    incident.classification_version = CLASSIFICATION_VERSION
    incident.classification_confidence = confidence
    incident.confidence_band = band
    incident.review_band = "human_review" if band != "high_confidence" else "auto_linked"
    incident.canonical_event_type = event_types.most_common(1)[0][0]
    event_times = [item.event_time for item in observations if item.event_time]
    incident.first_event_time = min(event_times) if event_times else None
    incident.last_event_time = max(event_times) if event_times else None
    incident.first_seen_at = min(item.retrieved_at for item in observations)
    incident.last_seen_at = max(item.retrieved_at for item in observations)
    incident.canonical_location = Counter(
        item.original_location for item in evidence_observations
    ).most_common(1)[0][0]
    incident.canonical_grid = (
        Counter(item.grid for item in evidence_observations if item.grid).most_common(1)[0][0]
        if any(item.grid for item in evidence_observations)
        else None
    )
    incident.canonical_agency = (
        Counter(item.agency for item in evidence_observations if item.agency).most_common(1)[0][0]
        if any(item.agency for item in evidence_observations)
        else None
    )
    incident.canonical_station = (
        Counter(item.station for item in evidence_observations if item.station).most_common(1)[0][0]
        if any(item.station for item in evidence_observations)
        else None
    )
    for item in observations:
        if item.agency is not None:
            existing_agency = db.scalar(
                select(IncidentRespondingAgency.id).where(
                    IncidentRespondingAgency.incident_id == incident.id,
                    IncidentRespondingAgency.observation_id == item.id,
                    IncidentRespondingAgency.agency == item.agency,
                )
            )
            if existing_agency is None:
                db.add(
                    IncidentRespondingAgency(
                        id=str(uuid4()),
                        incident_id=incident.id,
                        observation_id=item.id,
                        agency=item.agency,
                        first_seen_at=_event_time(item),
                        last_seen_at=_event_time(item),
                    )
                )
        if item.station is not None:
            existing_station = db.scalar(
                select(IncidentRespondingStation.id).where(
                    IncidentRespondingStation.incident_id == incident.id,
                    IncidentRespondingStation.observation_id == item.id,
                    IncidentRespondingStation.station == item.station,
                )
            )
            if existing_station is None:
                db.add(
                    IncidentRespondingStation(
                        id=str(uuid4()),
                        incident_id=incident.id,
                        observation_id=item.id,
                        station=item.station,
                        first_seen_at=_event_time(item),
                        last_seen_at=_event_time(item),
                    )
                )

    contradiction_count = current_contradiction_count(evidence_observations)
    families = {item.normalized_event_family for item in evidence_observations}
    if len(families) > 1:
        for item in evidence_observations:
            _add_evidence(
                db,
                incident.id,
                item.id,
                "contradictory",
                "conflicting_event_type",
                "Source rows for this canonical incident contain different event families.",
                {"families": sorted(families), "source_event_type": item.original_event_type},
            )
    seen_event_ids: dict[str, list[DispatchObservation]] = {}
    for item in evidence_observations:
        if item.source_event_id:
            seen_event_ids.setdefault(item.source_event_id, []).append(item)
    for source_event_id, items in seen_event_ids.items():
        if len(items) > 1:
            times = [_event_time(item) for item in items]
            locations = {normalize_location(item.original_location) for item in items}
            if max(times) - min(times) > timedelta(minutes=90) or len(locations) > 1:
                for item in items:
                    _add_evidence(
                        db,
                        incident.id,
                        item.id,
                        "contradictory",
                        "reused_identifier",
                        "The source event identifier appears with incompatible time or location evidence.",
                        {"source_event_id": source_event_id, "locations": sorted(locations)},
                    )
    # Contradictory evidence is append-only provenance. The current incident projection must
    # be derived from current grouped observations so an older taxonomy or superseded source
    # row cannot permanently poison an otherwise consistent incident.
    incident.contradiction_count = contradiction_count
    previous_state = incident.state
    next_state = _state_for(incident, family, confidence, contradiction_count)
    if prior_family != family or prior_band != band or abs(prior_confidence - confidence) >= 0.01:
        _add_timeline(
            db,
            incident.id,
            "classification_changed",
            details={
                "prior_family": prior_family,
                "new_family": family,
                "prior_confidence": prior_confidence,
                "new_confidence": confidence,
                "prior_band": prior_band,
                "new_band": band,
                "classification_version": CLASSIFICATION_VERSION,
            },
            actor_user_id=actor_user_id,
        )
    if next_state != previous_state:
        incident.state = next_state
        _add_timeline(
            db,
            incident.id,
            "state_changed",
            prior_state=previous_state,
            new_state=next_state,
            details={
                "reason": "classification and contradiction rescore",
                "contradiction_count": contradiction_count,
            },
            actor_user_id=actor_user_id,
        )
    if (
        family in STRUCTURE_FAMILIES
        and confidence >= 0.85
        and incident.review_signal_status == "not_issued"
    ):
        incident.review_signal_status = "active"
        incident.review_signal_issued_at = _now()
        _add_timeline(
            db,
            incident.id,
            "review_signal_issued",
            details={"reason": "high-confidence structure-related classification"},
            actor_user_id=actor_user_id,
        )
    if contradiction_count and incident.review_signal_status == "active":
        incident.review_signal_status = "revoked"
        incident.review_signal_revoked_at = _now()
        incident.review_signal_revocation_reason = "contradictory source evidence lowered the incident confidence and requires human review"
        _add_timeline(
            db,
            incident.id,
            "review_signal_revoked",
            details={
                "reason": incident.review_signal_revocation_reason,
                "original_signal_status": "active",
            },
            actor_user_id=actor_user_id,
        )
    incident.classification_explanation = explanation
    incident.current_explanation = {
        "source_observation_count": len(observations),
        "evidence_group_count": len(evidence_groups),
        "evidence_grouping_version": EVIDENCE_GROUPING_VERSION,
        "source_observation_ids": [item.id for item in observations],
        "source_row_ids": [item.raw_dispatch_row_id for item in observations],
        "classification": explanation,
        "contradiction_count": contradiction_count,
        "rescore_hook": "new evidence triggers this deterministic recomputation",
    }
    return contradiction_count


def _candidate_incidents(
    db: Session, provider_id: str
) -> list[tuple[CanonicalIncident, list[DispatchObservation]]]:
    incidents = db.scalars(
        select(CanonicalIncident).where(
            CanonicalIncident.provider_id == provider_id,
            CanonicalIncident.is_active.is_(True),
        )
    ).all()
    return [
        (incident, _observations_for_links(db, _current_links(db, incident.id)))
        for incident in incidents
    ]


def _existing_source_record_incident(
    db: Session, observation: DispatchObservation
) -> Optional[tuple[CanonicalIncident, Optional[DispatchObservation]]]:
    if not observation.source_record_id:
        return None
    alias = db.scalar(
        select(IncidentAlias).where(
            IncidentAlias.provider_id == observation.provider_id,
            IncidentAlias.alias_type == "source_record_id",
            IncidentAlias.alias_value == observation.source_record_id,
        )
    )
    if alias is None:
        return None
    incident = db.get(CanonicalIncident, alias.incident_id)
    while incident is not None and not incident.is_active and incident.merged_into_id:
        incident = db.get(CanonicalIncident, incident.merged_into_id)
    if incident is None or not incident.is_active:
        return None
    reference = db.get(DispatchObservation, alias.observation_id)
    return incident, reference


def _retrieval_observations(db: Session, retrieval_id: str) -> list[DispatchObservation]:
    snapshot = db.scalar(select(RawSnapshot).where(RawSnapshot.retrieval_id == retrieval_id))
    if snapshot is None:
        raise ValueError("retrieval has no raw snapshot")
    return list(
        db.scalars(
            select(DispatchObservation)
            .where(DispatchObservation.raw_snapshot_id == snapshot.id)
            .order_by(DispatchObservation.event_time, DispatchObservation.id)
        ).all()
    )


def unprocessed_retrievals(
    db: Session, *, provider_id: Optional[str] = None
) -> list[ProviderRetrieval]:
    """Return imported snapshots whose accepted observations have no completed assembly run.

    Dispatch ingestion deliberately commits the immutable raw snapshot before canonical
    incident assembly. That preserves source evidence if assembly fails, but it also means
    a later worker must be able to find and finish the retained retrieval. A run left in a
    non-completed state is treated the same way: processing is idempotent and can resume
    from its current observation links.
    """

    query = (
        select(ProviderRetrieval)
        .join(RawSnapshot, RawSnapshot.retrieval_id == ProviderRetrieval.id)
        .outerjoin(
            IncidentProcessingRun,
            IncidentProcessingRun.retrieval_id == ProviderRetrieval.id,
        )
        .where(
            ProviderRetrieval.normalized_record_count > 0,
            or_(
                IncidentProcessingRun.id.is_(None),
                IncidentProcessingRun.status != "completed",
            ),
        )
        .order_by(ProviderRetrieval.retrieved_at, ProviderRetrieval.id)
    )
    if provider_id:
        query = query.where(ProviderRetrieval.provider_id == provider_id)
    return list(db.scalars(query).all())


def process_retrieval(
    db: Session,
    retrieval: ProviderRetrieval,
    settings: Settings,
    *,
    actor_user_id: Optional[str],
    reason: str = "incremental_import",
    request_id: Optional[str] = None,
) -> IncidentProcessingRun:
    if retrieval.acquisition_mode == "live_poll" and not live_polling_is_authorized(
        db, settings, retrieval.provider_id
    ):
        raise PermissionError(
            f"live polling for {retrieval.provider_id} is disabled or lacks the required approval basis; manually supplied snapshots and fixtures remain available"
        )
    if retrieval.acquisition_mode not in PROCESSABLE_ACQUISITION_MODES:
        raise PermissionError(
            "incident processing accepts manually supplied snapshots, fixtures, and approved live retrievals only"
        )
    # Serialize incident assembly per provider. PostgreSQL takes a row lock; this write also
    # forces SQLite to acquire its database write lock before candidate search.
    db.execute(
        update(Provider)
        .where(Provider.id == retrieval.provider_id)
        .values(updated_at=Provider.updated_at)
    )
    db.flush()
    existing_run = db.scalar(
        select(IncidentProcessingRun).where(IncidentProcessingRun.retrieval_id == retrieval.id)
    )
    if existing_run is not None and existing_run.status == "completed":
        # A replayed snapshot can predate a taxonomy correction. Keep the original processing
        # run immutable, but refresh the current incident projection from preserved source text.
        observations = _retrieval_observations(db, retrieval.id)
        incident_ids = db.scalars(
            select(IncidentObservationLink.incident_id)
            .where(
                IncidentObservationLink.observation_id.in_([item.id for item in observations]),
                IncidentObservationLink.is_current.is_(True),
            )
            .distinct()
        ).all()
        for incident_id in incident_ids:
            incident = db.get(CanonicalIncident, incident_id)
            if (
                incident is not None
                and incident.is_active
                and incident_needs_classification_refresh(db, incident)
            ):
                rescore_incident(
                    db,
                    incident,
                    actor_user_id=actor_user_id,
                    request_id=request_id or f"incident-replay-refresh:{incident.id}",
                )
        return existing_run
    observations = _retrieval_observations(db, retrieval.id)
    if existing_run is None:
        run = IncidentProcessingRun(
            id=str(uuid4()),
            provider_id=retrieval.provider_id,
            retrieval_id=retrieval.id,
            acquisition_mode=retrieval.acquisition_mode,
            reason=reason,
            linkage_version=LINKAGE_VERSION,
            classification_version=CLASSIFICATION_VERSION,
            status="processing",
            observation_count=len(observations),
            actor_user_id=actor_user_id,
        )
        db.add(run)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing_run = db.scalar(
                select(IncidentProcessingRun).where(
                    IncidentProcessingRun.retrieval_id == retrieval.id
                )
            )
            if existing_run is None:
                raise
            if existing_run.status == "completed":
                return existing_run
            run = existing_run
    else:
        # A prior worker can fail after persisting a processing row. Preserve that run's
        # identity and audit trail, then finish any observations it did not reach.
        run = existing_run
        run.acquisition_mode = retrieval.acquisition_mode
        run.reason = reason
        run.linkage_version = LINKAGE_VERSION
        run.classification_version = CLASSIFICATION_VERSION
        run.status = "processing"
        run.observation_count = len(observations)
        run.actor_user_id = actor_user_id
        run.linked_count = 0
        run.new_incident_count = 0
        run.review_count = 0
        run.contradiction_count = 0
        db.flush()
    new_count = 0
    linked_count = 0
    review_count = 0
    contradiction_count = 0
    for observation in observations:
        if _current_link_for_observation(db, observation.id) is not None:
            linked_count += 1
            continue
        existing_identity = _existing_source_record_incident(db, observation)
        if existing_identity is not None:
            identity_incident, reference = existing_identity
            choice = LinkageDecision(
                candidate=identity_incident,
                reference_observation=reference,
                decision="match",
                stage="deterministic",
                score=1.0,
                confidence_band="high_confidence",
                features={"same_source_record_id": True},
                explanation={
                    "reason": "exact source record identity was already assigned; retrieval replay is idempotent",
                    "thresholds": {"match": 0.88, "human_review": 0.62},
                    "model": "deterministic source identity guard",
                },
            )
        else:
            candidates = _candidate_incidents(db, retrieval.provider_id)
            choice = choose_linkage(observation, candidates)
        decision = _record_decision(
            db,
            observation,
            choice.decision,
            choice.stage,
            choice.score,
            choice.confidence_band,
            choice.features,
            choice.explanation,
            candidate_incident_id=choice.candidate.id if choice.candidate else None,
            reference_observation_id=choice.reference_observation.id
            if choice.reference_observation
            else None,
            actor_user_id=actor_user_id,
        )
        if choice.decision == "match" and choice.candidate is not None:
            incident = choice.candidate
            _link_observation(
                db,
                incident,
                observation,
                link_type=choice.stage,
                decision_id=decision.id,
                actor_user_id=actor_user_id,
            )
            linked_count += 1
        else:
            if choice.candidate is not None and "reused" in str(
                choice.explanation.get("reason", "")
            ):
                _add_evidence(
                    db,
                    choice.candidate.id,
                    observation.id,
                    "contradictory",
                    "reused_identifier",
                    "A source identifier was reused with incompatible time or location evidence; the new row was kept separate.",
                    {"reason": choice.explanation.get("reason"), "observation_id": observation.id},
                )
                db.flush()
                recompute_incident(db, choice.candidate, actor_user_id=actor_user_id)
            incident = _create_incident_record(db, observation)
            _link_observation(
                db,
                incident,
                observation,
                link_type="automatic_new",
                decision_id=decision.id,
                actor_user_id=actor_user_id,
            )
            new_count += 1
            if choice.decision == "possible_match":
                review_count += 1
                _add_evidence(
                    db,
                    incident.id,
                    observation.id,
                    "contradictory",
                    "possible_existing_incident",
                    "A possible existing incident was kept separate pending human review.",
                    {
                        "candidate_incident_id": choice.candidate.id if choice.candidate else None,
                        "score": choice.score,
                        "explanation": choice.explanation,
                    },
                )
        db.flush()
        contradiction_count += recompute_incident(db, incident, actor_user_id=actor_user_id)
    run.status = "completed"
    run.linked_count = linked_count
    run.new_incident_count = new_count
    run.review_count = review_count
    run.contradiction_count = contradiction_count
    record_audit(
        db,
        action="incident.retrieval_processed",
        resource_type="incident_processing_run",
        resource_id=run.id,
        actor_user_id=actor_user_id,
        request_id=request_id or f"incident-process:{run.id}",
        metadata={
            "retrieval_id": retrieval.id,
            "provider_id": retrieval.provider_id,
            "acquisition_mode": retrieval.acquisition_mode,
            "observation_count": len(observations),
            "new_incident_count": new_count,
            "linked_count": linked_count,
            "review_count": review_count,
            "contradiction_count": contradiction_count,
        },
    )
    return run


def rescore_incident(
    db: Session,
    incident: CanonicalIncident,
    *,
    actor_user_id: Optional[str],
    request_id: Optional[str] = None,
) -> int:
    contradiction_count = recompute_incident(db, incident, actor_user_id=actor_user_id)
    _add_timeline(
        db,
        incident.id,
        "rescored",
        details={
            "linkage_version": LINKAGE_VERSION,
            "classification_version": CLASSIFICATION_VERSION,
            "contradiction_count": contradiction_count,
        },
        actor_user_id=actor_user_id,
    )
    record_audit(
        db,
        action="incident.rescored",
        resource_type="canonical_incident",
        resource_id=incident.id,
        actor_user_id=actor_user_id,
        request_id=request_id or f"incident-rescore:{incident.id}",
        metadata={
            "linkage_version": LINKAGE_VERSION,
            "classification_version": CLASSIFICATION_VERSION,
            "contradiction_count": contradiction_count,
        },
    )
    return contradiction_count


def transition_state(
    db: Session,
    incident: CanonicalIncident,
    new_state: str,
    *,
    reason: str,
    actor_user_id: Optional[str],
    request_id: Optional[str] = None,
) -> None:
    if new_state not in VALID_STATES:
        raise ValueError(f"unsupported incident state: {new_state}")
    if new_state == incident.state:
        return
    if new_state not in ALLOWED_TRANSITIONS.get(incident.state, set()):
        raise ValueError(f"invalid incident state transition: {incident.state} -> {new_state}")
    previous = incident.state
    incident.state = new_state
    _add_timeline(
        db,
        incident.id,
        "state_changed",
        prior_state=previous,
        new_state=new_state,
        details={"reason": reason, "manual": True},
        actor_user_id=actor_user_id,
    )
    record_audit(
        db,
        action="incident.state_changed",
        resource_type="canonical_incident",
        resource_id=incident.id,
        actor_user_id=actor_user_id,
        request_id=request_id or f"incident-state:{incident.id}",
        metadata={"prior_state": previous, "new_state": new_state, "reason": reason},
    )


def merge_incidents(
    db: Session,
    survivor: CanonicalIncident,
    absorbed: CanonicalIncident,
    *,
    reason: str,
    actor_user_id: Optional[str],
    request_id: Optional[str] = None,
) -> None:
    if survivor.id == absorbed.id:
        raise ValueError("an incident cannot be merged into itself")
    if not survivor.is_active or not absorbed.is_active:
        raise ValueError("only active incidents can be merged")
    if survivor.provider_id != absorbed.provider_id:
        raise ValueError("incidents from different providers cannot be merged")
    moved_ids: list[str] = []
    for link in _current_links(db, absorbed.id):
        link.is_current = False
        link.assignment_key = None
        link.ended_at = _now()
        db.flush()
        observation = db.get(DispatchObservation, link.observation_id)
        if observation is None:
            raise ValueError("incident link points to a missing source observation")
        _link_observation(
            db,
            survivor,
            observation,
            link_type="manual_merge",
            decision_id=None,
            actor_user_id=actor_user_id,
        )
        moved_ids.append(observation.id)
    db.flush()
    absorbed.is_active = False
    absorbed.merged_into_id = survivor.id
    absorbed.state = STATE_CLOSED
    merge = IncidentMerge(
        id=str(uuid4()),
        survivor_incident_id=survivor.id,
        absorbed_incident_id=absorbed.id,
        reason=reason,
        explanation={"moved_observation_ids": moved_ids, "source_rows_preserved": True},
        actor_user_id=actor_user_id,
    )
    db.add(merge)
    _add_timeline(
        db,
        survivor.id,
        "merged",
        details={"absorbed_incident_id": absorbed.id, "reason": reason},
        actor_user_id=actor_user_id,
    )
    _add_timeline(
        db,
        absorbed.id,
        "merged",
        details={"survivor_incident_id": survivor.id, "reason": reason},
        actor_user_id=actor_user_id,
    )
    recompute_incident(db, survivor, actor_user_id=actor_user_id)
    record_audit(
        db,
        action="incident.merged",
        resource_type="canonical_incident",
        resource_id=survivor.id,
        actor_user_id=actor_user_id,
        request_id=request_id or f"incident-merge:{survivor.id}:{absorbed.id}",
        metadata={
            "absorbed_incident_id": absorbed.id,
            "moved_observation_ids": moved_ids,
            "reason": reason,
        },
    )


def split_incident(
    db: Session,
    incident: CanonicalIncident,
    observation_ids: list[str],
    *,
    reason: str,
    actor_user_id: Optional[str],
    request_id: Optional[str] = None,
) -> CanonicalIncident:
    if not incident.is_active:
        raise ValueError("only active incidents can be split")
    requested = set(observation_ids)
    current = {link.observation_id: link for link in _current_links(db, incident.id)}
    if not requested or not requested.issubset(current):
        raise ValueError(
            "split observations must be non-empty and currently belong to the incident"
        )
    if len(requested) == len(current):
        raise ValueError(
            "a split must leave at least one source observation on the original incident"
        )
    observations = [db.get(DispatchObservation, observation_id) for observation_id in requested]
    if any(item is None for item in observations):
        raise ValueError("split references a missing source observation")
    first = observations[0]
    assert first is not None
    new_incident = _create_incident_record(db, first)
    # _create_incident_record only creates the ledger row; the first observation is moved below.
    for observation_id in requested:
        old_link = current[observation_id]
        old_link.is_current = False
        old_link.assignment_key = None
        old_link.ended_at = _now()
        db.flush()
        observation = db.get(DispatchObservation, observation_id)
        assert observation is not None
        _link_observation(
            db,
            new_incident,
            observation,
            link_type="manual_split",
            decision_id=None,
            actor_user_id=actor_user_id,
        )
    db.flush()
    recompute_incident(db, incident, actor_user_id=actor_user_id)
    recompute_incident(db, new_incident, actor_user_id=actor_user_id)
    split = IncidentSplit(
        id=str(uuid4()),
        original_incident_id=incident.id,
        new_incident_id=new_incident.id,
        moved_observation_ids=sorted(requested),
        reason=reason,
        explanation={"source_rows_preserved": True, "moved_count": len(requested)},
        actor_user_id=actor_user_id,
    )
    db.add(split)
    _add_timeline(
        db,
        incident.id,
        "split",
        details={
            "new_incident_id": new_incident.id,
            "moved_observation_ids": sorted(requested),
            "reason": reason,
        },
        actor_user_id=actor_user_id,
    )
    _add_timeline(
        db,
        new_incident.id,
        "split",
        details={
            "original_incident_id": incident.id,
            "moved_observation_ids": sorted(requested),
            "reason": reason,
        },
        actor_user_id=actor_user_id,
    )
    record_audit(
        db,
        action="incident.split",
        resource_type="canonical_incident",
        resource_id=incident.id,
        actor_user_id=actor_user_id,
        request_id=request_id or f"incident-split:{incident.id}:{new_incident.id}",
        metadata={
            "new_incident_id": new_incident.id,
            "moved_observation_ids": sorted(requested),
            "reason": reason,
        },
    )
    return new_incident
