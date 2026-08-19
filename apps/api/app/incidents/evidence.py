from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.incidents.linkage import normalize_location, utc_datetime
from app.models import DispatchObservation

EVIDENCE_GROUPING_VERSION = "dispatch-evidence-grouping.v1"


@dataclass(frozen=True)
class ObservationEvidenceGroup:
    fingerprint: tuple[str, ...]
    observations: tuple[DispatchObservation, ...]

    @property
    def representative(self) -> DispatchObservation:
        return min(
            self.observations,
            key=lambda item: (
                utc_datetime(item.retrieved_at) or datetime.max.replace(tzinfo=timezone.utc),
                item.id,
            ),
        )

    @property
    def source_record_ids(self) -> list[str]:
        return sorted(
            {item.source_record_id for item in self.observations if item.source_record_id}
        )

    @property
    def source_snapshot_ids(self) -> list[str]:
        return sorted({item.raw_snapshot_id for item in self.observations})

    @property
    def first_retrieved_at(self) -> datetime:
        return min(item.retrieved_at for item in self.observations)

    @property
    def last_retrieved_at(self) -> datetime:
        return max(item.retrieved_at for item in self.observations)


def observation_evidence_fingerprint(observation: DispatchObservation) -> tuple[str, ...]:
    """Identify one source event across repeated unchanged captures.

    Event time, source event identity, source wording, taxonomy family, and normalized
    location are part of the key so a later update or reused identifier stays separate.
    """

    identity_kind = "source_event_id" if observation.source_event_id else "source_record_id"
    identity = observation.source_event_id or observation.source_record_id
    event_time = utc_datetime(observation.event_time)
    return (
        observation.provider_id,
        identity_kind,
        identity,
        event_time.isoformat() if event_time else "",
        " ".join((observation.original_event_type or "").upper().split()),
        observation.normalized_event_family or "",
        normalize_location(observation.original_location),
    )


def group_observations(
    observations: Iterable[DispatchObservation],
) -> list[ObservationEvidenceGroup]:
    grouped: dict[tuple[str, ...], list[DispatchObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation_evidence_fingerprint(observation), []).append(observation)
    return [
        ObservationEvidenceGroup(fingerprint=fingerprint, observations=tuple(items))
        for fingerprint, items in grouped.items()
    ]


def representative_observations(
    observations: Iterable[DispatchObservation],
) -> list[DispatchObservation]:
    return [group.representative for group in group_observations(observations)]


def current_contradiction_count(observations: Iterable[DispatchObservation]) -> int:
    """Count contradictions in the current evidence projection, not its retained history."""

    items = list(observations)
    count = int(len({item.normalized_event_family for item in items}) > 1)
    observations_by_event_id: dict[str, list[DispatchObservation]] = {}
    for item in items:
        if item.source_event_id:
            observations_by_event_id.setdefault(item.source_event_id, []).append(item)
    for same_identifier_items in observations_by_event_id.values():
        if len(same_identifier_items) < 2:
            continue
        times = [
            timestamp
            for item in same_identifier_items
            if (timestamp := utc_datetime(item.event_time) or utc_datetime(item.retrieved_at))
            is not None
        ]
        locations = {normalize_location(item.original_location) for item in same_identifier_items}
        time_conflict = bool(times) and max(times) - min(times) > timedelta(minutes=90)
        if time_conflict or len(locations) > 1:
            count += 1
    return count
