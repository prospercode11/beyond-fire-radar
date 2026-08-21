from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import SessionToken, User
from app.security import hash_session_token

DbSession = Annotated[Session, Depends(get_db)]


def request_id(request: Request, x_request_id: Annotated[Optional[str], Header()] = None) -> str:
    state_request_id = getattr(request.state, "request_id", None)
    if state_request_id:
        return state_request_id
    if x_request_id and re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", x_request_id):
        return x_request_id
    return str(uuid4())


def get_current_user(
    db: DbSession,
    authorization: Annotated[Optional[str], Header()] = None,
) -> User:
    # Single-operator desktop mode resolves the one local account without a session
    # token, so every route keeps its role checks and every audit record keeps a real
    # actor while the shell drops its sign-in screen. Deliberately ignores any token
    # that was sent, so a stale one cannot lock the operator out of their own install.
    if get_settings().enable_single_operator_mode:
        operator = db.scalar(
            select(User).where(User.is_active.is_(True)).order_by(User.created_at, User.id)
        )
        if operator is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="no local operator account exists",
            )
        return operator
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    token = authorization[7:].strip()
    if not token or len(token) > 512:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    token_hash = hash_session_token(token)
    session = db.scalar(
        select(SessionToken).where(
            SessionToken.token_hash == token_hash,
            SessionToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    settings = get_settings()
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session else now
    last_used_at = (
        session.last_used_at.replace(tzinfo=timezone.utc)
        if session is not None and session.last_used_at is not None
        else None
    )
    idle_expired = (
        last_used_at is not None
        and (now - last_used_at).total_seconds() > settings.session_idle_ttl_hours * 3600
    )
    if session is None or session.replaced_at is not None or expires_at <= now or idle_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired or invalid"
        )
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user inactive")
    session.last_used_at = now
    db.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*role_names: str):
    def dependency(user: CurrentUser) -> User:
        names = {role.name for role in user.roles}
        if not names.intersection(role_names):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return user

    return dependency


AdminUser = Annotated[User, Depends(require_role("administrator"))]
IngestionUser = Annotated[User, Depends(require_role("administrator", "analyst", "researcher"))]
IncidentEditor = Annotated[User, Depends(require_role("administrator", "analyst"))]
PropertyImporter = Annotated[User, Depends(require_role("administrator", "analyst", "researcher"))]
PropertyReviewer = Annotated[
    User, Depends(require_role("administrator", "licensed_adjuster", "analyst"))
]
OpportunityReviewer = Annotated[
    User, Depends(require_role("administrator", "licensed_adjuster", "analyst"))
]
