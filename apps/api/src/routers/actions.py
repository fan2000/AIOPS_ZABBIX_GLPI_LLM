"""Routes de gestion des runbooks et validation humaine des actions (Niveau 3)."""

from typing import Any, Dict, List
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from database.connection import get_db_session
from packages.contracts.src.runbook import (
    ExecutionStatus,
    RunbookDefinition,
    RunbookExecutionRequest,
    RunbookExecutionResult,
)
from packages.domain.models.database import ActionApproval, ActionExecution, AuditLog, Runbook
from packages.observability.src.metrics import record_remediation_execution
from services.remediation_worker.src.runner import remediation_runner

router = APIRouter(prefix="/api/v1/actions", tags=["Remediation & Runbooks"])


@router.get("/runbooks", response_model=List[Dict[str, Any]])
async def list_runbooks(session: AsyncSession = Depends(get_db_session)) -> List[Dict[str, Any]]:
    """Liste tous les runbooks autorisés dans le catalogue."""
    stmt = select(Runbook).where(Runbook.is_enabled == True)
    runbooks = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.identifier,
            "name": r.name,
            "description": r.description,
            "runner_type": r.runner_type,
            "target_os": r.target_os,
            "timeout_seconds": r.timeout_seconds,
            "required_role": r.required_role,
            "parameter_schema": r.parameter_schema,
        }
        for r in runbooks
    ]


@router.post("/execute", response_model=Dict[str, Any])
async def execute_runbook_action(
    request: RunbookExecutionRequest,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Exécute de façon contrôlée et auditée un runbook préalablement approuvé avec RBAC (CWE-306/CWE-285)."""
    # 1. Vérification de l'existence du runbook
    stmt = select(Runbook).where(Runbook.identifier == request.runbook_id, Runbook.is_enabled == True)
    rb = (await session.execute(stmt)).scalar_one_or_none()
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook introuvable ou désactivé")

    # 2. Contrôle RBAC : vérification des privilèges de l'utilisateur connecté
    if not current_user.has_sufficient_role(rb.required_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Droits insuffisants : le rôle '{current_user.role}' ne dispose pas des privilèges nécessaires pour exécuter ce runbook (requis : '{rb.required_role}')",
        )

    rb_def = RunbookDefinition(
        id=rb.identifier,
        name=rb.name,
        description=rb.description,
        runner_type=rb.runner_type,
        target_os=rb.target_os,
        timeout_seconds=rb.timeout_seconds,
        required_role=rb.required_role,
        parameter_schema=rb.parameter_schema,
        template_command=rb.template_command,
    )

    # 3. Exécution dans le runner sandboxé
    try:
        result = await remediation_runner.execute(rb_def, request)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    # 4. Enregistrement en base d'audit avec l'identité réelle vérifiée
    effective_approver = current_user.username or request.approved_by_user_id

    execution_record = ActionExecution(
        id=result.execution_id,
        incident_id=request.incident_id,
        runbook_identifier=request.runbook_id,
        approved_by=effective_approver,
        execution_status=result.status.value,
        parameters=request.parameters,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_seconds=result.duration_seconds,
        post_check_verified=result.post_check_verified,
        verification_details=result.verification_details,
    )
    session.add(execution_record)

    audit_entry = AuditLog(
        action="RUNBOOK_EXECUTED",
        resource_type="runbook",
        resource_id=request.runbook_id,
        user_id=current_user.id,
        details={
            "incident_id": str(request.incident_id),
            "approved_by": effective_approver,
            "user_role": current_user.role,
            "status": result.status.value,
            "exit_code": result.exit_code,
        },
    )
    session.add(audit_entry)
    await session.commit()

    record_remediation_execution(status=result.status.value, runner_type=rb.runner_type)

    return {
        "execution_id": str(result.execution_id),
        "status": result.status.value,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": result.duration_seconds,
        "verified_by_zabbix": result.post_check_verified,
    }
