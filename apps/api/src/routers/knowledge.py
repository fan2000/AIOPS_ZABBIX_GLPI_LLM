"""Gestion et consultation de la base de connaissances et recherche RAG."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_db_session
from packages.domain.models.database import KnowledgeDocument
from packages.rag.src.retriever import hybrid_retriever
from services.knowledge_worker.src.worker import knowledge_worker

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge & RAG"])


class SearchRequest(BaseModel):
    query: str
    entity_id: str = "0"
    top_k: int = 4


@router.get("/documents")
async def list_knowledge_documents(
    limit: int = Query(50, le=100),
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
async def trigger_kb_sync() -> Dict[str, Any]:
    """Déclenche manuellement la synchronisation des articles GLPI."""
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
