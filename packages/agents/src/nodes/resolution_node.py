"""Nœud Agent Résolution : Sélection des runbooks et formulation des recommandations."""

from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState


async def resolution_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Sélectionne les procédures approuvées du catalogue en fonction du diagnostic."""
    primary_event = state.get("primary_event", {})
    problem = primary_event.get("problem", "").lower()
    asset_info = state.get("asset_info", {})
    os_name = (asset_info.get("operatingsystem") or "").lower()

    recommended_actions: List[Dict[str, Any]] = []

    # 1. Cas CPU élevé
    if "cpu" in problem:
        recommended_actions.append({
            "action": "Collecter la liste des processus les plus consommateurs (Lecture seule)",
            "runbook_id": "rb-collect-top-processes",
            "parameters": {},
            "requires_approval": False,
            "execution_mode": "read_only",
            "risk_level": "LOW",
        })

    # 2. Cas Service arrêté
    elif "service" in problem or "spooler" in problem or "nginx" in problem:
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

    # 3. Cas Disque plein
    elif "disk" in problem or "espace" in problem or "fs" in problem:
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

    return {"recommended_actions": recommended_actions}
