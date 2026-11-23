"""Worker de synchronisation, batch embeddings, anti-corruption DLQ et réindexation pgvector."""

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import async_session_maker
from packages.connectors.glpi.src.client import glpi_client
from packages.domain.models.database import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbeddingDLQ,
    KnowledgeSyncJob,
)
from packages.observability.src.metrics import set_rag_index_health
from packages.rag.src.chunker import clean_html, html_to_structured_text, text_chunker
from packages.rag.src.embeddings import embeddings_service


class KnowledgeWorker:
    """Synchronise GLPI/documents vers pgvector avec batching, garde-fou anti-corruption et DLQ."""

    async def _resolve_dlq_for_doc(
        self,
        session: AsyncSession,
        source_type: str,
        external_id: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        await session.execute(
            update(KnowledgeEmbeddingDLQ)
            .where(
                KnowledgeEmbeddingDLQ.source_type == source_type,
                KnowledgeEmbeddingDLQ.external_id == str(external_id),
                KnowledgeEmbeddingDLQ.status == "pending_retry",
            )
            .values(status="resolved", updated_at=now)
        )

    async def _enqueue_embedding_dlq(
        self,
        session: AsyncSession,
        source_type: str,
        external_id: str,
        entity_id: str,
        title: str,
        raw_content: str,
        error_message: str,
        document_id: Optional[uuid.UUID] = None,
    ) -> KnowledgeEmbeddingDLQ:
        now = datetime.now(timezone.utc)
        stmt = select(KnowledgeEmbeddingDLQ).where(
            KnowledgeEmbeddingDLQ.source_type == source_type,
            KnowledgeEmbeddingDLQ.external_id == str(external_id),
            KnowledgeEmbeddingDLQ.status == "pending_retry",
        )
        dlq_row = (await session.execute(stmt)).scalar_one_or_none()
        if dlq_row is not None:
            dlq_row.attempts += 1
            dlq_row.title = title[:255]
            dlq_row.raw_content = raw_content
            dlq_row.entity_id = str(entity_id)
            if document_id is not None:
                dlq_row.document_id = document_id
            dlq_row.last_error = error_message[:1000]
            dlq_row.updated_at = now
            if dlq_row.attempts >= dlq_row.max_attempts:
                dlq_row.status = "exhausted"
                dlq_row.next_retry_at = None
            else:
                dlq_row.next_retry_at = now + timedelta(minutes=min(60, 2**dlq_row.attempts))
            return dlq_row

        dlq_row = KnowledgeEmbeddingDLQ(
            id=uuid.uuid4(),
            document_id=document_id,
            source_type=source_type,
            external_id=str(external_id),
            entity_id=str(entity_id),
            title=title[:255],
            raw_content=raw_content,
            status="pending_retry",
            attempts=1,
            max_attempts=5,
            last_error=error_message[:1000],
            next_retry_at=now + timedelta(minutes=2),
            created_at=now,
            updated_at=now,
        )
        session.add(dlq_row)
        return dlq_row

    async def _refresh_prometheus_health(self, session: AsyncSession) -> None:
        try:
            dlq_cnt = (
                await session.execute(
                    select(func.count(KnowledgeEmbeddingDLQ.id)).where(
                        KnowledgeEmbeddingDLQ.status == "pending_retry"
                    )
                )
            ).scalar() or 0
            fb_cnt = (
                await session.execute(
                    select(func.count(KnowledgeChunk.id)).where(
                        KnowledgeChunk.is_fallback_embedding == True  # noqa: E712
                    )
                )
            ).scalar() or 0
            set_rag_index_health(int(dlq_cnt), int(fb_cnt))
        except Exception:
            pass

    async def _upsert_document_and_chunks(
        self,
        session: AsyncSession,
        source_type: str,
        external_id: str,
        title: str,
        entity_id: str,
        cleaned_content: str,
        metadata_extra: Optional[Dict[str, Any]] = None,
        require_real: Optional[bool] = None,
    ) -> Tuple[KnowledgeDocument, int, bool]:
        """Génère les chunks sémantiques et embeddings en lot avant toute mutation SQL, puis remplace atomiquement."""
        content_hash = hashlib.sha256(f"{title}\n{cleaned_content}".encode("utf-8")).hexdigest()
        base_meta: Dict[str, Any] = {"title": title, "source_type": source_type}
        if metadata_extra:
            base_meta.update(metadata_extra)

        semantic_chunks = text_chunker.chunk_document(
            cleaned_content,
            title=title,
            source_type=source_type,
            metadata=base_meta,
        )
        chunk_texts = [sc.text for sc in semantic_chunks]

        # Anti-corruption : calculer les embeddings AVANT de supprimer/modifier la base
        emb_pairs = (
            await embeddings_service.get_embeddings_batch(chunk_texts, require_real=require_real)
            if chunk_texts
            else []
        )

        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.source_type == source_type,
            KnowledgeDocument.external_id == str(external_id),
        )
        doc_obj = (await session.execute(stmt)).scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if doc_obj is not None:
            doc_obj.title = title
            doc_obj.entity_id = str(entity_id)
            doc_obj.raw_content = cleaned_content
            doc_obj.content_hash = content_hash
            doc_obj.version += 1
            doc_obj.last_synced_at = now
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_obj.id))
        else:
            doc_obj = KnowledgeDocument(
                id=uuid.uuid4(),
                source_type=source_type,
                external_id=str(external_id),
                title=title,
                entity_id=str(entity_id),
                raw_content=cleaned_content,
                content_hash=content_hash,
                last_synced_at=now,
            )
            session.add(doc_obj)
            await session.flush()

        all_real = bool(emb_pairs)
        for idx, (sc, (vec, emb_meta)) in enumerate(zip(semantic_chunks, emb_pairs)):
            is_fb = bool(emb_meta.get("is_fallback", False))
            if is_fb:
                all_real = False
            session.add(
                KnowledgeChunk(
                    id=uuid.uuid4(),
                    document_id=doc_obj.id,
                    chunk_index=idx,
                    chunk_text=sc.text,
                    entity_id=str(entity_id),
                    metadata_fields=dict(sc.metadata),
                    embedding_model=str(emb_meta.get("model", embeddings_service.model_name)),
                    embedding_version=int(emb_meta.get("version", 1)),
                    is_fallback_embedding=is_fb,
                    embedding=vec,
                )
            )

        if all_real:
            await self._resolve_dlq_for_doc(session, source_type, str(external_id))

        return doc_obj, len(semantic_chunks), all_real

    async def sync_glpi_kb(self) -> KnowledgeSyncJob:
        """Exécute une synchronisation incrémentale GLPI avec batching embeddings et file DLQ."""
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
                kb_items = await glpi_client.get_knowledge_items(limit=100, max_items=1000)
                imported_docs = 0
                indexed_chunks = 0
                dlq_enqueued = 0

                for item in kb_items:
                    cleaned = html_to_structured_text(item.answer)
                    if not cleaned:
                        continue  # Ignorer les pages vides (ex: article racine 'Home' sans contenu)

                    content_hash = hashlib.sha256(f"{item.name}\n{cleaned}".encode("utf-8")).hexdigest()
                    doc_stmt = select(KnowledgeDocument).where(
                        KnowledgeDocument.source_type == "glpi_kb",
                        KnowledgeDocument.external_id == str(item.id),
                    )
                    existing_doc = (await session.execute(doc_stmt)).scalar_one_or_none()

                    if existing_doc and existing_doc.content_hash == content_hash:
                        chunk_cnt = (
                            await session.execute(
                                select(func.count(KnowledgeChunk.id)).where(
                                    KnowledgeChunk.document_id == existing_doc.id
                                )
                            )
                        ).scalar() or 0
                        if chunk_cnt > 0:
                            existing_doc.last_synced_at = datetime.now(timezone.utc)
                            continue

                    item_meta: Dict[str, Any] = {"is_faq": item.is_faq}
                    if getattr(item, "date_mod", None):
                        item_meta["updated_at"] = item.date_mod.isoformat()

                    try:
                        _, chunk_count, _ = await self._upsert_document_and_chunks(
                            session=session,
                            source_type="glpi_kb",
                            external_id=str(item.id),
                            title=item.name,
                            entity_id=str(item.entities_id),
                            cleaned_content=cleaned,
                            metadata_extra=item_meta,
                        )
                        imported_docs += 1
                        indexed_chunks += chunk_count
                    except Exception as item_err:
                        await self._enqueue_embedding_dlq(
                            session=session,
                            source_type="glpi_kb",
                            external_id=str(item.id),
                            entity_id=str(item.entities_id),
                            title=item.name,
                            raw_content=cleaned,
                            error_message=str(item_err),
                            document_id=existing_doc.id if existing_doc else None,
                        )
                        dlq_enqueued += 1

                total_docs = (await session.execute(select(func.count(KnowledgeDocument.id)))).scalar() or imported_docs
                total_chunks = (await session.execute(select(func.count(KnowledgeChunk.id)))).scalar() or indexed_chunks

                if dlq_enqueued > 0 and imported_docs == 0:
                    job.status = "failed"
                    job.error_message = f"{dlq_enqueued} document(s) en échec embeddings placés en DLQ."
                elif dlq_enqueued > 0:
                    job.status = "completed_with_dlq"
                    job.error_message = f"{dlq_enqueued} document(s) partiels placés en DLQ."
                else:
                    job.status = "completed"

                job.documents_imported = total_docs
                job.chunks_indexed = total_chunks
                job.finished_at = datetime.now(timezone.utc)
                await self._refresh_prometheus_health(session)
                await session.commit()
                return job

            except Exception as e:
                job.status = "failed"
                job.error_message = str(e)[:1000]
                job.finished_at = datetime.now(timezone.utc)
                await self._refresh_prometheus_health(session)
                await session.commit()
                return job

    async def index_custom_document(
        self,
        title: str,
        content: str,
        source_type: str,
        external_id: str,
        entity_id: str = "0",
        require_real: Optional[bool] = None,
    ) -> KnowledgeDocument:
        """Indexe un document personnalisé ou une proposition KB validée dans pgvector."""
        cleaned = html_to_structured_text(content) or clean_html(content) or content.strip()
        async with async_session_maker() as session:
            doc_obj, _, _ = await self._upsert_document_and_chunks(
                session=session,
                source_type=source_type,
                external_id=str(external_id),
                title=title,
                entity_id=str(entity_id),
                cleaned_content=cleaned,
                require_real=require_real,
            )
            await self._refresh_prometheus_health(session)
            await session.commit()
            return doc_obj

    async def retry_dlq_items(
        self,
        limit: int = 25,
        entity_scope: Optional[List[str]] = None,
        require_real: bool = True,
    ) -> Dict[str, Any]:
        """Retente l'indexation des documents placés dans la DLQ embeddings."""
        processed = 0
        resolved = 0
        failed = 0
        errors: List[str] = []

        async with async_session_maker() as session:
            stmt = select(KnowledgeEmbeddingDLQ).where(
                KnowledgeEmbeddingDLQ.status == "pending_retry"
            )
            if entity_scope and "*" not in entity_scope:
                stmt = stmt.where(KnowledgeEmbeddingDLQ.entity_id.in_(entity_scope))
            stmt = stmt.order_by(KnowledgeEmbeddingDLQ.updated_at).limit(limit)

            rows = list((await session.execute(stmt)).scalars().all())
            for row in rows:
                processed += 1
                try:
                    await self._upsert_document_and_chunks(
                        session=session,
                        source_type=row.source_type,
                        external_id=row.external_id,
                        title=row.title,
                        entity_id=row.entity_id,
                        cleaned_content=row.raw_content,
                        require_real=require_real,
                    )
                    resolved += 1
                except Exception as exc:
                    failed += 1
                    errors.append(f"{row.external_id}: {str(exc)[:180]}")
                    await self._enqueue_embedding_dlq(
                        session=session,
                        source_type=row.source_type,
                        external_id=row.external_id,
                        entity_id=row.entity_id,
                        title=row.title,
                        raw_content=row.raw_content,
                        error_message=str(exc),
                        document_id=row.document_id,
                    )

            await self._refresh_prometheus_health(session)
            await session.commit()

        return {
            "processed": processed,
            "resolved": resolved,
            "failed": failed,
            "errors": errors,
        }

    async def _reindex_document_list(
        self,
        session: AsyncSession,
        docs: List[KnowledgeDocument],
        require_real: Optional[bool],
        success_key: str,
    ) -> Dict[str, Any]:
        """Réindexe une liste de documents avec chunking contextuel v2 et gestion DLQ."""
        processed = 0
        succeeded = 0
        failed = 0
        errors: List[str] = []

        for doc in docs:
            if not doc.raw_content or not doc.raw_content.strip():
                continue
            processed += 1
            try:
                await self._upsert_document_and_chunks(
                    session=session,
                    source_type=doc.source_type,
                    external_id=doc.external_id,
                    title=doc.title,
                    entity_id=doc.entity_id,
                    cleaned_content=doc.raw_content,
                    require_real=require_real,
                )
                succeeded += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{doc.external_id}: {str(exc)[:180]}")
                await self._enqueue_embedding_dlq(
                    session=session,
                    source_type=doc.source_type,
                    external_id=doc.external_id,
                    entity_id=doc.entity_id,
                    title=doc.title,
                    raw_content=doc.raw_content,
                    error_message=str(exc),
                    document_id=doc.id,
                )

        await self._refresh_prometheus_health(session)
        await session.commit()
        return {
            "processed": processed,
            success_key: succeeded,
            "failed": failed,
            "errors": errors,
        }

    async def reindex_fallback_chunks(
        self,
        entity_scope: Optional[List[str]] = None,
        limit: int = 50,
        require_real: bool = True,
    ) -> Dict[str, Any]:
        """Réindexe vers de vrais vecteurs les documents contenant actuellement des chunks fallback."""
        async with async_session_maker() as session:
            doc_ids_stmt = (
                select(KnowledgeDocument.id)
                .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(KnowledgeChunk.is_fallback_embedding == True)  # noqa: E712
                .distinct()
                .limit(limit)
            )
            if entity_scope and "*" not in entity_scope:
                doc_ids_stmt = doc_ids_stmt.where(KnowledgeDocument.entity_id.in_(entity_scope))

            doc_ids = list((await session.execute(doc_ids_stmt)).scalars().all())
            docs: List[KnowledgeDocument] = []
            if doc_ids:
                docs = list(
                    (
                        await session.execute(
                            select(KnowledgeDocument).where(KnowledgeDocument.id.in_(doc_ids))
                        )
                    ).scalars().all()
                )
            return await self._reindex_document_list(session, docs, require_real=require_real, success_key="reindexed")

    async def reindex_contextual_chunks(
        self,
        entity_scope: Optional[List[str]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Réindexe les documents existants avec découpage sémantique v2 et métadonnées contextuelles."""
        async with async_session_maker() as session:
            stmt = select(KnowledgeDocument).limit(limit)
            if entity_scope and "*" not in entity_scope:
                stmt = stmt.where(KnowledgeDocument.entity_id.in_(entity_scope))
            docs = list((await session.execute(stmt)).scalars().all())
            return await self._reindex_document_list(session, docs, require_real=None, success_key="reindexed")


knowledge_worker = KnowledgeWorker()
