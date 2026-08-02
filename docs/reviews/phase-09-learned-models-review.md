# Phase 9 independent review — Learned models and learning infrastructure

## Review scope

Independent Luna performed a read-only review of the Phase 9 implementation after remediation. The review covered the learning service, migration-owned schema, routes/schemas, focused tests, execution documents, source/manifest eligibility boundary, and Model Lab UI. Live Sarasota polling, Boca, Broadcastify, outreach, Phase 4/5 changes, and Phase 10 were not in scope.

## Final decision

APPROVED for the inactive local Phase 9 learning-foundation gate.

Reviewer: Pascal/Nietzsche, agent `019fc13c-43c6-7f42-bcb0-041ad3073fd5`.

Final severity counts: Critical 0, High 0, Medium 1 documentation note, Low 0.

The Medium note identified stale pending-review wording in the handoff and missing challenger/check-constraint detail in the data dictionary. Both were corrected in this closure update. No implementation finding remained.

## Remediated findings

The initial independent review identified five High findings. They were fixed and rechecked:

1. Evaluation now records reliability bins and Brier diagnostics, predictive entropy, selective-prediction coverage/abstention/risk, and Wilson risk intervals. The metrics remain directional and `accuracy_claim_allowed=false`.
2. Promotion and rollback use idempotent `model_control_actions`, row locks, a unique champion index, and the allowed-status check constraint introduced by migration `0018_learning_control_actions`.
3. Real-data eligibility validates persisted official Sarasota manual retrievals/imports, imported status, manual attestation, source hashes, recognized acquisition mode, declared providers/modes/authorization/hashes, and excludes fixture/live data.
4. Dataset row generation validates manifest incident membership, score/label incident agreement, score/label/manifest as-of boundaries, and stores per-feature score/source-observation provenance.
5. Training requires `ready` or explicitly mechanics-only `mechanics_ready` snapshots and rejects blocked snapshots. Replay requires matching feature and label contracts.

## Evidence

- Focused Phase 9 suite: 4 passed after remediation, including metric outputs, blocked-snapshot rejection, inactive mechanics training, replay idempotency, drift, fallback policy, and disabled promotion.
- Final repository verification and required migration/API checks are recorded in the Phase 9 handoff.
- Authenticated browser verification displayed the Model Lab fallback posture with learned model inactive and probability display off; desktop and 390×844 mobile checks completed without console warnings/errors or final horizontal overflow.

## Remaining limitations

Real approved outcome labels, held-out improvement over baseline, valid calibration for deployment, improved top-alert precision, complete error analysis, administrator activation, live source approval, production identity/MFA, PostgreSQL/PostGIS, Redis, and production deployment remain open gates. No learned model is active and no real-world accuracy claim is made.
