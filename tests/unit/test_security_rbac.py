"""Tests unitaires pour la sécurité, tokens JWT et signatures HMAC."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pytest
from packages.domain.models.database import User
from packages.security.src.hmac_auth import get_webhook_secret, verify_hmac_signature
from packages.security.src.jwt import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from packages.security.src.rate_limiter import InMemoryRateLimiter
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user


def test_password_hashing():
    raw = "SuperSecretPassword123!"
    hashed = get_password_hash(raw)
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_create_and_decode():
    data = {"sub": "admin", "role": "operator"}
    token = create_access_token(data, expires_delta=timedelta(minutes=30))
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "admin"
    assert decoded["role"] == "operator"


def test_rate_limiter_in_memory():
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=10)
    client_ip = "10.0.0.1"
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    # 4ème requête dépasse la limite
    assert limiter.is_allowed(client_ip) is False


def test_rate_limiter_cleanup_anti_leak_cwe_770():
    """Vérifie la purge des clés obsolètes pour prévenir les fuites mémoire (CWE-770)."""
    limiter = InMemoryRateLimiter(max_requests=5, window_seconds=1)
    for i in range(600):
        limiter._history[f"stale_client_{i}"] = [0.0]  # Vieux timestamps
    limiter._last_cleanup = 0.0  # Force le nettoyage
    assert limiter.is_allowed("active_client") is True
    # Les anciennes clés doivent avoir été purgées
    assert len(limiter._history) < 500


def test_rbac_role_hierarchy():
    """Vérifie la hiérarchie des rôles RBAC (admin > operator > viewer)."""
    admin_ctx = AuthenticatedUserContext(None, "admin-user", "admin", ["all"])
    op_ctx = AuthenticatedUserContext(None, "op-user", "operator", ["runbook:execute"])
    view_ctx = AuthenticatedUserContext(None, "view-user", "viewer", ["incident:read"])

    # Admin peut tout exécuter
    assert admin_ctx.has_sufficient_role("admin") is True
    assert admin_ctx.has_sufficient_role("operator") is True
    assert admin_ctx.has_sufficient_role("viewer") is True

    # Operator peut exécuter operator et viewer, mais pas admin
    assert op_ctx.has_sufficient_role("admin") is False
    assert op_ctx.has_sufficient_role("operator") is True
    assert op_ctx.has_sufficient_role("viewer") is True

    # Viewer ne peut exécuter que viewer
    assert view_ctx.has_sufficient_role("admin") is False
    assert view_ctx.has_sufficient_role("operator") is False
    assert view_ctx.has_sufficient_role("viewer") is True


def test_production_hmac_secret_guard_cwe_798(monkeypatch):
    """Vérifie le blocage de démarrage en production avec secret par défaut (CWE-798)."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ZABBIX_WEBHOOK_SECRET", "zabbix-webhook-shared-hmac-secret-key-32chars")
    with pytest.raises(RuntimeError, match="CWE-798"):
        get_webhook_secret()


@pytest.mark.asyncio
async def test_deactivated_user_token_rejected_cwe_613():
    """Vérifie le rejet HTTP 403 d'un token valide pour un compte désactivé (CWE-613)."""
    mock_session = AsyncMock()
    mock_deactivated_user = MagicMock(spec=User)
    mock_deactivated_user.username = "fired_admin"
    mock_deactivated_user.is_active = False

    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = mock_deactivated_user
    mock_session.execute.return_value = exec_res

    token = create_access_token({"sub": "fired_admin", "role": "admin"})
    auth_cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(auth=auth_cred, session=mock_session)

    assert exc_info.value.status_code == 403
    assert "désactivé" in exc_info.value.detail
