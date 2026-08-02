from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select

from app.audit import record_audit
from app.config import get_settings
from app.dependencies import CurrentUser, DbSession, request_id
from app.models import Role, SessionToken, User
from app.schemas import BootstrapStatus, Credentials, TokenResponse, UserResponse
from app.security import hash_password, new_session_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
DEFAULT_ROLES = {
    "administrator": "Can manage users, providers, configuration, and audit access.",
    "licensed_adjuster": "Can perform licensed internal review workflows.",
    "analyst": "Can analyze source and opportunity data.",
    "researcher": "Can research and annotate records without outreach.",
    "read_only_reviewer": "Can read permitted records without changing them.",
}


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=sorted(role.name for role in user.roles),
    )


def _create_session(db: DbSession, user: User) -> TokenResponse:
    raw_token, token_hash = new_session_token()
    now = datetime.now(timezone.utc)
    settings = get_settings()
    expires_at = now + timedelta(hours=settings.session_ttl_hours)
    active_sessions = list(
        db.scalars(
            select(SessionToken)
            .where(SessionToken.user_id == user.id, SessionToken.revoked_at.is_(None))
            .order_by(SessionToken.created_at, SessionToken.id)
        ).all()
    )
    while len(active_sessions) >= settings.max_active_sessions:
        oldest = active_sessions.pop(0)
        oldest.revoked_at = now
        oldest.replaced_at = now
    db.add(
        SessionToken(
            id=str(uuid4()),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
            last_used_at=now,
        )
    )
    return TokenResponse(access_token=raw_token, expires_at=expires_at, user=_user_response(user))


@router.get("/bootstrap/status", response_model=BootstrapStatus)
def bootstrap_status(db: DbSession) -> BootstrapStatus:
    count = db.scalar(select(func.count()).select_from(User)) or 0
    return BootstrapStatus(
        user_count=count, available=count == 0 and get_settings().enable_bootstrap
    )


@router.post("/bootstrap", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def bootstrap(
    credentials: Credentials, db: DbSession, rid: str = Depends(request_id)
) -> TokenResponse:
    if not get_settings().enable_bootstrap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bootstrap is disabled")
    count = db.scalar(select(func.count()).select_from(User)) or 0
    settings = get_settings()
    if count != 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="bootstrap is already closed"
        )
    if credentials.email.lower() != settings.bootstrap_admin_email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="bootstrap email is not configured"
        )
    if credentials.password != settings.bootstrap_admin_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="bootstrap password is not configured"
        )

    roles = []
    for name, description in DEFAULT_ROLES.items():
        role = Role(id=str(uuid4()), name=name, description=description)
        db.add(role)
        roles.append(role)
    user = User(
        id=str(uuid4()),
        email=credentials.email.lower(),
        display_name=credentials.email.split("@", 1)[0],
        password_hash=hash_password(credentials.password),
    )
    user.roles = roles
    db.add(user)
    db.flush()
    record_audit(
        db,
        action="auth.bootstrap",
        resource_type="user",
        resource_id=user.id,
        actor_user_id=user.id,
        request_id=rid,
        metadata={"role_count": len(roles)},
    )
    result = _create_session(db, user)
    db.commit()
    return result


@router.post("/login", response_model=TokenResponse)
def login(credentials: Credentials, db: DbSession, rid: str = Depends(request_id)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == credentials.email.lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(credentials.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    result = _create_session(db, user)
    record_audit(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        actor_user_id=user.id,
        request_id=rid,
    )
    db.commit()
    return result


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return _user_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: CurrentUser,
    db: DbSession,
    authorization: Optional[str] = Header(default=None),
    rid: str = Depends(request_id),
) -> None:
    token_hash = None
    if authorization and authorization.startswith("Bearer "):
        from app.security import hash_session_token

        token_hash = hash_session_token(authorization[7:].strip())
    session = db.scalar(
        select(SessionToken).where(
            SessionToken.token_hash == token_hash, SessionToken.user_id == user.id
        )
    )
    if session is not None:
        session.revoked_at = datetime.now(timezone.utc)
    record_audit(
        db,
        action="auth.logout_requested",
        resource_type="user",
        resource_id=user.id,
        actor_user_id=user.id,
        request_id=rid,
        metadata={"token_revoked": session is not None},
    )
    db.commit()
