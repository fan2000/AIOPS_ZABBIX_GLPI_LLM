"""Nœud Agent Validation : Contrôle de sécurité dynamique sur catalogue, anti-hallucination et rapport."""

import time
from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.contracts.src.ai import (
    ConfidenceDetail,
    ConfidenceLevel,
    DiagnosticHypothesis,
    DiagnosticReport,
    ExecutionMode,
    HypothesisStatus,
    KnowledgeSourceCitation,
    RecommendedAction,
)
from packages.observability.src.metrics import record_agent_execution

DEFAULT_APPROVED_RUNBOOK_IDS = {
    "rb-collect-top-processes",
    "rb-win-service-restart",
    "rb-linux-service-restart",
    "rb-disk-cleanup-logs",
}
APPROVED_RUNBOOK_IDS = DEFAULT_APPROVED_RUNBOOK_IDS


async def validation_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Valide la cohérence du diagnostic contre les runbooks autorisés en base et génère le rapport."""
    t0 = time.perf_counter()
    validation_errors: List[str] = []
    actions = state.get("recommended_actions", [])

    allowed_ids = set(state.get("approved_runbook_ids") or DEFAULT_APPROVED_RUNBOOK_IDS)

    # Contrôle de sécurité : tout runbook proposé doit figurer dans le catalogue actif approuvé
    for act in actions:
        rb_id = act.get("runbook_id")
        if rb_id and rb_id not in allowed_ids:
            validation_errors.append(f"Action bloquée : Le runbook '{rb_id}' n'est pas dans le catalogue approuvé.")
            act["runbook_id"] = None
            act["requires_approval"] = True

    validation_passed = len(validation_errors) == 0

    conf_raw = state.get("confidence_detail", {})
    raw_lvl = str(conf_raw.get("level", "insufficient_evidence")).strip().lower()
    if raw_lvl == "medium":
        raw_lvl = "moderate"
    try:
        conf_level_enum = ConfidenceLevel(raw_lvl)
    except ValueError:
        conf_level_enum = ConfidenceLevel.INSUFFICIENT_EVIDENCE

    confidence_obj = ConfidenceDetail(
        level=conf_level_enum,
        explanation=conf_raw.get("explanation", "Calibration par défaut."),
    )

    hypotheses_list = []
    for h in state.get("hypotheses", []):
        raw_status = str(h.get("status", "unconfirmed")).strip().lower()
        try:
            status_enum = HypothesisStatus(raw_status)
        except ValueError:
            status_enum = HypothesisStatus.UNCONFIRMED
        hypotheses_list.append(
            DiagnosticHypothesis(
                description=h.get("description", ""),
                evidence=h.get("evidence", []),
                status=status_enum,
            )
        )

    safe_citations = []
    for c in state.get("rag_citations", []):
        try:
            c_copy = dict(c)
            raw_score = float(c_copy.get("relevance_score", 0.0))
            c_copy["relevance_score"] = min(1.0, max(0.0, raw_score))
            safe_citations.append(KnowledgeSourceCitation(**c_copy))
        except Exception:
            pass

    report = DiagnosticReport(
        ticket_id=state.get("ticket_id"),
        host=state.get("host_name", "UNKNOWN"),
        incident=state.get("primary_event", {}).get("problem", "Incident"),
        observations=state.get("observations", ["Alerte détectée"]),
        hypotheses=hypotheses_list,
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
        knowledge_sources=safe_citations,
        confidence=confidence_obj,
        status="pending_technician_review",
    )

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("validation_agent", "success" if validation_passed else "guarded")

    approval_candidates = [
        a for a in actions if bool(a.get("requires_approval")) and bool(a.get("runbook_id"))
    ]
    requires_human = len(approval_candidates) > 0
    hitl_status = (
        "waiting_human_approval"
        if (requires_human and state.get("hitl_enabled"))
        else "completed"
    )

    return {
        "validation_passed": validation_passed,
        "validation_errors": validation_errors,
        "blocked_actions_count": len(validation_errors),
        "requires_human_approval": requires_human,
        "pending_approval_action": approval_candidates[0] if requires_human else None,
        "hitl_status": hitl_status,
        "diagnostic_report": report.model_dump(mode="json"),
        "agent_telemetry": {
            "Validation Agent": {
                "duration_ms": dur_ms,
                "status": "ok" if validation_passed else "guarded",
                "blocked_actions": len(validation_errors),
                "requires_human_approval": requires_human,
            }
        },
    }
