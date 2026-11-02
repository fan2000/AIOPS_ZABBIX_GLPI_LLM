"""Nœud Agent Retour d'Expérience (Knowledge Feedback) : Enrichissement de la KB GLPI."""

from typing import Any, Dict
from packages.agents.src.state import IncidentAgentState


async def feedback_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Prépare une proposition d'article ou de mise à jour pour la base de connaissances GLPI."""
    report = state.get("diagnostic_report", {})
    action_result = state.get("action_execution_result")
    technician_comment = state.get("technician_comment")

    problem = report.get("incident", "Incident résolu")
    host = report.get("host", "Équipement")

    kb_draft = {
        "title": f"Procédure de résolution validée : {problem}",
        "category": "AIOps - Retours d'expérience",
        "content": (
            f"<h3>Incident : {problem} sur {host}</h3>\n"
            f"<p><strong>Observations initiales :</strong> {', '.join(report.get('observations', []))}</p>\n"
            f"<p><strong>Actions ayant résolu l'incident :</strong> {action_result.get('stdout', 'Action manuelle confirmée') if action_result else 'Intervention technicien'}</p>\n"
            f"<p><strong>Notes du technicien :</strong> {technician_comment or 'Résolution standard conforme'}</p>"
        ),
        "status": "pending_kb_manager_review",
    }

    return {"kb_proposal": kb_draft}
