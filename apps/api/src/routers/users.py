"""Administration IAM des utilisateurs, rôles RBAC, entités GLPI et MFA (réservé admin)."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import asc, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from database.connection import get_db_session
from packages.domain.models.database import AuditLog, Role, User, UserSession
from packages.security.src.jwt import get_password_hash_async
from packages.security.src.mfa import validate_password_strength

router = APIRouter(prefix="/api/v1/users", tags=["Users & RBAC Administration"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,50}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)
    full_name: Optional[str] = Field(None, max_length=150)
    role: Literal["admin", "operator", "viewer"] = "viewer"
    allowed_entities: List[str] = Field(default_factory=lambda: ["0"])
    is_active: bool = True


class AdminUpdateUserRequest(BaseModel):
    role: Optional[Literal["admin", "operator", "viewer"]] = None
    allowed_entities: Optional[List[str]] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = Field(None, max_length=150)
    email: Optional[str] = Field(None, min_length=5, max_length=255)


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=1, max_length=128)


def _require_admin(current_user: AuthenticatedUserContext = Depends(get_current_user)) -> AuthenticatedUserContext:
    if current_user.role.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : le rôle 'admin' est strictement requis pour gérer les utilisateurs et rôles.",
        )
    return current_user


def _serialize_admin_user(u: User, role_obj: Optional[Role]) -> Dict[str, Any]:
    role_name = role_obj.name if role_obj else "viewer"
    perms = list(role_obj.permissions) if (role_obj and isinstance(role_obj.permissions, list)) else []
    entities = ["*"] if role_name.lower() == "admin" else (u.allowed_entities if isinstance(u.allowed_entities, list) else ["0"])
    return {
        "id": str(u.id),
        "username": u.username,
        "email": u.email,
        "full_name": getattr(u, "full_name", None),
        "role": role_name,
        "permissions": perms,
        "allowed_entities": [str(e) for e in entities],
        "is_active": bool(u.is_active),
        "mfa_enabled": getattr(u, "mfa_enabled", False) is True,
        "last_login_at": u.last_login_at.isoformat() if isinstance(getattr(u, "last_login_at", None), datetime) else None,
        "created_at": u.created_at.isoformat() if isinstance(getattr(u, "created_at", None), datetime) else None,
    }


@router.get("/roles")
async def list_roles(
    _admin: AuthenticatedUserContext = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Retourne les rôles RBAC configurés et leurs permissions."""
    roles = (await session.execute(select(Role).order_by(asc(Role.name)))).scalars().all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "permissions": list(r.permissions or []),
        }
        for r in roles
    ]


@router.get("")
async def list_users(
    _admin: AuthenticatedUserContext = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste tous les comptes utilisateurs, rôles RBAC, entités GLPI et statut MFA."""
    roles = (await session.execute(select(Role))).scalars().all()
    role_by_id = {r.id: r for r in roles}
    users = (await session.execute(select(User).order_by(asc(User.username)))).scalars().all()
    return [_serialize_admin_user(u, role_by_id.get(u.role_id)) for u in users]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user_by_admin(
    req: AdminCreateUserRequest,
    request: Request,
    admin: AuthenticatedUserContext = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Crée un compte utilisateur avec rôle et portée multi-entités GLPI explicites."""
    clean_username = req.username.strip()
    clean_email = req.email.strip().lower()
    if not _USERNAME_RE.match(clean_username):
        raise HTTPException(status_code=400, detail="Nom d'utilisateur invalide.")
    if not _EMAIL_RE.match(clean_email):
        raise HTTPException(status_code=400, detail="Adresse email invalide.")

    pwd_err = validate_password_strength(req.password)
    if pwd_err:
        raise HTTPException(status_code=400, detail=pwd_err)

    existing = (
        await session.execute(select(User).where(or_(User.username == clean_username, User.email == clean_email)))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Identifiant ou email déjà existant.")

    role_obj = (await session.execute(select(Role).where(Role.name == req.role))).scalar_one_or_none()
    if not role_obj:
        raise HTTPException(status_code=400, detail=f"Rôle inconnu : {req.role}")

    entities = ["*"] if req.role == "admin" else ([str(e).strip() for e in req.allowed_entities if str(e).strip()] or ["0"])
    user = User(
        id=uuid4(),
        username=clean_username,
        email=clean_email,
        full_name=(req.full_name or "").strip() or None,
        hashed_password=await get_password_hash_async(req.password),
        role_id=role_obj.id,
        allowed_entities=entities,
        is_active=req.is_active,
        mfa_enabled=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()

    session.add(
        AuditLog(
            id=uuid4(),
            user_id=admin.id,
            action="ADMIN_USER_CREATED",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"created_username": user.username, "role": req.role, "allowed_entities": entities, "by": admin.username},
        )
    )
    await session.commit()
    return _serialize_admin_user(user, role_obj)


@router.patch("/{user_id}")
async def update_user_by_admin(
    user_id: UUID,
    req: AdminUpdateUserRequest,
    request: Request,
    admin: AuthenticatedUserContext = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Met à jour le rôle, les entités GLPI, le statut actif ou le profil d'un utilisateur."""
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    is_self = admin.id is not None and user.id == admin.id
    if is_self:
        if req.is_active is False:
            raise HTTPException(status_code=400, detail="Un administrateur ne peut pas désactiver son propre compte.")
        if req.role is not None and req.role != "admin":
            raise HTTPException(status_code=400, detail="Un administrateur ne peut pas rétrograder son propre rôle.")

    role_obj = (await session.execute(select(Role).where(Role.id == user.role_id))).scalar_one_or_none()
    if req.role is not None:
        target_role = (await session.execute(select(Role).where(Role.name == req.role))).scalar_one_or_none()
        if not target_role:
            raise HTTPException(status_code=400, detail=f"Rôle inconnu : {req.role}")
        user.role_id = target_role.id
        role_obj = target_role
        if req.role == "admin":
            user.allowed_entities = ["*"]

    if req.allowed_entities is not None and (role_obj is None or role_obj.name != "admin"):
        cleaned = [str(e).strip() for e in req.allowed_entities if str(e).strip()]
        user.allowed_entities = cleaned or ["0"]

    if req.full_name is not None:
        user.full_name = req.full_name.strip() or None

    if req.email is not None:
        clean_email = req.email.strip().lower()
        if not _EMAIL_RE.match(clean_email):
            raise HTTPException(status_code=400, detail="Adresse email invalide.")
        dup = (await session.execute(select(User).where(User.email == clean_email, User.id != user.id))).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="Email déjà attribué à un autre compte.")
        user.email = clean_email

    if req.is_active is not None:
        user.is_active = req.is_active
        if req.is_active is False:
            await session.execute(
                update(UserSession)
                .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(timezone.utc))
            )

    session.add(
        AuditLog(
            id=uuid4(),
            user_id=admin.id,
            action="ADMIN_USER_UPDATED",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={
                "target_username": user.username,
                "role": role_obj.name if role_obj else None,
                "is_active": user.is_active,
                "allowed_entities": user.allowed_entities,
                "by": admin.username,
            },
        )
    )
    await session.commit()
    return _serialize_admin_user(user, role_obj)


@router.post("/{user_id}/reset-mfa")
async def reset_user_mfa(
    user_id: UUID,
    request: Request,
    admin: AuthenticatedUserContext = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Réinitialise d'urgence le second facteur MFA d'un utilisateur (perte d'appareil)."""
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = []

    session.add(
        AuditLog(
            id=uuid4(),
            user_id=admin.id,
            action="ADMIN_USER_MFA_RESET",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"target_username": user.username, "by": admin.username},
        )
    )
    await session.commit()
    return {"user_id": str(user.id), "username": user.username, "mfa_enabled": False}


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    req: AdminResetPasswordRequest,
    request: Request,
    admin: AuthenticatedUserContext = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Réinitialise le mot de passe d'un utilisateur et révoque toutes ses sessions."""
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    pwd_err = validate_password_strength(req.new_password)
    if pwd_err:
        raise HTTPException(status_code=400, detail=pwd_err)

    user.hashed_password = await get_password_hash_async(req.new_password)
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    session.add(
        AuditLog(
            id=uuid4(),
            user_id=admin.id,
            action="ADMIN_USER_PASSWORD_RESET",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            details={"target_username": user.username, "by": admin.username},
        )
    )
    await session.commit()
    return {"user_id": str(user.id), "status": "password_reset"}
