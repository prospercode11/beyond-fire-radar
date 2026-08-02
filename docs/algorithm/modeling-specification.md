# Modeling specification

## Cold-start rule

Phase 0/1 implements no predictive model and displays no arbitrary probability. Synthetic fixtures are for pipeline and failure testing only. They must never support an accuracy claim.

## Planned layered system

The future modeling system is a set of independently versioned components:

1. Source Quality
2. Incident Validity
3. Property Match
4. Material Loss
5. Loss Complexity
6. Beyond Adjusting Fit
7. Data Sufficiency
8. Opportunity Ranking
9. Selective Alerting Policy

Conversion analytics is a later, separate layer and cannot be used as a proxy for physical damage.

## Required contract for every model

Each model release must specify its target, feature contract, `available_at` behavior, missing-data behavior, training dataset manifest, version, calibration method, uncertainty method, explanation output, threshold, approval, and rollback artifact. Time-based and grouped validation are mandatory; future source updates and reviewer outcomes must not leak into earlier predictions.

## Phase 5 ranking policy

The Phase 5 baseline is an explicitly versioned weighted geometric mean over source quality, incident validity, property-match quality, material-loss evidence, loss complexity, Beyond Adjusting fit, and data sufficiency, with a freshness feature recorded separately. It is called a provisional ranking/evidence tier, not an empirical probability. Alerts must abstain when critical evidence is missing, a property match is unresolved, negative/contradictory evidence remains, the source gate is not an authorized manual snapshot, or fit evidence is unavailable. Every score carries an as-of boundary, feature versions, available-at timestamps, source observations, transformations, and explanation. Human overrides are append-only and cannot rewrite the baseline.

The release registry is authoritative for scoring priors, rule terms, component versions, and the explicit `probability_display=false` invariant. A release can be registered only with all components, non-negative priors summing to one, and no probability display. Score history records the explicit predecessor used for rollback. Historical scoring selects incident assignments, classifications, contradictions, property source rows, and other evidence using effective timestamps at the as-of boundary. The current implementation is a cold-start expert-prior contract; it does not claim accuracy, calibration, damage, insurance coverage, claim validity, or contact eligibility.

## Acceptance criteria for future model deployment

Deployment requires real labeled outcomes, held-out calibration, precision-at-K measurement, leakage checks, subgroup/error analysis, reproducibility, human administrator approval, and rollback. The desired pilot target of 80% Elite immediate-review usefulness and 95% Elite parcel accuracy is a measured target, not a current result.
