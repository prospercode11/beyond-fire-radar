from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

from app.models import CanonicalIncident, DispatchObservation

LINKAGE_VERSION = "incident-linkage.v1"
CLASSIFICATION_VERSION = "incident-classification.v1"
MATCH_THRESHOLD = 0.88
REVIEW_THRESHOLD = 0.62
DETERMINISTIC_TIME_WINDOW_MINUTES = 90
SAME_CASE_EVENT_UPDATE_WINDOW_MINUTES = DETERMINISTIC_TIME_WINDOW_MINUTES
ALTERNATE_CASE_EVENT_DUPLICATE_WINDOW_MINUTES = 5
MAX_CLUSTER_SPAN_HOURS = 24

STATE_NEW = "Newly observed"
STATE_AWAITING = "Awaiting corroboration"
STATE_PROPERTY_UNRESOLVED = "Property unresolved"
STATE_LIKELY_STRUCTURE = "Likely structure-related"
STATE_HIGH_STRUCTURE = "High-confidence structure-related"
STATE_DISPOSITION_PENDING = "Disposition pending"
STATE_CONFIRMED = "Confirmed meaningful incident"
STATE_DOWNGRADED = "Downgraded"
STATE_FALSE_ALARM = "False alarm"
STATE_CLOSED = "Closed"
STATE_SUPPRESSED = "Suppressed"

VALID_STATES = {
    STATE_NEW,
    STATE_AWAITING,
    STATE_PROPERTY_UNRESOLVED,
    STATE_LIKELY_STRUCTURE,
    STATE_HIGH_STRUCTURE,
    STATE_DISPOSITION_PENDING,
    STATE_CONFIRMED,
    STATE_DOWNGRADED,
    STATE_FALSE_ALARM,
    STATE_CLOSED,
    STATE_SUPPRESSED,
}

_ABBREVIATIONS = {
    "STREET": "ST",
    "ROAD": "RD",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "LANE": "LN",
    "COURT": "CT",
    "HIGHWAY": "HWY",
    "PARKWAY": "PKWY",
    "PLACE": "PL",
    "TERRACE": "TER",
}


@dataclass(frozen=True)
class LinkageDecision:
    candidate: Optional[CanonicalIncident]
    reference_observation: Optional[DispatchObservation]
    decision: str
    stage: str
    score: float
    confidence_band: str
    features: dict[str, Any]
    explanation: dict[str, Any]


def utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_location(value: Optional[str]) -> str:
    if not value:
        return ""
    text = re.sub(r"[^A-Z0-9 ]+", " ", value.upper())
    tokens = [_ABBREVIATIONS.get(token, token) for token in text.split()]
    return " ".join(tokens)


def _house_number(value: str) -> Optional[str]:
    match = re.match(r"^(\d+[A-Z]?)\b", value)
    return match.group(1) if match else None


def _street_tokens(value: str) -> set[str]:
    tokens = value.split()
    if tokens and _house_number(value):
        tokens = tokens[1:]
    return set(tokens)


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.5
    return round(SequenceMatcher(None, left, right).ratio(), 4)


def _token_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.5
    return round(len(left & right) / len(left | right), 4)


def _time_similarity(left: Optional[datetime], right: Optional[datetime]) -> float:
    left_utc = utc_datetime(left)
    right_utc = utc_datetime(right)
    if left_utc is None or right_utc is None:
        return 0.5
    delta_minutes = abs((left_utc - right_utc).total_seconds()) / 60
    return round(math.exp(-delta_minutes / 120), 4) if delta_minutes <= 720 else 0.0


def pair_features(left: DispatchObservation, right: DispatchObservation) -> dict[str, Any]:
    left_location = normalize_location(left.original_location)
    right_location = normalize_location(right.original_location)
    left_family = (left.normalized_event_family or "").lower()
    right_family = (right.normalized_event_family or "").lower()
    same_event_id = bool(
        left.source_event_id
        and right.source_event_id
        and left.source_event_id == right.source_event_id
    )
    same_case = bool(
        left.source_case_number
        and right.source_case_number
        and left.source_case_number == right.source_case_number
        and (not left.agency or not right.agency or left.agency == right.agency)
    )
    left_time = utc_datetime(left.event_time)
    right_time = utc_datetime(right.event_time)
    time_difference_minutes = (
        round(abs((left_time - right_time).total_seconds()) / 60, 2)
        if left_time is not None and right_time is not None
        else None
    )
    return {
        "same_source_record_id": bool(
            left.source_record_id and left.source_record_id == right.source_record_id
        ),
        "same_source_event_id": same_event_id,
        "same_source_case_number": same_case,
        "time_similarity": _time_similarity(left.event_time, right.event_time),
        "time_difference_minutes": time_difference_minutes,
        "address_similarity": _similarity(left_location, right_location),
        "house_number_agreement": (
            1.0
            if _house_number(left_location)
            and _house_number(left_location) == _house_number(right_location)
            else 0.0
            if _house_number(left_location) and _house_number(right_location)
            else 0.5
        ),
        "street_token_overlap": _token_overlap(
            _street_tokens(left_location), _street_tokens(right_location)
        ),
        "grid_agreement": (
            1.0
            if left.grid and right.grid and left.grid == right.grid
            else 0.0
            if left.grid and right.grid
            else 0.5
        ),
        "agency_agreement": (
            1.0
            if left.agency and right.agency and left.agency == right.agency
            else 0.0
            if left.agency and right.agency
            else 0.5
        ),
        "station_agreement": (
            1.0
            if left.station and right.station and left.station == right.station
            else 0.0
            if left.station and right.station
            else 0.5
        ),
        "event_family_agreement": (
            1.0
            if left_family and right_family and left_family == right_family
            else 0.2
            if left_family and right_family
            else 0.5
        ),
        "event_type_similarity": _similarity(
            (left.original_event_type or "").upper(), (right.original_event_type or "").upper()
        ),
        "shared_location_tokens": sorted(
            _street_tokens(left_location) & _street_tokens(right_location)
        ),
    }


def _weighted_score(features: dict[str, Any]) -> float:
    weights = {
        "time_similarity": 0.23,
        "address_similarity": 0.20,
        "house_number_agreement": 0.12,
        "street_token_overlap": 0.10,
        "grid_agreement": 0.08,
        "agency_agreement": 0.06,
        "station_agreement": 0.04,
        "event_family_agreement": 0.08,
        "event_type_similarity": 0.05,
        "same_source_event_id": 0.02,
        "same_source_case_number": 0.02,
    }
    score = sum(weights[key] * float(features[key]) for key in weights)
    if features["same_source_record_id"]:
        score = max(score, 0.995)
    if features["same_source_event_id"] or features["same_source_case_number"]:
        score = max(score, 0.94)
    return round(min(1.0, max(0.0, score)), 4)


def _identifier_conflict(
    new: DispatchObservation, existing: Iterable[DispatchObservation]
) -> Optional[str]:
    for old in existing:
        features = pair_features(new, old)
        if features["same_source_event_id"]:
            if (
                features["time_difference_minutes"] is not None
                and features["time_difference_minutes"] > DETERMINISTIC_TIME_WINDOW_MINUTES
            ) or features["address_similarity"] < 0.55:
                return "reused_source_event_id"
            # An event identifier is not a permanent incident identifier. Preserve delayed
            # updates when the same agency case number agrees, but require alternate or
            # missing case numbers to share an effectively identical event time. This keeps
            # the Sarasota multi-agency duplicate-row case together without treating a reused
            # shared event ID as one incident merely because its address is unchanged.
            if features["time_difference_minutes"] is not None and features[
                "time_difference_minutes"
            ] > (
                SAME_CASE_EVENT_UPDATE_WINDOW_MINUTES
                if features["same_source_case_number"]
                else ALTERNATE_CASE_EVENT_DUPLICATE_WINDOW_MINUTES
            ):
                return "reused_source_event_id"
        if (
            new.source_case_number
            and old.source_case_number
            and new.source_case_number == old.source_case_number
            and features["agency_agreement"] == 1.0
            and (
                features["address_similarity"] < 0.55
                or (
                    features["time_difference_minutes"] is not None
                    and features["time_difference_minutes"] > DETERMINISTIC_TIME_WINDOW_MINUTES
                )
            )
        ):
            return "reused_source_case_number"
    return None


def _different_reliable_ids(
    new: DispatchObservation, old: DispatchObservation, features: dict[str, Any]
) -> bool:
    # A source event identifier is stronger than an agency-local case number when
    # the rest of the event identity agrees. This handles one dispatch event
    # represented by multiple agency case numbers without weakening the reused-ID
    # guard: materially different event times or locations are rejected above.
    if (
        features["same_source_event_id"]
        and features["address_similarity"] >= 0.98
        and features["event_family_agreement"] >= 0.8
        and (
            features["time_difference_minutes"] is None
            or features["time_difference_minutes"] <= DETERMINISTIC_TIME_WINDOW_MINUTES
        )
    ):
        return False
    same_agency = bool(new.agency and old.agency and new.agency == old.agency)
    if not same_agency:
        return False
    if (
        new.source_case_number
        and old.source_case_number
        and new.source_case_number != old.source_case_number
        and features["address_similarity"] >= 0.8
        and (
            features["time_difference_minutes"] is None
            or features["time_difference_minutes"] <= 180
        )
    ):
        return True
    return False


def cluster_is_consistent(
    new: DispatchObservation, existing: Iterable[DispatchObservation]
) -> tuple[bool, str]:
    observations = list(existing)
    all_observations = observations + [new]
    times = []
    for item in all_observations:
        item_time = utc_datetime(item.event_time)
        if item_time is not None:
            times.append(item_time)
    if times and (max(times) - min(times)).total_seconds() > MAX_CLUSTER_SPAN_HOURS * 3600:
        return False, "cluster time span exceeds the anti-overmerge limit"
    for old in observations:
        features = pair_features(new, old)
        if features["address_similarity"] < 0.35 and features["time_similarity"] > 0.7:
            return False, "near-simultaneous records have incompatible locations"
        conflict = _identifier_conflict(new, [old])
        if conflict:
            return False, f"identifier conflict: {conflict}"
    return True, "cluster remains within time, location, and identifier limits"


def choose_linkage(
    new_observation: DispatchObservation,
    candidates: Iterable[tuple[CanonicalIncident, list[DispatchObservation]]],
) -> LinkageDecision:
    best: Optional[LinkageDecision] = None
    for incident, observations in candidates:
        if not observations:
            continue
        conflict = _identifier_conflict(new_observation, observations)
        pair_results = [(pair_features(new_observation, old), old) for old in observations]
        pair_results.sort(key=lambda item: _weighted_score(item[0]), reverse=True)
        features, reference = pair_results[0]
        score = _weighted_score(features)
        deterministic_reason = None
        if features["same_source_record_id"]:
            deterministic_reason = "exact source record identity"
        elif (
            features["same_source_event_id"]
            and not conflict
            and features["time_similarity"] >= 0.45
            and features["address_similarity"] >= 0.55
        ):
            deterministic_reason = "exact agency event identifier with compatible time and location"
        elif (
            features["same_source_case_number"]
            and not conflict
            and features["time_similarity"] >= 0.45
            and features["address_similarity"] >= 0.55
        ):
            deterministic_reason = "exact agency case number with compatible time and location"
        elif (
            features["address_similarity"] >= 0.98
            and features["time_difference_minutes"] is not None
            and features["time_difference_minutes"] <= DETERMINISTIC_TIME_WINDOW_MINUTES
            and features["event_family_agreement"] >= 0.8
            and not _different_reliable_ids(new_observation, reference, features)
        ):
            deterministic_reason = "exact normalized address within the conservative event window"

        consistent, consistency_reason = cluster_is_consistent(new_observation, observations)
        if (
            conflict
            or not consistent
            or _different_reliable_ids(new_observation, reference, features)
        ):
            decision = "non_match"
            stage = "deterministic_guard"
            confidence_band = "no_match"
            score = min(score, 0.20)
            reason = conflict or "different reliable agency case numbers indicate separate events"
        elif deterministic_reason:
            decision = "match"
            stage = "deterministic"
            confidence_band = "high_confidence"
            score = max(score, 0.94)
            reason = deterministic_reason
        elif score >= MATCH_THRESHOLD and consistent:
            decision = "match"
            stage = "probabilistic"
            confidence_band = "high_confidence"
            reason = "combined time, location, agency, station, grid, and event features exceed the match threshold"
        elif score >= REVIEW_THRESHOLD:
            decision = "possible_match"
            stage = "probabilistic"
            confidence_band = "human_review"
            reason = (
                "combined features are in the human-review band; no automatic merge is permitted"
            )
        else:
            decision = "non_match"
            stage = "probabilistic"
            confidence_band = "no_match"
            reason = "combined features do not meet the review threshold"
        result = LinkageDecision(
            candidate=incident,
            reference_observation=reference,
            decision=decision,
            stage=stage,
            score=score,
            confidence_band=confidence_band,
            features=features,
            explanation={
                "reason": reason,
                "consistency_check": consistency_reason,
                "thresholds": {"match": MATCH_THRESHOLD, "human_review": REVIEW_THRESHOLD},
                "source_fields_used": [
                    "source_record_id",
                    "source_event_id",
                    "source_case_number",
                    "event_time",
                    "original_location",
                    "agency",
                    "station",
                    "grid",
                    "normalized_event_family",
                ],
                "coordinates_available": False,
                "model": "explainable weighted baseline; not machine learning",
            },
        )
        result_is_guard = result.stage == "deterministic_guard"
        best_is_guard = best is not None and best.stage == "deterministic_guard"
        if (
            best is None
            or (result_is_guard and not best_is_guard)
            or (result_is_guard == best_is_guard and result.score > best.score)
        ):
            best = result
    if best is not None:
        return best
    return LinkageDecision(
        candidate=None,
        reference_observation=None,
        decision="new_incident",
        stage="candidate_search",
        score=0.0,
        confidence_band="no_match",
        features={},
        explanation={
            "reason": "no active canonical incident was eligible for comparison",
            "thresholds": {"match": MATCH_THRESHOLD, "human_review": REVIEW_THRESHOLD},
        },
    )
