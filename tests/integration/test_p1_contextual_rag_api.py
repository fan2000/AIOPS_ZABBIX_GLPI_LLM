"""Tests d'intégration P1 #4 : Filtres métadonnées /search, /reindex-contextual RBAC et /stats v2."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user, get_knowledge_read_user
from apps.api.src.main import app
from database.connection import get_db_session
from packages.contracts.src.ai import KnowledgeSourceCitation


def _mock_result(scalar=None, scalars_all=None):
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar.return_value = scalar
    res.scalars.return_value.all.return_value = scalars_all or []
    return res


def _fake_session(side_effects):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.execute.side_effect = side_effects
    return session


def test_knowledge_search_forwards_metadata_filters(monkeypatch):
    """POST /api/v1/knowledge/search transmet os, service, site_code, category et updated_after à hybrid_retriever."""
    reader = AuthenticatedUserContext(uuid4(), "op_rag", "operator", ["knowledge:read"], ["*"])
    captured = {}

    async def _fake_search(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return [
            KnowledgeSourceCitation(
                article_id="3",
                title="Procédure : Espace disque saturé /var/log",
                source_type="glpi_kb",
                relevance_score=0.95,
                snippet="Nettoyer /var/log",
                metadata={"os": "linux", "category": "disk", "site_code": "DC-PAR-1"},
            )
        ]

    monkeypatch.setattr("apps.api.src.routers.knowledge.hybrid_retriever.search", _fake_search)
    app.dependency_overrides[get_knowledge_read_user] = lambda: reader
    app.dependency_overrides[get_db_session] = lambda: _fake_session([])

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/knowledge/search",
            json={
                "query": "disque plein /var/log",
                "os": "linux",
                "service": "nginx",
                "site_code": "DC-PAR-1",
                "category": "disk",
                "updated_after": "2026-11-01T00:00:00Z",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["metadata"]["os"] == "linux"
        assert captured["kwargs"]["metadata_filters"] == {
            "os": "linux",
            "service": "nginx",
            "site_code": "DC-PAR-1",
            "category": "disk",
            "updated_after": "2026-11-01T00:00:00Z",
        }
    finally:
        app.dependency_overrides.clear()


def test_reindex_contextual_rbac_and_audit(monkeypatch):
    """POST /api/v1/knowledge/reindex-contextual refuse viewer (403) et audite operator (200)."""
    viewer = AuthenticatedUserContext(uuid4(), "viewer1", "viewer", ["incident:read"], ["*"])
    operator = AuthenticatedUserContext(uuid4(), "op1", "operator", ["runbook:execute"], ["*"])

    app.dependency_overrides[get_db_session] = lambda: _fake_session([])
    app.dependency_overrides[get_current_user] = lambda: viewer

    try:
        client = TestClient(app)
        assert client.post("/api/v1/knowledge/reindex-contextual").status_code == 403

        monkeypatch.setattr(
            "apps.api.src.routers.knowledge.knowledge_worker.reindex_contextual_chunks",
            AsyncMock(return_value={"processed": 3, "reindexed": 3, "failed": 0, "errors": []}),
        )
        session_op = _fake_session([])
        app.dependency_overrides[get_current_user] = lambda: operator
        app.dependency_overrides[get_db_session] = lambda: session_op

        resp = client.post("/api/v1/knowledge/reindex-contextual")
        assert resp.status_code == 200
        assert resp.json()["reindexed"] == 3
        assert session_op.add.call_args[0][0].action == "KB_REINDEX_CONTEXTUAL_TRIGGERED"
    finally:
        app.dependency_overrides.clear()


def test_knowledge_stats_and_document_detail_expose_contextual_metadata():
    """GET /stats et GET /documents/{id} exposent les métadonnées contextuelles v2 et metadata_gin_index_active."""
    reader = AuthenticatedUserContext(uuid4(), "op_ctx", "operator", ["knowledge:read"], ["*"])
    fake_pg_bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    doc_id = uuid4()
    now = datetime.now(timezone.utc)

    session_stats = _fake_session(
        [
            _mock_result(scalar=4),  # documents_count
            _mock_result(scalar=6),  # chunks_count
            _mock_result(scalar=0),  # fallback_chunks_count
            _mock_result(scalar=1),  # pending_proposals_count
            _mock_result(
                scalars_all=[
                    "ix_knowledge_chunks_embedding_hnsw",
                    "ix_knowledge_chunks_search_tsv_gin",
                    "ix_knowledge_documents_title_tsv_gin",
                    "ix_knowledge_chunks_search_tsv_multi_gin",
                    "ix_knowledge_documents_title_tsv_multi_gin",
                    "ix_knowledge_chunks_metadata_fields_gin",
                ]
            ),
            _mock_result(scalar=0),  # dlq_pending_count
            _mock_result(scalar=6),  # contextual_chunks_count
        ]
    )
    session_stats.bind = fake_pg_bind

    app.dependency_overrides[get_knowledge_read_user] = lambda: reader
    app.dependency_overrides[get_db_session] = lambda: session_stats

    try:
        client = TestClient(app)
        stats_resp = client.get("/api/v1/knowledge/stats")
        assert stats_resp.status_code == 200
        s = stats_resp.json()
        assert s["metadata_gin_index_active"] is True
        assert s["contextual_chunks_count"] == 6
        assert 15.0 <= s["chunk_overlap_pct"] <= 20.0

        fake_doc = SimpleNamespace(
            id=doc_id,
            external_id="3",
            title="Espace disque saturé /var/log",
            source_type="glpi_kb",
            entity_id="0",
            raw_content="Contenu",
            content_hash="hash",
            version=2,
            last_synced_at=now,
        )
        fake_chunk = SimpleNamespace(
            id=uuid4(),
            chunk_index=0,
            chunk_text="[Source: GLPI KB | OS: linux] Texte",
            metadata_fields={"chunk_schema_version": 2, "os": "linux", "category": "disk"},
            embedding_model="nomic-embed-text",
            embedding_version=1,
            is_fallback_embedding=False,
        )
        session_doc = _fake_session([_mock_result(scalar=fake_doc), _mock_result(scalars_all=[fake_chunk])])
        app.dependency_overrides[get_db_session] = lambda: session_doc

        doc_resp = client.get(f"/api/v1/knowledge/documents/{doc_id}")
        assert doc_resp.status_code == 200
        chunks = doc_resp.json()["chunks"]
        assert chunks[0]["metadata_fields"]["os"] == "linux"
        assert chunks[0]["metadata_fields"]["chunk_schema_version"] == 2
    finally:
        app.dependency_overrides.clear()
