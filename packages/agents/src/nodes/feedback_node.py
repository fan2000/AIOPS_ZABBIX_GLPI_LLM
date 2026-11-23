"""Nœud Agent Retour d'Expérience (Knowledge Feedback) : Préparation des propositions KB GLPI."""

import html
import time
from typing import Any, Dict
from packages.agents.src.state import IncidentAgentState
from packages.observability.src.metrics import record_agent_execution


async def feedback_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Prépare une proposition d'article structurée pour la base de connaissances (Knowledge Center & GLPI)."""
    t0 = time.perf_counter()
    report = state.get("diagnostic_report", {})
    action_result = state.get("action_execution_result")
    technician_comment = state.get("technician_comment")
    entity_id = str(state.get("entity_id") or "0")

    problem = report.get("incident", "Incident résolu")
    host = report.get("host", "Équipement")
    obs_html = ", ".join(html.escape(str(o)) for o in report.get("observations", []))
    hyp_html = ", ".join(html.escape(str(h.get("description", ""))) for h in report.get("hypotheses", []))
    chk_html = ", ".join(html.escape(str(c)) for c in report.get("checks", []))

    if action_result:
        action_summary = html.escape(str(action_result.get("stdout") or "Action exécutée avec succès"))[:500]
    else:
        proposed = ", ".join(html.escape(str(a.get("action", ""))) for a in report.get("recommended_actions", []))
        action_summary = proposed or "En attente de validation technicien Niveau 3"

    kb_draft = {
        "title": f"Procédure de résolution : {problem}"[:250],
        "category": "AIOps - Retours d'expérience",
        "entity_id": entity_id,
        "content": (
            f"<h3>Incident : {html.escape(str(problem))} sur {html.escape(str(host))}</h3>\n"
            f"<p><strong>Observations initiales :</strong> {obs_html or 'N/A'}</p>\n"
            f"<p><strong>Hypothèses diagnostiques :</strong> {hyp_html or 'N/A'}</p>\n"
            f"<p><strong>Vérifications recommandées :</strong> {chk_html or 'N/A'}</p>\n"
            f"<p><strong>Actions / Remédiation :</strong> {action_summary}</p>\n"
            f"<p><strong>Notes du technicien :</strong> {html.escape(str(technician_comment or 'Brouillon initial généré automatiquement - à valider après résolution'))}</p>"
        ),
        "status": "pending_review",
    }

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("feedback_agent", "success")

    return {
        "kb_proposal": kb_draft,
        "agent_telemetry": {
            "Feedback Agent": {"duration_ms": dur_ms, "status": "ok"}
        },
    }
