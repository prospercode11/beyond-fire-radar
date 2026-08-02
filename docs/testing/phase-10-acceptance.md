# Phase 10 acceptance evidence

## Automated checks

| Area | Required evidence |
| --- | --- |
| Format/lint/types/tests/build | `./scripts/verify.sh` |
| Migration | `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate`; isolated upgrade, downgrade one revision, and re-upgrade |
| API smoke | clean isolated API plus `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py api-smoke` |
| Dependency scan | `./scripts/dependency_audit.sh`; exact advisory review is in `docs/security/dependency-audit.md` |
| Security | security headers, trusted hosts, production-setting rejection, RBAC/session checks, upload/archive limits, audit tamper detection |
| Operational | concurrent limiter, latency budget, object-storage tamper injection, backup verify/restore, readiness/metrics/operations routes |
| Data replay | Sarasota fixture/manual mechanics import, process, replay, and canonical-incident count equality |
| Browser | authenticated desktop/mobile views, keyboard/focus, error/empty/loading states, no horizontal overflow |

## Required E2E posture

The final E2E uses only repository mechanics fixtures or explicitly labeled manual prototype inputs. It verifies bootstrap/login, source-mode visibility, import/process/replay, canonical incidents/timelines/classification/linkage explanations, property import/match abstention and human review, scoring explanation, internal workflow/outcome/analytics/audit surfaces, RBAC, and degraded dependency behavior. It must not be interpreted as real-world accuracy or legal approval.

## Acceptance boundary

The gate closes with no unresolved critical/high finding, but remains a local/staging readiness gate until managed PostgreSQL/PostGIS, Redis, object storage, identity/MFA, source approvals, domain/TLS, and operator-owned recovery exercises are completed.
