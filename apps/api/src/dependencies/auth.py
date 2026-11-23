"""Dépendances d'authentification JWT, RBAC et isolation multi-entités GLPI."""

import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_db_session
from packages.domain.models.database import Role, User
from packages.security.src.jwt import decode_access_token

security_bearer = HTTPBearer(auto_error=False)

LAB_MODE_ENABLED = os.getenv("LAB_MODE_ENABLED", "false").lower() == "true"

ROLE_HIERARCHY = {
    "admin": 3,
    "operator": 2,
    "viewer": 1,
}


class AuthenticatedUserContext:
    def __init__(
        self,
        id: Optional[UUID],
        username: str,
        role: str,
        permissions: list[str],
        allowed_entities: Optional[List[str]] = None,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        mfa_enabled: bool = False,
        last_login_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.username = username
        self.role = role
        self.permissions = permissions
        self.email = email
        self.full_name = full_name
        self.mfa_enabled = bool(mfa_enabled)
        self.last_login_at = last_login_at
        self.created_at = created_at
        if role.lower() == "admin":
            self.allowed_entities: List[str] = ["*"]
        else:
            raw = allowed_entities if allowed_entities else ["0"]
            self.allowed_entities = [str(e) for e in raw] or ["0"]

    def has_sufficient_role(self, required_role: str) -> bool:
        user_level = ROLE_HIERARCHY.get(self.role.lower(), 0)
        req_level = ROLE_HIERARCHY.get(required_role.lower(), 0)
        return user_level >= req_level

    def can_access_entity(self, entity_id: str) -> bool:
        """Vérifie si l'utilisateur est autorisé sur une entité GLPI donnée."""
        if "*" in self.allowed_entities:
            return True
        ent = str(entity_id)
        return ent in self.allowed_entities or ent == "0"

    def resolve_entity_scope(self, requested_entity_id: Optional[str]) -> List[str]:
        """Résout la portée d'entités autorisées ou lève 403 en cas de tentative IDOR multi-sites."""
        if requested_entity_id is not None and str(requested_entity_id).strip() != "":
            req = str(requested_entity_id).strip()
            if "*" in self.allowed_entities:
                return ["*"] if req == "*" else [req, "0"] if req != "0" else ["0"]
            if not self.can_access_entity(req):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Accès refusé à l'entité GLPI demandée (isolation multi-sites)",
                )
            return [req, "0"] if req != "0" else ["0"]

        if "*" in self.allowed_entities:
            return ["*"]
        return list(dict.fromkeys([*self.allowed_entities, "0"]))


async def _resolve_bearer_user(
    auth: HTTPAuthorizationCredentials,
    session: AsyncSession,
) -> AuthenticatedUserContext:
    payload = decode_access_token(auth.credentials)
    if not payload or "sub" not in payload or payload.get("token_type") == "mfa_challenge":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton d'authentification invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload["sub"]
    role_name = payload.get("role", "viewer")
    token_entities = payload.get("allowed_entities")

    # 1. Vérification stricte du compte en base : détecter révocation/désactivation (CWE-613)
    stmt = select(User).where(User.username == username)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compte utilisateur désactivé ou révoqué",
            )
        raw_user_entities = getattr(user, "allowed_entities", None)
        user_entities = raw_user_entities if isinstance(raw_user_entities, list) else (token_entities or ["0"])
        raw_email = getattr(user, "email", None)
        raw_full_name = getattr(user, "full_name", None)
        raw_mfa = getattr(user, "mfa_enabled", False)
        raw_last_login = getattr(user, "last_login_at", None)
        raw_created = getattr(user, "created_at", None)
        safe_email = raw_email if isinstance(raw_email, str) else None
        safe_full_name = raw_full_name if isinstance(raw_full_name, str) else None
        safe_mfa = raw_mfa is True
        safe_last_login = raw_last_login if isinstance(raw_last_login, datetime) else None
        safe_created = raw_created if isinstance(raw_created, datetime) else None

        if hasattr(user, "role_id") and user.role_id is not None:
            role_stmt = select(Role).where(Role.id == user.role_id)
            role_obj = (await session.execute(role_stmt)).scalar_one_or_none()
            permissions = role_obj.permissions if (role_obj and hasattr(role_obj, "permissions")) else []
            current_role = role_obj.name if (role_obj and hasattr(role_obj, "name")) else role_name
            return AuthenticatedUserContext(
                id=getattr(user, "id", None),
                username=getattr(user, "username", username),
                role=current_role,
                permissions=permissions,
                allowed_entities=user_entities,
                email=safe_email,
                full_name=safe_full_name,
                mfa_enabled=safe_mfa,
                last_login_at=safe_last_login,
                created_at=safe_created,
            )

    if not LAB_MODE_ENABLED and not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur associé au jeton introuvable",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUserContext(
        id=None,
        username=username,
        role=role_name,
        permissions=payload.get("permissions", []),
        allowed_entities=token_entities or (["*"] if role_name.lower() == "admin" else ["0"]),
    )


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUserContext:
    """Valide le jeton Bearer JWT et extrait l'utilisateur authentifié (CWE-306 / CWE-287 / CWE-613)."""
    if auth and auth.credentials:
        return await _resolve_bearer_user(auth, session)

    if LAB_MODE_ENABLED:
        return AuthenticatedUserContext(
            id=None,
            username="lab-technician",
            role="operator",
            permissions=["incident:read", "incident:update", "runbook:execute"],
            allowed_entities=["*"],
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise pour cette ressource",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_knowledge_read_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUserContext:
    """Authentification multi-entités pour la lecture/recherche RAG (stricte en prod, entité racine '0' en dev sans token)."""
    if auth and auth.credentials:
        return await _resolve_bearer_user(auth, session)

    strict_prod = (
        os.getenv("ENVIRONMENT", "development").lower() == "production"
        or os.getenv("KNOWLEDGE_STRICT_AUTH", "false").lower() in ("true", "1", "yes")
    )
    if strict_prod and not LAB_MODE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise pour accéder à la base de connaissances en production",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUserContext(
        id=None,
        username="anonymous-root-viewer",
        role="viewer",
        permissions=["knowledge:read"],
        allowed_entities=["0"],
    )
