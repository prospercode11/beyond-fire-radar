from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SessionToken, User
from app.security import hash_session_token

DbSession = Annotated[Session, Depends(get_db)]


def request_id(x_request_id: Annotated[Optional[str], Header()] = None) -> str:
    return x_request_id or str(uuid4())


def get_current_user(
    db: DbSession,
    authorization: Annotated[Optional[str], Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    token_hash = hash_session_token(authorization[7:].strip())
    session = db.scalar(
        select(SessionToken).where(
            SessionToken.token_hash == token_hash,
            SessionToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    if session is None or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired or invalid"
        )
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user inactive")
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
