"""Moteur de recherche hybride RAG (vectorielle + lexicale) avec Reciprocal Rank Fusion."""

import os
from typing import Any, Dict, List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from packages.contracts.src.ai import KnowledgeSourceCitation
from packages.domain.models.database import KnowledgeChunk, KnowledgeDocument
from packages.rag.src.embeddings import embeddings_service

SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.55"))


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class HybridRetriever:
    """Recherche hybride dense (vectorielle) et sparse (mots-clés) avec filtrage par entité."""

    def __init__(self, top_k: int = 4, threshold: float = SIMILARITY_THRESHOLD):
        self.top_k = top_k
        self.threshold = threshold

    async def search(
        self,
        query: str,
        session: AsyncSession,
        entity_id: str = "0",
        allowed_entities: Optional[List[str]] = None,
    ) -> List[KnowledgeSourceCitation]:
        """Exécute une recherche hybride et retourne les passages sourcés qualifiés."""
        if not query.strip():
            return []

        query_vector = await embeddings_service.get_embedding(query)
        entities_filter = allowed_entities or [entity_id, "0"]

        # 1. Sélection des chunks éligibles par entité
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeChunk.entity_id.in_(entities_filter))
        )
        results = (await session.execute(stmt)).all()

        scored_candidates: List[Dict[str, Any]] = []

        keywords = [w.lower() for w in query.split() if len(w) > 3]

        for chunk, doc in results:
            # Score vectoriel
            vec_score = 0.0
            if isinstance(chunk.embedding, list) and chunk.embedding:
                vec_score = max(0.0, cosine_similarity(query_vector, chunk.embedding))

            # Score lexical basique
            text_lower = chunk.chunk_text.lower()
            lex_matches = sum(1 for kw in keywords if kw in text_lower)
            lex_score = min(1.0, lex_matches / max(1, len(keywords)))

            # Fusion RRF (Reciprocal Rank Fusion simplifiée)
            hybrid_score = round(0.7 * vec_score + 0.3 * lex_score, 3)

            if hybrid_score >= self.threshold:
                scored_candidates.append({
                    "chunk": chunk,
                    "doc": doc,
                    "score": hybrid_score,
                })

        # Tri décroissant par score combiné
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        top_items = scored_candidates[:self.top_k]

        citations: List[KnowledgeSourceCitation] = []
        for item in top_items:
            doc: KnowledgeDocument = item["doc"]
            chunk: KnowledgeChunk = item["chunk"]
            citations.append(
                KnowledgeSourceCitation(
                    article_id=doc.external_id,
                    title=doc.title,
                    source_type="glpi_kb" if "kb" in doc.source_type.lower() else "wiki",
                    relevance_score=item["score"],
                    snippet=chunk.chunk_text[:300] + ("..." if len(chunk.chunk_text) > 300 else ""),
                )
            )

        return citations


hybrid_retriever = HybridRetriever()
