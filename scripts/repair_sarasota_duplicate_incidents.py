#!/usr/bin/env python3
"""Repair exact Sarasota duplicate incidents while preserving an audit trail.

The normal ingestion path prevents these duplicates. This maintenance command is deliberately
dry-run by default so operators can inspect the deterministic groups before applying a merge.
Only incidents sharing the provider, exact source event identifier, normalized location, and
UTC event timestamp are eligible. Exact timestamps prevent a reused identifier from creating a
transitive merge across separate events at the same address.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.db import SessionLocal  # noqa: E402
from app.incidents.linkage import normalize_location, utc_datetime  # noqa: E402
from app.incidents.service import merge_incidents  # noqa: E402
from app.models import (  # noqa: E402
    CanonicalIncident,
    DispatchObservation,
    IncidentObservationLink,
)


def _observations(db, incident_id: str) -> list[DispatchObservation]:
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
        ).all()
    )


def _duplicate_key(
    provider_id: str, observation: DispatchObservation
) -> tuple[str, str, str, str] | None:
    event_time = utc_datetime(observation.event_time)
    if not observation.source_event_id or event_time is None:
        return None
    return (
        provider_id,
        observation.source_event_id,
        normalize_location(observation.original_location),
        event_time.isoformat(),
    )


def _observations_match_key(
    provider_id: str,
    observations: list[DispatchObservation],
    key: tuple[str, str, str, str],
) -> bool:
    return bool(observations) and all(
        _duplicate_key(provider_id, observation) == key for observation in observations
    )


def _incident_matches_key(db, incident_id: str, key: tuple[str, str, str, str]) -> bool:
    return _observations_match_key(key[0], _observations(db, incident_id), key)


def duplicate_groups(db, provider_id: str) -> list[tuple[tuple[str, str, str, str], list[str]]]:
    groups: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    incidents = db.scalars(
        select(CanonicalIncident)
        .where(
            CanonicalIncident.provider_id == provider_id,
            CanonicalIncident.is_active.is_(True),
        )
        .order_by(CanonicalIncident.created_at, CanonicalIncident.id)
    ).all()
    for incident in incidents:
        for observation in _observations(db, incident.id):
            key = _duplicate_key(provider_id, observation)
            if key is None:
                continue
            groups[key].add(incident.id)
    return sorted(
        (
            key,
            sorted(incident_ids),
        )
        for key, incident_ids in groups.items()
        if len(incident_ids) > 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-id",
        default="sarasota.official_dispatch",
        help="Provider whose active canonical incidents should be checked.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deterministic merges. Without this flag the command is read-only.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        groups = duplicate_groups(db, args.provider_id)
        if not groups:
            print(f"No exact duplicate groups found for {args.provider_id}.")
            return 0
        for key, incident_ids in groups:
            print(f"duplicate key={key[1:]} incidents={','.join(incident_ids)}")
        if not args.apply:
            print("Dry run only. Re-run with --apply to record audited merges.")
            return 0

        merged = 0
        for key, incident_ids in groups:
            active = [db.get(CanonicalIncident, incident_id) for incident_id in incident_ids]
            active = [
                incident for incident in active if incident is not None and incident.is_active
            ]
            if len(active) < 2:
                continue
            active.sort(key=lambda incident: (incident.created_at, incident.id))
            survivor = active[0]
            for absorbed in active[1:]:
                # Groups are computed before applying any merge. Revalidate the complete
                # observation sets so overlapping keys such as A/B and B/C cannot turn into
                # a transitive A/B/C merge.
                if not _incident_matches_key(db, survivor.id, key) or not _incident_matches_key(
                    db, absorbed.id, key
                ):
                    print(
                        f"skipped overlapping group key={key[1:]} "
                        f"survivor={survivor.id} absorbed={absorbed.id}"
                    )
                    continue
                merge_incidents(
                    db,
                    survivor,
                    absorbed,
                    reason=(
                        "Deterministic Sarasota duplicate repair: exact source event ID, "
                        "normalized location, and UTC event timestamp; source rows retained."
                    ),
                    actor_user_id=None,
                    request_id=f"sarasota-duplicate-repair:{survivor.id}:{absorbed.id}",
                )
                merged += 1
        db.commit()
        print(f"Applied {merged} audited merge(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
