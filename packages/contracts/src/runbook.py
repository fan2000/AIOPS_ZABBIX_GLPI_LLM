"""Contrats de données pour le catalogue et l'exécution contrôlée de runbooks."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class RunbookRunnerType(str, Enum):
    POWERSHELL = "powershell"
    BASH_SSH = "bash_ssh"
    ANSIBLE = "ansible"


class TargetOS(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    ALL = "all"


class ExecutionStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    VERIFIED_BY_ZABBIX = "verified_by_zabbix"


class RunbookDefinition(BaseModel):
    """Définition d'un runbook préapprouvé dans le catalogue."""
    id: str = Field(..., description="Identifiant unique du runbook (ex: rb-win-service-restart)")
    name: str
    description: str
    runner_type: RunbookRunnerType
    target_os: TargetOS
    timeout_seconds: int = Field(60, ge=5, le=600)
    required_role: str = "operator"
    parameter_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Schéma JSON strict validant les paramètres autorisés"
    )
    template_command: str = Field(..., description="Modèle de commande sans shell arbitraire")


class RunbookExecutionRequest(BaseModel):
    """Requête de validation et d'exécution d'un runbook."""
    runbook_id: str
    incident_id: UUID
    parameters: Dict[str, Any]
    approved_by_user_id: str


class RunbookExecutionResult(BaseModel):
    """Rapport d'exécution auditable d'une action de remédiation."""
    execution_id: UUID
    runbook_id: str
    incident_id: UUID
    status: ExecutionStatus
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    post_check_verified: bool = False
    verification_details: Optional[str] = None
