"""Routes d'authentification, émission de tokens JWT et gestion de session."""

from datetime import timedelta
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_db_session
from packages.domain.models.database import Role, User
from packages.security.src.jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    verify_password,
)
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & IAM"])


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: Dict[str, Any]


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authentifie un opérateur/administrateur et délivre un jeton JWT sécurisé."""
    stmt = select(User).where(User.username == req.username, User.is_active == True)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Récupérer le rôle associé
    role_stmt = select(Role).where(Role.id == user.role_id)
    role_obj = (await session.execute(role_stmt)).scalar_one_or_none()
    role_name = role_obj.name if role_obj else "viewer"
    permissions = role_obj.permissions if role_obj else []

    token_data = {
        "sub": user.username,
        "role": role_name,
        "permissions": permissions,
        "user_id": str(user.id),
    }

    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": role_name,
            "permissions": permissions,
        },
    )


@router.get("/me", response_model=Dict[str, Any])
async def get_my_profile(
    current_user: AuthenticatedUserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retourne les informations du profil utilisateur connecté."""
    return {
        "id": str(current_user.id) if current_user.id else None,
        "username": current_user.username,
        "role": current_user.role,
        "permissions": current_user.permissions,
    }
