"""Worker de synchronisation et d'ingestion documentaire GLPI vers pgvector."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import List
from sqlalchemy import func, select
from database.connection import async_session_maker
from packages.connectors.glpi.src.client import glpi_client
from packages.domain.models.database import KnowledgeChunk, KnowledgeDocument, KnowledgeSyncJob
from packages.rag.src.chunker import clean_html, text_chunker
from packages.rag.src.embeddings import embeddings_service


class KnowledgeWorker:
    """Synchronise les articles de la base de connaissances GLPI vers la base vectorielle."""

    async def sync_glpi_kb(self) -> KnowledgeSyncJob:
        """Exécute un cycle de synchronisation incrémentale."""
        job_id = uuid.uuid4()
        started_at = datetime.now(timezone.utc)

        async with async_session_maker() as session:
            job = KnowledgeSyncJob(
                id=job_id,
                source="glpi_kb",
                status="running",
                started_at=started_at,
            )
            session.add(job)
            await session.commit()

            try:
                kb_items = await glpi_client.get_knowledge_items(limit=100)
                imported_docs = 0
                indexed_chunks = 0

                for item in kb_items:
                    cleaned = clean_html(item.answer)
                    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

                    # Vérification si document déjà indexé et inchangé
                    doc_stmt = select(KnowledgeDocument).where(
                        KnowledgeDocument.source_type == "glpi_kb",
                        KnowledgeDocument.external_id == str(item.id),
                    )
                    existing_doc = (await session.execute(doc_stmt)).scalar_one_or_none()

                    if existing_doc and existing_doc.content_hash == content_hash:
                        existing_doc.last_synced_at = datetime.now(timezone.utc)
                        continue  # Inchangé

                    if existing_doc:
                        existing_doc.raw_content = cleaned
                        existing_doc.content_hash = content_hash
                        existing_doc.version += 1
                        existing_doc.last_synced_at = datetime.now(timezone.utc)
                        doc_obj = existing_doc
                    else:
                        doc_obj = KnowledgeDocument(
                            id=uuid.uuid4(),
                            source_type="glpi_kb",
                            external_id=str(item.id),
                            title=item.name,
                            entity_id=str(item.entities_id),
                            raw_content=cleaned,
                            content_hash=content_hash,
                        )
                        session.add(doc_obj)
                        await session.flush()

                    imported_docs += 1

                    # Découpage et vectorisation
                    chunks = text_chunker.split_text(cleaned)
                    for idx, chunk_text in enumerate(chunks):
                        vec = await embeddings_service.get_embedding(chunk_text)
                        chunk_obj = KnowledgeChunk(
                            id=uuid.uuid4(),
                            document_id=doc_obj.id,
                            chunk_index=idx,
                            chunk_text=chunk_text,
                            entity_id=doc_obj.entity_id,
                            embedding=vec,
                        )
                        session.add(chunk_obj)
                        indexed_chunks += 1

                # Nombre total de documents actifs en base
                total_docs = (await session.execute(select(func.count(KnowledgeDocument.id)))).scalar() or len(kb_items)
                total_chunks = (await session.execute(select(func.count(KnowledgeChunk.id)))).scalar() or indexed_chunks

                job.status = "completed"
                job.documents_imported = total_docs
                job.chunks_indexed = total_chunks
                job.finished_at = datetime.now(timezone.utc)
                await session.commit()
                return job

            except Exception as e:
                job.status = "failed"
                job.error_message = str(e)
                job.finished_at = datetime.now(timezone.utc)
                await session.commit()
                return job


knowledge_worker = KnowledgeWorker()
