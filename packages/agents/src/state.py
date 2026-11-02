"""État global et typé du graphe d'orchestration LangGraph."""

from typing import Any, Dict, List, Optional, TypedDict
from packages.contracts.src.ai import (
    ConfidenceDetail,
    DiagnosticHypothesis,
    DiagnosticReport,
    KnowledgeSourceCitation,
    RecommendedAction,
)
from packages.contracts.src.events import NormalizedIncidentEvent


class IncidentAgentState(TypedDict, total=False):
    """État partagé entre tous les nœuds agents du graphe LangGraph."""

    # Données d'entrée brutes
    incident_id: str
    ticket_id: Optional[int]
    host_name: str
    zabbix_host_id: str
    events: List[Dict[str, Any]]
    primary_event: Dict[str, Any]

    # Données de contexte collectées
    asset_info: Dict[str, Any]
    metric_history: List[Dict[str, Any]]
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

    # Décision humaine (Human-in-the-Loop)
    human_approved: Optional[bool]
    technician_comment: Optional[str]
    action_execution_result: Optional[Dict[str, Any]]

    # Rapport final
    diagnostic_report: Optional[Dict[str, Any]]
    error: Optional[str]
