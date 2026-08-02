# Known limitations at v1 closure

- Docker/Colima is unavailable on the implementation host. PostgreSQL/PostGIS and Redis integration tests, managed backup, and real R2 behavior are not claimed as executed.
- No written Sarasota dispatch or property-source approval artifact, production credential, license determination, or legal permission was supplied. Sarasota imports remain manual/file/fixture/replay workflows and live polling remains disabled.
- Repository CSV/JSON/HTML/XLSX/ZIP fixtures are mechanics-only evidence. They do not establish real-world parser coverage, incident classification accuracy, property-match accuracy, scoring quality, calibration, or conversion.
- Production SSO/MFA, enterprise provisioning, secret rotation, external error-tracking hookup, and an operator-owned access review remain deployment gates.
- The Python dependency scan has an exact-ID review list for advisories whose fixes were not available on the current package index or whose affected code path is not used. Re-run the scan before deployment and fail on any new advisory.
- The current local rate limiter is bounded and suitable only for development; production requires Redis readiness.
- The current notification queue is internal and synchronous; no external delivery or consumer outreach exists.
- RPO/RTO, throughput, browser support beyond the inspected Chromium-like environment, and managed-service cost are deployment measurements, not repository claims.
- Error tracking is an integration point (`ERROR_TRACKING_DSN`), not a configured external account.
