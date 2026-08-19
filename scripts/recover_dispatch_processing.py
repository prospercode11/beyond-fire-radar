#!/usr/bin/env python3
"""Recover retained live dispatch snapshots that never reached incident assembly.

The command is dry-run by default. ``--apply`` acquires the provider polling lease,
processes each queued retrieval oldest-first, scores only eligible fire incidents, and
records a recovery audit event for every repaired retrieval.
"""

from __future__ import annotations

import argparse

from app.config import get_settings
from app.providers.polling import (
    BROWARD_PROVIDER_ID,
    MIAMI_DADE_PROVIDER_ID,
    SARASOTA_PROVIDER_ID,
    BrowardPollingService,
    MiamiDadePollingService,
    SarasotaPollingService,
)

SERVICES = {
    SARASOTA_PROVIDER_ID: SarasotaPollingService,
    MIAMI_DADE_PROVIDER_ID: MiamiDadePollingService,
    BROWARD_PROVIDER_ID: BrowardPollingService,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the audited recovery")
    parser.add_argument(
        "--provider-id",
        choices=sorted(SERVICES),
        action="append",
        help="recover only one provider; repeatable",
    )
    args = parser.parse_args()
    settings = get_settings()
    provider_ids = args.provider_id or sorted(SERVICES)
    results = {}
    for provider_id in provider_ids:
        service = SERVICES[provider_id](settings)
        result = service.recover_unprocessed_retrievals(dry_run=not args.apply)
        results[provider_id] = {
            "pending_retrieval_count": result.pending_retrieval_count,
            "pending_observation_count": result.pending_observation_count,
            "recovered_retrieval_ids": list(result.recovered_retrieval_ids),
        }
    print({"dry_run": not args.apply, "providers": results})


if __name__ == "__main__":
    main()
