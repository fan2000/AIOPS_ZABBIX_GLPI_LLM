"""Routes de gestion des runbooks et validation humaine des actions (Niveau 3)."""

from datetime import datetime, timezone
import html
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from database.connection import get_db_session
from packages.agents.src.graph import get_hitl_thread_state, resume_hitl_incident_analysis
from packages.connectors.glpi.src.client import glpi_client
from packages.contracts.src.glpi import GlpiFollowupCreate
from packages.contracts.src.runbook import (
    ExecutionStatus,
    RunbookDefinition,
    RunbookExecutionRequest,
    RunbookExecutionResult,
)
from packages.domain.models.database import ActionApproval, ActionExecution, AuditLog, Incident, Runbook
from packages.observability.src.metrics import record_hitl_decision, record_remediation_execution
from services.incident_worker.src.context_enrichment import upsert_kb_proposal_from_state
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
    """Exécute de façon contrôlée et auditée un runbook préalablement approuvé avec RBAC (CWE-306/CWE-285/CWE-755)."""
    # 1. Vérification de l'existence de l'incident associé (prévention violation FK et perte d'audit CWE-755)
    inc_stmt = select(Incident).where(Incident.id == request.incident_id)
    incident_obj = (await session.execute(inc_stmt)).scalar_one_or_none()
    if not incident_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{request.incident_id}' introuvable en base de données",
        )

    # 2. Vérification de l'existence du runbook
    stmt = select(Runbook).where(Runbook.identifier == request.runbook_id, Runbook.is_enabled == True)
    rb = (await session.execute(stmt)).scalar_one_or_none()
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook introuvable ou désactivé")

    # 3. Contrôle RBAC : vérification des privilèges de l'utilisateur connecté
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

    # 4. Exécution dans le runner sandboxé
    try:
        result = await remediation_runner.execute(rb_def, request)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    # 5. Enregistrement en base d'audit avec l'identité réelle vérifiée
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
        "post_check_verified": result.post_check_verified,
        "verification_details": result.verification_details,
    }


class ApprovalDecisionRequest(BaseModel):
    """Décision d'un opérateur sur une approbation LangGraph HITL en attente."""

    approved: bool
    comment: str = Field("", max_length=1000)
    parameters_override: Optional[Dict[str, Any]] = None


def _serialize_approval(app: ActionApproval, inc: Optional[Incident] = None) -> Dict[str, Any]:
    """Sérialise une demande d'approbation HITL avec contexte incident optionnel."""
    data: Dict[str, Any] = {
        "id": str(app.id),
        "incident_id": str(app.incident_id),
        "runbook_identifier": app.runbook_identifier,
        "parameters": app.parameters or {},
        "status": app.status,
        "thread_id": app.thread_id,
        "checkpoint_id": app.checkpoint_id,
        "risk_level": getattr(app, "risk_level", None) or "MEDIUM",
        "action_summary": getattr(app, "action_summary", None) or app.runbook_identifier,
        "execution_id": str(app.execution_id) if getattr(app, "execution_id", None) else None,
        "requested_at": app.requested_at.isoformat() if app.requested_at else None,
        "decided_at": app.decided_at.isoformat() if app.decided_at else None,
        "decided_by_user": app.decided_by_user,
        "rejection_reason": app.rejection_reason,
    }
    if inc is not None:
        data.update(
            {
                "incident_number": inc.incident_number,
                "incident_title": inc.title,
                "incident_severity": inc.severity,
                "incident_status": inc.status,
                "primary_asset_name": inc.primary_asset_name,
                "entity_id": str(inc.entity_id or "0"),
                "glpi_ticket_id": inc.glpi_ticket_id,
            }
        )
    return data


async def _post_hitl_glpi_followup(inc: Incident, html_body: str) -> None:
    """Publie un suivi privé GLPI best-effort lors d'une décision HITL."""
    if not inc.glpi_ticket_id or not str(inc.glpi_ticket_id).isdigit():
        return
    try:
        await glpi_client.add_private_followup(
            GlpiFollowupCreate(
                items_id=int(inc.glpi_ticket_id),
                content=html_body,
                is_private=1,
            )
        )
    except Exception:
        pass


@router.get("/approvals")
async def list_approvals(
    status_filter: Optional[str] = Query(None, alias="status"),
    incident_id: Optional[UUID] = Query(None),
    limit: int = Query(50, le=200),
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste les demandes d'approbation HITL filtrées par statut, incident et périmètre GLPI."""
    stmt = (
        select(ActionApproval, Incident)
        .join(Incident, ActionApproval.incident_id == Incident.id)
        .order_by(desc(ActionApproval.requested_at))
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(ActionApproval.status == status_filter)
    if incident_id:
        stmt = stmt.where(ActionApproval.incident_id == incident_id)

    rows = (await session.execute(stmt)).all()
    results: List[Dict[str, Any]] = []
    for app, inc in rows:
        if current_user.can_access_entity(str(inc.entity_id or "0")):
            results.append(_serialize_approval(app, inc))
    return results


@router.get("/approvals/{approval_id}/checkpoint")
async def inspect_approval_checkpoint(
    approval_id: UUID,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Inspecte l'état du checkpoint PostgreSQL LangGraph associé à une approbation HITL."""
    app = (
        await session.execute(select(ActionApproval).where(ActionApproval.id == approval_id))
    ).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Demande d'approbation introuvable")

    inc = (
        await session.execute(select(Incident).where(Incident.id == app.incident_id))
    ).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident associé introuvable")

    if not current_user.can_access_entity(str(inc.entity_id or "0")):
        raise HTTPException(status_code=403, detail="Accès refusé à l'entité GLPI de cet incident")

    checkpoint_state: Dict[str, Any] = {
        "thread_id": app.thread_id,
        "exists": False,
        "paused": False,
        "next_nodes": [],
        "state": {},
    }
    if app.thread_id:
        checkpoint_state = await get_hitl_thread_state(app.thread_id)

    return {
        "approval": _serialize_approval(app, inc),
        "checkpoint": checkpoint_state,
    }


async def _resume_hitl_and_sync_kb(
    app: ActionApproval,
    inc: Incident,
    human_approved: bool,
    username: str,
    comment: str,
    execution_summary: Optional[Dict[str, Any]],
    session: AsyncSession,
) -> Optional[Dict[str, Any]]:
    """Reprend un thread LangGraph suspendu de façon tolérante et met à jour la proposition KB."""
    if not app.thread_id:
        return None
    try:
        resumed = await resume_hitl_incident_analysis(
            thread_id=app.thread_id,
            human_approved=human_approved,
            decided_by=username,
            technician_comment=comment,
            action_execution_result=execution_summary,
        )
    except ValueError as exc:
        return {
            "thread_id": app.thread_id,
            "paused": False,
            "next_nodes": [],
            "hitl_status": "checkpoint_unavailable",
            "kb_proposal_generated": False,
            "warning": str(exc),
        }

    resumed_state = resumed.get("state") or {}
    kb_prop = None
    if isinstance(resumed_state, dict):
        kb_prop = await upsert_kb_proposal_from_state(
            inc,
            resumed_state,
            session,
            created_by=f"hitl:{username}",
        )

    return {
        "thread_id": resumed.get("thread_id", app.thread_id),
        "paused": bool(resumed.get("paused", False)),
        "next_nodes": resumed.get("next_nodes", []),
        "checkpoint_id": resumed.get("checkpoint_id"),
        "hitl_status": (resumed_state.get("hitl_status") if isinstance(resumed_state, dict) else None)
        or ("resumed_approved" if human_approved else "resumed_rejected"),
        "kb_proposal_generated": kb_prop is not None,
    }


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Approuve ou rejette une action en attente et reprend le graphe LangGraph persisté."""
    if not current_user.has_sufficient_role("operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rôle insuffisant ({current_user.role}). Opérateur ou administrateur requis.",
        )

    app = (
        await session.execute(select(ActionApproval).where(ActionApproval.id == approval_id))
    ).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Demande d'approbation introuvable")

    if app.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cette demande a déjà été traitée (statut actuel: {app.status})",
        )

    inc = (
        await session.execute(select(Incident).where(Incident.id == app.incident_id))
    ).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident associé introuvable")

    if not current_user.can_access_entity(str(inc.entity_id or "0")):
        raise HTTPException(status_code=403, detail="Accès refusé à l'entité GLPI de cet incident")

    rb = (
        await session.execute(select(Runbook).where(Runbook.identifier == app.runbook_identifier))
    ).scalar_one_or_none()

    required_role = rb.required_role if rb else "operator"
    if not current_user.has_sufficient_role(required_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Rôle insuffisant ({current_user.role}) pour décider du runbook "
                f"'{app.runbook_identifier}' (requis: {required_role})."
            ),
        )

    now = datetime.now(timezone.utc)
    effective_params = dict(app.parameters or {})
    if payload.parameters_override:
        effective_params.update(payload.parameters_override)

    execution_summary: Optional[Dict[str, Any]] = None
    hitl_resumed_out: Optional[Dict[str, Any]] = None

    if payload.approved:
        if not rb or not rb.is_enabled:
            raise HTTPException(
                status_code=404,
                detail=f"Runbook '{app.runbook_identifier}' introuvable ou désactivé",
            )

        rb_def = RunbookDefinition(
            id=rb.identifier,
            name=rb.name,
            description=rb.description,
            runner_type=rb.runner_type,
            target_os=rb.target_os,
            timeout_seconds=rb.timeout_seconds,
            required_role=rb.required_role,
            parameter_schema=rb.parameter_schema or {},
            template_command=rb.template_command,
        )
        exec_req = RunbookExecutionRequest(
            runbook_id=rb.identifier,
            incident_id=inc.id,
            parameters=effective_params,
            approved_by_user_id=current_user.username,
        )
        result: RunbookExecutionResult = await remediation_runner.execute(rb_def, exec_req)

        exec_row = ActionExecution(
            id=result.execution_id,
            incident_id=inc.id,
            runbook_identifier=rb.identifier,
            approved_by=current_user.username,
            execution_status=result.status.value,
            parameters=effective_params,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            started_at=now,
            finished_at=datetime.now(timezone.utc),
            post_check_verified=result.post_check_verified,
            verification_details=result.verification_details,
        )
        session.add(exec_row)
        record_remediation_execution(status=result.status.value, runner_type=rb.runner_type)

        app.status = "approved"
        app.decided_at = now
        app.decided_by_user = current_user.username
        app.execution_id = result.execution_id
        app.parameters = effective_params
        app.rejection_reason = None
        record_hitl_decision("approved", getattr(app, "risk_level", None) or "MEDIUM")

        if result.status == ExecutionStatus.SUCCESS:
            inc.status = "RESOLVED"
            inc.recovery_at = inc.recovery_at or now
        else:
            inc.status = "IN_PROGRESS"

        execution_summary = {
            "execution_id": str(result.execution_id),
            "runbook_id": rb.identifier,
            "status": result.status.value,
            "exit_code": result.exit_code,
            "stdout": (result.stdout or "")[:1000],
            "stderr": (result.stderr or "")[:1000],
            "duration_seconds": result.duration_seconds,
            "post_check_verified": result.post_check_verified,
            "verification_details": result.verification_details,
        }

        hitl_resumed_out = await _resume_hitl_and_sync_kb(
            app=app,
            inc=inc,
            human_approved=True,
            username=current_user.username,
            comment=payload.comment,
            execution_summary=execution_summary,
            session=session,
        )

        session.add(
            AuditLog(
                id=uuid4(),
                user_id=current_user.id,
                action="HITL_APPROVAL_APPROVED",
                resource_type="ActionApproval",
                resource_id=str(app.id),
                details={
                    "incident_id": str(inc.id),
                    "runbook_id": rb.identifier,
                    "thread_id": app.thread_id,
                    "execution_id": str(result.execution_id),
                    "execution_status": result.status.value,
                    "comment": payload.comment,
                },
            )
        )

        await _post_hitl_glpi_followup(
            inc,
            (
                f"<p><b>[AIOps HITL - Approbation]</b> Runbook <code>{html.escape(rb.identifier)}</code> "
                f"approuvé par <b>{html.escape(current_user.username)}</b>.</p>"
                f"<p>Statut d'exécution : <b>{html.escape(result.status.value)}</b> (code {result.exit_code})</p>"
                f"<p>Commentaire opérateur : {html.escape(payload.comment or 'Aucun')}</p>"
            ),
        )
    else:
        app.status = "rejected"
        app.decided_at = now
        app.decided_by_user = current_user.username
        app.rejection_reason = (payload.comment or "Rejeté par l'opérateur")[:255]
        record_hitl_decision("rejected", getattr(app, "risk_level", None) or "MEDIUM")

        if inc.status == "WAITING_APPROVAL":
            inc.status = "IN_PROGRESS"

        hitl_resumed_out = await _resume_hitl_and_sync_kb(
            app=app,
            inc=inc,
            human_approved=False,
            username=current_user.username,
            comment=payload.comment,
            execution_summary=None,
            session=session,
        )

        session.add(
            AuditLog(
                id=uuid4(),
                user_id=current_user.id,
                action="HITL_APPROVAL_REJECTED",
                resource_type="ActionApproval",
                resource_id=str(app.id),
                details={
                    "incident_id": str(inc.id),
                    "runbook_id": app.runbook_identifier,
                    "thread_id": app.thread_id,
                    "rejection_reason": app.rejection_reason,
                },
            )
        )

        await _post_hitl_glpi_followup(
            inc,
            (
                f"<p><b>[AIOps HITL - Rejet]</b> Runbook <code>{html.escape(app.runbook_identifier)}</code> "
                f"rejeté par <b>{html.escape(current_user.username)}</b>.</p>"
                f"<p>Motif : {html.escape(app.rejection_reason or 'Non précisé')}</p>"
            ),
        )

    await session.commit()

    return {
        "approval": _serialize_approval(app, inc),
        "execution": execution_summary,
        "hitl_resumed": hitl_resumed_out,
    }
