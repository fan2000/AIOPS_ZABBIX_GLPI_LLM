"""Assemblage du graphe d'états LangGraph pour l'orchestration des 7 agents."""

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from packages.agents.src.nodes.correlation_node import correlation_agent_node
from packages.agents.src.nodes.diagnosis_node import diagnosis_agent_node
from packages.agents.src.nodes.feedback_node import feedback_agent_node
from packages.agents.src.nodes.incident_node import incident_agent_node
from packages.agents.src.nodes.knowledge_node import knowledge_agent_node
from packages.agents.src.nodes.resolution_node import resolution_agent_node
from packages.agents.src.nodes.validation_node import validation_agent_node
from packages.agents.src.state import IncidentAgentState


def build_incident_graph() -> StateGraph:
    """Construit et compile le graphe d'orchestration multi-agents LangGraph."""
    graph = StateGraph(IncidentAgentState)

    # Ajout des 7 agents sous forme de nœuds typés
    graph.add_node("incident_agent", incident_agent_node)
    graph.add_node("correlation_agent", correlation_agent_node)
    graph.add_node("knowledge_agent", knowledge_agent_node)
    graph.add_node("diagnosis_agent", diagnosis_agent_node)
    graph.add_node("resolution_agent", resolution_agent_node)
    graph.add_node("validation_agent", validation_agent_node)
    graph.add_node("feedback_agent", feedback_agent_node)

    # Définition des transitions séquentielles déterministes
    graph.add_edge(START, "incident_agent")
    graph.add_edge("incident_agent", "correlation_agent")
    graph.add_edge("correlation_agent", "knowledge_agent")
    graph.add_edge("knowledge_agent", "diagnosis_agent")
    graph.add_edge("diagnosis_agent", "resolution_agent")
    graph.add_edge("resolution_agent", "validation_agent")
    graph.add_edge("validation_agent", END)

    return graph


# Compilation du graphe
incident_workflow = build_incident_graph().compile()


async def run_incident_analysis(state: IncidentAgentState) -> IncidentAgentState:
    """Point d'entrée pour l'exécution asynchrone complète du graphe sur un incident."""
    result = await incident_workflow.ainvoke(state)
    return result
