"""Tests d'intégration API P2 #9 : Qualité RAG, Knowledge Gaps, Brouillon KB & GraphRAG."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user, get_knowledge_read_user
from apps.api.src.main import app
from database.connection import get_db_session


def _mock_result(scalar=None, all_rows=None):
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar.return_value = scalar
    res.scalars.return_value.all.return_value = all_rows or []
    res.all.return_value = all_rows or []
    return res


def _fake_session(side_effects):
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute.side_effect = side_effects
    return session


def test_knowledge_quality_gaps_and_graph_endpoints(monkeypatch):
    """GET /quality, /gaps et /graph exposent les métriques, gaps et graphe scopés multi-entités."""
    reader = AuthenticatedUserContext(
        id=uuid4(),
        username="viewer_rag",
        role="viewer",
        permissions=["incident:read"],
        allowed_entities=["0"],
    )
    app.dependency_overrides[get_knowledge_read_user] = lambda: reader
    app.dependency_overrides[get_db_session] = lambda: _fake_session([])

    sample_gap_payload = {
        "metrics": {
            "total_incidents": 4,
            "total_analyzed_incidents": 4,
            "citation_coverage_rate": 0.5,
            "avg_relevance_score": 0.62,
            "avg_faithfulness_score": 0.78,
            "insufficient_evidence_rate": 0.5,
            "latest_eval_recall_at_5": 1.0,
            "latest_eval_mrr": 1.0,
            "gaps_count": 1,
            "critical_gaps_count": 1,
        },
        "gaps": [
            {
                "family_key": "anomalie z<n>",
                "sample_incident_id": str(uuid4()),
                "sample_title": "Anomalie Z99",
                "recommended_kb_title": "Procédure : Anomalie Z99",
                "entity_id": "0",
                "category": "general",
                "inferred_os": "network",
                "inferred_service": "general",
                "incident_count": 2,
                "analyzed_count": 2,
                "affected_hosts": ["CORE-RTR-842"],
                "max_severity": "DISASTER",
                "avg_rag_score": 0.0,
                "citation_coverage_rate": 0.0,
                "insufficient_evidence_rate": 1.0,
                "avg_faithfulness_score": 0.75,
                "priority_score": 77.0,
                "priority_level": "CRITICAL",
                "has_pending_proposal": False,
            }
        ],
    }
    sample_graph = {
        "nodes": [{"id": "asset:CORE-RTR-842", "type": "asset", "label": "CORE-RTR-842", "metadata": {}}],
        "edges": [],
        "matched_node_ids": ["asset:CORE-RTR-842"],
        "stats": {"assets": 1, "services": 0, "incidents": 0, "kb_articles": 0, "runbooks": 0, "edges": 0},
        "focus": {"query": "CORE-RTR-842", "asset": None},
    }

    monkeypatch.setattr(
        "apps.api.src.routers.knowledge.detect_knowledge_gaps",
        AsyncMock(return_value=sample_gap_payload),
    )
    monkeypatch.setattr(
        "apps.api.src.routers.knowledge.build_operational_graph",
        AsyncMock(return_value=sample_graph),
    )

    try:
        client = TestClient(app)
        r_qual = client.get("/api/v1/knowledge/quality")
        assert r_qual.status_code == 200
        q_body = r_qual.json()
        assert q_body["latest_eval_recall_at_5"] == 1.0
        assert len(q_body["top_gaps"]) == 1

        r_gaps = client.get("/api/v1/knowledge/gaps")
        assert r_gaps.status_code == 200
        assert r_gaps.json()["gaps"][0]["priority_level"] == "CRITICAL"

        r_graph = client.get("/api/v1/knowledge/graph?q=CORE-RTR-842")
        assert r_graph.status_code == 200
        assert r_graph.json()["stats"]["assets"] == 1
    finally:
        app.dependency_overrides.clear()


def test_gap_draft_proposal_viewer_forbidden():
    """Un utilisateur viewer reçoit HTTP 403 sur POST /api/v1/knowledge/gaps/draft-proposal."""
    viewer = AuthenticatedUserContext(
        id=uuid4(),
        username="viewer_noc",
        role="viewer",
        permissions=["incident:read"],
        allowed_entities=["*"],
    )
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_db_session] = lambda: _fake_session([])

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/knowledge/gaps/draft-proposal",
            json={
                "incident_id": str(uuid4()),
                "title": "Procédure : Anomalie Z99",
                "family_key": "anomalie z99",
            },
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_gap_draft_proposal_operator_creates_proposal_and_audit():
    """Un opérateur peut générer un brouillon KB (201 Created) avec persistance KnowledgeProposal et AuditLog."""
    inc_id = uuid4()
    operator = AuthenticatedUserContext(
        id=uuid4(),
        username="ops_rag",
        role="operator",
        permissions=["knowledge:write"],
        allowed_entities=["0"],
    )
    fake_inc = SimpleNamespace(
        id=inc_id,
        title="Anomalie propriétaire obscure Z99 sur CORE-RTR-842",
        severity="DISASTER",
        primary_asset_name="CORE-RTR-842",
        entity_id="0",
    )
    session = _fake_session([_mock_result(scalar=fake_inc)])
    app.dependency_overrides[get_current_user] = lambda: operator
    app.dependency_overrides[get_db_session] = lambda: session

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/knowledge/gaps/draft-proposal",
            json={
                "incident_id": str(inc_id),
                "title": "Procédure : Anomalie propriétaire obscure Z99",
                "family_key": "anomalie proprietaire obscure z99",
                "category": "AIOps - Gap (network)",
                "inferred_os": "network",
                "affected_hosts": ["CORE-RTR-842"],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pending_review"
        assert body["created_by"] == "gap-detector:ops_rag"
        assert body["entity_id"] == "0"
        assert "show ip interface brief" in body["content"]
        # 2 objets ajoutés : KnowledgeProposal + AuditLog
        assert session.add.call_count == 2
        assert session.commit.await_count == 1
    finally:
        app.dependency_overrides.clear()
