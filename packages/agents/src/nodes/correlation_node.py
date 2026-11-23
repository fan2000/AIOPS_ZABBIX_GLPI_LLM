"""Nœud Agent Corrélation : Évaluation des dépendances et signatures d'incidents."""

import time
from typing import Any, Dict
from packages.agents.src.state import IncidentAgentState
from packages.observability.src.metrics import record_agent_execution


async def correlation_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Examine les événements associés et identifie les relations de cause à effet."""
    t0 = time.perf_counter()
    events = state.get("events", [])
    observations = list(state.get("observations", []))

    is_correlated = len(events) > 1
    reason = "Alerte isolée"

    if is_correlated:
        triggers = [str(e.get("problem", "")) for e in events if e.get("problem")]
        reason = f"Corrélation multi-alertes ({len(events)} événements) sur {state.get('host_name')} : {', '.join(triggers[:3])}"
        observations.append(f"Analyse de corrélation : {reason}")

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("correlation_agent", "success")

    return {
        "is_correlated": is_correlated,
        "correlation_reason": reason,
        "observations": observations,
        "agent_telemetry": {
            "Correlation Agent": {"duration_ms": dur_ms, "status": "ok", "correlated": is_correlated}
        },
    }
