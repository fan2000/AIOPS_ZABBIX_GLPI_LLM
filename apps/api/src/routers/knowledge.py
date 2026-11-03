"""Gestion et consultation de la base de connaissances et recherche RAG."""

import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_db_session
from packages.domain.models.database import KnowledgeDocument
from packages.rag.src.retriever import hybrid_retriever
from packages.security.src.rate_limiter import default_limiter
from services.knowledge_worker.src.worker import knowledge_worker

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge & RAG"])

_kb_sync_lock = asyncio.Lock()


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500, description="Requête textuelle ou symptômes")
    entity_id: str = Field("0", max_length=50)
    top_k: int = Field(4, ge=1, le=20)


@router.get("/documents")
async def list_knowledge_documents(
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste les documents de connaissances indexés."""
    stmt = select(KnowledgeDocument).order_by(desc(KnowledgeDocument.last_synced_at)).limit(limit)
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


@router.post("/sync")
async def trigger_kb_sync(request: Request) -> Dict[str, Any]:
    """Déclenche la synchronisation des articles GLPI avec rate-limiting et verrouillage concurrent (CWE-770)."""
    client_ip = request.client.host if request.client else "unknown"
    if not default_limiter.is_allowed(f"kb_sync:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes de synchronisation. Veuillez patienter avant de réessayer.",
        )

    if _kb_sync_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une synchronisation de la base de connaissances est déjà en cours d'exécution.",
        )

    async with _kb_sync_lock:
        job = await knowledge_worker.sync_glpi_kb()
        return {
            "job_id": str(job.id),
            "status": job.status,
            "documents_imported": job.documents_imported,
            "chunks_indexed": job.chunks_indexed,
        }


@router.post("/search")
async def search_knowledge(
    req: SearchRequest,
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Recherche hybride vectorielle et textuelle avec reranking."""
    citations = await hybrid_retriever.search(req.query, session, entity_id=req.entity_id)
    return [c.model_dump() for c in citations]
