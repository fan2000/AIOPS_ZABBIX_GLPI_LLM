"""Tests d'intégration Module 2 P0 : Routes /documents/{id}, IDOR+AuditLog, /dlq, /reindex-fallback et /stats."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user, get_knowledge_read_user
from apps.api.src.main import app
from database.connection import get_db_session


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


def test_knowledge_document_detail_idor_blocked_with_audit_and_allowed_success():
    """GET /documents/{id} retourne les chunks si autorisé, ou HTTP 403 + AuditLog en cas de tentative IDOR inter-entités."""
    doc_id = uuid4()
    now = datetime.now(timezone.utc)
    foreign_doc = SimpleNamespace(
        id=doc_id,
        external_id="KB-99",
        title="Procédure Site 20",
        source_type="glpi_kb",
        entity_id="20",
        raw_content="Contenu confidentiel site 20",
        content_hash="abc123",
        version=2,
        last_synced_at=now,
    )
    chunk_row = SimpleNamespace(
        id=uuid4(),
        chunk_index=0,
        chunk_text="[Titre: Procédure Site 20] Détail",
        embedding_model="nomic-embed-text",
        embedding_version=1,
        is_fallback_embedding=False,
    )

    user_site_1 = AuthenticatedUserContext(uuid4(), "op_site1", "operator", ["knowledge:read"], ["0", "1"])
    session_idor = _fake_session([_mock_result(scalar=foreign_doc)])
    app.dependency_overrides[get_knowledge_read_user] = lambda: user_site_1
    app.dependency_overrides[get_db_session] = lambda: session_idor

    try:
        client = TestClient(app)
        resp_403 = client.get(f"/api/v1/knowledge/documents/{doc_id}")
        assert resp_403.status_code == 403
        assert "isolation multi-sites" in resp_403.json()["detail"]
        assert session_idor.add.call_count == 1
        assert session_idor.add.call_args[0][0].action == "KB_IDOR_BLOCKED"

        user_site_20 = AuthenticatedUserContext(uuid4(), "op_site20", "operator", ["knowledge:read"], ["20"])
        session_ok = _fake_session([_mock_result(scalar=foreign_doc), _mock_result(scalars_all=[chunk_row])])
        app.dependency_overrides[get_knowledge_read_user] = lambda: user_site_20
        app.dependency_overrides[get_db_session] = lambda: session_ok

        resp_200 = client.get(f"/api/v1/knowledge/documents/{doc_id}")
        assert resp_200.status_code == 200
        body = resp_200.json()
        assert body["title"] == "Procédure Site 20"
        assert len(body["chunks"]) == 1
        assert body["chunks"][0]["embedding_model"] == "nomic-embed-text"
    finally:
        app.dependency_overrides.clear()


def test_knowledge_dlq_and_reindex_rbac_and_audit(monkeypatch):
    """GET /dlq, POST /dlq/retry et POST /reindex-fallback bloquent viewer (403) et auditent operator (200)."""
    viewer = AuthenticatedUserContext(uuid4(), "viewer1", "viewer", ["incident:read"], ["*"])
    operator = AuthenticatedUserContext(uuid4(), "op1", "operator", ["incident:read", "runbook:execute"], ["*"])

    app.dependency_overrides[get_db_session] = lambda: _fake_session([])
    app.dependency_overrides[get_current_user] = lambda: viewer

    try:
        client = TestClient(app)
        assert client.get("/api/v1/knowledge/dlq").status_code == 403
        assert client.post("/api/v1/knowledge/dlq/retry").status_code == 403
        assert client.post("/api/v1/knowledge/reindex-fallback").status_code == 403

        dlq_item = SimpleNamespace(
            id=uuid4(),
            document_id=None,
            source_type="glpi_kb",
            external_id="44",
            entity_id="0",
            title="Article en attente",
            status="pending_retry",
            attempts=1,
            max_attempts=5,
            last_error="Timeout Ollama",
            next_retry_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session_dlq = _fake_session([_mock_result(scalars_all=[dlq_item])])
        app.dependency_overrides[get_current_user] = lambda: operator
        app.dependency_overrides[get_db_session] = lambda: session_dlq

        resp_dlq = client.get("/api/v1/knowledge/dlq")
        assert resp_dlq.status_code == 200
        assert len(resp_dlq.json()) == 1
        assert resp_dlq.json()[0]["external_id"] == "44"

        monkeypatch.setattr(
            "apps.api.src.routers.knowledge.knowledge_worker.retry_dlq_items",
            AsyncMock(return_value={"processed": 1, "resolved": 1, "failed": 0, "errors": []}),
        )
        monkeypatch.setattr(
            "apps.api.src.routers.knowledge.knowledge_worker.reindex_fallback_chunks",
            AsyncMock(return_value={"processed": 2, "reindexed": 2, "failed": 0, "errors": []}),
        )

        session_retry = _fake_session([])
        app.dependency_overrides[get_db_session] = lambda: session_retry
        r_retry = client.post("/api/v1/knowledge/dlq/retry")
        assert r_retry.status_code == 200
        assert r_retry.json()["resolved"] == 1
        assert session_retry.add.call_args[0][0].action == "KB_DLQ_RETRY_TRIGGERED"

        session_reindex = _fake_session([])
        app.dependency_overrides[get_db_session] = lambda: session_reindex
        r_reindex = client.post("/api/v1/knowledge/reindex-fallback")
        assert r_reindex.status_code == 200
        assert r_reindex.json()["reindexed"] == 2
        assert session_reindex.add.call_args[0][0].action == "KB_REINDEX_FALLBACK_TRIGGERED"
    finally:
        app.dependency_overrides.clear()


def test_knowledge_stats_exposes_bilingual_fts_dlq_and_provider_health():
    """GET /stats expose fts_bilingual_active, dlq_pending_count, embedding_provider et circuit_state."""
    reader = AuthenticatedUserContext(uuid4(), "op_stats", "operator", ["knowledge:read"], ["*"])
    fake_pg_bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    session = _fake_session(
        [
            _mock_result(scalar=4),  # documents_count
            _mock_result(scalar=6),  # chunks_count
            _mock_result(scalar=1),  # fallback_chunks_count
            _mock_result(scalar=2),  # pending_proposals_count
            _mock_result(
                scalars_all=[
                    "ix_knowledge_chunks_embedding_hnsw",
                    "ix_knowledge_chunks_search_tsv_gin",
                    "ix_knowledge_documents_title_tsv_gin",
                    "ix_knowledge_chunks_search_tsv_multi_gin",
                    "ix_knowledge_documents_title_tsv_multi_gin",
                ]
            ),
            _mock_result(scalar=3),  # dlq_pending_count
        ]
    )
    session.bind = fake_pg_bind

    app.dependency_overrides[get_knowledge_read_user] = lambda: reader
    app.dependency_overrides[get_db_session] = lambda: session

    try:
        client = TestClient(app)
        resp = client.get("/api/v1/knowledge/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["documents_count"] == 4
        assert body["chunks_count"] == 6
        assert body["fallback_chunks_count"] == 1
        assert body["real_embedding_chunks_count"] == 5
        assert body["dlq_pending_count"] == 3
        assert body["hnsw_index_active"] is True
        assert body["gin_index_active"] is True
        assert body["fts_bilingual_active"] is True
        assert body["embedding_provider"] == "ollama"
        assert body["embedding_circuit_state"] in ("closed", "open")
    finally:
        app.dependency_overrides.clear()
