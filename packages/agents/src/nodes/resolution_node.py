"""Nœud Agent Résolution : Sélection des runbooks du catalogue et niveaux de risque."""

import time
from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.observability.src.metrics import record_agent_execution


async def resolution_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Sélectionne les procédures approuvées du catalogue en fonction du diagnostic."""
    t0 = time.perf_counter()
    primary_event = state.get("primary_event", {})
    problem = primary_event.get("problem", "").lower()
    asset_info = state.get("asset_info", {}) or {}
    os_name = (asset_info.get("operatingsystem") or "").lower()

    recommended_actions: List[Dict[str, Any]] = []

    if "cpu" in problem or "ram" in problem or "swap" in problem or "memory" in problem:
        recommended_actions.append({
            "action": "Collecter la liste des processus les plus consommateurs CPU/RAM (Lecture seule)",
            "runbook_id": "rb-collect-top-processes",
            "parameters": {},
            "requires_approval": False,
            "execution_mode": "read_only",
            "risk_level": "LOW",
        })

    elif "service" in problem or "spooler" in problem or "nginx" in problem or "stopped" in problem:
        service_target = "nginx" if "linux" in os_name else "Spooler"
        if "linux" in os_name:
            recommended_actions.append({
                "action": f"Redémarrage contrôlé du service Linux {service_target}",
                "runbook_id": "rb-linux-service-restart",
                "parameters": {"service_name": service_target},
                "requires_approval": True,
                "execution_mode": "remediation",
                "risk_level": "MEDIUM",
            })
        else:
            recommended_actions.append({
                "action": f"Redémarrage contrôlé du service Windows {service_target}",
                "runbook_id": "rb-win-service-restart",
                "parameters": {"service_name": service_target},
                "requires_approval": True,
                "execution_mode": "remediation",
                "risk_level": "MEDIUM",
            })

    elif "disk" in problem or "espace" in problem or "fs" in problem or "var/log" in problem:
        recommended_actions.append({
            "action": "Purge préventive des logs archivés de plus de 15 jours",
            "runbook_id": "rb-disk-cleanup-logs",
            "parameters": {},
            "requires_approval": True,
            "execution_mode": "remediation",
            "risk_level": "MEDIUM",
        })

    else:
        recommended_actions.append({
            "action": "Intervention manuelle du technicien requise selon procédure ITIL",
            "runbook_id": None,
            "parameters": {},
            "requires_approval": True,
            "execution_mode": "read_only",
            "risk_level": "LOW",
        })

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("resolution_agent", "success")

    return {
        "recommended_actions": recommended_actions,
        "agent_telemetry": {
            "Resolution Agent": {"duration_ms": dur_ms, "status": "ok", "actions_count": len(recommended_actions)}
        },
    }
