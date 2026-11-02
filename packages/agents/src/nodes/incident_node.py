"""Nœud Agent Incident : Extraction des faits, symptômes et métriques."""

from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState


async def incident_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Analyse les alertes, extrait les symptômes prouvés et construit les observations initiales."""
    primary_event = state.get("primary_event", {})
    events = state.get("events", [primary_event])
    host_name = state.get("host_name", "UNKNOWN-HOST")

    observations: List[str] = []
    
    # Extraction des métriques réelles prouvées
    problem = primary_event.get("problem", "Anomalie non spécifiée")
    severity = primary_event.get("severity", "WARNING")
    metric = primary_event.get("metric")
    val = primary_event.get("value")

    observations.append(f"Alerte Zabbix principale : {problem} (Sévérité : {severity})")
    if metric and val is not None:
        observations.append(f"Métrique observée : {metric} = {val}")

    if len(events) > 1:
        observations.append(f"Nombre d'événements groupés pour cet incident : {len(events)}")

    asset_info = state.get("asset_info", {})
    if asset_info and asset_info.get("operatingsystem"):
        observations.append(f"Système d'exploitation : {asset_info['operatingsystem']}")

    return {"observations": observations}
