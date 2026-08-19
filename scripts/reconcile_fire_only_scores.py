#!/usr/bin/env python3
"""Reconcile existing score runs after the fire-only scoring release.

The command never deletes evidence or score history. It recomputes retained incident
classifications, deactivates current non-fire score rows with an audit event, and
releases current fire rows onto the current proximity-aware scoring version.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.audit import record_audit
from app.db import SessionLocal
from app.incidents.service import incident_needs_classification_refresh, rescore_incident
from app.models import CanonicalIncident, OpportunityScoreRun, User
from app.opportunities.scoring import (
    FIRE_SCOREABILITY_VERSION,
    PROPERTY_PROVIDER_BY_DISPATCH_PROVIDER,
    SCORING_VERSION,
    incident_score_eligibility,
    score_incident,
)
from sqlalchemy import select


def reconcile(*, dry_run: bool) -> dict[str, int]:
    with SessionLocal() as db:
        actor = db.scalar(
            select(User).where(User.is_active.is_(True)).order_by(User.created_at, User.id)
        )
        if actor is None and not dry_run:
            raise RuntimeError("an active user is required to write the audited reconciliation")

        reclassified = 0
        active_incidents = list(
            db.scalars(
                select(CanonicalIncident)
                .where(CanonicalIncident.is_active.is_(True))
                .order_by(CanonicalIncident.first_event_time, CanonicalIncident.id)
            ).all()
        )
        for incident in active_incidents:
            if not incident_needs_classification_refresh(db, incident):
                continue
            reclassified += 1
            if not dry_run:
                rescore_incident(
                    db,
                    incident,
                    actor_user_id=actor.id if actor else None,
                    request_id=f"fire-only-classification-reconcile:{incident.id}",
                )

        current_runs = list(
            db.scalars(
                select(OpportunityScoreRun)
                .where(OpportunityScoreRun.is_current.is_(True))
                .order_by(OpportunityScoreRun.created_at, OpportunityScoreRun.id)
            ).all()
        )
        current_run_incident_ids = {run.incident_id for run in current_runs}
        deactivated = 0
        rescored = 0
        retained = 0
        generated = 0
        for run in current_runs:
            incident = db.get(CanonicalIncident, run.incident_id)
            if incident is None:
                continue
            eligible, reason, _ = incident_score_eligibility(db, incident)
            if not eligible:
                deactivated += 1
                if not dry_run:
                    run.is_current = False
                    record_audit(
                        db,
                        action="opportunity.score_deactivated",
                        resource_type="opportunity_score_run",
                        resource_id=run.id,
                        actor_user_id=actor.id if actor else None,
                        request_id=f"fire-only-reconcile:{run.id}",
                        metadata={
                            "reason": reason,
                            "policy_version": FIRE_SCOREABILITY_VERSION,
                            "source_evidence_retained": True,
                        },
                    )
                continue
            if run.scoring_version != SCORING_VERSION:
                rescored += 1
                if not dry_run:
                    score_incident(
                        db,
                        incident,
                        property_provider_id=run.property_provider_id,
                        actor_user_id=actor.id if actor else None,
                    )
            else:
                retained += 1
        for incident in active_incidents:
            if incident.id in current_run_incident_ids:
                continue
            eligible, _, _ = incident_score_eligibility(db, incident)
            if not eligible:
                continue
            generated += 1
            if not dry_run:
                score_incident(
                    db,
                    incident,
                    property_provider_id=PROPERTY_PROVIDER_BY_DISPATCH_PROVIDER.get(
                        incident.provider_id
                    ),
                    actor_user_id=actor.id if actor else None,
                )
        if not dry_run:
            db.commit()
        return {
            "current_runs": len(current_runs),
            "reclassified": reclassified,
            "deactivated": deactivated,
            "rescored": rescored,
            "retained": retained,
            "generated": generated,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args()
    result = reconcile(dry_run=args.dry_run)
    print(
        {"dry_run": args.dry_run, "completed_at": datetime.now(timezone.utc).isoformat(), **result}
    )


if __name__ == "__main__":
    main()
