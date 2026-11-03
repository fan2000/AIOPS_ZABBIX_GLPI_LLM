"""Tests d'intégration des endpoints FastAPI."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from apps.api.src.main import app
from database.connection import get_db_session
from packages.domain.models.database import Role, Runbook, User
from packages.security.src.hmac_auth import get_webhook_secret
from packages.security.src.jwt import create_access_token, get_password_hash


@pytest.mark.asyncio
async def test_health_live_endpoint():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_zabbix_webhook_endpoint_authenticated():
    transport = httpx.ASGITransport(app=app)
    payload = {
        "event_id": "99901",
        "event_type": "PROBLEM",
        "host_id": "1002",
        "host_name": "SRV-TEST-01",
        "trigger_id": "881",
        "severity": "HIGH",
        "problem": "Test Problem alert",
        "value": 1.0,
    }
    secret = get_webhook_secret()
    headers = {"Authorization": f"Bearer {secret}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/webhooks/zabbix", json=payload, headers=headers)
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["event_id"] == "99901"
        assert "idempotency_key" in data


@pytest.mark.asyncio
async def test_list_runbooks_endpoint():
    # Mock de la session DB pour test d'intégration unitaire hors conteneur
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_rb = MagicMock(spec=Runbook)
    mock_rb.identifier = "rb-win-service-restart"
    mock_rb.name = "Restart Windows Service"
    mock_rb.description = "Test description"
    mock_rb.runner_type = "powershell"
    mock_rb.target_os = "windows"
    mock_rb.timeout_seconds = 60
    mock_rb.required_role = "operator"
    mock_rb.parameter_schema = {}
    mock_result.scalars.return_value.all.return_value = [mock_rb]
    mock_session.execute.return_value = mock_result

    async def override_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/actions/runbooks")
            assert resp.status_code == 200
            runbooks = resp.json()
            assert isinstance(runbooks, list)
            assert len(runbooks) == 1
            assert runbooks[0]["id"] == "rb-win-service-restart"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auth_login_and_me_endpoints():
    mock_session = AsyncMock()
    mock_role = MagicMock(spec=Role)
    mock_role.name = "admin"
    mock_role.permissions = ["all"]
    mock_role.id = uuid4()

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid4()
    mock_user.username = "testadmin"
    mock_user.email = "admin@aiops.local"
    mock_user.hashed_password = get_password_hash("testpassword123")
    mock_user.role_id = mock_role.id
    mock_user.is_active = True

    # Configuration des retours pour login
    exec_res_user = MagicMock()
    exec_res_user.scalar_one_or_none.return_value = mock_user
    exec_res_role = MagicMock()
    exec_res_role.scalar_one_or_none.return_value = mock_role

    mock_session.execute.side_effect = [exec_res_user, exec_res_role, exec_res_user, exec_res_role]

    async def override_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Login réussi
            login_resp = await client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "testpassword123"},
            )
            assert login_resp.status_code == 200
            data = login_resp.json()
            assert "access_token" in data
            token = data["access_token"]
            assert data["user"]["role"] == "admin"

            # 2. Consultation du profil /me avec le jeton Bearer
            me_resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert me_resp.status_code == 200
            me_data = me_resp.json()
            assert me_data["username"] == "testadmin"
            assert me_data["role"] == "admin"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_runbook_execution_rbac_viewer_rejected_cwe_285():
    """Vérifie qu'un utilisateur avec le rôle 'viewer' ne peut exécuter un runbook 'operator' (403 Forbidden)."""
    mock_session = AsyncMock()
    mock_rb = MagicMock(spec=Runbook)
    mock_rb.identifier = "rb-win-service-restart"
    mock_rb.name = "Restart Windows Service"
    mock_rb.description = "Test"
    mock_rb.runner_type = "powershell"
    mock_rb.target_os = "windows"
    mock_rb.timeout_seconds = 60
    mock_rb.required_role = "operator"
    mock_rb.parameter_schema = {}
    mock_rb.template_command = "Restart-Service"
    mock_rb.is_enabled = True

    exec_res_user = MagicMock()
    exec_res_user.scalar_one_or_none.return_value = None

    exec_res_rb = MagicMock()
    exec_res_rb.scalar_one_or_none.return_value = mock_rb

    mock_session.execute.side_effect = [exec_res_user, exec_res_rb]

    async def override_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Création d'un token avec rôle 'viewer'
    viewer_token = create_access_token({"sub": "viewer_user", "role": "viewer", "permissions": ["incident:read"]})

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/actions/execute",
                headers={"Authorization": f"Bearer {viewer_token}"},
                json={
                    "runbook_id": "rb-win-service-restart",
                    "incident_id": str(uuid4()),
                    "parameters": {},
                    "approved_by_user_id": "viewer_user",
                },
            )
            assert resp.status_code == 403
            assert "Droits insuffisants" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()

