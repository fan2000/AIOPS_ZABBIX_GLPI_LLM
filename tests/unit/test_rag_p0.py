"""Tests unitaires P0 pour le pipeline RAG (chunker overlap, embeddings circuit-breaker/prod guard, retriever)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from packages.domain.models.database import KnowledgeChunk, KnowledgeDocument
from packages.rag.src.chunker import TextChunker
from packages.rag.src.embeddings import EmbeddingsService
from packages.rag.src.retriever import HybridRetriever, build_safe_or_tsquery, cosine_similarity


def test_chunker_overlap_and_contextual_prefix():
    chunker = TextChunker(chunk_size=140, chunk_overlap=40)
    text = (
        "Premier paragraphe decrivant la verification CPU avec la commande Get-Process sur le serveur.\n\n"
        "Deuxieme paragraphe decrivant l'analyse des journaux applicatifs dans /var/log/nginx/error.log pour diagnostic.\n\n"
        "Troisieme paragraphe sur la validation finale du redemarrage systemd."
    )
    chunks = chunker.split_text(text, title="Saturation CPU Serveur")
    assert len(chunks) >= 2
    assert all(c.startswith("[Titre: Saturation CPU Serveur] ") for c in chunks)

    # Le deuxième chunk doit contenir un recouvrement issu de la fin du premier chunk
    body1 = chunks[0].split("] ", 1)[1]
    body2 = chunks[1].split("] ", 1)[1]
    tail_words = body1.split()[-3:]
    assert any(w in body2 for w in tail_words)


@pytest.mark.asyncio
async def test_embeddings_strict_production_guard_and_circuit_breaker():
    # En production strict, aucune génération de fallback factice n'est tolérée
    prod_svc = EmbeddingsService(
        base_url="http://127.0.0.1:59998",
        allow_fallback=False,
        timeout_seconds=0.1,
    )
    with pytest.raises(RuntimeError, match="production strict"):
        await prod_svc.get_embedding_with_metadata("test saturation cpu")
    assert prod_svc._failure_count >= 1

    # En dev/test, le feature-hashing préserve une vraie proximité sémantique + métadonnée is_fallback=True
    dev_svc = EmbeddingsService(
        base_url="http://127.0.0.1:59998",
        allow_fallback=True,
        timeout_seconds=0.1,
        max_cache_size=3,
    )
    v_cpu1, meta1 = await dev_svc.get_embedding_with_metadata("Saturation CPU anormale processus top")
    v_cpu2, _ = await dev_svc.get_embedding_with_metadata("Diagnostic CPU processus consommateur")
    v_disk, _ = await dev_svc.get_embedding_with_metadata("Espace disque partition /var/log plein")

    assert meta1["is_fallback"] is True
    assert len(v_cpu1) == 768
    assert cosine_similarity(v_cpu1, v_cpu2) > cosine_similarity(v_cpu1, v_disk)

    # Borne LRU cache respectée
    await dev_svc.get_embedding_with_metadata("extra 1")
    await dev_svc.get_embedding_with_metadata("extra 2")
    assert len(dev_svc._cache) <= 3


def test_build_safe_or_tsquery_sanitization():
    q = "CPU saturation! sur /var/log -- DROP TABLE; nginx"
    tsq = build_safe_or_tsquery(q)
    assert " | " in tsq
    assert "cpu:*" in tsq
    assert "nginx:*" in tsq
    assert ";" not in tsq


@pytest.mark.asyncio
async def test_retriever_accepts_ndarray_like_vector_in_python_fallback():
    retriever = HybridRetriever(top_k=3, threshold=0.20)
    dev_svc = EmbeddingsService(allow_fallback=True)
    vec = dev_svc._generate_deterministic_fallback("CPU saturation processus")

    class FakeNdArray:
        """Simule un vecteur NumPy ndarray retourné par pgvector SQLAlchemy (non isinstance list)."""
        def __init__(self, data):
            self._d = list(data)
        def __len__(self):
            return len(self._d)
        def __iter__(self):
            return iter(self._d)

    doc = KnowledgeDocument(
        external_id="KB-CPU-01",
        title="Procédure Saturation CPU",
        source_type="glpi_kb",
        entity_id="0",
        raw_content="Lister les processus CPU",
        content_hash="abc",
    )
    chunk = KnowledgeChunk(
        document_id=doc.id,
        chunk_index=0,
        chunk_text="Vérifier les processus consommateurs de CPU.",
        entity_id="0",
        embedding=FakeNdArray(vec),
    )

    mock_session = AsyncMock()
    mock_session.bind = None  # Force repli Python
    res = MagicMock()
    res.all.return_value = [(chunk, doc)]
    mock_session.execute.return_value = res

    citations = await retriever.search("CPU saturation processus", session=mock_session, entity_id="0")
    assert len(citations) == 1
    assert citations[0].article_id == "KB-CPU-01"
    assert citations[0].relevance_score >= 0.4
