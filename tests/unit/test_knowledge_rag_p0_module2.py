"""Tests unitaires Module 2 P0 : Embeddings multi-providers batchés, DLQ anti-corruption, FTS bilingue & source_types."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import httpx
import pytest
from packages.domain.models.database import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbeddingDLQ,
)
from packages.rag.src.embeddings import EmbeddingsService
from packages.rag.src.retriever import (
    HybridRetriever,
    _normalize_source_type,
    build_safe_plain_or_query,
)
from services.knowledge_worker.src import worker as kw_mod


def test_bilingual_plain_tsquery_and_source_type_normalization():
    """build_safe_plain_or_query n'ajoute pas :* pour activer les stemmers FR/EN et _normalize_source_type préserve les 4 types."""
    tsq = build_safe_plain_or_query("Saturations disques -- arrêtés; DROP TABLE")
    assert " | " in tsq
    assert ":*" not in tsq
    assert "saturations" in tsq
    assert ";" not in tsq

    assert _normalize_source_type("glpi_kb") == "glpi_kb"
    assert _normalize_source_type("resolved_ticket") == "resolved_ticket"
    assert _normalize_source_type("runbook_doc") == "runbook_doc"
    assert _normalize_source_type("wiki") == "wiki"


@pytest.mark.asyncio
async def test_embeddings_batch_multi_provider_and_strict_guard(monkeypatch):
    """Vérifie le batching Ollama (/api/embed), TEI (/embed), OpenAI-compat (/v1/embeddings), le cache LRU et la garde strict prod."""
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            calls.append((url, json, headers))
            if "127.0.0.1:59999" in url:
                raise httpx.ConnectError("Connection refused")
            if url.endswith("/api/embed"):
                inputs = json["input"]
                return FakeResponse(200, {"embeddings": [[float(i + 1), 0.5, 0.0, 0.0] for i in range(len(inputs))]})
            if url.endswith("/embed"):
                inputs = json["inputs"]
                return FakeResponse(200, [[0.1 * (i + 1), 0.2, 0.3, 0.4] for i in range(len(inputs))])
            if url.endswith("/v1/embeddings"):
                inputs = json["input"]
                data = [
                    {"index": idx, "embedding": [0.9, float(idx), 0.1, 0.2]}
                    for idx in reversed(range(len(inputs)))
                ]
                return FakeResponse(200, {"data": data})
            return FakeResponse(500, {})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("packages.rag.src.embeddings.redis_streams.get_client", AsyncMock(return_value=None))

    # 1. Ollama batch natif + déduplication + cache LRU
    ollama_svc = EmbeddingsService(provider="ollama", dimension=4, allow_fallback=False, timeout_seconds=1.0)
    res_ollama = await ollama_svc.get_embeddings_batch(["cpu high", "disk full", "cpu high"])
    assert len(res_ollama) == 3
    assert res_ollama[0][0] == res_ollama[2][0]
    assert res_ollama[0][1]["is_fallback"] is False
    assert len(calls) == 1
    assert len(calls[0][1]["input"]) == 2

    res_cached = await ollama_svc.get_embeddings_batch(["cpu high"])
    assert res_cached[0][1]["cache_hit"] is True
    assert len(calls) == 1  # Aucun nouvel appel HTTP

    # 2. HuggingFace TEI
    tei_svc = EmbeddingsService(
        provider="tei",
        base_url="http://tei.local:8080",
        dimension=4,
        allow_fallback=False,
        timeout_seconds=1.0,
    )
    res_tei = await tei_svc.get_embeddings_batch(["test tei"])
    assert res_tei[0][0][0] == pytest.approx(0.1)
    assert calls[-1][0] == "http://tei.local:8080/embed"

    # 3. OpenAI-compatible (réordonnancement par index + Authorization Bearer)
    oai_svc = EmbeddingsService(
        provider="openai_compat",
        base_url="http://vllm.local:8000",
        api_key="tok-secret",
        dimension=4,
        allow_fallback=False,
        timeout_seconds=1.0,
    )
    res_oai = await oai_svc.get_embeddings_batch(["first", "second"])
    assert res_oai[0][0][1] == 0.0
    assert res_oai[1][0][1] == 1.0
    assert calls[-1][2]["Authorization"] == "Bearer tok-secret"

    # 4. Garde stricte production si fournisseur KO
    failing_svc = EmbeddingsService(
        provider="ollama",
        base_url="http://127.0.0.1:59999",
        dimension=4,
        allow_fallback=False,
        timeout_seconds=0.1,
        max_retries=0,
    )
    with pytest.raises(RuntimeError, match="production strict"):
        await failing_svc.get_embeddings_batch(["should fail cleanly"])


@pytest.mark.asyncio
async def test_knowledge_worker_sync_enqueues_dlq_on_strict_embedding_failure(monkeypatch):
    """En cas d'indisponibilité embeddings en prod strict, KnowledgeWorker préserve l'index et place en DLQ sans chunk fallback."""
    added_objects = []
    mock_session = AsyncMock()
    mock_session.add = lambda obj: added_objects.append(obj)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    res_none = MagicMock()
    res_none.scalar_one_or_none.return_value = None
    res_none.scalar.return_value = 0
    mock_session.execute.return_value = res_none

    @asynccontextmanager
    async def _fake_session_maker():
        yield mock_session

    monkeypatch.setattr(kw_mod, "async_session_maker", _fake_session_maker)
    monkeypatch.setattr(
        kw_mod.glpi_client,
        "get_knowledge_items",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=77,
                    name="Procédure BGP Failover",
                    answer="<p>Vérifier le voisin BGP AS65001 et l'état de l'interface.</p>",
                    entities_id=1,
                    is_faq=0,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        kw_mod.embeddings_service,
        "get_embeddings_batch",
        AsyncMock(side_effect=RuntimeError("Embedding provider indisponible en mode production strict")),
    )

    worker = kw_mod.KnowledgeWorker()
    job = await worker.sync_glpi_kb()

    assert job.status == "failed"
    assert "DLQ" in (job.error_message or "")
    chunks_added = [o for o in added_objects if isinstance(o, KnowledgeChunk)]
    dlq_added = [o for o in added_objects if isinstance(o, KnowledgeEmbeddingDLQ)]
    assert len(chunks_added) == 0
    assert len(dlq_added) == 1
    assert dlq_added[0].external_id == "77"
    assert dlq_added[0].status == "pending_retry"


@pytest.mark.asyncio
async def test_retriever_filters_and_preserves_runbook_source_type():
    """HybridRetriever filtre par source_types et conserve 'runbook_doc' au lieu de le convertir en 'wiki'."""
    retriever = HybridRetriever(top_k=4, threshold=0.10)
    dev_svc = EmbeddingsService(allow_fallback=True)
    vec = dev_svc._generate_deterministic_fallback("redemarrage service nginx systemd")

    doc_rb = KnowledgeDocument(
        id=uuid4(),
        external_id="rb-linux-service-restart",
        title="Runbook Redémarrage Service Linux",
        source_type="runbook_doc",
        entity_id="0",
        raw_content="Redémarrage service nginx systemd",
        content_hash="rbhash",
    )
    chunk_rb = KnowledgeChunk(
        id=uuid4(),
        document_id=doc_rb.id,
        chunk_index=0,
        chunk_text="Procédure redemarrage service nginx systemd contrôlé.",
        entity_id="0",
        embedding=vec,
    )

    mock_session = AsyncMock()
    mock_session.bind = None
    res = MagicMock()
    res.all.return_value = [(chunk_rb, doc_rb)]
    mock_session.execute.return_value = res

    citations = await retriever.search(
        "redemarrage service nginx",
        session=mock_session,
        entity_id="0",
        source_types=["runbook_doc"],
    )
    assert len(citations) == 1
    assert citations[0].source_type == "runbook_doc"
    assert citations[0].article_id == "rb-linux-service-restart"
