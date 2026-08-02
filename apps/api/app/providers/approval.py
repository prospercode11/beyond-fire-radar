from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import LegalApproval

LIVE_SARASOTA_APPROVAL_SUBJECT = "sarasota.dispatch.live_polling"
LOCAL_USER_AUTHORIZATION_BASIS = "explicit_user_permission"


@dataclass(frozen=True)
class LivePollingDecision:
    allowed: bool
    authorization_basis: Optional[str]
    reason: str


def live_polling_decision(db: Session, settings: Settings) -> LivePollingDecision:
    if not settings.enable_live_sarasota_dispatch_polling:
        return LivePollingDecision(False, None, "live Sarasota polling feature flag is disabled")

    if (
        settings.app_env.lower() == "development"
        and settings.sarasota_live_authorization_basis == LOCAL_USER_AUTHORIZATION_BASIS
    ):
        return LivePollingDecision(
            True,
            LOCAL_USER_AUTHORIZATION_BASIS,
            "development polling was explicitly enabled by the operator; this is not a legal approval record",
        )

    approval = db.scalar(
        select(LegalApproval)
        .where(
            LegalApproval.subject == LIVE_SARASOTA_APPROVAL_SUBJECT,
            LegalApproval.status == "approved",
            LegalApproval.approved_at.is_not(None),
        )
        .order_by(LegalApproval.approved_at.desc(), LegalApproval.id.desc())
    )
    if approval is None:
        return LivePollingDecision(
            False,
            None,
            "live Sarasota polling requires a recorded LegalApproval with status approved and approved_at",
        )
    return LivePollingDecision(
        True,
        f"legal_approval:{approval.id}",
        "live polling is authorized by a recorded LegalApproval",
    )


def live_polling_is_authorized(db: Session, settings: Settings) -> bool:
    return live_polling_decision(db, settings).allowed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
