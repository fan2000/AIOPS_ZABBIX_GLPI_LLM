"""Tests unitaires P1 #4 : Chunking sémantique HTML/Markdown, Contextual Retrieval & filtres métadonnées RAG."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from packages.domain.models.database import KnowledgeChunk, KnowledgeDocument
from packages.rag.src.chunker import (
    TextChunker,
    extract_operational_metadata,
    html_to_structured_text,
)
from packages.rag.src.embeddings import EmbeddingsService
from packages.rag.src.retriever import HybridRetriever


def test_html_to_structured_text_preserves_headings_code_and_lists():
    """Convertit HTML en Markdown structuré en préservant titres, blocs <pre><code> et listes."""
    raw_html = (
        "<h2>Diagnostic Disque</h2>"
        "<p>Inspecter l'occupation des partitions sous Ubuntu Linux :</p>"
        "<ul><li>Lister les gros fichiers</li><li>Vérifier <code>df -h /var/log</code></li></ul>"
        "<pre><code>find /var/log -type f -name '*.gz' -mtime +15\nsystemctl status nginx</code></pre>"
    )
    structured = html_to_structured_text(raw_html)
    assert "## Diagnostic Disque" in structured
    assert "- Lister les gros fichiers" in structured
    assert "`df -h /var/log`" in structured
    assert "```\nfind /var/log -type f -name '*.gz' -mtime +15\nsystemctl status nginx\n```" in structured


def test_semantic_chunker_atomic_code_list_and_overlap_ratio():
    """Préserve les blocs de code atomiques, sépare les sections et applique un overlap entre 15% et 20%."""
    chunker = TextChunker()
    ratio = chunker.chunk_overlap / chunker.chunk_size
    assert 0.15 <= ratio <= 0.20

    doc_html = (
        "<h1>Procédure Purge Nginx</h1>"
        "<p>Cette section décrit la vérification initiale des logs volumineux sur /var/log/nginx.</p>"
        "<pre><code>ls -lh /var/log/nginx\nsystemctl status nginx\ndf -h /var/log</code></pre>"
        "<h2>Validation Post-Purge</h2>"
        "<p>Vérifier ensuite que les workers nginx traitent correctement les requêtes HTTP sur le port 443.</p>"
    )
    chunks = chunker.chunk_document(doc_html, title="Procédure Purge Nginx", source_type="glpi_kb")
    assert len(chunks) >= 2
    assert any(c.has_code_block for c in chunks)
    # Le bloc de code multi-lignes ne doit jamais être coupé en deux
    code_chunk = next(c for c in chunks if c.has_code_block)
    assert "ls -lh /var/log/nginx\nsystemctl status nginx\ndf -h /var/log" in code_chunk.raw_text
    assert code_chunk.section == "Procédure Purge Nginx"
    assert chunks[-1].section == "Validation Post-Purge"

    # Vérifier le recouvrement réel entre chunks de prose consécutifs
    small_chunker = TextChunker(chunk_size=260, chunk_overlap=45)
    prose = (
        "Un incident critique survient lorsque le répertoire /var/log accumule des journaux non compressés "
        "pendant plusieurs semaines sans rotation logrotate active sur le serveur Debian. "
        "L'opérateur doit alors contrôler les inodes libres, vérifier les descripteurs ouverts avec lsof "
        "et exécuter la purge approuvée avant de confirmer la reprise applicative dans GLPI."
    )
    prose_chunks = small_chunker.chunk_document(prose, title="Rotation Logs", source_type="glpi_kb")
    assert len(prose_chunks) >= 2
    tail_words = prose_chunks[0].raw_text.split()[-3:]
    assert any(w in prose_chunks[1].raw_text for w in tail_words)


def test_extract_operational_metadata_matrix():
    """Déduit os (linux, windows, cross_platform, network), service, category et site_code."""
    m_linux = extract_operational_metadata(
        "Purge disque /var/log DC-PAR-1",
        "Exécuter df -h et systemctl reload nginx sur Ubuntu.",
    )
    assert m_linux["os"] == "linux"
    assert m_linux["category"] == "disk"
    assert m_linux["service"] == "nginx"
    assert "nginx" in m_linux["services"]
    assert m_linux["site_code"] == "DC-PAR-1"

    m_win = extract_operational_metadata(
        "Service Spooler arrêté",
        "Exécuter Restart-Service Spooler en PowerShell sous Windows Server.",
    )
    assert m_win["os"] == "windows"
    assert m_win["category"] == "service"
    assert m_win["service"] == "spooler"

    m_cross = extract_operational_metadata(
        "Saturation CPU anormale",
        "Identifier les processus avec top sous Linux ou Get-Process sous Windows.",
    )
    assert m_cross["os"] == "cross_platform"
    assert m_cross["category"] == "cpu"

    m_net = extract_operational_metadata(
        "Perte BGP routeur cœur OT-LYON-01",
        "Vérifier l'état du voisin BGP et la configuration VLAN Cisco IOS.",
    )
    assert m_net["os"] == "network"
    assert m_net["category"] == "network"
    assert m_net["service"] == "bgp"
    assert m_net["site_code"] == "OT-LYON-01"


def test_chunk_document_contextual_prefix_and_schema_v2():
    """Chaque chunk embarque l'en-tête Contextual Retrieval et les métadonnées structurées v2."""
    chunker = TextChunker()
    chunks = chunker.chunk_document(
        "<p>Purger les fichiers logs expirés sur /var/log pour libérer la partition nginx sur SITE-MRS-02.</p>",
        title="Nettoyage /var/log",
        source_type="glpi_kb",
        metadata={"updated_at": "2026-11-20T12:00:00Z"},
    )
    assert len(chunks) == 1
    c = chunks[0]
    assert c.text.startswith("[Source: GLPI KB | OS: linux | Service: nginx | Catégorie: disk | Site: SITE-MRS-02 | Titre: Nettoyage /var/log] ")
    assert c.metadata["chunk_schema_version"] == 2
    assert c.metadata["updated_at"] == "2026-11-20T12:00:00Z"


@pytest.mark.asyncio
async def test_retriever_metadata_filters_exclude_mismatching_os_and_return_metadata():
    """HybridRetriever filtre strictement par metadata_filters (os, category) et expose citation.metadata."""
    retriever = HybridRetriever(top_k=4, threshold=0.10)
    dev_svc = EmbeddingsService(allow_fallback=True)
    q = "disque plein nettoyage"
    vec = dev_svc._generate_deterministic_fallback(q)

    doc_linux = KnowledgeDocument(
        id=uuid4(),
        external_id="KB-LIN-1",
        title="Disque plein /var/log Linux",
        source_type="glpi_kb",
        entity_id="0",
        raw_content="Purger /var/log sous Linux",
        content_hash="h1",
    )
    chunk_linux = KnowledgeChunk(
        id=uuid4(),
        document_id=doc_linux.id,
        chunk_index=0,
        chunk_text="[Source: GLPI KB | OS: linux | Catégorie: disk] Purge disque plein Linux /var/log.",
        entity_id="0",
        metadata_fields={
            "os": "linux",
            "category": "disk",
            "service": "general",
            "services": [],
            "site_code": "GLOBAL",
            "updated_at": "2026-11-20T10:00:00Z",
        },
        embedding=vec,
    )

    doc_win = KnowledgeDocument(
        id=uuid4(),
        external_id="KB-WIN-1",
        title="Disque C plein Windows",
        source_type="glpi_kb",
        entity_id="0",
        raw_content="Purger Temp sous Windows",
        content_hash="h2",
    )
    chunk_win = KnowledgeChunk(
        id=uuid4(),
        document_id=doc_win.id,
        chunk_index=0,
        chunk_text="[Source: GLPI KB | OS: windows | Catégorie: disk] Nettoyage disque plein Windows Temp.",
        entity_id="0",
        metadata_fields={
            "os": "windows",
            "category": "disk",
            "service": "general",
            "services": [],
            "site_code": "DC-PAR-1",
            "updated_at": "2026-11-20T10:00:00Z",
        },
        embedding=vec,
    )

    mock_session = AsyncMock()
    mock_session.bind = None
    res = MagicMock()
    res.all.return_value = [(chunk_linux, doc_linux), (chunk_win, doc_win)]
    mock_session.execute.return_value = res

    hits_linux = await retriever.search(
        q,
        session=mock_session,
        entity_id="0",
        metadata_filters={"os": "linux", "category": "disk"},
    )
    assert len(hits_linux) == 1
    assert hits_linux[0].article_id == "KB-LIN-1"
    assert hits_linux[0].metadata["os"] == "linux"
    assert hits_linux[0].metadata["category"] == "disk"
