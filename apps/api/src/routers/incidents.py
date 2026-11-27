"""Gestion et consultation des incidents AIOps, diagnostics enrichis, citations RAG et feedback technicien."""

import html
import os
import time
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.src.dependencies.auth import (
    AuthenticatedUserContext,
    get_current_user,
    get_knowledge_read_user,
)
from database.connection import get_db_session
from packages.agents.src.graph import start_hitl_incident_analysis
from packages.agents.src.state import IncidentAgentState
from packages.contracts.src.incident import IncidentRead
from packages.domain.models.database import (
    AIAnalysisRun,
    AIRecommendation,
    ActionApproval,
    ActionExecution,
    AuditLog,
    Incident,
    IncidentEvent,
    IncidentFeedback,
    KnowledgeProposal,
    RecommendationSource,
)
from packages.security.src.rate_limiter import default_limiter
from services.incident_worker.src.context_enrichment import (
    create_pending_approval_if_paused,
    enrich_incident_context,
    persist_analysis_result,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["Incidents"])


class IncidentFeedbackRequest(BaseModel):
    is_recommendation_accepted: bool = True
    rating_score: int = Field(5, ge=1, le=5)
    feedback_notes: str = Field("", max_length=2000)
    generate_kb_proposal: bool = True


def _safe_entity_id(inc: Incident) -> str:
    raw = getattr(inc, "entity_id", "0")
    return str(raw) if isinstance(raw, (str, int)) else "0"


@router.get("", response_model=List[IncidentRead])
async def list_incidents(
    status_filter: Optional[str] = Query(None, alias="status"),
    severity_filter: Optional[str] = Query(None, alias="severity"),
    limit: int = Query(50, le=200),
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[Incident]:
    """Liste les incidents avec filtres optionnels et isolation multi-entités GLPI."""
    scope = current_user.resolve_entity_scope(None)
    stmt = select(Incident).order_by(desc(Incident.opened_at)).limit(limit)
    if "*" not in scope:
        stmt = stmt.where(Incident.entity_id.in_(scope))
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter.upper())
    if severity_filter:
        stmt = stmt.where(Incident.severity == severity_filter.upper())

    results = (await session.execute(stmt)).scalars().all()
    return list(results)


@router.get("/{incident_id}")
async def get_incident(
    incident_id: UUID,
    current_user: AuthenticatedUserContext = Depends(get_knowledge_read_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retourne le détail d'un incident avec vérification d'isolation multi-entités (anti-IDOR)."""
    stmt = select(Incident).where(Incident.id == incident_id)
    inc = (await session.execute(stmt)).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident introuvable")

    inc_entity = _safe_entity_id(inc)
    if not current_user.can_access_entity(inc_entity):
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                user_id=current_user.id,
                action="INCIDENT_IDOR_BLOCKED",
                resource_type="incident",
                resource_id=str(incident_id),
                details={
                    "username": current_user.username,
                    "target_entity": inc_entity,
                    "allowed_entities": current_user.allowed_entities,
                },
            )
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à l'entité GLPI de cet incident",
        )

    ev_stmt = (
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(desc(IncidentEvent.event_timestamp))
    )
    events = (await session.execute(ev_stmt)).scalars().all()

    ai_stmt = (
        select(AIAnalysisRun)
        .where(AIAnalysisRun.incident_id == incident_id)
        .order_by(desc(AIAnalysisRun.created_at))
        .limit(1)
    )
    analysis = (await session.execute(ai_stmt)).scalar_one_or_none()

    recs = []
    sources_out: List[Dict[str, Any]] = []
    if analysis:
        rec_stmt = select(AIRecommendation).where(AIRecommendation.analysis_run_id == analysis.id)
        recs = list((await session.execute(rec_stmt)).scalars().all())
        rec_ids = [r.id for r in recs]
        if rec_ids:
            src_rows = (
                await session.execute(
                    select(RecommendationSource).where(RecommendationSource.recommendation_id.in_(rec_ids))
                )
            ).scalars().all()
            seen_refs = set()
            for s in src_rows:
                if s.article_reference not in seen_refs:
                    seen_refs.add(s.article_reference)
                    sources_out.append({
                        "article_id": s.article_reference,
                        "title": s.source_title,
                        "relevance_score": round(float(s.relevance_score), 3),
                        "snippet": s.snippet,
                    })

    fb_rows = (
        await session.execute(
            select(IncidentFeedback)
            .where(IncidentFeedback.incident_id == incident_id)
            .order_by(desc(IncidentFeedback.created_at))
        )
    ).scalars().all()

    prop_obj = (
        await session.execute(
            select(KnowledgeProposal)
            .where(KnowledgeProposal.incident_id == incident_id)
            .order_by(desc(KnowledgeProposal.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    approval_rows = (
        await session.execute(
            select(ActionApproval)
            .where(ActionApproval.incident_id == incident_id)
            .order_by(desc(ActionApproval.requested_at))
        )
    ).scalars().all()

    exec_rows = (
        await session.execute(
            select(ActionExecution)
            .where(ActionExecution.incident_id == incident_id)
            .order_by(desc(ActionExecution.started_at))
        )
    ).scalars().all()

    inv_findings: List[str] = []
    if analysis and isinstance(getattr(analysis, "agent_telemetry", None), dict):
        inv_entry = analysis.agent_telemetry.get("Investigation Agent")
        if isinstance(inv_entry, dict) and isinstance(inv_entry.get("findings"), list):
            inv_findings = list(inv_entry["findings"])

    has_pending_approval = any(a.status in ("pending_approval", "PENDING") for a in approval_rows)

    return {
        "id": str(inc.id),
        "incident_number": inc.incident_number,
        "title": inc.title,
        "severity": inc.severity,
        "status": inc.status,
        "hitl_state": "waiting_human_approval" if has_pending_approval else "completed",
        "entity_id": inc.entity_id,
        "primary_asset_name": inc.primary_asset_name,
        "zabbix_host_id": inc.zabbix_host_id,
        "glpi_ticket_id": inc.glpi_ticket_id,
        "opened_at": inc.opened_at.isoformat(),
        "recovery_at": inc.recovery_at.isoformat() if inc.recovery_at else None,
        "events_count": len(events),
        "events": [
            {
                "event_id": e.zabbix_event_id,
                "status": e.event_status,
                "severity": e.severity,
                "metric": e.metric_key,
                "value": e.metric_value,
                "timestamp": e.event_timestamp.isoformat(),
            }
            for e in events
        ],
        "latest_analysis": {
            "model": analysis.model_name,
            "execution_mode": getattr(analysis, "execution_mode", "deterministic"),
            "duration_ms": analysis.duration_ms,
            "prompt_tokens": getattr(analysis, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(analysis, "completion_tokens", 0) or 0,
            "estimated_cost_usd": getattr(analysis, "estimated_cost_usd", 0.0) or 0.0,
            "agent_telemetry": getattr(analysis, "agent_telemetry", {}) or {},
            "investigation_findings": inv_findings,
            "hypotheses": analysis.hypotheses,
            "checks": analysis.checks,
            "confidence_level": analysis.confidence_level,
            "confidence_explanation": analysis.confidence_explanation,
            "knowledge_sources": sources_out,
            "created_at": analysis.created_at.isoformat(),
            "recommendations": [
                {
                    "id": str(r.id),
                    "action_text": r.action_text,
                    "runbook_id": r.runbook_id,
                    "parameters": r.parameters,
                    "execution_mode": r.execution_mode,
                    "risk_level": r.risk_level,
                    "requires_approval": r.requires_approval,
                }
                for r in recs
            ],
        } if analysis else None,
        "approvals": [
            {
                "id": str(a.id),
                "runbook_identifier": a.runbook_identifier,
                "parameters": a.parameters,
                "status": a.status,
                "thread_id": getattr(a, "thread_id", None),
                "checkpoint_id": getattr(a, "checkpoint_id", None),
                "risk_level": getattr(a, "risk_level", "MEDIUM"),
                "action_summary": getattr(a, "action_summary", None),
                "execution_id": str(a.execution_id) if getattr(a, "execution_id", None) else None,
                "requested_at": a.requested_at.isoformat(),
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                "decided_by_user": a.decided_by_user,
                "rejection_reason": a.rejection_reason,
            }
            for a in approval_rows
        ],
        "executions": [
            {
                "id": str(ex.id),
                "runbook_identifier": ex.runbook_identifier,
                "approved_by": ex.approved_by,
                "execution_status": ex.execution_status,
                "exit_code": ex.exit_code,
                "stdout": ex.stdout,
                "stderr": ex.stderr,
                "duration_seconds": ex.duration_seconds,
                "started_at": ex.started_at.isoformat(),
            }
            for ex in exec_rows
        ],
        "feedbacks": [
            {
                "id": str(f.id),
                "technician_username": f.technician_username,
                "is_recommendation_accepted": f.is_recommendation_accepted,
                "rating_score": f.rating_score,
                "feedback_notes": f.feedback_notes,
                "created_at": f.created_at.isoformat(),
            }
            for f in fb_rows
        ],
        "kb_proposal": {
            "id": str(prop_obj.id),
            "title": prop_obj.title,
            "status": prop_obj.status,
            "glpi_kb_id": prop_obj.glpi_kb_id,
            "created_at": prop_obj.created_at.isoformat(),
        } if prop_obj else None,
    }


@router.post("/{incident_id}/analyze")
async def trigger_incident_analysis(
    incident_id: UUID,
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Déclenche manuellement une nouvelle analyse LangGraph enrichie (RBAC operator+, anti-IDOR, anti-DoS)."""
    if not current_user.has_sufficient_role("operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits insuffisants : le rôle 'operator' ou 'admin' est requis pour relancer une analyse IA.",
        )

    client_ip = request.client.host if request.client else "unknown"
    if not default_limiter.is_allowed(f"incident_analyze:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes d'analyse simultanées. Veuillez patienter.",
        )

    start_t = time.time()
    stmt = select(Incident).where(Incident.id == incident_id)
    inc = (await session.execute(stmt)).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident introuvable")

    inc_entity = _safe_entity_id(inc)
    if not current_user.can_access_entity(inc_entity):
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                user_id=current_user.id,
                action="INCIDENT_IDOR_BLOCKED",
                resource_type="incident",
                resource_id=str(incident_id),
                details={"username": current_user.username, "target_entity": inc_entity, "endpoint": "analyze"},
            )
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à l'entité GLPI de cet incident",
        )

    primary_event_data = {
        "problem": inc.title,
        "severity": inc.severity,
        "host_name": inc.primary_asset_name,
        "host_id": inc.zabbix_host_id,
    }

    enriched = await enrich_incident_context(inc, primary_event_data, session)
    if enriched["events"]:
        first_ev = enriched["events"][0]
        if first_ev.get("metric"):
            primary_event_data["metric"] = first_ev.get("metric")
        if first_ev.get("value") is not None:
            primary_event_data["value"] = first_ev.get("value")

    state: IncidentAgentState = {
        "incident_id": str(inc.id),
        "ticket_id": int(inc.glpi_ticket_id) if inc.glpi_ticket_id and inc.glpi_ticket_id.isdigit() else None,
        "entity_id": str(inc.entity_id or "0"),
        "host_name": inc.primary_asset_name,
        "zabbix_host_id": inc.zabbix_host_id,
        "primary_event": primary_event_data,
        "events": enriched["events"],
        "asset_info": enriched["asset_info"],
        "metric_history": enriched["metric_history"],
        "approved_runbook_ids": enriched["approved_runbook_ids"],
        "observations": [],
    }

    thread_id = f"incident-{inc.id}-{uuid.uuid4().hex[:8]}"
    hitl_res = await start_hitl_incident_analysis(state, thread_id=thread_id)
    result = hitl_res["state"]
    report = result.get("diagnostic_report", {})
    dur_ms = int((time.time() - start_t) * 1000)

    await persist_analysis_result(inc, result, dur_ms, session)
    approval = await create_pending_approval_if_paused(inc, hitl_res, session)
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            user_id=current_user.id,
            action="INCIDENT_MANUAL_ANALYSIS_TRIGGERED",
            resource_type="incident",
            resource_id=str(inc.id),
            details={"triggered_by": current_user.username, "thread_id": thread_id, "duration_ms": dur_ms},
        )
    )
    await session.commit()

    return {
        "status": "waiting_human_approval" if hitl_res.get("paused") else "analyzed",
        "hitl_paused": bool(hitl_res.get("paused")),
        "thread_id": thread_id,
        "approval_id": str(approval.id) if approval else None,
        "report": report,
    }


@router.post("/{incident_id}/feedback", status_code=status.HTTP_201_CREATED)
async def submit_incident_feedback(
    incident_id: UUID,
    req: IncidentFeedbackRequest,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Enregistre le retour d'expérience technicien et enrichit/crée la proposition KB associée."""
    inc = (await session.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident introuvable")

    inc_entity = _safe_entity_id(inc)
    if not current_user.can_access_entity(inc_entity):
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                user_id=current_user.id,
                action="INCIDENT_IDOR_BLOCKED",
                resource_type="incident",
                resource_id=str(incident_id),
                details={"username": current_user.username, "target_entity": inc_entity, "endpoint": "feedback"},
            )
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à l'entité GLPI de cet incident",
        )

    feedback = IncidentFeedback(
        id=uuid.uuid4(),
        incident_id=inc.id,
        technician_username=current_user.username,
        is_recommendation_accepted=req.is_recommendation_accepted,
        rating_score=req.rating_score,
        feedback_notes=req.feedback_notes,
    )
    session.add(feedback)

    session.add(
        AuditLog(
            id=uuid.uuid4(),
            user_id=current_user.id,
            action="INCIDENT_FEEDBACK_RECORDED",
            resource_type="incident",
            resource_id=str(inc.id),
            details={
                "technician": current_user.username,
                "accepted": req.is_recommendation_accepted,
                "rating": req.rating_score,
            },
        )
    )

    proposal_id: Optional[str] = None
    if req.generate_kb_proposal:
        last_exec = (
            await session.execute(
                select(ActionExecution)
                .where(ActionExecution.incident_id == inc.id)
                .order_by(desc(ActionExecution.started_at))
                .limit(1)
            )
        ).scalar_one_or_none()

        last_run = (
            await session.execute(
                select(AIAnalysisRun)
                .where(AIAnalysisRun.incident_id == inc.id)
                .order_by(desc(AIAnalysisRun.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()

        hyp_txt = (
            ", ".join(html.escape(str(h.get("description", ""))) for h in (last_run.hypotheses or []))
            if last_run
            else "Diagnostic opérationnel"
        )
        exec_txt = (
            f"Runbook {html.escape(last_exec.runbook_identifier)} ({html.escape(last_exec.execution_status)}) : "
            f"{html.escape((last_exec.stdout or '')[:400])}"
            if last_exec
            else "Résolution validée manuellement par l'opérateur"
        )
        notes_html = html.escape(req.feedback_notes or "Procédure confirmée en exploitation.")
        kb_html = (
            f"<h3>Incident résolu : {html.escape(inc.title)} ({html.escape(inc.primary_asset_name)})</h3>\n"
            f"<p><strong>Cause racine qualifiée :</strong> {hyp_txt}</p>\n"
            f"<p><strong>Remédiation appliquée :</strong> {exec_txt}</p>\n"
            f"<p><strong>Validation Technicien ({html.escape(current_user.username)}, note {req.rating_score}/5) :</strong> {notes_html}</p>"
        )

        existing_prop = (
            await session.execute(
                select(KnowledgeProposal).where(KnowledgeProposal.incident_id == inc.id).limit(1)
            )
        ).scalar_one_or_none()

        if existing_prop:
            existing_prop.content = kb_html
            existing_prop.status = "pending_review"
            existing_prop.created_by = current_user.username
            proposal_id = str(existing_prop.id)
        else:
            new_prop = KnowledgeProposal(
                id=uuid.uuid4(),
                incident_id=inc.id,
                title=f"Procédure validée : {inc.title}"[:250],
                category="AIOps - Retours d'expérience",
                content=kb_html,
                entity_id=str(inc.entity_id or "0"),
                status="pending_review",
                created_by=current_user.username,
            )
            session.add(new_prop)
            await session.flush()
            proposal_id = str(new_prop.id)

    await session.commit()

    return {
        "feedback_id": str(feedback.id),
        "proposal_id": proposal_id,
        "status": "recorded",
    }
