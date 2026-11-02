"""Nœud Agent Corrélation : Évaluation des dépendances et signatures d'incidents."""

from typing import Any, Dict
from packages.agents.src.state import IncidentAgentState


async def correlation_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Examine les événements associés et identifie les relations de cause à effet."""
    events = state.get("events", [])
    primary_event = state.get("primary_event", {})
    observations = list(state.get("observations", []))

    is_correlated = len(events) > 1
    reason = "Alerte isolée"

    if is_correlated:
        triggers = [e.get("problem", "") for e in events]
        reason = f"Corrélation multi-alertes sur {state.get('host_name')} : {', '.join(triggers[:3])}"
        observations.append(f"Analyse de corrélation : {reason}")

    return {
        "is_correlated": is_correlated,
        "correlation_reason": reason,
        "observations": observations,
    }
