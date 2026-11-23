"""Gestion sécurisée de la base de connaissances, recherche RAG RRF et validation des propositions KB."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.src.dependencies.auth import (
    AuthenticatedUserContext,
    get_current_user,
    get_knowledge_read_user,
)
from database.connection import get_db_session
from packages.connectors.glpi.src.client import glpi_client
from packages.domain.models.database import (
    AuditLog,
    Incident,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbeddingDLQ,
    KnowledgeProposal,
    KnowledgeSyncJob,
)
from packages.observability.src.metrics import set_rag_index_health
from packages.rag.src.chunker import text_chunker
from packages.rag.src.embeddings import embeddings_service
from packages.rag.src.graph_rag import build_operational_graph
from packages.rag.src.quality import detect_knowledge_gaps
from packages.rag.src.retriever import hybrid_retriever
from packages.security.src.rate_limiter import default_limiter
from services.knowledge_worker.src.worker import knowledge_worker

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge & RAG"])

_kb_sync_lock = asyncio.Lock()


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500, description="Requête textuelle ou symptômes")
    entity_id: Optional[str] = Field(None, max_length=50)
    top_k: int = Field(4, ge=1, le=20)
    limit: Optional[int] = Field(None, ge=1, le=20)
    source_types: Optional[List[Literal["glpi_kb", "resolved_ticket", "runbook_doc", "wiki"]]] = None
    os: Optional[str] = Field(None, max_length=30)
    service: Optional[str] = Field(None, max_length=60)
    site_code: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=50)
    updated_after: Optional[str] = Field(None, max_length=40)


class ProposalDecisionRequest(BaseModel):
    publish_to_glpi: bool = True
    edited_title: Optional[str] = Field(None, max_length=255)
    edited_content: Optional[str] = None
    rejection_reason: Optional[str] = Field(None, max_length=500)


class GapDraftProposalRequest(BaseModel):
    incident_id: UUID
    title: str = Field(..., min_length=3, max_length=255)
    family_key: Optional[str] = Field(None, max_length=255)
    category: str = Field("AIOps - Knowledge Gap", max_length=120)
    inferred_os: Optional[str] = Field(None, max_length=40)
    affected_hosts: List[str] = Field(default_factory=list)


def _build_gap_draft_content(inc: Incident, req: GapDraftProposalRequest) -> str:
    """Génère un brouillon structuré de procédure KB à partir d'un Knowledge Gap détecté."""
    hosts_str = ", ".join(req.affected_hosts) if req.affected_hosts else inc.primary_asset_name
    os_hint = (req.inferred_os or "all").lower()
    if os_hint == "windows":
        diag_cmds = (
            "Get-Service | Where-Object {$_.Status -ne 'Running'}\n"
            "Get-EventLog -LogName System -Newest 25 | Format-Table TimeGenerated,EntryType,Source,Message"
        )
    elif os_hint == "network":
        diag_cmds = (
            "show ip interface brief\n"
            "show logging | last 30"
        )
    else:
        diag_cmds = (
            "systemctl status --failed\n"
            "top -b -n 1 | head -n 20\n"
            "df -h && journalctl -p err -n 30 --no-pager"
        )

    return (
        f"<h2>Symptômes & Périmètre</h2>\n"
        f"<p><strong>Famille d'incidents :</strong> {req.family_key or inc.title}</p>\n"
        f"<p><strong>Sévérité observée :</strong> {inc.severity} • <strong>Hôtes impactés :</strong> {hosts_str}</p>\n"
        f"<p>Ce brouillon a été généré suite à la détection d'un déficit documentaire RAG (Knowledge Gap).</p>\n\n"
        f"<h2>1. Vérifications préalables ({os_hint})</h2>\n"
        f"<pre><code>{diag_cmds}</code></pre>\n\n"
        f"<h2>2. Procédure de remédiation recommandée</h2>\n"
        f"<ul>\n"
        f"<li>Valider l'état du service/composant cible avant toute action corrective.</li>\n"
        f"<li>Compléter ici les commandes certifiées ou le runbook associé.</li>\n"
        f"</ul>\n\n"
        f"<h2>3. Contrôles post-action</h2>\n"
        f"<ul>\n"
        f"<li>Vérifier la résolution du déclencheur Zabbix et l'absence de récurrence sous 15 minutes.</li>\n"
        f"</ul>"
    )


def _require_operator_and_rate_limit(
    current_user: AuthenticatedUserContext,
    request: Request,
    bucket: str,
    action_label: str,
) -> None:
    """Vérifie le rôle opérateur/admin et applique la limitation de débit par IP (CWE-285 / CWE-770)."""
    if not current_user.has_sufficient_role("operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Droits insuffisants : le rôle 'operator' ou 'admin' est requis pour {action_label}.",
        )
    client_ip = request.client.host if request.client else "unknown"
    if not default_limiter.is_allowed(f"{bucket}:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes simultanées. Veuillez patienter avant de réessayer.",
        )


@router.get("/stats")
async def get_knowledge_stats(
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retourne les métriques réelles d'indexation pgvector (HNSW, GIN, fallback, propositions)."""
    scope = current_user.resolve_entity_scope(None)

    doc_stmt = select(func.count(KnowledgeDocument.id))
    chunk_stmt = select(func.count(KnowledgeChunk.id))
    fb_chunk_stmt = select(func.count(KnowledgeChunk.id)).where(
        KnowledgeChunk.is_fallback_embedding == True
    )
    prop_stmt = select(func.count(KnowledgeProposal.id)).where(
        KnowledgeProposal.status == "pending_review"
    )

    if "*" not in scope:
        doc_stmt = doc_stmt.where(KnowledgeDocument.entity_id.in_(scope))
        chunk_stmt = chunk_stmt.where(KnowledgeChunk.entity_id.in_(scope))
        fb_chunk_stmt = fb_chunk_stmt.where(KnowledgeChunk.entity_id.in_(scope))
        prop_stmt = prop_stmt.where(KnowledgeProposal.entity_id.in_(scope))

    docs_count = int((await session.execute(doc_stmt)).scalar() or 0)
    chunks_count = int((await session.execute(chunk_stmt)).scalar() or 0)
    fallback_chunks_count = int((await session.execute(fb_chunk_stmt)).scalar() or 0)
    pending_proposals_count = int((await session.execute(prop_stmt)).scalar() or 0)

    hnsw_active = False
    gin_active = False
    fts_bilingual_active = False
    metadata_gin_index_active = False
    bind = getattr(session, "bind", None)
    if bind is not None and getattr(getattr(bind, "dialect", None), "name", "") == "postgresql":
        try:
            idx_rows = (
                await session.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename IN ('knowledge_chunks', 'knowledge_documents')")
                )
            ).scalars().all()
            idx_names = set(idx_rows)
            hnsw_active = "ix_knowledge_chunks_embedding_hnsw" in idx_names
            gin_active = (
                "ix_knowledge_chunks_search_tsv_gin" in idx_names
                and "ix_knowledge_documents_title_tsv_gin" in idx_names
            )
            fts_bilingual_active = (
                "ix_knowledge_chunks_search_tsv_multi_gin" in idx_names
                and "ix_knowledge_documents_title_tsv_multi_gin" in idx_names
            )
            metadata_gin_index_active = "ix_knowledge_chunks_metadata_fields_gin" in idx_names
        except Exception:
            pass

    dlq_pending_count = 0
    try:
        dlq_stmt = select(func.count(KnowledgeEmbeddingDLQ.id)).where(
            KnowledgeEmbeddingDLQ.status == "pending_retry"
        )
        if "*" not in scope:
            dlq_stmt = dlq_stmt.where(KnowledgeEmbeddingDLQ.entity_id.in_(scope))
        dlq_pending_count = int((await session.execute(dlq_stmt)).scalar() or 0)
    except Exception:
        dlq_pending_count = 0

    contextual_chunks_count = 0
    try:
        ctx_stmt = select(func.count(KnowledgeChunk.id)).where(
            KnowledgeChunk.metadata_fields.op("->>")("chunk_schema_version") == "2"
        )
        if "*" not in scope:
            ctx_stmt = ctx_stmt.where(KnowledgeChunk.entity_id.in_(scope))
        contextual_chunks_count = int((await session.execute(ctx_stmt)).scalar() or 0)
    except Exception:
        contextual_chunks_count = 0

    emb_health = embeddings_service.get_health_status()
    set_rag_index_health(dlq_pending_count, fallback_chunks_count)

    return {
        "documents_count": docs_count,
        "chunks_count": chunks_count,
        "fallback_chunks_count": fallback_chunks_count,
        "real_embedding_chunks_count": max(0, chunks_count - fallback_chunks_count),
        "contextual_chunks_count": contextual_chunks_count,
        "chunk_overlap_pct": round((text_chunker.chunk_overlap / text_chunker.chunk_size) * 100, 1),
        "pending_proposals_count": pending_proposals_count,
        "dlq_pending_count": dlq_pending_count,
        "hnsw_index_active": hnsw_active,
        "gin_index_active": gin_active,
        "fts_bilingual_active": fts_bilingual_active,
        "metadata_gin_index_active": metadata_gin_index_active,
        "embedding_model": embeddings_service.model_name,
        "embedding_provider": emb_health["provider"],
        "embedding_version": emb_health["version"],
        "embedding_circuit_state": emb_health["circuit_state"],
        "embedding_batch_size": emb_health["batch_size"],
        "allow_fallback_embeddings": embeddings_service.allow_fallback,
        "allowed_entities": current_user.allowed_entities,
    }


@router.get("/sync-jobs")
async def list_sync_jobs(
    limit: int = Query(10, ge=1, le=50),
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Retourne l'historique des jobs de synchronisation KB GLPI."""
    stmt = select(KnowledgeSyncJob).order_by(desc(KnowledgeSyncJob.started_at)).limit(limit)
    jobs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(j.id),
            "source": j.source,
            "status": j.status,
            "documents_imported": j.documents_imported,
            "chunks_indexed": j.chunks_indexed,
            "started_at": j.started_at.isoformat(),
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "error_message": j.error_message,
        }
        for j in jobs
    ]


@router.get("/documents")
async def list_knowledge_documents(
    limit: int = Query(50, ge=1, le=100),
    entity_id: Optional[str] = Query(None, max_length=50),
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste les documents de connaissances indexés avec isolation multi-entités."""
    allowed_scope = current_user.resolve_entity_scope(entity_id)
    stmt = select(KnowledgeDocument)
    if "*" not in allowed_scope:
        stmt = stmt.where(KnowledgeDocument.entity_id.in_(allowed_scope))
    stmt = stmt.order_by(desc(KnowledgeDocument.last_synced_at)).limit(limit)

    docs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(d.id),
            "external_id": d.external_id,
            "title": d.title,
            "source_type": d.source_type,
            "entity_id": d.entity_id,
            "version": d.version,
            "last_synced_at": d.last_synced_at.isoformat(),
        }
        for d in docs
    ]


@router.get("/documents/{document_id}")
async def get_knowledge_document_detail(
    document_id: UUID,
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retourne le détail d'un document et ses chunks pgvector après vérification stricte multi-entités."""
    doc = (
        await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document de connaissances introuvable")

    if not current_user.can_access_entity(doc.entity_id):
        session.add(
            AuditLog(
                user_id=current_user.id,
                action="KB_IDOR_BLOCKED",
                resource_type="knowledge_document",
                resource_id=str(document_id),
                details={
                    "username": current_user.username,
                    "target_entity": doc.entity_id,
                    "allowed_entities": current_user.allowed_entities,
                },
            )
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à l'entité GLPI de ce document (isolation multi-sites)",
        )

    chunks = (
        await session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc.id)
            .order_by(asc(KnowledgeChunk.chunk_index))
        )
    ).scalars().all()

    return {
        "id": str(doc.id),
        "external_id": doc.external_id,
        "title": doc.title,
        "source_type": doc.source_type,
        "entity_id": doc.entity_id,
        "raw_content": doc.raw_content,
        "content_hash": doc.content_hash,
        "version": doc.version,
        "last_synced_at": doc.last_synced_at.isoformat(),
        "chunks": [
            {
                "id": str(c.id),
                "chunk_index": c.chunk_index,
                "chunk_text": c.chunk_text,
                "metadata_fields": getattr(c, "metadata_fields", None) or {},
                "embedding_model": c.embedding_model,
                "embedding_version": c.embedding_version,
                "is_fallback_embedding": bool(c.is_fallback_embedding),
            }
            for c in chunks
        ],
    }


@router.get("/dlq")
async def list_embedding_dlq(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste la file DLQ des documents en échec d'embeddings (opérateur/admin requis)."""
    if not current_user.has_sufficient_role("operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits insuffisants : le rôle 'operator' ou 'admin' est requis pour consulter la DLQ RAG.",
        )

    scope = current_user.resolve_entity_scope(None)
    stmt = select(KnowledgeEmbeddingDLQ)
    if "*" not in scope:
        stmt = stmt.where(KnowledgeEmbeddingDLQ.entity_id.in_(scope))
    if status_filter:
        stmt = stmt.where(KnowledgeEmbeddingDLQ.status == status_filter)
    stmt = stmt.order_by(desc(KnowledgeEmbeddingDLQ.updated_at)).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "document_id": str(r.document_id) if r.document_id else None,
            "source_type": r.source_type,
            "external_id": r.external_id,
            "entity_id": r.entity_id,
            "title": r.title,
            "status": r.status,
            "attempts": r.attempts,
            "max_attempts": r.max_attempts,
            "last_error": r.last_error,
            "next_retry_at": r.next_retry_at.isoformat() if r.next_retry_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.post("/dlq/retry")
async def retry_embedding_dlq(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Relance l'indexation réelle des documents présents dans la DLQ embeddings."""
    _require_operator_and_rate_limit(current_user, request, "kb_dlq_retry", "relancer la DLQ embeddings")
    scope = current_user.resolve_entity_scope(None)
    summary = await knowledge_worker.retry_dlq_items(limit=limit, entity_scope=scope, require_real=True)

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="KB_DLQ_RETRY_TRIGGERED",
            resource_type="knowledge_embedding_dlq",
            resource_id="batch",
            details={"triggered_by": current_user.username, **summary},
        )
    )
    await session.commit()
    return summary


@router.post("/reindex-fallback")
async def reindex_fallback_chunks(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Réindexe avec le provider d'embeddings actif les documents marqués is_fallback_embedding=True."""
    _require_operator_and_rate_limit(
        current_user, request, "kb_reindex_fallback", "réindexer les chunks fallback"
    )
    scope = current_user.resolve_entity_scope(None)
    summary = await knowledge_worker.reindex_fallback_chunks(
        entity_scope=scope, limit=limit, require_real=True
    )

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="KB_REINDEX_FALLBACK_TRIGGERED",
            resource_type="knowledge_chunk",
            resource_id="batch",
            details={"triggered_by": current_user.username, **summary},
        )
    )
    await session.commit()
    return summary


@router.post("/reindex-contextual")
async def reindex_contextual_chunks(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Réindexe les documents en chunking sémantique v2 avec Contextual Retrieval et métadonnées."""
    _require_operator_and_rate_limit(
        current_user, request, "kb_reindex_contextual", "réindexer les chunks contextuels"
    )
    scope = current_user.resolve_entity_scope(None)
    summary = await knowledge_worker.reindex_contextual_chunks(entity_scope=scope, limit=limit)

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="KB_REINDEX_CONTEXTUAL_TRIGGERED",
            resource_type="knowledge_chunk",
            resource_id="contextual_v2",
            details={"triggered_by": current_user.username, **summary},
        )
    )
    await session.commit()
    return summary


@router.post("/sync")
async def trigger_kb_sync(
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Déclenche la synchronisation des articles GLPI (RBAC operator/admin, rate-limiting & verrou CWE-770)."""
    _require_operator_and_rate_limit(current_user, request, "kb_sync", "synchroniser la KB")

    if _kb_sync_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une synchronisation de la base de connaissances est déjà en cours d'exécution.",
        )

    async with _kb_sync_lock:
        job = await knowledge_worker.sync_glpi_kb()
        session.add(
            AuditLog(
                user_id=current_user.id,
                action="KB_SYNC_TRIGGERED",
                resource_type="knowledge_sync_job",
                resource_id=str(job.id),
                details={
                    "triggered_by": current_user.username,
                    "status": job.status,
                    "documents_imported": job.documents_imported,
                    "chunks_indexed": job.chunks_indexed,
                },
            )
        )
        await session.commit()
        return {
            "job_id": str(job.id),
            "status": job.status,
            "documents_imported": job.documents_imported,
            "chunks_indexed": job.chunks_indexed,
        }


@router.post("/search")
async def search_knowledge(
    req: SearchRequest,
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Recherche hybride pgvector HNSW + Full-Text GIN RRF avec isolation multi-entités."""
    allowed_scope = current_user.resolve_entity_scope(req.entity_id)
    effective_k = req.limit or req.top_k
    meta_filters: Dict[str, Any] = {}
    if req.os:
        meta_filters["os"] = req.os
    if req.service:
        meta_filters["service"] = req.service
    if req.site_code:
        meta_filters["site_code"] = req.site_code
    if req.category:
        meta_filters["category"] = req.category
    if req.updated_after:
        meta_filters["updated_after"] = req.updated_after

    search_kwargs: Dict[str, Any] = {
        "session": session,
        "entity_id": req.entity_id or "0",
        "allowed_entities": allowed_scope,
        "top_k": effective_k,
        "source_types": req.source_types,
    }
    if meta_filters:
        search_kwargs["metadata_filters"] = meta_filters

    citations = await hybrid_retriever.search(req.query, **search_kwargs)
    return [c.model_dump() for c in citations]


@router.get("/proposals")
async def list_kb_proposals(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste les propositions d'articles générées par le Feedback Agent / techniciens."""
    allowed_scope = current_user.resolve_entity_scope(None)
    stmt = select(KnowledgeProposal)
    if "*" not in allowed_scope:
        stmt = stmt.where(KnowledgeProposal.entity_id.in_(allowed_scope))
    if status_filter:
        stmt = stmt.where(KnowledgeProposal.status == status_filter)
    stmt = stmt.order_by(desc(KnowledgeProposal.created_at)).limit(limit)

    props = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(p.id),
            "incident_id": str(p.incident_id),
            "title": p.title,
            "category": p.category,
            "content": p.content,
            "entity_id": p.entity_id,
            "status": p.status,
            "created_by": p.created_by,
            "reviewed_by": p.reviewed_by,
            "glpi_kb_id": p.glpi_kb_id,
            "created_at": p.created_at.isoformat(),
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        }
        for p in props
    ]


@router.post("/proposals/{proposal_id}/approve")
async def approve_kb_proposal(
    proposal_id: UUID,
    req: Optional[ProposalDecisionRequest] = None,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Approuve une proposition KB, la publie vers GLPI (best-effort) et l'indexe dans pgvector."""
    if not current_user.has_sufficient_role("operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits insuffisants : le rôle 'operator' ou 'admin' est requis pour approuver une fiche KB.",
        )

    prop = (
        await session.execute(select(KnowledgeProposal).where(KnowledgeProposal.id == proposal_id))
    ).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Proposition KB introuvable")

    if not current_user.can_access_entity(prop.entity_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à l'entité GLPI de cette proposition",
        )

    if req and req.edited_title:
        prop.title = req.edited_title
    if req and req.edited_content:
        prop.content = req.edited_content

    glpi_kb_id: Optional[str] = prop.glpi_kb_id
    publish_glpi = True if req is None else req.publish_to_glpi
    if publish_glpi and not glpi_kb_id:
        try:
            ent_num = int(prop.entity_id) if str(prop.entity_id).isdigit() else 0
            created_id = await glpi_client.create_knowledge_item(prop.title, prop.content, entities_id=ent_num)
            if created_id is not None:
                glpi_kb_id = str(created_id)
        except Exception:
            pass

    # Indexation immédiate dans pgvector pour rendre le retour d'expérience searchable par le RAG
    indexed_doc = await knowledge_worker.index_custom_document(
        title=prop.title,
        content=prop.content,
        source_type="glpi_kb" if glpi_kb_id else "wiki",
        external_id=glpi_kb_id or f"PROP-{str(prop.id)[:8].upper()}",
        entity_id=prop.entity_id,
    )

    prop.status = "approved_published"
    prop.reviewed_by = current_user.username
    prop.reviewed_at = datetime.now(timezone.utc)
    if glpi_kb_id:
        prop.glpi_kb_id = glpi_kb_id

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="KB_PROPOSAL_APPROVED",
            resource_type="knowledge_proposal",
            resource_id=str(prop.id),
            details={
                "reviewed_by": current_user.username,
                "glpi_kb_id": glpi_kb_id,
                "indexed_document_id": str(indexed_doc.id),
            },
        )
    )
    await session.commit()

    return {
        "proposal_id": str(prop.id),
        "status": prop.status,
        "glpi_kb_id": prop.glpi_kb_id,
        "indexed_document_id": str(indexed_doc.id),
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject_kb_proposal(
    proposal_id: UUID,
    req: Optional[ProposalDecisionRequest] = None,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Rejette une proposition KB générée par l'IA."""
    if not current_user.has_sufficient_role("operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits insuffisants pour rejeter une proposition KB.",
        )

    prop = (
        await session.execute(select(KnowledgeProposal).where(KnowledgeProposal.id == proposal_id))
    ).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Proposition KB introuvable")

    if not current_user.can_access_entity(prop.entity_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à l'entité GLPI de cette proposition",
        )

    prop.status = "rejected"
    prop.reviewed_by = current_user.username
    prop.reviewed_at = datetime.now(timezone.utc)

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="KB_PROPOSAL_REJECTED",
            resource_type="knowledge_proposal",
            resource_id=str(prop.id),
            details={
                "reviewed_by": current_user.username,
                "reason": req.rejection_reason if req else None,
            },
        )
    )
    await session.commit()

    return {
        "proposal_id": str(prop.id),
        "status": prop.status,
    }


@router.get("/quality")
async def get_rag_quality_metrics(
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Expose les métriques continues de qualité RAG (Faithfulness, Citations, Recall@5, MRR, Gaps)."""
    scope = current_user.resolve_entity_scope(None)
    result = await detect_knowledge_gaps(session=session, entity_scope=scope, limit=5)
    return {
        **result["metrics"],
        "top_gaps": result["gaps"],
    }


@router.get("/gaps")
async def list_knowledge_gaps(
    min_relevance: float = Query(0.45, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retourne les familles d'incidents récurrentes sans couverture documentaire RAG suffisante."""
    scope = current_user.resolve_entity_scope(None)
    return await detect_knowledge_gaps(
        session=session,
        entity_scope=scope,
        min_relevance=min_relevance,
        limit=limit,
    )


@router.post("/gaps/draft-proposal", status_code=status.HTTP_201_CREATED)
async def create_proposal_from_gap(
    req: GapDraftProposalRequest,
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Crée en 1 clic un brouillon de procédure KB dans la file de validation à partir d'un Knowledge Gap."""
    _require_operator_and_rate_limit(current_user, request, "kb_gap_draft", "créer un brouillon KB")

    inc = (
        await session.execute(select(Incident).where(Incident.id == req.incident_id))
    ).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident de référence introuvable pour ce Knowledge Gap")

    if not current_user.can_access_entity(inc.entity_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à l'entité GLPI de cet incident",
        )

    prop_id = uuid4()
    proposal = KnowledgeProposal(
        id=prop_id,
        incident_id=inc.id,
        title=req.title.strip(),
        category=req.category.strip() or "AIOps - Knowledge Gap",
        content=_build_gap_draft_content(inc, req),
        entity_id=inc.entity_id,
        status="pending_review",
        created_by=f"gap-detector:{current_user.username}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(proposal)
    session.add(
        AuditLog(
            id=uuid4(),
            user_id=current_user.id,
            action="KB_GAP_PROPOSAL_CREATED",
            resource_type="knowledge_proposal",
            resource_id=str(prop_id),
            details={
                "incident_id": str(inc.id),
                "family_key": req.family_key,
                "title": proposal.title,
                "created_by": current_user.username,
            },
        )
    )
    await session.commit()

    return {
        "id": str(proposal.id),
        "incident_id": str(proposal.incident_id),
        "title": proposal.title,
        "category": proposal.category,
        "content": proposal.content,
        "entity_id": proposal.entity_id,
        "status": proposal.status,
        "created_by": proposal.created_by,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
    }


@router.get("/graph")
async def get_knowledge_graph(
    q: Optional[str] = Query(None, max_length=120),
    asset: Optional[str] = Query(None, max_length=120),
    limit_incidents: int = Query(50, ge=5, le=150),
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Expose le GraphRAG léger Asset CMDB ↔ Service ↔ Incidents ↔ KB ↔ Runbooks."""
    scope = current_user.resolve_entity_scope(None)
    return await build_operational_graph(
        session=session,
        entity_scope=scope,
        focus_query=q,
        asset_name=asset,
        limit_incidents=limit_incidents,
    )
