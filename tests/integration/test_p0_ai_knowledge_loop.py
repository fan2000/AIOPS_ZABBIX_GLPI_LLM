"""Tests d'intégration P0 : RBAC multi-entités KB, télémétrie réelle /ai/status et boucle Feedback -> KB."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import httpx
import pytest

from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user, get_knowledge_read_user
from apps.api.src.main import app
from database.connection import get_db_session
from packages.domain.models.database import (
    AIAnalysisRun,
    ActionExecution,
    Incident,
    KnowledgeDocument,
    KnowledgeProposal,
)


@pytest.mark.asyncio
async def test_knowledge_search_idor_cross_entity_rejected_403():
    """Un opérateur restreint à l'entité '1' doit être bloqué (403) s'il interroge l'entité '2'."""
    mock_session = AsyncMock()

    async def override_db():
        yield mock_session

    async def override_reader():
        return AuthenticatedUserContext(
            id=uuid4(),
            username="op_site_1",
            role="operator",
            permissions=["knowledge:read"],
            allowed_entities=["0", "1"],
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_knowledge_read_user] = override_reader

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/knowledge/search",
                json={"query": "CPU saturation", "entity_id": "2", "top_k": 3},
            )
            assert resp.status_code == 403
            assert "isolation multi-sites" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_knowledge_strict_auth_in_production_401_and_viewer_sync_403(monkeypatch):
    """En production, /knowledge exige un JWT (401) et un viewer ne peut lancer /sync (403)."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LAB_MODE_ENABLED", "false")
    mock_session = AsyncMock()

    async def override_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r_unauth = await client.get("/api/v1/knowledge/documents")
            assert r_unauth.status_code == 401

        # Test viewer sur /sync
        async def override_viewer():
            return AuthenticatedUserContext(uuid4(), "viewer1", "viewer", ["incident:read"], ["0"])

        app.dependency_overrides[get_current_user] = override_viewer
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r_sync = await client.post("/api/v1/knowledge/sync")
            assert r_sync.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ai_status_returns_real_aggregated_telemetry():
    """Vérifie que /api/v1/ai/status calcule des métriques SQL réelles (zéro valeur hardcodée)."""
    mock_session = AsyncMock()

    run1 = MagicMock(spec=AIAnalysisRun)
    run1.duration_ms = 120
    run1.prompt_tokens = 200
    run1.completion_tokens = 50
    run1.estimated_cost_usd = 0.0001
    run1.execution_mode = "llm_live"
    run1.validation_passed = True
    run1.blocked_actions_count = 0
    run1.agent_telemetry = {
        "Incident Agent": {"duration_ms": 5, "status": "ok"},
        "Diagnosis Agent": {"duration_ms": 95, "status": "ok", "mode": "llm_live"},
    }

    run2 = MagicMock(spec=AIAnalysisRun)
    run2.duration_ms = 20
    run2.prompt_tokens = 0
    run2.completion_tokens = 0
    run2.estimated_cost_usd = 0.0
    run2.execution_mode = "deterministic_fallback"
    run2.validation_passed = True
    run2.blocked_actions_count = 1
    run2.agent_telemetry = {
        "Incident Agent": {"duration_ms": 3, "status": "ok"},
        "Diagnosis Agent": {"duration_ms": 10, "status": "ok", "mode": "deterministic_fallback"},
    }

    res_runs = MagicMock()
    res_runs.scalars.return_value.all.return_value = [run1, run2]
    res_count = MagicMock()
    res_count.scalar.return_value = 2
    mock_session.execute.side_effect = [res_runs, res_count]

    async def override_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_db

    try:
        with patch("apps.api.src.routers.health.llm_client.check_health", new=AsyncMock(return_value={
            "online": True, "provider": "ollama", "model": "gemma4:latest", "circuit_state": "closed", "available_models": ["gemma4:latest"]
        })):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/ai/status")
                assert resp.status_code == 200
                data = resp.json()
                assert data["telemetry_source"] == "real_db_aggregation"
                assert data["avg_latency_ms"] == 70
                assert data["total_analysis_count"] == 2
                assert data["total_prompt_tokens"] == 200
                assert data["total_completion_tokens"] == 50
                assert data["blocked_actions_total"] == 1
                diag = [a for a in data["agents"] if a["name"] == "Diagnosis Agent"][0]
                assert diag["telemetry_runs"] == 2
                assert diag["rate"] == "100.0%"
                assert diag["avg_duration_ms"] == 52
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_incident_feedback_and_kb_proposal_approval_loop():
    """Teste la boucle fermée : POST /feedback -> création KnowledgeProposal -> POST /approve -> indexation RAG."""
    inc_id = uuid4()
    prop_id = uuid4()
    doc_id = uuid4()

    mock_inc = MagicMock(spec=Incident)
    mock_inc.id = inc_id
    mock_inc.title = "CPU utilization above 90% sur SRV-APP-01"
    mock_inc.primary_asset_name = "SRV-APP-01"
    mock_inc.entity_id = "1"

    mock_exec = MagicMock(spec=ActionExecution)
    mock_exec.runbook_identifier = "rb-collect-top-processes"
    mock_exec.execution_status = "SUCCESS"
    mock_exec.stdout = "nginx worker consuming 98% CPU"

    mock_run = MagicMock(spec=AIAnalysisRun)
    mock_run.hypotheses = [{"description": "Boucle worker nginx"}]

    mock_prop = MagicMock(spec=KnowledgeProposal)
    mock_prop.id = prop_id
    mock_prop.incident_id = inc_id
    mock_prop.title = "Procédure validée : CPU utilization above 90% sur SRV-APP-01"
    mock_prop.content = "<h3>Procédure</h3>"
    mock_prop.entity_id = "1"
    mock_prop.status = "pending_review"
    mock_prop.glpi_kb_id = None

    mock_doc = MagicMock(spec=KnowledgeDocument)
    mock_doc.id = doc_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    # Séquence d'appels pour /feedback puis /approve
    r_inc = MagicMock(); r_inc.scalar_one_or_none.return_value = mock_inc
    r_exec = MagicMock(); r_exec.scalar_one_or_none.return_value = mock_exec
    r_run = MagicMock(); r_run.scalar_one_or_none.return_value = mock_run
    r_no_prop = MagicMock(); r_no_prop.scalar_one_or_none.return_value = None
    r_prop = MagicMock(); r_prop.scalar_one_or_none.return_value = mock_prop
    mock_session.execute.side_effect = [r_inc, r_exec, r_run, r_no_prop, r_prop]

    async def override_db():
        yield mock_session

    async def override_op():
        return AuthenticatedUserContext(uuid4(), "op_site_1", "operator", ["all"], ["0", "1"])

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_user] = override_op

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            fb_resp = await client.post(
                f"/api/v1/incidents/{inc_id}/feedback",
                json={
                    "is_recommendation_accepted": True,
                    "rating_score": 5,
                    "feedback_notes": "Redémarrage nginx a résolu la fuite CPU.",
                    "generate_kb_proposal": True,
                },
            )
            assert fb_resp.status_code == 201
            assert fb_resp.json()["status"] == "recorded"
            assert fb_resp.json()["proposal_id"] is not None

            with patch("apps.api.src.routers.knowledge.glpi_client.create_knowledge_item", new=AsyncMock(return_value=77)), \
                 patch("apps.api.src.routers.knowledge.knowledge_worker.index_custom_document", new=AsyncMock(return_value=mock_doc)):
                app_resp = await client.post(f"/api/v1/knowledge/proposals/{prop_id}/approve")
                assert app_resp.status_code == 200
                data = app_resp.json()
                assert data["status"] == "approved_published"
                assert data["glpi_kb_id"] == "77"
                assert data["indexed_document_id"] == str(doc_id)
    finally:
        app.dependency_overrides.clear()
