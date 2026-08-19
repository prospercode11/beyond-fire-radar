from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import LegalApproval

LIVE_SARASOTA_APPROVAL_SUBJECT = "sarasota.dispatch.live_polling"
LIVE_MIAMI_DADE_APPROVAL_SUBJECT = "miami_dade.fire_calls.live_polling"
LIVE_BROWARD_APPROVAL_SUBJECT = "broward.efirstalert_dispatch.live_polling"
LOCAL_USER_AUTHORIZATION_BASIS = "explicit_user_permission"


@dataclass(frozen=True)
class LivePollingDecision:
    allowed: bool
    authorization_basis: Optional[str]
    reason: str


def live_polling_decision(
    db: Session, settings: Settings, provider_id: str = "sarasota.official_dispatch"
) -> LivePollingDecision:
    source = {
        "sarasota.official_dispatch": (
            settings.enable_live_sarasota_dispatch_polling,
            settings.sarasota_live_authorization_basis,
            LIVE_SARASOTA_APPROVAL_SUBJECT,
            "Sarasota",
        ),
        "miami_dade.fire_calls": (
            settings.enable_live_miami_dade_dispatch_polling,
            settings.miami_dade_live_authorization_basis,
            LIVE_MIAMI_DADE_APPROVAL_SUBJECT,
            "Miami-Dade",
        ),
        "broward.efirstalert_dispatch": (
            settings.enable_live_broward_dispatch_polling,
            settings.broward_live_authorization_basis,
            LIVE_BROWARD_APPROVAL_SUBJECT,
            "Broward eFirstAlert",
        ),
    }.get(provider_id)
    if source is None:
        return LivePollingDecision(False, None, f"live polling is not configured for {provider_id}")
    enabled, local_authorization_basis, approval_subject, county_label = source
    if not enabled:
        return LivePollingDecision(
            False, None, f"live {county_label} polling feature flag is disabled"
        )

    if (
        settings.app_env.lower() in {"development", "desktop"}
        and (local_authorization_basis) == LOCAL_USER_AUTHORIZATION_BASIS
    ):
        return LivePollingDecision(
            True,
            LOCAL_USER_AUTHORIZATION_BASIS,
            "local polling was explicitly enabled by the operator; this is not a legal approval record",
        )

    approval = db.scalar(
        select(LegalApproval)
        .where(
            LegalApproval.subject == approval_subject,
            LegalApproval.status == "approved",
            LegalApproval.approved_at.is_not(None),
        )
        .order_by(LegalApproval.approved_at.desc(), LegalApproval.id.desc())
    )
    if approval is None:
        return LivePollingDecision(
            False,
            None,
            f"live {county_label} polling requires a recorded LegalApproval with status approved and approved_at",
        )
    return LivePollingDecision(
        True,
        f"legal_approval:{approval.id}",
        "live polling is authorized by a recorded LegalApproval",
    )


def live_polling_is_authorized(
    db: Session, settings: Settings, provider_id: str = "sarasota.official_dispatch"
) -> bool:
    return live_polling_decision(db, settings, provider_id).allowed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
