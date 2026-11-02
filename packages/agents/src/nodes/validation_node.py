"""Nœud Agent Validation : Contrôle de sécurité, filtrage anti-hallucination et rapport."""

from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.contracts.src.ai import (
    ConfidenceDetail,
    ConfidenceLevel,
    DiagnosticHypothesis,
    DiagnosticReport,
    ExecutionMode,
    KnowledgeSourceCitation,
    RecommendedAction,
)

APPROVED_RUNBOOK_IDS = {
    "rb-collect-top-processes",
    "rb-win-service-restart",
    "rb-linux-service-restart",
    "rb-disk-cleanup-logs",
}


async def validation_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Valide la cohérence du diagnostic, bloque les actions non autorisées et génère le rapport."""
    validation_errors: List[str] = []
    actions = state.get("recommended_actions", [])

    # Contrôle de sécurité : tout runbook proposé doit exister dans le catalogue autorisé
    for act in actions:
        rb_id = act.get("runbook_id")
        if rb_id and rb_id not in APPROVED_RUNBOOK_IDS:
            validation_errors.append(f"Action bloquée : Le runbook '{rb_id}' n'est pas dans le catalogue approuvé.")
            act["runbook_id"] = None
            act["requires_approval"] = True

    validation_passed = len(validation_errors) == 0

    # Construction du rapport final conforme au format Pydantic
    conf_raw = state.get("confidence_detail", {})
    confidence_obj = ConfidenceDetail(
        level=ConfidenceLevel(conf_raw.get("level", "insufficient_evidence")),
        explanation=conf_raw.get("explanation", "Calibration par défaut."),
    )

    report = DiagnosticReport(
        ticket_id=state.get("ticket_id"),
        host=state.get("host_name", "UNKNOWN"),
        incident=state.get("primary_event", {}).get("problem", "Incident"),
        observations=state.get("observations", ["Alerte détectée"]),
        hypotheses=[
            DiagnosticHypothesis(
                description=h.get("description", ""),
                evidence=h.get("evidence", []),
                status=h.get("status", "unconfirmed"),
            )
            for h in state.get("hypotheses", [])
        ],
        checks=state.get("missing_info_checks", []),
        recommended_actions=[
            RecommendedAction(
                action=a.get("action", ""),
                runbook_id=a.get("runbook_id"),
                parameters=a.get("parameters", {}),
                requires_approval=a.get("requires_approval", True),
                execution_mode=ExecutionMode(a.get("execution_mode", "read_only")),
                risk_level=a.get("risk_level", "LOW"),
            )
            for a in actions
        ],
        knowledge_sources=[
            KnowledgeSourceCitation(**c) for c in state.get("rag_citations", [])
        ],
        confidence=confidence_obj,
        status="pending_technician_review",
    )

    return {
        "validation_passed": validation_passed,
        "validation_errors": validation_errors,
        "diagnostic_report": report.model_dump(),
    }
