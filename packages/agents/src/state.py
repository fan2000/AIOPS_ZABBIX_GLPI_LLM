"""État global et typé du graphe d'orchestration LangGraph."""

from typing import Annotated, Any, Dict, List, Optional, TypedDict


def _merge_dicts(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fusionne de façon atomique la télémétrie produite par les nœuds parallèles LangGraph."""
    merged: Dict[str, Any] = dict(left or {})
    if right:
        merged.update(right)
    return merged


class IncidentAgentState(TypedDict, total=False):
    """État partagé entre tous les nœuds agents du graphe LangGraph."""

    # Données d'entrée brutes
    incident_id: str
    ticket_id: Optional[int]
    entity_id: str
    host_name: str
    zabbix_host_id: str
    events: List[Dict[str, Any]]
    primary_event: Dict[str, Any]

    # Données de contexte collectées
    asset_info: Dict[str, Any]
    metric_history: List[Dict[str, Any]]
    approved_runbook_ids: List[str]
    is_correlated: bool
    correlation_reason: str

    # Données documentaires RAG
    rag_citations: List[Dict[str, Any]]
    rag_searched: bool

    # Raisonnement & Diagnostic
    observations: List[str]
    hypotheses: List[Dict[str, Any]]
    missing_info_checks: List[str]
    confidence_detail: Dict[str, Any]

    # Remédiation & Actions
    recommended_actions: List[Dict[str, Any]]
    validation_passed: bool
    validation_errors: List[str]
    blocked_actions_count: int

    # Télémétrie & FinOps IA (fusionnée automatiquement sur fan-out/fan-in)
    agent_telemetry: Annotated[Dict[str, Any], _merge_dicts]
    execution_mode: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float

    # Décision humaine (Human-in-the-Loop) & Investigation conditionnelle
    hitl_enabled: bool
    thread_id: Optional[str]
    investigation_iterations: int
    max_investigation_iterations: int
    investigation_findings: List[str]
    investigation_exhausted: bool
    requires_human_approval: bool
    pending_approval_action: Optional[Dict[str, Any]]
    decided_by: Optional[str]
    hitl_status: str
    human_approved: Optional[bool]
    technician_comment: Optional[str]
    action_execution_result: Optional[Dict[str, Any]]

    # Rapport final
    diagnostic_report: Optional[Dict[str, Any]]
    kb_proposal: Optional[Dict[str, Any]]
    error: Optional[str]

    # Options d'isolation pour évaluation continue (Eval Harness)
    force_fast_diagnosis: Optional[bool]
    skip_rag_lookup: Optional[bool]
