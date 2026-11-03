"""Dépendances d'authentification JWT et contrôle d'accès basé sur les rôles (RBAC)."""

import os
from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import Depends, HTTPException, Request, status
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
    def __init__(self, id: Optional[UUID], username: str, role: str, permissions: list[str]):
        self.id = id
        self.username = username
        self.role = role
        self.permissions = permissions

    def has_sufficient_role(self, required_role: str) -> bool:
        user_level = ROLE_HIERARCHY.get(self.role.lower(), 0)
        req_level = ROLE_HIERARCHY.get(required_role.lower(), 0)
        return user_level >= req_level


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUserContext:
    """Valide le jeton Bearer JWT et extrait l'utilisateur authentifié (CWE-306 / CWE-287)."""
    if auth and auth.credentials:
        payload = decode_access_token(auth.credentials)
        if not payload or "sub" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Jeton d'authentification invalide ou expiré",
                headers={"WWW-Authenticate": "Bearer"},
            )
        username = payload["sub"]
        role_name = payload.get("role", "viewer")

        stmt = select(User).where(User.username == username, User.is_active == True)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user and hasattr(user, "role_id") and user.role_id is not None:
            # Charger les permissions du rôle
            role_stmt = select(Role).where(Role.id == user.role_id)
            role_obj = (await session.execute(role_stmt)).scalar_one_or_none()
            permissions = role_obj.permissions if (role_obj and hasattr(role_obj, "permissions")) else []
            current_role = role_obj.name if (role_obj and hasattr(role_obj, "name")) else role_name
            return AuthenticatedUserContext(
                id=getattr(user, "id", None),
                username=getattr(user, "username", username),
                role=current_role,
                permissions=permissions,
            )

        # Si utilisateur non trouvé en base mais jeton valide
        return AuthenticatedUserContext(
            id=None,
            username=username,
            role=role_name,
            permissions=payload.get("permissions", []),
        )

    # Mode Lab / Dev : utilisateur technicien par défaut si aucun en-tête n'est fourni
    if LAB_MODE_ENABLED:
        return AuthenticatedUserContext(
            id=None,
            username="lab-technician",
            role="operator",
            permissions=["incident:read", "incident:update", "runbook:execute"],
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise pour cette ressource",
        headers={"WWW-Authenticate": "Bearer"},
    )
