"""Nœud Agent Incident : Extraction des faits, symptômes, CMDB et historique métrique Zabbix."""

import time
from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.observability.src.metrics import record_agent_execution


async def incident_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Analyse les alertes, extrait les symptômes prouvés, CMDB et tendances Zabbix."""
    t0 = time.perf_counter()
    primary_event = state.get("primary_event", {})
    events = state.get("events", [primary_event])

    observations: List[str] = []

    problem = primary_event.get("problem", "Anomalie non spécifiée")
    severity = primary_event.get("severity", "WARNING")
    metric = primary_event.get("metric")
    val = primary_event.get("value")

    observations.append(f"Alerte Zabbix principale : {problem} (Sévérité : {severity})")
    if metric and val is not None:
        observations.append(f"Métrique observée : {metric} = {val}")

    if len(events) > 1:
        observations.append(f"Nombre d'événements groupés pour cet incident : {len(events)}")

    # Enrichissement CMDB (GLPI / Asset DB)
    asset_info = state.get("asset_info", {}) or {}
    if asset_info.get("operatingsystem"):
        observations.append(f"Système d'exploitation CMDB : {asset_info['operatingsystem']}")
    if asset_info.get("ip_address"):
        observations.append(f"Adresse IP équipement : {asset_info['ip_address']}")

    # Enrichissement tendance historique Zabbix
    metric_history = state.get("metric_history", []) or []
    numeric_vals: List[float] = []
    for pt in metric_history:
        try:
            numeric_vals.append(float(pt.get("value")))
        except (TypeError, ValueError):
            pass
    if numeric_vals:
        observations.append(
            f"Historique Zabbix ({len(numeric_vals)} points) : min={min(numeric_vals):.2f}, "
            f"max={max(numeric_vals):.2f}, dernier={numeric_vals[0]:.2f}"
        )

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("incident_agent", "success")

    return {
        "observations": observations,
        "agent_telemetry": {
            "Incident Agent": {"duration_ms": dur_ms, "status": "ok", "observations_count": len(observations)}
        },
    }
