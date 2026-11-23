"""Moteur de recherche hybride RAG natif PostgreSQL (pgvector HNSW + FTS GIN + RRF SQL) avec repli Python."""

import json
import os
import re
import time
from typing import Any, Dict, List, Literal, Optional
from sqlalchemy import ARRAY, Boolean, Float, Integer, String, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import async_session_maker
from packages.contracts.src.ai import KnowledgeSourceCitation
from packages.domain.models.database import KnowledgeChunk, KnowledgeDocument
from packages.observability.src.metrics import record_rag_search
from packages.rag.src.embeddings import embeddings_service

SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.20"))
MAX_QUERY_LENGTH = 500


def cosine_similarity(v1: Any, v2: Any) -> float:
    """Calcule la similarité cosinus entre deux vecteurs numériques."""
    if v1 is None or v2 is None:
        return 0.0
    try:
        len1 = len(v1)
        len2 = len(v2)
    except TypeError:
        return 0.0
    if len1 == 0 or len1 != len2:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(v1, v2))
    norm1 = sum(float(a) * float(a) for a in v1) ** 0.5
    norm2 = sum(float(b) * float(b) for b in v2) ** 0.5
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def _clean_query_tokens(query: str) -> List[str]:
    """Extrait jusqu'à 12 jetons normalisés uniques pour construction sécurisée de tsquery."""
    raw_tokens = re.findall(r"[a-zA-Z0-9_À-ÿ]+", query.lower())
    clean_terms: List[str] = []
    seen = set()
    for tok in raw_tokens:
        sanitized = re.sub(r"[^a-z0-9_à-ÿ]", "", tok)
        if len(sanitized) >= 2 and sanitized not in seen:
            seen.add(sanitized)
            clean_terms.append(sanitized)
        if len(clean_terms) >= 12:
            break
    return clean_terms


def build_safe_or_tsquery(query: str) -> str:
    """Construit une expression tsquery PostgreSQL sécurisée en mode OR préfixé (: *)."""
    return " | ".join(f"{term}:*" for term in _clean_query_tokens(query))


def build_safe_plain_or_query(query: str) -> str:
    """Construit une expression tsquery OR sans suffixe :* afin d'activer les stemmers french/english."""
    return " | ".join(_clean_query_tokens(query))


def _normalize_source_type(raw: Optional[str]) -> Literal["glpi_kb", "resolved_ticket", "runbook_doc", "wiki"]:
    """Préserve les 4 types de sources documentaires autorisés dans KnowledgeSourceCitation."""
    val = (raw or "").strip().lower()
    if val == "resolved_ticket" or "ticket" in val:
        return "resolved_ticket"
    if val == "runbook_doc" or "runbook" in val:
        return "runbook_doc"
    if val == "wiki":
        return "wiki"
    return "glpi_kb" if ("kb" in val or val == "") else "wiki"


def _is_postgres_session(session: AsyncSession) -> bool:
    """Détermine si la session cible une base PostgreSQL (production pgvector)."""
    bind = getattr(session, "bind", None)
    dialect = getattr(bind, "dialect", None) if bind is not None else None
    return getattr(dialect, "name", "") == "postgresql"


_META_FILTER_SQL = """
  AND (:filter_os = FALSE OR lower(coalesce(c.metadata_fields->>'os', 'all')) = ANY(:os_values))
  AND (
      :filter_service = FALSE
      OR lower(coalesce(c.metadata_fields->>'service', '')) = :service_val
      OR coalesce(c.metadata_fields->'services', '[]'::jsonb) @> CAST(:service_json AS jsonb)
  )
  AND (:filter_site = FALSE OR upper(coalesce(c.metadata_fields->>'site_code', 'GLOBAL')) = ANY(:site_values))
  AND (:filter_category = FALSE OR lower(coalesce(c.metadata_fields->>'category', 'general')) = :category_val)
  AND (:filter_updated = FALSE OR coalesce(c.metadata_fields->>'updated_at', '') >= :updated_after)
"""


def _normalize_metadata_filters(filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = filters or {}
    os_raw = str(raw.get("os") or "").strip().lower()
    os_active = bool(os_raw and os_raw not in ("all", "*"))
    os_values = [os_raw, "cross_platform", "all"] if os_active else []

    svc_raw = str(raw.get("service") or "").strip().lower()
    svc_active = bool(svc_raw and svc_raw != "general")

    site_raw = str(raw.get("site_code") or "").strip().upper()
    site_active = bool(site_raw and site_raw != "*")
    site_values = (
        ["GLOBAL"] if site_raw == "GLOBAL" else [site_raw, "GLOBAL"]
    ) if site_active else []

    cat_raw = str(raw.get("category") or "").strip().lower()
    cat_active = bool(cat_raw and cat_raw not in ("all", "*"))

    upd_raw = str(raw.get("updated_after") or "").strip()
    upd_active = bool(upd_raw)

    return {
        "filter_os": os_active,
        "os_raw": os_raw,
        "os_values": os_values,
        "filter_service": svc_active,
        "service_val": svc_raw,
        "service_json": json.dumps([svc_raw]) if svc_active else "[]",
        "filter_site": site_active,
        "site_values": site_values,
        "filter_category": cat_active,
        "category_val": cat_raw,
        "filter_updated": upd_active,
        "updated_after": upd_raw,
    }


def _matches_metadata_filters(chunk_meta: Optional[Dict[str, Any]], norm: Dict[str, Any]) -> bool:
    meta = chunk_meta or {}
    if norm["filter_os"]:
        chunk_os = str(meta.get("os") or "all").strip().lower()
        if chunk_os not in norm["os_values"]:
            return False
    if norm["filter_service"]:
        svc = str(meta.get("service") or "").strip().lower()
        svcs = [str(s).strip().lower() for s in (meta.get("services") or [])]
        if svc != norm["service_val"] and norm["service_val"] not in svcs:
            return False
    if norm["filter_site"]:
        site = str(meta.get("site_code") or "GLOBAL").strip().upper()
        if site not in norm["site_values"]:
            return False
    if norm["filter_category"]:
        cat = str(meta.get("category") or "general").strip().lower()
        if cat != norm["category_val"]:
            return False
    if norm["filter_updated"]:
        upd = str(meta.get("updated_at") or "")
        if not upd or upd < norm["updated_after"]:
            return False
    return True


class HybridRetriever:
    """Recherche hybride dense (pgvector HNSW) et lexicale (FTS GIN) avec Reciprocal Rank Fusion (RRF)."""

    def __init__(self, top_k: int = 4, threshold: float = SIMILARITY_THRESHOLD):
        self.top_k = top_k
        self.threshold = threshold

    async def search(
        self,
        query: str,
        session: Optional[AsyncSession] = None,
        entity_id: str = "0",
        allowed_entities: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        source_types: Optional[List[str]] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeSourceCitation]:
        """Exécute une recherche hybride et retourne les passages sourcés qualifiés."""
        if not query or not query.strip():
            return []

        t0 = time.perf_counter()
        # Borne maximale anti-DoS / ReDoS (CWE-20)
        clean_query = query.strip()[:MAX_QUERY_LENGTH]
        try:
            query_vector = await embeddings_service.get_embedding(clean_query)
        except Exception:
            query_vector = embeddings_service._generate_deterministic_fallback(clean_query)

        if allowed_entities is not None:
            entities_filter = list(dict.fromkeys(allowed_entities))
        else:
            entities_filter = list(dict.fromkeys([str(entity_id), "0"]))

        clean_sources = [str(s).strip().lower() for s in (source_types or []) if str(s).strip()] or None
        effective_top_k = max(1, min(20, top_k or self.top_k))

        if session is not None:
            res = await self._execute_search(
                clean_query,
                query_vector,
                entities_filter,
                effective_top_k,
                session,
                clean_sources,
                metadata_filters,
            )
            record_rag_search("hybrid", time.perf_counter() - t0)
            return res

        async with async_session_maker() as standalone_session:
            res = await self._execute_search(
                clean_query,
                query_vector,
                entities_filter,
                effective_top_k,
                standalone_session,
                clean_sources,
                metadata_filters,
            )
            record_rag_search("hybrid", time.perf_counter() - t0)
            return res

    async def _execute_search(
        self,
        clean_query: str,
        query_vector: List[float],
        entities_filter: List[str],
        effective_top_k: int,
        session: AsyncSession,
        source_types: Optional[List[str]] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeSourceCitation]:
        if _is_postgres_session(session):
            try:
                sql_results = await self._execute_search_postgres_sql(
                    clean_query,
                    query_vector,
                    entities_filter,
                    effective_top_k,
                    session,
                    source_types,
                    metadata_filters,
                )
                return sql_results
            except Exception as sql_err:
                # Repli gracieux si colonnes/index pas encore migrés dans une instance éphémère
                print(f"Avertissement repli recherche RAG Python ({sql_err})")

        return await self._execute_search_python(
            clean_query,
            query_vector,
            entities_filter,
            effective_top_k,
            session,
            source_types,
            metadata_filters,
        )

    async def _execute_search_postgres_sql(
        self,
        clean_query: str,
        query_vector: List[float],
        entities_filter: List[str],
        effective_top_k: int,
        session: AsyncSession,
        source_types: Optional[List[str]] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeSourceCitation]:
        """Exécute la fusion RRF vectorielle HNSW + Full-Text bilingue GIN + filtres JSONB en SQL."""
        allow_all = "*" in entities_filter
        env_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"
        include_fallback_env = os.getenv("RAG_INCLUDE_FALLBACK_EMBEDDINGS")
        if include_fallback_env is not None:
            include_fallback = include_fallback_env.lower() in ("true", "1", "yes")
        else:
            include_fallback = not env_prod

        ef_search = max(10, min(400, int(os.getenv("RAG_HNSW_EF_SEARCH", "64"))))
        try:
            await session.execute(
                text("SELECT set_config('hnsw.ef_search', :ef, true)"),
                {"ef": str(ef_search)},
            )
        except Exception:
            pass

        cand_limit = max(25, effective_top_k * 8)
        vec_literal = "[" + ",".join(f"{float(x):.6f}" for x in query_vector) + "]"
        tsq_prefix = build_safe_or_tsquery(clean_query)
        tsq_stem = build_safe_plain_or_query(clean_query)
        filter_sources = bool(source_types)
        meta_norm = _normalize_metadata_filters(metadata_filters)

        sql = text(
            f"""
            WITH vec_candidates AS (
                SELECT
                    c.id AS chunk_id,
                    (1.0 - (c.embedding <=> CAST(:qvec AS vector))) AS vec_sim,
                    ROW_NUMBER() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector) ASC) AS vec_rank
                FROM knowledge_chunks c
                JOIN knowledge_documents d ON d.id = c.document_id
                WHERE (:allow_all = TRUE OR c.entity_id = ANY(:entities))
                  AND (:filter_sources = FALSE OR d.source_type = ANY(:source_types))
                  AND c.embedding IS NOT NULL
                  AND (:include_fallback = TRUE OR c.is_fallback_embedding = FALSE)
                  {_META_FILTER_SQL}
                ORDER BY c.embedding <=> CAST(:qvec AS vector) ASC
                LIMIT :cand_limit
            ),
            fts_candidates AS (
                SELECT
                    c.id AS chunk_id,
                    (
                        0.6 * ts_rank_cd(
                            d.title_tsv_multi,
                            (to_tsquery('french', :tsq_stem) || to_tsquery('english', :tsq_stem) || to_tsquery('simple', :tsq_prefix))
                        )
                        + 0.4 * ts_rank_cd(
                            c.search_tsv_multi,
                            (to_tsquery('french', :tsq_stem) || to_tsquery('english', :tsq_stem) || to_tsquery('simple', :tsq_prefix))
                        )
                    ) AS fts_score,
                    ROW_NUMBER() OVER (
                        ORDER BY (
                            0.6 * ts_rank_cd(
                                d.title_tsv_multi,
                                (to_tsquery('french', :tsq_stem) || to_tsquery('english', :tsq_stem) || to_tsquery('simple', :tsq_prefix))
                            )
                            + 0.4 * ts_rank_cd(
                                c.search_tsv_multi,
                                (to_tsquery('french', :tsq_stem) || to_tsquery('english', :tsq_stem) || to_tsquery('simple', :tsq_prefix))
                            )
                        ) DESC
                    ) AS fts_rank
                FROM knowledge_chunks c
                JOIN knowledge_documents d ON d.id = c.document_id
                WHERE :tsq_stem <> ''
                  AND (:allow_all = TRUE OR c.entity_id = ANY(:entities))
                  AND (:filter_sources = FALSE OR d.source_type = ANY(:source_types))
                  {_META_FILTER_SQL}
                  AND (
                      d.title_tsv_multi @@ (to_tsquery('french', :tsq_stem) || to_tsquery('english', :tsq_stem) || to_tsquery('simple', :tsq_prefix))
                      OR c.search_tsv_multi @@ (to_tsquery('french', :tsq_stem) || to_tsquery('english', :tsq_stem) || to_tsquery('simple', :tsq_prefix))
                  )
                ORDER BY fts_score DESC
                LIMIT :cand_limit
            ),
            fused AS (
                SELECT
                    COALESCE(v.chunk_id, f.chunk_id) AS chunk_id,
                    COALESCE(v.vec_sim, 0.0) AS vec_sim,
                    COALESCE(f.fts_score, 0.0) AS fts_score,
                    (f.fts_rank IS NOT NULL) AS has_fts_match,
                    ROUND(
                        LEAST(
                            1.0,
                            GREATEST(
                                COALESCE(v.vec_sim, 0.0),
                                (
                                    COALESCE(1.0 / (60.0 + v.vec_rank), 0.0)
                                    + COALESCE(1.0 / (60.0 + f.fts_rank), 0.0)
                                ) / (2.0 / 61.0)
                            )
                        )::numeric,
                        3
                    )::float AS rrf_score
                FROM vec_candidates v
                FULL OUTER JOIN fts_candidates f ON v.chunk_id = f.chunk_id
            )
            SELECT
                d.external_id,
                d.title,
                d.source_type,
                c.chunk_text,
                c.metadata_fields,
                fused.rrf_score
            FROM fused
            JOIN knowledge_chunks c ON c.id = fused.chunk_id
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE (fused.has_fts_match = TRUE OR fused.vec_sim >= :threshold)
              AND fused.rrf_score >= :threshold
            ORDER BY fused.rrf_score DESC, fused.fts_score DESC, fused.vec_sim DESC
            LIMIT :top_k
            """
        ).bindparams(
            bindparam("qvec", type_=String),
            bindparam("tsq_prefix", type_=String),
            bindparam("tsq_stem", type_=String),
            bindparam("allow_all", type_=Boolean),
            bindparam("filter_sources", type_=Boolean),
            bindparam("include_fallback", type_=Boolean),
            bindparam("entities", type_=ARRAY(String)),
            bindparam("source_types", type_=ARRAY(String)),
            bindparam("filter_os", type_=Boolean),
            bindparam("os_values", type_=ARRAY(String)),
            bindparam("filter_service", type_=Boolean),
            bindparam("service_val", type_=String),
            bindparam("service_json", type_=String),
            bindparam("filter_site", type_=Boolean),
            bindparam("site_values", type_=ARRAY(String)),
            bindparam("filter_category", type_=Boolean),
            bindparam("category_val", type_=String),
            bindparam("filter_updated", type_=Boolean),
            bindparam("updated_after", type_=String),
            bindparam("cand_limit", type_=Integer),
            bindparam("threshold", type_=Float),
            bindparam("top_k", type_=Integer),
        )

        rows = (
            await session.execute(
                sql,
                {
                    "qvec": vec_literal,
                    "tsq_prefix": tsq_prefix,
                    "tsq_stem": tsq_stem,
                    "allow_all": allow_all,
                    "filter_sources": filter_sources,
                    "include_fallback": include_fallback,
                    "entities": [str(e) for e in entities_filter if e != "*"] or ["0"],
                    "source_types": source_types or [],
                    "filter_os": meta_norm["filter_os"],
                    "os_values": meta_norm["os_values"],
                    "filter_service": meta_norm["filter_service"],
                    "service_val": meta_norm["service_val"],
                    "service_json": meta_norm["service_json"],
                    "filter_site": meta_norm["filter_site"],
                    "site_values": meta_norm["site_values"],
                    "filter_category": meta_norm["filter_category"],
                    "category_val": meta_norm["category_val"],
                    "filter_updated": meta_norm["filter_updated"],
                    "updated_after": meta_norm["updated_after"],
                    "cand_limit": cand_limit,
                    "threshold": float(self.threshold),
                    "top_k": effective_top_k,
                },
            )
        ).all()

        citations: List[KnowledgeSourceCitation] = []
        for ext_id, title, source_type, chunk_text, meta_fields, score in rows:
            bounded_score = min(1.0, max(0.0, float(score)))
            src_lit = _normalize_source_type(source_type)
            citations.append(
                KnowledgeSourceCitation(
                    article_id=str(ext_id),
                    title=str(title),
                    source_type=src_lit,
                    relevance_score=bounded_score,
                    snippet=(chunk_text or "")[:300] + ("..." if len(chunk_text or "") > 300 else ""),
                    metadata=dict(meta_fields or {}),
                )
            )
        return citations

    async def _execute_search_python(
        self,
        clean_query: str,
        query_vector: List[float],
        entities_filter: List[str],
        effective_top_k: int,
        session: AsyncSession,
        source_types: Optional[List[str]] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeSourceCitation]:
        """Repli Python compatible SQLite/Mocks acceptant tout itérable ou ndarray pgvector."""
        stmt = select(KnowledgeChunk, KnowledgeDocument).join(
            KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id
        )
        if "*" not in entities_filter:
            stmt = stmt.where(KnowledgeChunk.entity_id.in_(entities_filter))
        if source_types:
            stmt = stmt.where(KnowledgeDocument.source_type.in_(source_types))

        results = (await session.execute(stmt)).all()
        norm_filters = _normalize_metadata_filters(metadata_filters)
        scored_candidates: List[Dict[str, Any]] = []
        keywords = [w.lower() for w in re.findall(r"[a-zA-Z0-9_\-\.\/À-ÿ]+", clean_query) if len(w) >= 2]

        for chunk, doc in results:
            if not _matches_metadata_filters(getattr(chunk, "metadata_fields", None), norm_filters):
                continue
            vec_score = 0.0
            emb = getattr(chunk, "embedding", None)
            if emb is not None:
                try:
                    if len(emb) == len(query_vector):
                        vec_score = max(0.0, cosine_similarity(query_vector, emb))
                except TypeError:
                    vec_score = 0.0

            title_lower = (doc.title or "").lower()
            text_lower = (chunk.chunk_text or "").lower()

            title_matches = sum(1 for kw in keywords if kw in title_lower)
            text_matches = sum(1 for kw in keywords if kw in text_lower)

            title_score = title_matches / max(1, len(keywords))
            text_score = text_matches / max(1, len(keywords))
            lex_score = min(1.0, 0.6 * title_score + 0.4 * text_score)

            if lex_score > 0:
                hybrid_score = round(max(0.4 * vec_score + 0.6 * lex_score, 0.2 * vec_score + 0.8 * lex_score), 3)
            else:
                hybrid_score = round(vec_score, 3)

            if hybrid_score >= self.threshold or lex_score >= 0.25:
                scored_candidates.append({
                    "chunk": chunk,
                    "doc": doc,
                    "score": max(hybrid_score, round(lex_score, 3)),
                })

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        top_items = scored_candidates[:effective_top_k]

        citations: List[KnowledgeSourceCitation] = []
        for item in top_items:
            doc = item["doc"]
            chunk = item["chunk"]
            bounded_score = min(1.0, max(0.0, float(item["score"])))
            src_lit = _normalize_source_type(doc.source_type)
            citations.append(
                KnowledgeSourceCitation(
                    article_id=doc.external_id,
                    title=doc.title,
                    source_type=src_lit,
                    relevance_score=bounded_score,
                    snippet=chunk.chunk_text[:300] + ("..." if len(chunk.chunk_text) > 300 else ""),
                    metadata=dict(getattr(chunk, "metadata_fields", None) or {}),
                )
            )

        return citations


hybrid_retriever = HybridRetriever()
