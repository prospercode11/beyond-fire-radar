from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.models import (
    CanonicalIncident,
    DispatchObservation,
    IncidentObservationLink,
    IncidentPropertyCandidate,
    IncidentPropertyMatchRun,
    Parcel,
    ParcelAddressAlias,
    PropertyImport,
    PropertyMatchDecision,
    PropertyMatchFeature,
)
from app.properties.address import (
    ADDRESS_NORMALIZATION_VERSION,
    NormalizedAddress,
    normalize_address,
)

MATCHER_VERSION = "property-match.v1"
FEATURE_VERSION = "property-match-features.v1"
MATCH_THRESHOLD = 0.78
EXACT_THRESHOLD = 0.92
MARGIN_THRESHOLD = 0.10
EXACT_MARGIN_THRESHOLD = 0.15


def _utc_datetime(value: datetime) -> datetime:
    """Treat database-naive timestamps as UTC before comparing them."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _similar(left: Optional[str], right: Optional[str]) -> Optional[float]:
    if not left or not right:
        return None
    return SequenceMatcher(None, left, right).ratio()


def _haversine_miles(
    lat1: Optional[float], lon1: Optional[float], lat2: Optional[float], lon2: Optional[float]
) -> Optional[float]:
    if None in {lat1, lon1, lat2, lon2}:
        return None
    assert lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None
    radius = 3958.8
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def _incident_observations(db: Session, incident_id: str) -> list[DispatchObservation]:
    return list(
        db.scalars(
            select(DispatchObservation)
            .join(
                IncidentObservationLink,
                IncidentObservationLink.observation_id == DispatchObservation.id,
            )
            .where(
                IncidentObservationLink.incident_id == incident_id,
                IncidentObservationLink.is_current.is_(True),
            )
            .order_by(DispatchObservation.event_time, DispatchObservation.id)
        ).all()
    )


def _latest_correction(db: Session, incident_id: str) -> Optional[str]:
    decision = db.scalar(
        select(PropertyMatchDecision)
        .where(
            PropertyMatchDecision.incident_id == incident_id,
            PropertyMatchDecision.decision == "corrected",
        )
        .order_by(PropertyMatchDecision.created_at.desc(), PropertyMatchDecision.id.desc())
    )
    return decision.corrected_address if decision else None


def current_property_decision(db: Session, incident_id: str) -> Optional[PropertyMatchDecision]:
    return db.scalar(
        select(PropertyMatchDecision)
        .where(PropertyMatchDecision.incident_id == incident_id)
        .order_by(PropertyMatchDecision.created_at.desc(), PropertyMatchDecision.id.desc())
    )


def _incident_address(
    db: Session, incident: CanonicalIncident
) -> tuple[NormalizedAddress, Optional[float], Optional[float], list[str]]:
    observations = _incident_observations(db, incident.id)
    corrected = _latest_correction(db, incident.id)
    source = (
        corrected
        or incident.canonical_location
        or (observations[0].original_location if observations else "")
    )
    municipality = None
    postal_code = None
    latitude = None
    longitude = None
    precision = None
    for observation in observations:
        municipality = municipality or None
        latitude = latitude if latitude is not None else observation.latitude
        longitude = longitude if longitude is not None else observation.longitude
        precision = precision or observation.location_precision
    address = normalize_address(source, municipality=municipality, postal_code=postal_code)
    if precision and precision not in {"", "unknown"}:
        address = NormalizedAddress(
            original=address.original,
            normalized=address.normalized,
            precision=precision,
            house_number=address.house_number,
            street_prefix=address.street_prefix,
            street_name=address.street_name,
            street_type=address.street_type,
            street_suffix=address.street_suffix,
            unit=address.unit,
            municipality=address.municipality,
            postal_code=address.postal_code,
            street_tokens=address.street_tokens,
            warnings=address.warnings,
        )
    return address, latitude, longitude, [item.id for item in observations]


def _property_address(parcel: Parcel) -> NormalizedAddress:
    return normalize_address(
        parcel.situs_original,
        municipality=parcel.municipality,
        postal_code=parcel.postal_code,
        unit=parcel.unit,
    )


def _address_core_matches(left: NormalizedAddress, right: NormalizedAddress) -> bool:
    """Match the address components both sources actually supplied."""
    if not left.house_number or not right.house_number:
        return False
    if left.house_number != right.house_number or left.street_name != right.street_name:
        return False
    if left.street_type and right.street_type and left.street_type != right.street_type:
        return False
    if left.street_prefix and right.street_prefix and left.street_prefix != right.street_prefix:
        return False
    if left.street_suffix and right.street_suffix and left.street_suffix != right.street_suffix:
        return False
    if left.unit and left.unit != right.unit:
        return False
    if left.municipality and right.municipality and left.municipality != right.municipality:
        return False
    if left.postal_code and right.postal_code and left.postal_code != right.postal_code:
        return False
    return True


def _candidate_pool(
    db: Session,
    provider_id: str,
    address: NormalizedAddress,
    latitude: Optional[float],
    longitude: Optional[float],
) -> list[Parcel]:
    base = select(Parcel).where(Parcel.provider_id == provider_id, Parcel.is_active.is_(True))
    candidates: dict[str, Parcel] = {}

    def add(query) -> None:
        for parcel in db.scalars(query.limit(500)).all():
            candidates[parcel.id] = parcel

    if address.normalized:
        add(base.where(Parcel.normalized_address == address.normalized))
        add(
            base.join(ParcelAddressAlias, ParcelAddressAlias.parcel_id == Parcel.id).where(
                ParcelAddressAlias.normalized_address == address.normalized
            )
        )

    street_names = set()
    if address.street_name:
        street_names.add(address.street_name)
    if address.precision == "intersection":
        for token in address.street_tokens:
            street_names.add(token.split()[0])
    for street_name in street_names:
        query = base.where(Parcel.street_name.ilike(f"%{street_name}%"))
        if address.house_number and address.precision not in {"street_block", "intersection"}:
            query = query.where(
                or_(Parcel.house_number == address.house_number, Parcel.house_number.is_(None))
            )
        if address.municipality:
            query = query.where(
                or_(
                    Parcel.municipality.ilike(address.municipality),
                    Parcel.municipality.is_(None),
                )
            )
        if address.postal_code:
            query = query.where(
                or_(Parcel.postal_code == address.postal_code, Parcel.postal_code.is_(None))
            )
        add(query)

    if address.municipality or address.postal_code:
        location_filters: list[Any] = []
        if address.municipality:
            location_filters.append(Parcel.municipality.ilike(address.municipality))
        if address.postal_code:
            location_filters.append(Parcel.postal_code == address.postal_code)
        add(base.where(or_(*location_filters)))

    if latitude is not None and longitude is not None:
        # A bounding-box query is deliberately only candidate generation; the scorer retains
        # the exact haversine evidence and can abstain when the candidates remain close.
        add(
            base.where(
                Parcel.latitude.between(latitude - 0.25, latitude + 0.25),
                Parcel.longitude.between(longitude - 0.25, longitude + 0.25),
            )
        )

    # Preserve condo/master relationships for human review even when only one side carries the
    # incident's situs address. Address aliases are queried before this expansion.
    master_ids = {
        parcel.master_parcel_id for parcel in candidates.values() if parcel.master_parcel_id
    }
    parcel_ids = {parcel.parcel_id for parcel in candidates.values()}
    if master_ids or parcel_ids:
        relationship_filters: list[Any] = []
        if master_ids:
            relationship_filters.append(Parcel.parcel_id.in_(master_ids))
        if parcel_ids:
            relationship_filters.append(Parcel.master_parcel_id.in_(parcel_ids))
        add(base.where(or_(*relationship_filters)))

    if not candidates:
        # For landmarks and otherwise malformed locations, return a bounded, deterministic
        # review pool. No candidate from this fallback can be auto-recommended because the
        # source precision gate below requires an exact address.
        add(base.order_by(Parcel.parcel_id))
    return sorted(candidates.values(), key=lambda parcel: parcel.parcel_id)[:500]


def _property_use_score(event_family: str, category: Optional[str]) -> Optional[float]:
    if not category:
        return None
    category = category.lower()
    if "structure" in event_family.lower() or "fire" in event_family.lower():
        if any(
            word in category
            for word in ("residential", "commercial", "multifamily", "condo", "industrial")
        ):
            return 1.0
        if any(word in category for word in ("vacant", "land", "parking")):
            return 0.2
    return 0.5


def _score_candidate(
    incident: CanonicalIncident,
    incident_address: NormalizedAddress,
    incident_latitude: Optional[float],
    incident_longitude: Optional[float],
    parcel: Parcel,
    candidate_count: int,
) -> tuple[
    float, dict[str, Optional[float]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]
]:
    property_address = _property_address(parcel)
    address_core_matches = _address_core_matches(incident_address, property_address)
    values: dict[str, Optional[float]] = {
        "address_exact": (
            1.0
            if incident_address.normalized == property_address.normalized or address_core_matches
            else 0.0
        ),
        "house_number_agreement": 1.0
        if incident_address.house_number
        and incident_address.house_number == property_address.house_number
        else 0.0
        if incident_address.house_number and property_address.house_number
        else None,
        "street_similarity": _similar(incident_address.street_name, property_address.street_name),
        "street_type_agreement": 1.0
        if incident_address.street_type
        and incident_address.street_type == property_address.street_type
        else 0.0
        if incident_address.street_type and property_address.street_type
        else None,
        "directional_agreement": 1.0
        if incident_address.street_prefix
        and incident_address.street_prefix == property_address.street_prefix
        else 0.0
        if incident_address.street_prefix and property_address.street_prefix
        else None,
        "unit_agreement": 1.0
        if incident_address.unit and incident_address.unit == property_address.unit
        else 0.0
        if incident_address.unit and property_address.unit
        else None,
        "municipality_agreement": 1.0
        if incident_address.municipality
        and property_address.municipality
        and incident_address.municipality == property_address.municipality
        else 0.0
        if incident_address.municipality and property_address.municipality
        else None,
        "postal_code_agreement": 1.0
        if incident_address.postal_code
        and incident_address.postal_code == property_address.postal_code
        else 0.0
        if incident_address.postal_code and property_address.postal_code
        else None,
        "grid_agreement": 1.0
        if incident.canonical_grid and parcel.grid and incident.canonical_grid == parcel.grid
        else 0.0
        if incident.canonical_grid and parcel.grid
        else None,
        "geographic_proximity": None,
        "property_context": _property_use_score(
            incident.classification_family, parcel.property_use_category
        ),
        "candidate_density": max(0.0, 1.0 - min(candidate_count, 20) / 20),
    }
    distance = _haversine_miles(
        incident_latitude, incident_longitude, parcel.latitude, parcel.longitude
    )
    if distance is not None:
        values["geographic_proximity"] = max(0.0, 1.0 - min(distance, 10.0) / 10.0)
    weights = {
        "address_exact": 0.28,
        "house_number_agreement": 0.18,
        "street_similarity": 0.16,
        "street_type_agreement": 0.06,
        "directional_agreement": 0.04,
        "unit_agreement": 0.08,
        "municipality_agreement": 0.06,
        "postal_code_agreement": 0.05,
        "grid_agreement": 0.04,
        "geographic_proximity": 0.03,
        "property_context": 0.02,
    }
    available = [
        (name, value) for name, value in values.items() if value is not None and name in weights
    ]
    denominator = sum(weights[name] for name, _ in available) or 1.0
    score = sum(weights[name] * float(value) for name, value in available) / denominator
    supporting = [
        {
            "code": name,
            "value": value,
            "summary": f"{name.replace('_', ' ')} contributed {value:.2f}",
        }
        for name, value in available
        if value is not None and value >= 0.75
    ]
    contradictory: list[dict[str, Any]] = []
    for name, value in available:
        if (
            value is not None
            and value <= 0.0
            and name
            in {
                "house_number_agreement",
                "street_similarity",
                "municipality_agreement",
                "postal_code_agreement",
                "unit_agreement",
            }
        ):
            contradictory.append(
                {"code": name, "summary": f"{name.replace('_', ' ')} conflicts with the candidate"}
            )
    if (
        parcel.latitude is not None
        and parcel.longitude is not None
        and not (-90 <= parcel.latitude <= 90 and -180 <= parcel.longitude <= 180)
    ):
        contradictory.append(
            {"code": "invalid_geometry", "summary": "parcel coordinates are outside valid bounds"}
        )
    if parcel.data_quality.get("invalid_coordinate"):
        contradictory.append(
            {"code": "invalid_geometry", "summary": "source coordinates failed validation"}
        )
    quality = {
        "missing_coordinates": parcel.latitude is None or parcel.longitude is None,
        "candidate_density": candidate_count,
        "source_version": parcel.source_version,
        "stale": bool(
            parcel.effective_at
            and _utc_datetime(parcel.effective_at)
            < datetime.now(timezone.utc) - timedelta(days=730)
        ),
        "address_warnings": list(property_address.warnings),
    }
    return score, values, supporting, contradictory, quality


def run_property_match(
    db: Session,
    incident: CanonicalIncident,
    *,
    property_provider_id: str,
    property_import_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> IncidentPropertyMatchRun:
    current_import = (
        db.get(PropertyImport, property_import_id)
        if property_import_id
        else db.scalar(
            select(PropertyImport)
            .where(
                PropertyImport.provider_id == property_provider_id,
                PropertyImport.is_current.is_(True),
            )
            .order_by(PropertyImport.created_at.desc())
        )
    )
    if current_import is None or current_import.provider_id != property_provider_id:
        raise ValueError("no current property import is available for this provider")
    if not current_import.is_current:
        raise ValueError(
            "historical property imports cannot be used for new matches; select the current import"
        )
    incident_address, latitude, longitude, observation_ids = _incident_address(db, incident)
    run = IncidentPropertyMatchRun(
        id=str(uuid4()),
        incident_id=incident.id,
        property_provider_id=property_provider_id,
        property_import_id=current_import.id,
        status="running",
        matcher_version=MATCHER_VERSION,
        address_normalization_version=ADDRESS_NORMALIZATION_VERSION,
        source_observation_ids=observation_ids,
        created_by=actor_user_id,
    )
    db.add(run)
    db.flush()
    parcels = _candidate_pool(db, property_provider_id, incident_address, latitude, longitude)
    scored: list[
        tuple[
            Parcel,
            float,
            dict[str, Optional[float]],
            list[dict[str, Any]],
            list[dict[str, Any]],
            dict[str, Any],
        ]
    ] = []
    for parcel in parcels:
        score, features, supporting, contradictory, quality = _score_candidate(
            incident, incident_address, latitude, longitude, parcel, len(parcels)
        )
        scored.append((parcel, score, features, supporting, contradictory, quality))
    scored.sort(key=lambda item: (-item[1], item[0].parcel_id))
    top_score = scored[0][1] if scored else 0.0
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    margin = top_score - second_score if scored else None
    source_precision = incident_address.precision
    same_location_candidates = [
        item
        for item in scored
        if item[0].house_number == incident_address.house_number
        and item[0].street_name == incident_address.street_name
    ]
    unit_ambiguous = (
        not incident_address.unit
        and len(
            [
                item
                for item in same_location_candidates
                if item[0].unit or item[0].number_of_units and item[0].number_of_units > 1
            ]
        )
        > 1
    )
    low_precision = source_precision in {
        "street_block",
        "intersection",
        "landmark",
        "highway",
        "approximate",
        "unusable",
    }
    for rank, (parcel, score, features, supporting, contradictory, quality) in enumerate(
        scored[:20], start=1
    ):
        candidate_margin = score - (scored[rank][1] if rank < len(scored) else 0.0)
        candidate_contradictions = list(contradictory)
        if unit_ambiguous:
            candidate_contradictions.append(
                {
                    "code": "unit_ambiguity",
                    "summary": "multiple units or master/unit parcels share the incident address",
                }
            )
        if low_precision:
            candidate_contradictions.append(
                {
                    "code": "low_source_precision",
                    "summary": f"source location precision is {source_precision}",
                }
            )
        if quality["stale"]:
            candidate_contradictions.append(
                {
                    "code": "stale_property_data",
                    "summary": "property source effective date is older than the freshness guard",
                }
            )
        if candidate_contradictions and any(
            item["code"]
            in {"invalid_geometry", "unit_ambiguity", "low_source_precision", "stale_property_data"}
            for item in candidate_contradictions
        ):
            recommendation = "abstain"
            is_abstained = True
        elif (
            rank == 1
            and score >= EXACT_THRESHOLD
            and (margin or 0.0) >= EXACT_MARGIN_THRESHOLD
            and source_precision in {"exact_address", "exact_address_with_unit"}
        ):
            recommendation = "recommended"
            is_abstained = False
        elif (
            rank == 1
            and score >= MATCH_THRESHOLD
            and (margin or 0.0) >= MARGIN_THRESHOLD
            and source_precision in {"exact_address", "exact_address_with_unit"}
        ):
            recommendation = "recommended"
            is_abstained = False
        else:
            recommendation = "review"
            is_abstained = True
        classification = (
            "exact"
            if rank == 1 and score >= EXACT_THRESHOLD
            else "strong"
            if rank == 1 and score >= MATCH_THRESHOLD
            else "ambiguous"
            if score >= 0.5
            else "weak"
        )
        if low_precision or unit_ambiguous or not scored:
            classification = "unresolved" if score < 0.5 else "ambiguous"
        explanation = {
            "summary": "Candidate ranked from versioned address, identifier, geographic, context, and data-quality evidence; this is not a probability.",
            "supporting_evidence": supporting,
            "contradictory_evidence": candidate_contradictions,
            "source_precision": source_precision,
            "best_candidate_margin": margin,
            "abstention_reason": candidate_contradictions[0]["code"]
            if is_abstained and candidate_contradictions
            else None,
            "matcher_version": MATCHER_VERSION,
        }
        candidate = IncidentPropertyCandidate(
            id=str(uuid4()),
            match_run_id=run.id,
            incident_id=incident.id,
            parcel_id=parcel.id,
            rank=rank,
            match_score=score,
            score_margin=candidate_margin,
            classification=classification,
            recommendation_status=recommendation,
            is_abstained=is_abstained,
            supporting_evidence=supporting,
            contradictory_evidence=candidate_contradictions,
            features=features,
            explanation=explanation,
            property_data_quality=quality,
        )
        db.add(candidate)
        db.flush()
        for feature_name, value in features.items():
            db.add(
                PropertyMatchFeature(
                    id=str(uuid4()),
                    candidate_id=candidate.id,
                    feature_name=feature_name,
                    numeric_value=value,
                    contribution=value,
                    available_at=current_import.effective_at or current_import.retrieved_at,
                    feature_version=FEATURE_VERSION,
                    explanation=f"{feature_name.replace('_', ' ')} was available from the incident/property snapshot",
                )
            )
    if not scored:
        run.status = "abstained"
        run.abstention_reason = "no_candidate"
    elif low_precision:
        run.status = "abstained"
        run.abstention_reason = "low_source_precision"
    elif unit_ambiguous:
        run.status = "abstained"
        run.abstention_reason = "unit_ambiguity"
    elif scored[0][1] >= MATCH_THRESHOLD and (margin or 0.0) >= MARGIN_THRESHOLD:
        run.status = "matched"
    else:
        run.status = "human_review"
        run.abstention_reason = "insufficient_separation_or_score"
    run.candidate_count = len(scored)
    run.completed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        action="property.match_run_created",
        resource_type="incident_property_match_run",
        resource_id=run.id,
        actor_user_id=actor_user_id,
        request_id="property-match:" + run.id,
        metadata={
            "incident_id": incident.id,
            "property_provider_id": property_provider_id,
            "property_import_id": current_import.id,
            "status": run.status,
            "candidate_count": run.candidate_count,
            "abstention_reason": run.abstention_reason,
        },
    )
    return run


def record_property_decision(
    db: Session,
    incident: CanonicalIncident,
    *,
    decision: str,
    reason: str,
    actor_user_id: str,
    request_id: str,
    candidate: Optional[IncidentPropertyCandidate] = None,
    corrected_address: Optional[str] = None,
) -> PropertyMatchDecision:
    if decision not in {"confirmed", "rejected", "cleared", "corrected"}:
        raise ValueError("decision must be confirmed, rejected, cleared, or corrected")
    if decision == "confirmed" and candidate is None:
        raise ValueError("confirmed decisions require a candidate")
    if decision == "corrected" and not corrected_address:
        raise ValueError("corrected decisions require corrected_address")
    if candidate is not None and candidate.incident_id != incident.id:
        raise ValueError("candidate does not belong to incident")
    result = PropertyMatchDecision(
        id=str(uuid4()),
        incident_id=incident.id,
        candidate_id=candidate.id if candidate else None,
        parcel_id=candidate.parcel_id if candidate and decision == "confirmed" else None,
        match_run_id=candidate.match_run_id if candidate else None,
        decision=decision,
        corrected_address=corrected_address,
        reason=reason,
        actor_user_id=actor_user_id,
    )
    db.add(result)
    record_audit(
        db,
        action="property.match_decision_recorded",
        resource_type="canonical_incident",
        resource_id=incident.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={
            "decision": decision,
            "candidate_id": candidate.id if candidate else None,
            "parcel_id": candidate.parcel_id if candidate and decision == "confirmed" else None,
            "corrected_address": corrected_address,
        },
    )
    return result
