# External activation checklist

This checklist is a hard gate, not an approval record. Empty or unchecked items must keep the corresponding integration disabled.

- [ ] Written Sarasota dispatch authorization, access terms, retention terms, and responsible owner recorded in `legal_approvals`.
- [ ] Approved manual snapshot is attached with source, retrieval time, hash, authorization basis, and acquisition mode `manual_snapshot`.
- [ ] Any live polling proposal is separately reviewed for terms, rate limits, authentication, CAPTCHA, and privacy; no bypass is permitted.
- [ ] Sarasota property-source approval/terms and an approved real snapshot are recorded before official property data is used.
- [ ] PostgreSQL/PostGIS, Redis, object storage, TLS, backups, and access controls are provisioned and tested in an isolated staging environment.
- [ ] Human reviewer identity, role, outcome-label policy, retention, and correction process are approved.
- [ ] Real held-out evaluation data, leakage checks, calibration, error analysis, and model release approval exist before learned serving is enabled.
- [ ] Any external notification or outreach proposal has separate legal/product approval; consumer outreach remains prohibited in v1.

Current repository posture: Sarasota live polling is false, learned serving is false, official property automation is disabled, and no approval is inferred from fixture or manually uploaded data.
