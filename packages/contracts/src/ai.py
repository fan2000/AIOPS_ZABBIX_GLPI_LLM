"""Contrats de données structurées pour le moteur de diagnostic IA et le RAG."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class HypothesisStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"
    RULED_OUT = "ruled_out"


class ExecutionMode(str, Enum):
    READ_ONLY = "read_only"
    REMEDIATION = "remediation"


class ConfidenceLevel(str, Enum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class DiagnosticHypothesis(BaseModel):
    description: str = Field(..., description="Description de l'hypothèse technique")
    evidence: List[str] = Field(default_factory=list, description="Faits et métriques appuyant l'hypothèse")
    status: HypothesisStatus = Field(HypothesisStatus.UNCONFIRMED)


class RecommendedAction(BaseModel):
    action: str = Field(..., description="Action recommandée")
    runbook_id: Optional[str] = Field(None, description="Identifiant du runbook du catalogue si automatisable")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Paramètres stricts pour le runbook")
    requires_approval: bool = Field(True, description="Vrai si nécessite validation humaine préalable")
    execution_mode: ExecutionMode = Field(ExecutionMode.READ_ONLY)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"


class KnowledgeSourceCitation(BaseModel):
    article_id: str = Field(..., description="ID ou référence unique de la source (ex: KB-012, TICKET-981)")
    title: str = Field(..., description="Titre du document source")
    source_type: Literal["glpi_kb", "resolved_ticket", "runbook_doc", "wiki"]
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    snippet: str = Field(..., description="Extrait textuel justifiant la citation")


class ConfidenceDetail(BaseModel):
    level: ConfidenceLevel
    explanation: str = Field(..., description="Justification qualitative du niveau de confiance")


class DiagnosticReport(BaseModel):
    """Rapport de diagnostic IA structuré et sourcé conforme au contrat de section 10."""
    model_config = ConfigDict(frozen=True)

    ticket_id: Optional[int] = Field(None, description="Numéro du ticket GLPI")
    host: str = Field(..., description="Nom de l'équipement")
    incident: str = Field(..., description="Titre synthétique de l'incident")
    observations: List[str] = Field(..., min_length=1, description="Faits vérifiés et métriques réelles")
    hypotheses: List[DiagnosticHypothesis] = Field(default_factory=list)
    checks: List[str] = Field(default_factory=list, description="Vérifications et contrôles recommandés")
    recommended_actions: List[RecommendedAction] = Field(default_factory=list)
    knowledge_sources: List[KnowledgeSourceCitation] = Field(default_factory=list)
    confidence: ConfidenceDetail
    status: Literal["pending_technician_review", "approved", "rejected", "auto_analyzed"] = "pending_technician_review"
