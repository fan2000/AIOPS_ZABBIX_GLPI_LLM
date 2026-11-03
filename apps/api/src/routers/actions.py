"""Routes de gestion des runbooks et validation humaine des actions (Niveau 3)."""

from typing import Any, Dict, List
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
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
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Exécute de façon contrôlée et auditée un runbook préalablement approuvé."""
    # 1. Vérification de l'existence du runbook
    stmt = select(Runbook).where(Runbook.identifier == request.runbook_id, Runbook.is_enabled == True)
    rb = (await session.execute(stmt)).scalar_one_or_none()
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook introuvable ou désactivé")

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

    # 2. Exécution dans le runner sandboxé
    try:
        result = await remediation_runner.execute(rb_def, request)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    # 3. Enregistrement en base d'audit
    execution_record = ActionExecution(
        id=result.execution_id,
        incident_id=request.incident_id,
        runbook_identifier=request.runbook_id,
        approved_by=request.approved_by_user_id,
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
        details={
            "incident_id": str(request.incident_id),
            "approved_by": request.approved_by_user_id,
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
