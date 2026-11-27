"""Sécurité, hachage et tokens JWT pour la plateforme AI IT Operations."""

import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

DEFAULT_SECRET_PLACEHOLDER = "change-this-ultra-secure-random-secret-key-in-production-min32chars"
SECRET_KEY = os.getenv("APP_SECRET_KEY", DEFAULT_SECRET_PLACEHOLDER)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

if ENVIRONMENT == "production":
    if SECRET_KEY == DEFAULT_SECRET_PLACEHOLDER or len(SECRET_KEY) < 32:
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR (CWE-798): "
            "Production environment requires a unique, secure APP_SECRET_KEY of at least 32 characters."
        )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 heures de session
REFRESH_TOKEN_EXPIRE_DAYS = 7
MFA_CHALLENGE_EXPIRE_MINUTES = 5


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si le mot de passe en clair correspond au hash bcrypt."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Génère le hash pbkdf2_sha256/bcrypt du mot de passe."""
    return pwd_context.hash(password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Vérifie le mot de passe hors boucle événementielle asyncio via asyncio.to_thread."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


async def get_password_hash_async(password: str) -> str:
    """Hache le mot de passe hors boucle événementielle asyncio via asyncio.to_thread."""
    return await asyncio.to_thread(get_password_hash, password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Crée un jeton d'accès JWT signé."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Décode et valide un jeton d'accès JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def create_mfa_challenge_token(user_id: str, username: str) -> str:
    """Émet un jeton éphémère (5 min) autorisant uniquement la validation du second facteur MFA."""
    return create_access_token(
        data={
            "sub": username,
            "user_id": user_id,
            "token_type": "mfa_challenge",
        },
        expires_delta=timedelta(minutes=MFA_CHALLENGE_EXPIRE_MINUTES),
    )


def decode_mfa_challenge_token(token: str) -> Optional[Dict[str, Any]]:
    """Décode un jeton de challenge MFA et vérifie son type explicite."""
    payload = decode_access_token(token)
    if not payload or payload.get("token_type") != "mfa_challenge":
        return None
    return payload


def generate_refresh_token() -> str:
    """Génère un Refresh Token opaque cryptographiquement aléatoire."""
    return f"aiops_rt_{secrets.token_urlsafe(48)}"
