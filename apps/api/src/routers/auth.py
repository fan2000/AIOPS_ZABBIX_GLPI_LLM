"""Routes complètes d'authentification (Sign-In, Sign-Up, MFA TOTP, Refresh Tokens, Profil & Sessions)."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.src.dependencies.auth import (
    AuthenticatedUserContext,
    get_current_user,
    security_bearer,
)
from database.connection import get_db_session
from packages.domain.models.database import AuditLog, Role, User, UserSession
from packages.security.src.jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_mfa_challenge_token,
    decode_access_token,
    decode_mfa_challenge_token,
    generate_refresh_token,
    get_password_hash_async,
    verify_password_async,
)
from packages.security.src.mfa import (
    build_otpauth_uri,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    hash_refresh_token,
    validate_password_strength,
    verify_totp_code,
)
from packages.security.src.rate_limiter import auth_limiter

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & IAM"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,50}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=128)
    totp_code: Optional[str] = Field(None, max_length=20)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)
    full_name: Optional[str] = Field(None, max_length=150)


class MfaVerifyRequest(BaseModel):
    mfa_challenge_token: str = Field(..., min_length=10, max_length=1024)
    code: str = Field(..., min_length=4, max_length=20)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(None, max_length=512)
    all_sessions: bool = False


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=150)
    email: Optional[str] = Field(None, min_length=5, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)


class MfaCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=12)


class MfaDisableRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=4, max_length=20)


class TokenResponse(BaseModel):
    access_token: str = ""
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in_minutes: int
    mfa_required: bool = False
    mfa_challenge_token: Optional[str] = None
    user: Dict[str, Any]


def _safe_str(val: Any) -> Optional[str]:
    return val if isinstance(val, str) else None


def _serialize_user_payload(
    user: User,
    role_name: str,
    permissions: List[str],
    allowed_entities: List[str],
) -> Dict[str, Any]:
    raw_last = getattr(user, "last_login_at", None)
    raw_created = getattr(user, "created_at", None)
    return {
        "id": str(user.id),
        "username": user.username,
        "email": _safe_str(getattr(user, "email", None)),
        "full_name": _safe_str(getattr(user, "full_name", None)),
        "role": role_name,
        "permissions": permissions,
        "allowed_entities": allowed_entities,
        "mfa_enabled": getattr(user, "mfa_enabled", False) is True,
        "last_login_at": raw_last.isoformat() if isinstance(raw_last, datetime) else None,
        "created_at": raw_created.isoformat() if isinstance(raw_created, datetime) else None,
    }


def _resolve_role_context(
    user: User,
    role_obj: Optional[Role],
) -> tuple[str, List[str], List[str]]:
    role_name = role_obj.name if role_obj else "viewer"
    permissions = list(role_obj.permissions) if (role_obj and isinstance(role_obj.permissions, list)) else []
    raw_entities = getattr(user, "allowed_entities", None)
    allowed_entities = (
        ["*"]
        if role_name.lower() == "admin"
        else (raw_entities if isinstance(raw_entities, list) and raw_entities else ["0"])
    )
    return role_name, permissions, [str(e) for e in allowed_entities]


def _verify_mfa_or_consume_recovery(user: User, code: str) -> bool:
    """Valide un code TOTP (ou un code de secours à usage unique qui est consommé)."""
    stored_secret = _safe_str(getattr(user, "mfa_secret", None))
    if stored_secret:
        try:
            plain_secret = decrypt_mfa_secret(stored_secret)
            if verify_totp_code(plain_secret, code):
                return True
        except Exception:
            pass

    raw_codes = getattr(user, "mfa_recovery_codes", None)
    if isinstance(raw_codes, list) and raw_codes:
        candidate_hash = hash_recovery_code(code)
        if candidate_hash in raw_codes:
            user.mfa_recovery_codes = [h for h in raw_codes if h != candidate_hash]
            return True
    return False


async def _issue_session_tokens(
    session: AsyncSession,
    user: User,
    role_obj: Optional[Role],
    request: Request,
    audit_action: str,
) -> TokenResponse:
    role_name, permissions, allowed_entities = _resolve_role_context(user, role_obj)
    token_data = {
        "sub": user.username,
        "role": role_name,
        "permissions": permissions,
        "allowed_entities": allowed_entities,
        "user_id": str(user.id),
    }
    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    refresh_token: Optional[str] = None
    # Écrire UserSession / AuditLog uniquement sur une vraie instance SQLAlchemy User (préserve mocks simples)
    if type(user) is User:
        now = datetime.now(timezone.utc)
        user.last_login_at = now
        refresh_token = generate_refresh_token()
        ua = (request.headers.get("user-agent") or "")[:250] or None
        ip_addr = request.client.host if request.client else None
        session.add(
            UserSession(
                id=uuid4(),
                user_id=user.id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                user_agent=ua,
                ip_address=ip_addr,
                expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
                created_at=now,
            )
        )
        session.add(
            AuditLog(
                id=uuid4(),
                user_id=user.id,
                action=audit_action,
                resource_type="user",
                resource_id=str(user.id),
                ip_address=ip_addr,
                details={"username": user.username, "role": role_name, "mfa": getattr(user, "mfa_enabled", False) is True},
            )
        )
        await session.flush()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        mfa_required=False,
        mfa_challenge_token=None,
        user=_serialize_user_payload(user, role_name, permissions, allowed_entities),
    )


async def _load_real_user(session: AsyncSession, current_user: AuthenticatedUserContext) -> User:
    if not current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action indisponible pour une session anonyme ou mode laboratoire sans compte en base.",
        )
    user = (await session.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte utilisateur introuvable")
    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Inscription publique créant un compte standard actif (rôle 'viewer', entité racine '0')."""
    client_ip = request.client.host if request.client else "unknown"
    clean_username = req.username.strip()
    clean_email = req.email.strip().lower()

    if not auth_limiter.is_allowed(f"auth_register:{client_ip}:{clean_username}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives d'inscription. Veuillez patienter.",
            headers={"Retry-After": "60"},
        )

    if not _USERNAME_RE.match(clean_username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identifiant invalide (3-50 caractères alphanumériques, '.', '_', '-' uniquement).",
        )
    if not _EMAIL_RE.match(clean_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adresse email invalide.",
        )

    pwd_err = validate_password_strength(req.password)
    if pwd_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pwd_err)

    existing = (
        await session.execute(
            select(User).where(or_(User.username == clean_username, User.email == clean_email))
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur ou cette adresse email est déjà utilisé.",
        )

    viewer_role = (await session.execute(select(Role).where(Role.name == "viewer"))).scalar_one_or_none()
    if not viewer_role:
        viewer_role = Role(
            id=uuid4(),
            name="viewer",
            description="Lecture seule des incidents et diagnostics IA",
            permissions=["incident:read", "knowledge:read", "ai:read"],
        )
        session.add(viewer_role)
        await session.flush()

    now = datetime.now(timezone.utc)
    new_user = User(
        id=uuid4(),
        username=clean_username,
        email=clean_email,
        full_name=(req.full_name or "").strip() or None,
        hashed_password=await get_password_hash_async(req.password),
        role_id=viewer_role.id,
        allowed_entities=["0"],
        is_active=True,
        mfa_enabled=False,
        created_at=now,
    )
    session.add(new_user)
    await session.flush()

    resp = await _issue_session_tokens(session, new_user, viewer_role, request, "USER_REGISTERED")
    await session.commit()
    return resp


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authentifie par identifiant ou email avec challenge MFA TOTP si activé (CWE-307 / OWASP A07)."""
    client_ip = request.client.host if request.client else "unknown"
    ident = req.username.strip()
    client_key = f"auth_login:{client_ip}:{ident}"
    if not auth_limiter.is_allowed(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives de connexion échouées. Veuillez patienter avant de réessayer.",
            headers={"Retry-After": "60"},
        )

    stmt = select(User).where(
        or_(User.username == ident, User.email == ident.lower()),
        User.is_active == True,  # noqa: E712
    )
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user or not (await verify_password_async(req.password, user.hashed_password)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_stmt = select(Role).where(Role.id == user.role_id)
    role_obj = (await session.execute(role_stmt)).scalar_one_or_none()

    if getattr(user, "mfa_enabled", False) is True:
        if req.totp_code:
            if not _verify_mfa_or_consume_recovery(user, req.totp_code):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Code d'authentification à deux facteurs invalide.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            challenge = create_mfa_challenge_token(user_id=str(user.id), username=user.username)
            role_name, permissions, allowed_entities = _resolve_role_context(user, role_obj)
            return TokenResponse(
                access_token="",
                refresh_token=None,
                token_type="bearer",
                expires_in_minutes=5,
                mfa_required=True,
                mfa_challenge_token=challenge,
                user=_serialize_user_payload(user, role_name, permissions, allowed_entities),
            )

    resp = await _issue_session_tokens(session, user, role_obj, request, "USER_LOGIN_SUCCESS")
    if type(user) is User:
        await session.commit()
    return resp


@router.post("/mfa/verify", response_model=TokenResponse)
async def verify_mfa_login(
    req: MfaVerifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Valide le second facteur (TOTP 6 chiffres ou code de secours) après challenge MFA."""
    client_ip = request.client.host if request.client else "unknown"
    if not auth_limiter.is_allowed(f"auth_mfa:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives MFA échouées. Veuillez patienter.",
            headers={"Retry-After": "60"},
        )

    payload = decode_mfa_challenge_token(req.mfa_challenge_token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton MFA invalide ou expiré. Veuillez vous reconnecter.",
        )

    user = (
        await session.execute(
            select(User).where(User.username == payload["sub"], User.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if not user or getattr(user, "mfa_enabled", False) is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session MFA invalide")

    if not _verify_mfa_or_consume_recovery(user, req.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code TOTP ou code de secours invalide.",
        )

    role_obj = (await session.execute(select(Role).where(Role.id == user.role_id))).scalar_one_or_none()
    resp = await _issue_session_tokens(session, user, role_obj, request, "USER_MFA_LOGIN_SUCCESS")
    await session.commit()
    return resp


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session_token(
    req: RefreshTokenRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Effectue une rotation sécurisée du Refresh Token et émet un nouveau JWT d'accès."""
    now = datetime.now(timezone.utc)
    token_hash = hash_refresh_token(req.refresh_token)
    sess_row = (
        await session.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if not sess_row or sess_row.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide, expiré ou révoqué.",
        )

    user = (await session.execute(select(User).where(User.id == sess_row.user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur désactivé ou introuvable.",
        )

    sess_row.revoked_at = now
    role_obj = (await session.execute(select(Role).where(Role.id == user.role_id))).scalar_one_or_none()
    resp = await _issue_session_tokens(session, user, role_obj, request, "USER_TOKEN_REFRESHED")
    await session.commit()
    return resp


@router.post("/logout")
async def logout_session(
    request: Request,
    req: Optional[LogoutRequest] = None,
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Révoque le Refresh Token courant (ou toutes les sessions) et journalise la déconnexion."""
    now = datetime.now(timezone.utc)
    body = req or LogoutRequest()
    revoked_count = 0
    actor_id: Optional[UUID] = None

    if auth and auth.credentials:
        payload = decode_access_token(auth.credentials)
        if payload and payload.get("user_id"):
            try:
                actor_id = UUID(str(payload["user_id"]))
            except Exception:
                actor_id = None

    if body.all_sessions and actor_id:
        res = await session.execute(
            update(UserSession)
            .where(UserSession.user_id == actor_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        revoked_count = int(getattr(res, "rowcount", 0) or 0)
    elif body.refresh_token:
        sess_row = (
            await session.execute(
                select(UserSession).where(
                    UserSession.refresh_token_hash == hash_refresh_token(body.refresh_token),
                    UserSession.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if sess_row:
            sess_row.revoked_at = now
            actor_id = actor_id or sess_row.user_id
            revoked_count = 1

    if actor_id is not None:
        session.add(
            AuditLog(
                id=uuid4(),
                user_id=actor_id,
                action="USER_LOGOUT",
                resource_type="user_session",
                resource_id=str(actor_id),
                ip_address=request.client.host if request.client else None,
                details={"all_sessions": body.all_sessions, "revoked_count": revoked_count},
            )
        )
        await session.commit()

    return {"status": "logged_out", "revoked_sessions": revoked_count}


@router.get("/me", response_model=Dict[str, Any])
async def get_my_profile(
    current_user: AuthenticatedUserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retourne le profil complet, rôle RBAC, permissions, entités GLPI et statut MFA."""
    return {
        "id": str(current_user.id) if current_user.id else None,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "permissions": current_user.permissions,
        "allowed_entities": current_user.allowed_entities,
        "mfa_enabled": current_user.mfa_enabled,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }


@router.patch("/profile")
async def update_my_profile(
    req: ProfileUpdateRequest,
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Met à jour les informations personnelles (nom complet, email) de l'utilisateur connecté."""
    user = await _load_real_user(session, current_user)
    if req.email is not None:
        clean_email = req.email.strip().lower()
        if not _EMAIL_RE.match(clean_email):
            raise HTTPException(status_code=400, detail="Adresse email invalide.")
        dup = (
            await session.execute(select(User).where(User.email == clean_email, User.id != user.id))
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="Cette adresse email est déjà utilisée par un autre compte.")
        user.email = clean_email

    if req.full_name is not None:
        user.full_name = req.full_name.strip() or None

    session.add(
        AuditLog(
            id=uuid4(),
            user_id=user.id,
            action="USER_PROFILE_UPDATED",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"email": user.email, "full_name": user.full_name},
        )
    )
    await session.commit()

    role_obj = (await session.execute(select(Role).where(Role.id == user.role_id))).scalar_one_or_none()
    role_name, permissions, allowed_entities = _resolve_role_context(user, role_obj)
    return _serialize_user_payload(user, role_name, permissions, allowed_entities)


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Modifie le mot de passe après vérification de l'ancien et révoque les sessions actives."""
    user = await _load_real_user(session, current_user)
    if not (await verify_password_async(req.current_password, user.hashed_password)):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect.")

    pwd_err = validate_password_strength(req.new_password)
    if pwd_err:
        raise HTTPException(status_code=400, detail=pwd_err)

    user.hashed_password = await get_password_hash_async(req.new_password)
    now = datetime.now(timezone.utc)
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.add(
        AuditLog(
            id=uuid4(),
            user_id=user.id,
            action="USER_PASSWORD_CHANGED",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"username": user.username},
        )
    )
    await session.commit()
    return {"status": "password_updated", "sessions_revoked": True}


@router.get("/sessions")
async def list_my_sessions(
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste les sessions Refresh Token actives et récentes de l'utilisateur."""
    user = await _load_real_user(session, current_user)
    now = datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(UserSession)
            .where(UserSession.user_id == user.id)
            .order_by(UserSession.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return [
        {
            "id": str(s.id),
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
            "is_active": s.revoked_at is None and s.expires_at > now,
        }
        for s in rows
    ]


@router.delete("/sessions/{session_id}")
async def revoke_my_session(
    session_id: UUID,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Révoque à distance une session utilisateur spécifique."""
    user = await _load_real_user(session, current_user)
    sess_row = (
        await session.execute(
            select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not sess_row:
        raise HTTPException(status_code=404, detail="Session introuvable")
    if sess_row.revoked_at is None:
        sess_row.revoked_at = datetime.now(timezone.utc)
        session.add(
            AuditLog(
                id=uuid4(),
                user_id=user.id,
                action="USER_SESSION_REVOKED",
                resource_type="user_session",
                resource_id=str(session_id),
                details={"username": user.username},
            )
        )
        await session.commit()
    return {"status": "revoked", "session_id": str(session_id)}


@router.post("/mfa/setup")
async def setup_mfa(
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Génère un nouveau secret TOTP et l'URI otpauth:// pour enrôlement Authenticator (sans l'activer)."""
    user = await _load_real_user(session, current_user)
    plain_secret = generate_totp_secret()
    user.mfa_secret = encrypt_mfa_secret(plain_secret)
    await session.commit()

    uri = build_otpauth_uri(secret=plain_secret, username=user.username, issuer="AI IT Operations")
    return {
        "secret": plain_secret,
        "otpauth_uri": uri,
        "issuer": "AI IT Operations",
        "mfa_enabled": bool(user.mfa_enabled),
    }


@router.post("/mfa/enable")
async def enable_mfa(
    req: MfaCodeRequest,
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Confirme l'enrôlement TOTP via un code à 6 chiffres et émet 8 codes de secours à usage unique."""
    user = await _load_real_user(session, current_user)
    stored_secret = _safe_str(getattr(user, "mfa_secret", None))
    if not stored_secret:
        raise HTTPException(
            status_code=400,
            detail="Veuillez d'abord initialiser la configuration MFA (/mfa/setup).",
        )

    try:
        plain_secret = decrypt_mfa_secret(stored_secret)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not verify_totp_code(plain_secret, req.code):
        raise HTTPException(
            status_code=400,
            detail="Code TOTP invalide. Vérifiez l'heure de votre appareil et réessayez.",
        )

    recovery_codes = generate_recovery_codes(8)
    user.mfa_enabled = True
    user.mfa_recovery_codes = [hash_recovery_code(c) for c in recovery_codes]

    session.add(
        AuditLog(
            id=uuid4(),
            user_id=user.id,
            action="USER_MFA_ENABLED",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"username": user.username},
        )
    )
    await session.commit()

    return {
        "mfa_enabled": True,
        "recovery_codes": recovery_codes,
    }


@router.post("/mfa/disable")
async def disable_mfa(
    req: MfaDisableRequest,
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Désactive la double authentification TOTP après vérification du mot de passe et du code MFA."""
    user = await _load_real_user(session, current_user)
    if not (await verify_password_async(req.password, user.hashed_password)):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")

    if user.mfa_enabled and not _verify_mfa_or_consume_recovery(user, req.code):
        raise HTTPException(status_code=401, detail="Code TOTP ou code de secours invalide.")

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = []

    session.add(
        AuditLog(
            id=uuid4(),
            user_id=user.id,
            action="USER_MFA_DISABLED",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"username": user.username},
        )
    )
    await session.commit()
    return {"mfa_enabled": False}
