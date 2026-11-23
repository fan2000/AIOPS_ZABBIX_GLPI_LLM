"""Assemblage du graphe LangGraph avec investigation conditionnelle et Human-in-the-Loop persistant."""

from typing import Any, Dict, Optional
from langgraph.graph import END, START, StateGraph
from packages.agents.src.checkpointer import postgres_checkpointer
from packages.agents.src.nodes.correlation_node import correlation_agent_node
from packages.agents.src.nodes.diagnosis_node import diagnosis_agent_node
from packages.agents.src.nodes.feedback_node import feedback_agent_node
from packages.agents.src.nodes.human_approval_node import human_approval_gate_node
from packages.agents.src.nodes.incident_node import incident_agent_node
from packages.agents.src.nodes.investigation_node import investigation_agent_node
from packages.agents.src.nodes.knowledge_node import knowledge_agent_node
from packages.agents.src.nodes.resolution_node import resolution_agent_node
from packages.agents.src.nodes.validation_node import validation_agent_node
from packages.agents.src.state import IncidentAgentState


def route_after_diagnosis(state: IncidentAgentState) -> str:
    """Route vers l'investigation lecture seule si preuves insuffisantes (max 2 tours, arrêt anticipé)."""
    conf = state.get("confidence_detail", {}) or {}
    level = str(conf.get("level", "")).lower()
    iterations = int(state.get("investigation_iterations") or 0)
    max_iter = int(state.get("max_investigation_iterations") or 2)
    exhausted = bool(state.get("investigation_exhausted", False))

    if level == "insufficient_evidence" and not exhausted and iterations < max_iter:
        return "investigation_agent"
    return "resolution_agent"


def route_after_validation(state: IncidentAgentState) -> str:
    """Route vers la porte d'approbation humaine si HITL actif et runbook à risque MEDIUM/HIGH."""
    if bool(state.get("hitl_enabled", False)) and bool(state.get("requires_human_approval", False)):
        return "human_approval_gate"
    return "feedback_agent"


def build_incident_graph() -> StateGraph:
    """Construit le graphe d'orchestration multi-agents LangGraph avec boucles conditionnelles & HITL."""
    graph = StateGraph(IncidentAgentState)

    graph.add_node("incident_agent", incident_agent_node)
    graph.add_node("correlation_agent", correlation_agent_node)
    graph.add_node("knowledge_agent", knowledge_agent_node)
    graph.add_node("diagnosis_agent", diagnosis_agent_node)
    graph.add_node("investigation_agent", investigation_agent_node)
    graph.add_node("resolution_agent", resolution_agent_node)
    graph.add_node("validation_agent", validation_agent_node)
    graph.add_node("human_approval_gate", human_approval_gate_node)
    graph.add_node("feedback_agent", feedback_agent_node)

    # Fan-out parallèle collecte/corrélation/RAG -> diagnostic
    graph.add_edge(START, "incident_agent")
    graph.add_edge("incident_agent", "correlation_agent")
    graph.add_edge("incident_agent", "knowledge_agent")
    graph.add_edge("correlation_agent", "diagnosis_agent")
    graph.add_edge("knowledge_agent", "diagnosis_agent")

    # Boucle conditionnelle d'investigation lecture seule
    graph.add_conditional_edges(
        "diagnosis_agent",
        route_after_diagnosis,
        {
            "investigation_agent": "investigation_agent",
            "resolution_agent": "resolution_agent",
        },
    )
    graph.add_edge("investigation_agent", "diagnosis_agent")

    # Résolution -> Validation -> Porte HITL conditionnelle -> Feedback -> END
    graph.add_edge("resolution_agent", "validation_agent")
    graph.add_conditional_edges(
        "validation_agent",
        route_after_validation,
        {
            "human_approval_gate": "human_approval_gate",
            "feedback_agent": "feedback_agent",
        },
    )
    graph.add_edge("human_approval_gate", "feedback_agent")
    graph.add_edge("feedback_agent", END)

    return graph


# 1. Graphe sans pause (rétro-compatible tests unitaires & mode synchrone)
incident_workflow = build_incident_graph().compile()

# 2. Graphe HITL persistant dans PostgreSQL avec interruption avant la porte humaine
hitl_incident_workflow = build_incident_graph().compile(
    checkpointer=postgres_checkpointer,
    interrupt_before=["human_approval_gate"],
)


async def run_incident_analysis(state: IncidentAgentState) -> IncidentAgentState:
    """Exécution complète synchrone (sans pause HITL) du graphe multi-agents."""
    payload = dict(state)
    payload.setdefault("hitl_enabled", False)
    result = await incident_workflow.ainvoke(payload)
    return result


async def start_hitl_incident_analysis(
    state: IncidentAgentState,
    thread_id: str,
) -> Dict[str, Any]:
    """Démarre une exécution LangGraph persistante (avec mise en pause avant human_approval_gate si requis)."""
    config = {"configurable": {"thread_id": str(thread_id)}}
    payload: IncidentAgentState = {
        **state,
        "hitl_enabled": True,
        "thread_id": str(thread_id),
        "investigation_iterations": int(state.get("investigation_iterations") or 0),
        "max_investigation_iterations": int(state.get("max_investigation_iterations") or 2),
    }
    await hitl_incident_workflow.ainvoke(payload, config=config)
    snapshot = await hitl_incident_workflow.aget_state(config)
    values = dict(snapshot.values) if snapshot and snapshot.values else dict(payload)
    next_nodes = list(snapshot.next or []) if snapshot else []
    checkpoint_id = (snapshot.config or {}).get("configurable", {}).get("checkpoint_id") if snapshot else None

    return {
        "state": values,
        "paused": len(next_nodes) > 0,
        "next_nodes": next_nodes,
        "checkpoint_id": checkpoint_id,
        "thread_id": str(thread_id),
    }


async def resume_hitl_incident_analysis(
    thread_id: str,
    human_approved: bool,
    decided_by: str,
    technician_comment: Optional[str] = None,
    action_execution_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Reprend un graphe LangGraph mis en pause après décision humaine (Approuver ou Rejeter)."""
    config = {"configurable": {"thread_id": str(thread_id)}}
    snapshot = await hitl_incident_workflow.aget_state(config)
    if not snapshot or not snapshot.values:
        raise ValueError(f"Aucun checkpoint LangGraph trouvé pour le thread '{thread_id}'")

    update_payload: Dict[str, Any] = {
        "human_approved": human_approved,
        "decided_by": decided_by,
        "technician_comment": technician_comment,
    }
    if action_execution_result is not None:
        update_payload["action_execution_result"] = action_execution_result

    await hitl_incident_workflow.aupdate_state(config, update_payload)
    await hitl_incident_workflow.ainvoke(None, config=config)

    final_snapshot = await hitl_incident_workflow.aget_state(config)
    values = dict(final_snapshot.values) if final_snapshot and final_snapshot.values else {}
    next_nodes = list(final_snapshot.next or []) if final_snapshot else []
    checkpoint_id = (
        (final_snapshot.config or {}).get("configurable", {}).get("checkpoint_id")
        if final_snapshot
        else None
    )

    return {
        "state": values,
        "paused": len(next_nodes) > 0,
        "next_nodes": next_nodes,
        "checkpoint_id": checkpoint_id,
        "thread_id": str(thread_id),
    }


async def get_hitl_thread_state(thread_id: str) -> Dict[str, Any]:
    """Consulte l'état d'un thread LangGraph persisté (en pause ou terminé)."""
    config = {"configurable": {"thread_id": str(thread_id)}}
    snapshot = await hitl_incident_workflow.aget_state(config)
    if not snapshot or not snapshot.values:
        return {
            "exists": False,
            "thread_id": str(thread_id),
            "paused": False,
            "next_nodes": [],
            "checkpoint_id": None,
            "hitl_status": "not_found",
        }
    next_nodes = list(snapshot.next or [])
    checkpoint_id = (snapshot.config or {}).get("configurable", {}).get("checkpoint_id")
    values = dict(snapshot.values)
    return {
        "exists": True,
        "thread_id": str(thread_id),
        "paused": len(next_nodes) > 0,
        "next_nodes": next_nodes,
        "checkpoint_id": checkpoint_id,
        "hitl_status": values.get("hitl_status", "waiting_human_approval" if next_nodes else "completed"),
        "requires_human_approval": bool(values.get("requires_human_approval", False)),
        "pending_approval_action": values.get("pending_approval_action"),
    }
