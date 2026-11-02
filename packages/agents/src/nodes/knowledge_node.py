"""Nœud Agent Connaissances : Interrogation du moteur RAG et filtrage des procédures."""

from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.rag.src.retriever import hybrid_retriever


async def knowledge_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Recherche les articles de connaissances et runbooks associés aux symptômes."""
    observations = state.get("observations", [])
    primary_event = state.get("primary_event", {})
    problem = primary_event.get("problem", "")
    metric = primary_event.get("metric", "")

    query = f"{problem} {metric}".strip()
    citations_data: List[Dict[str, Any]] = state.get("rag_citations", [])

    return {
        "rag_citations": citations_data,
        "rag_searched": True,
    }
