# Compliance and outreach boundaries

Beyond Fire Radar is an internal research and review tool. It is not a consumer-facing claims or solicitation system.

## Prohibited in the current application

- Automatic email, SMS, phone, robocall, voicemail, social message, or AI voice outreach.
- Claim-filing instructions, automatic claim recommendations, coverage statements, or settlement/payment estimates.
- Language such as “you have covered damage.”
- Automatic contract generation or referral compensation.
- Contacting property owners, occupants, agents, associations, or managers.

## Allowed foundation behavior

- Preserve authorized source records and source terms.
- Show internal reviewers that a record is a possible property loss and not independently verified.
- Record human review labels, suppressions, existing-client status, do-not-contact status, and legal approvals.
- Keep research-only organizational relationships with source, date, verification status, confidence, legal-use category, and last-verified date once those records are added.
- Phase 2 manual snapshot ingestion requires an explicit authorization attestation and retains the raw source bytes for review. Phase 3 processing labels those retrievals `manual_snapshot` and does not treat that label as a legal approval.
- Incident processing accepts `live_poll` only when the Sarasota runtime approval decision passes. Local development may use the exact operator basis `explicit_user_permission`; this is not a legal approval. Production/staging require a persisted approved `LegalApproval`. Manual/fixture processing remains available, and the external-source approval gate is not bypassed.

## Future outreach gate

Any outreach module requires written legal approval, a separate feature flag, approved templates and sender identity, consent/opt-out controls where applicable, time-window enforcement, human approval, and complete logs. No consumer-outreach integration exists in Phase 3.
