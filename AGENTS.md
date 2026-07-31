# Repository operating rules

These rules are mandatory for Beyond Fire Radar.

1. Inspect existing code before adding a new abstraction.
2. Never claim a feature works without running its verification command.
3. Run formatting, linting, type checking, unit tests, integration tests, and relevant end-to-end tests after substantive changes.
4. Do not continue when a required verification command fails.
5. Do not make up API endpoints, data fields, permissions, credentials, model accuracy, or source licenses.
6. Never use synthetic records as evidence of real-world model accuracy.
7. Store deterministic mechanics in code and scripts, not in prompts.
8. Keep model features versioned.
9. Keep source provenance for every derived fact.
10. Keep the application runnable after every phase.
11. Record known limitations plainly.
12. Do not leave essential functionality as TODO comments.
13. Do not implement automatic consumer outreach.
14. Do not infer insurance coverage or claim validity.
15. Prefer precision and abstention over excessive alerts.
16. Never merge a phase until its acceptance gate passes.
17. Use migration files for database changes.
18. Use feature flags for incomplete or legally gated integrations.
19. Every model release must be reproducible and reversible.
20. Every export, suppression, assignment, model deployment, and status transition must be audited.

## Verification contract

From the repository root, a substantive change is complete only when these commands have been run and their results recorded in the handoff/current-state documents:

```bash
./scripts/verify.sh
python scripts/dev.py migrate
python scripts/dev.py api-smoke
```

The first command runs Python formatting/lint/type/test checks and the Next.js production build. Integration tests that require PostgreSQL/PostGIS or Redis must be clearly marked and may only be skipped when the service is unavailable; a skipped external integration is not a passed production verification.

## Scope boundary

Phase 1 contains governance and runtime foundations only. Do not add dispatch parsing, property resolution, learned models, dashboard workflows, notifications, or outreach in this phase. Future work must use the phase gate in `docs/execution/master-checklist.md`.
