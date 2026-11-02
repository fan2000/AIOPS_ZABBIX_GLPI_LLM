"""Tests d'intégration des endpoints FastAPI."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from apps.api.src.main import app
from database.connection import get_db_session
from packages.domain.models.database import Runbook
from packages.security.src.hmac_auth import get_webhook_secret


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
