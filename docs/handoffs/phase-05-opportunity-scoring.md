# Phase 5 handoff — Transparent opportunity-scoring foundation

Date: 2026-08-01
Status: complete for the local/manual prototype gate
Commit: recorded after final verification

## Delivered

Phase 5 adds a governed, explainable ranking foundation over Sarasota incident and manually/file imported property evidence already present in the repository. It does not add a source, live polling, property automation, learned model, dashboard, notification, outreach, or insurance/claim inference.

- Migration-owned scoring releases, score runs, feature records, human overrides, explicit as-of boundaries, predecessor history, and temporal incident-link intervals.
- Separately versioned source quality, incident validity, property-match quality, material-loss evidence, loss complexity, Beyond Adjusting fit, freshness, and data-sufficiency components.
- A weighted-geometric provisional rank with missing-data penalties, negative/contradictory/property hard gates, evidence tiers, human-review bands, abstention, and feature-level explanations.
- Authenticated APIs for score, list, rescore, release registration, override, and rollback operations.
- Source observation IDs, property source-row lineage, available-at timestamps, transformations, scoring release, as-of time, and alert eligibility rationale on every score run.
- Alert eligibility remains fail-closed: synthetic fixture and live/unauthorized sources cannot produce operational alerts; explicitly authorized manual snapshots still require resolved property evidence, no hard contradiction/negative gate, and fit evidence.
- Contract-only temporal/grouped evaluation artifacts and adversarial scoring tests. No accuracy or calibration claim is made.

## Verification evidence

From the repository root:

```text
./scripts/verify.sh                                  PASS
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate PASS
clean isolated API: python scripts/dev.py api-smoke   PASS
```

The API smoke was run against a fresh SQLite database and raw-snapshot directory so prior local legacy data could not change the provenance result. It verified health/live-polling-disabled state, bootstrap/login, provider access, synthetic fixture labeling, incident processing, replay, and no duplicate canonical incidents.

The migration round-trip used a fresh SQLite database and upgraded to `0011_temporal_incident_links`, downgraded to `0010_scoring_asof_predecessor`, and upgraded to `0011` again. PostgreSQL/PostGIS/Redis integration could not run because Docker/Colima is unavailable on the host.

The scoring contract evaluator passed the grouped/temporal availability checks and reported `accuracy_claim_allowed=false`; the manifest is a contract fixture, not real-world accuracy evidence.

## Independent review

The independent Luna review at `docs/reviews/phase-05-opportunity-scoring-review.md` completed after all critical/high findings were fixed. The final review found no critical or high-severity implementation findings.

## External and product boundaries

- Sarasota live polling remains disabled.
- The external-source approval gate remains intact; manual/file and synthetic acquisition modes are explicitly distinguished from live-collected data.
- Official Sarasota property approval/terms and a real approved property snapshot remain open.
- No Boca, Broadcastify, consumer outreach, final dashboard, learned model, probability, calibration, damage, coverage, or claim-validity conclusion was added.

## Next controlled step

Phase 6 may begin only after this handoff is accepted. Phase 6 must preserve the Phase 5 provenance, abstention, and no-outreach boundaries and must not activate live Sarasota polling or official property automation.
