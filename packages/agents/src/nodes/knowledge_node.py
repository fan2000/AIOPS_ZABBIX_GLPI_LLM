"""Nœud Agent Connaissances : Interrogation du moteur RAG pgvector et filtrage multi-entités."""

import time
from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.observability.src.metrics import record_agent_execution
from packages.rag.src.retriever import hybrid_retriever


async def knowledge_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Recherche les articles de connaissances et runbooks associés aux symptômes via RAG hybride."""
    t0 = time.perf_counter()
    primary_event = state.get("primary_event", {})
    problem = primary_event.get("problem", "")
    metric = primary_event.get("metric", "")
    entity_id = str(state.get("entity_id") or "0")

    query = f"{problem} {metric}".strip()
    citations_data: List[Dict[str, Any]] = list(state.get("rag_citations", []))
    search_status = "ok"

    if not citations_data and query and not bool(state.get("skip_rag_lookup", False)):
        asset_info = state.get("asset_info") or {}
        os_raw = str(asset_info.get("operatingsystem") or "").lower()
        meta_filters: Dict[str, Any] = {}
        if "windows" in os_raw:
            meta_filters["os"] = "windows"
        elif any(k in os_raw for k in ("linux", "ubuntu", "debian", "rhel", "centos")):
            meta_filters["os"] = "linux"
        if asset_info.get("site_code"):
            meta_filters["site_code"] = str(asset_info["site_code"])

        try:
            citations = []
            if meta_filters:
                try:
                    citations = await hybrid_retriever.search(
                        query=query, entity_id=entity_id, top_k=3, metadata_filters=meta_filters
                    )
                except TypeError:
                    citations = []
            if not citations:
                citations = await hybrid_retriever.search(query=query, entity_id=entity_id, top_k=3)
            citations_data = [c.model_dump(mode="json") for c in citations]
        except Exception:
            citations_data = []
            search_status = "degraded"

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("knowledge_agent", search_status)

    return {
        "rag_citations": citations_data,
        "rag_searched": True,
        "agent_telemetry": {
            "Knowledge Agent": {"duration_ms": dur_ms, "status": search_status, "citations_count": len(citations_data)}
        },
    }
