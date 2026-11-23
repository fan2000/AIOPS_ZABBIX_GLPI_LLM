"""Enrichissement de contexte CMDB/Zabbix et persistance intégrale des diagnostics, citations RAG et propositions KB."""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.connectors.glpi.src.client import glpi_client
from packages.connectors.zabbix.src.client import zabbix_client
from packages.domain.models.database import (
    AIAnalysisRun,
    AIRecommendation,
    ActionApproval,
    Asset,
    Incident,
    IncidentEvent,
    KnowledgeProposal,
    RecommendationSource,
    Runbook,
)
from packages.observability.src.metrics import record_hitl_decision


async def enrich_incident_context(
    incident: Incident,
    primary_event: Dict[str, Any],
    session: AsyncSession,
) -> Dict[str, Any]:
    """Collecte le contexte réel (CMDB Asset, historique Zabbix, événements corrélés, runbooks actifs)."""
    # 1. Chargement ou enrichissement de la fiche Asset CMDB
    asset_info: Dict[str, Any] = {}
    asset_stmt = select(Asset).where(
        (Asset.zabbix_host_id == incident.zabbix_host_id)
        | (Asset.name == incident.primary_asset_name)
    ).limit(1)
    asset_obj = (await session.execute(asset_stmt)).scalar_one_or_none()

    if asset_obj is None:
        glpi_asset = None
        zbx_host = None
        try:
            glpi_asset = await glpi_client.search_computer(incident.primary_asset_name)
        except Exception:
            glpi_asset = None
        try:
            if incident.zabbix_host_id and incident.zabbix_host_id not in ("0", "UNKNOWN"):
                zbx_host = await zabbix_client.get_host(incident.zabbix_host_id)
        except Exception:
            zbx_host = None

        ip_addr = (incident.incident_metadata or {}).get("ip_address")
        if not ip_addr and zbx_host and isinstance(zbx_host.get("interfaces"), list) and zbx_host["interfaces"]:
            ip_addr = zbx_host["interfaces"][0].get("ip")

        # Inférence propre de l'OS à partir du profil hôte / tags si CMDB vide
        host_lower = (incident.primary_asset_name or "").lower()
        os_guess = None
        if zbx_host and zbx_host.get("description"):
            os_guess = str(zbx_host["description"])[:95]
        elif "win" in host_lower:
            os_guess = "Windows Server"
        elif any(k in host_lower for k in ("lnx", "linux", "srv-", "zabbix", "web", "db")):
            os_guess = "Linux"

        asset_obj = Asset(
            id=uuid.uuid4(),
            name=incident.primary_asset_name,
            zabbix_host_id=incident.zabbix_host_id,
            glpi_id=glpi_asset.id if glpi_asset else None,
            entity_id=str(glpi_asset.entity_id) if glpi_asset else str(incident.entity_id or "0"),
            ip_address=ip_addr,
            os_name=os_guess,
            tags={"site_code": (incident.incident_metadata or {}).get("site_code", "PAR-DC1")},
        )
        session.add(asset_obj)
        await session.flush()
    else:
        asset_obj.last_seen_at = datetime.now(timezone.utc)

    asset_info = {
        "name": asset_obj.name,
        "operatingsystem": asset_obj.os_name or "",
        "ip_address": asset_obj.ip_address or "",
        "glpi_id": asset_obj.glpi_id,
        "entity_id": asset_obj.entity_id,
    }

    # 2. Chargement de tous les événements rattachés à l'incident
    ev_stmt = (
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident.id)
        .order_by(desc(IncidentEvent.event_timestamp))
    )
    db_events = (await session.execute(ev_stmt)).scalars().all()
    all_events: List[Dict[str, Any]] = [
        {
            "problem": e.raw_payload.get("problem", incident.title)
            if isinstance(e.raw_payload, dict)
            else incident.title,
            "severity": e.severity,
            "host_name": e.host_name,
            "host_id": incident.zabbix_host_id,
            "metric": e.metric_key,
            "value": e.metric_value,
            "event_id": e.zabbix_event_id,
        }
        for e in db_events
    ] or [primary_event]

    # 3. Historique métrique Zabbix (best-effort si item_id présent)
    metric_history: List[Dict[str, Any]] = []
    item_id = None
    for ev_row in db_events:
        if isinstance(ev_row.raw_payload, dict):
            item_id = ev_row.raw_payload.get("item_id") or ev_row.raw_payload.get("itemid")
            if item_id:
                break
    if item_id:
        try:
            raw_hist = await zabbix_client.get_item_history(str(item_id), limit=10)
            if isinstance(raw_hist, list):
                metric_history = raw_hist
        except Exception:
            metric_history = []

    # 4. Runbooks actifs en base pour validation dynamique
    rb_rows = (
        await session.execute(select(Runbook.identifier).where(Runbook.is_enabled == True))
    ).scalars().all()
    approved_runbook_ids = list(rb_rows) if rb_rows else []

    return {
        "asset_info": asset_info,
        "events": all_events,
        "metric_history": metric_history,
        "approved_runbook_ids": approved_runbook_ids,
    }


async def persist_analysis_result(
    incident: Incident,
    final_state: Dict[str, Any],
    duration_ms: int,
    session: AsyncSession,
) -> AIAnalysisRun:
    """Persiste l'analyse, ses recommandations, les citations RAG sourcées et le brouillon KnowledgeProposal."""
    report = final_state.get("diagnostic_report") or {}
    conf = report.get("confidence", {})
    conf_level = conf.get("level", "moderate") if isinstance(conf, dict) else str(conf or "moderate")
    conf_expl = conf.get("explanation", "") if isinstance(conf, dict) else ""

    ai_run = AIAnalysisRun(
        id=uuid.uuid4(),
        incident_id=incident.id,
        model_name=str(final_state.get("model_used") or os.getenv("OLLAMA_MODEL", "gemma4:latest")),
        execution_mode=str(final_state.get("execution_mode") or "deterministic"),
        execution_status="completed",
        duration_ms=max(0, int(duration_ms)),
        prompt_tokens=int(final_state.get("prompt_tokens") or 0),
        completion_tokens=int(final_state.get("completion_tokens") or 0),
        estimated_cost_usd=float(final_state.get("estimated_cost_usd") or 0.0),
        hypotheses=report.get("hypotheses", []),
        checks=report.get("checks", []),
        confidence_level=conf_level,
        confidence_explanation=conf_expl,
        agent_telemetry=final_state.get("agent_telemetry") or {},
        validation_passed=bool(final_state.get("validation_passed", True)),
        blocked_actions_count=int(final_state.get("blocked_actions_count") or 0),
    )
    session.add(ai_run)
    await session.flush()

    sources_data = report.get("knowledge_sources", []) or final_state.get("rag_citations", []) or []

    for action in report.get("recommended_actions", []):
        recommendation = AIRecommendation(
            id=uuid.uuid4(),
            analysis_run_id=ai_run.id,
            action_text=str(action.get("action", "")),
            runbook_id=action.get("runbook_id"),
            parameters=action.get("parameters", {}),
            execution_mode=str(action.get("execution_mode", "read_only")),
            risk_level=str(action.get("risk_level", "LOW")),
            requires_approval=bool(action.get("requires_approval", True)),
        )
        session.add(recommendation)
        await session.flush()

        for src in sources_data:
            try:
                session.add(
                    RecommendationSource(
                        id=uuid.uuid4(),
                        recommendation_id=recommendation.id,
                        article_reference=str(src.get("article_id", "KB-REF")),
                        source_title=str(src.get("title", "Document de référence"))[:255],
                        relevance_score=float(src.get("relevance_score", 0.0)),
                        snippet=str(src.get("snippet", "")),
                    )
                )
            except Exception:
                pass

    # Persistance d'une proposition KB initiale si aucune n'existe déjà pour cet incident
    kb_draft = final_state.get("kb_proposal")
    if isinstance(kb_draft, dict) and kb_draft.get("title") and kb_draft.get("content"):
        existing_prop = (
            await session.execute(
                select(KnowledgeProposal).where(KnowledgeProposal.incident_id == incident.id).limit(1)
            )
        ).scalar_one_or_none()
        if not existing_prop:
            session.add(
                KnowledgeProposal(
                    id=uuid.uuid4(),
                    incident_id=incident.id,
                    title=str(kb_draft["title"])[:255],
                    category=str(kb_draft.get("category", "AIOps - Retours d'expérience"))[:120],
                    content=str(kb_draft["content"]),
                    entity_id=str(incident.entity_id or kb_draft.get("entity_id") or "0"),
                    status="pending_review",
                    created_by="feedback-agent",
                )
            )

    return ai_run


async def create_pending_approval_if_paused(
    incident: Incident,
    hitl_result: Dict[str, Any],
    session: AsyncSession,
) -> Optional[ActionApproval]:
    """Crée une demande ActionApproval liée au checkpoint LangGraph lorsque le graphe est mis en pause HITL."""
    if not hitl_result.get("paused"):
        return None

    final_state = hitl_result.get("state") or {}
    pending_action = final_state.get("pending_approval_action")
    if not isinstance(pending_action, dict) or not pending_action.get("runbook_id"):
        return None

    runbook_id = str(pending_action["runbook_id"])
    risk_level = str(pending_action.get("risk_level") or "MEDIUM")
    thread_id = str(hitl_result.get("thread_id") or "")
    checkpoint_id = str(hitl_result.get("checkpoint_id") or "") or None
    action_summary = str(pending_action.get("action") or runbook_id)
    parameters = pending_action.get("parameters") or {}

    existing_stmt = select(ActionApproval).where(
        ActionApproval.incident_id == incident.id,
        ActionApproval.runbook_identifier == runbook_id,
        ActionApproval.status == "pending_approval",
    ).limit(1)
    approval = (await session.execute(existing_stmt)).scalar_one_or_none()

    if approval is not None:
        approval.thread_id = thread_id
        approval.checkpoint_id = checkpoint_id
        approval.parameters = parameters
        approval.risk_level = risk_level
        approval.action_summary = action_summary
        approval.requested_at = datetime.now(timezone.utc)
    else:
        approval = ActionApproval(
            id=uuid.uuid4(),
            incident_id=incident.id,
            runbook_identifier=runbook_id,
            parameters=parameters,
            status="pending_approval",
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            risk_level=risk_level,
            action_summary=action_summary,
        )
        session.add(approval)
        record_hitl_decision("pending", risk_level)

    incident.status = "WAITING_APPROVAL"
    return approval


async def upsert_kb_proposal_from_state(
    incident: Incident,
    resumed_state: Dict[str, Any],
    session: AsyncSession,
    created_by: str = "feedback-agent",
) -> Optional[KnowledgeProposal]:
    """Crée ou met à jour la proposition KB après reprise complète et exécution de feedback_agent."""
    kb_draft = resumed_state.get("kb_proposal")
    if not isinstance(kb_draft, dict) or not kb_draft.get("title") or not kb_draft.get("content"):
        return None

    existing_prop = (
        await session.execute(
            select(KnowledgeProposal).where(KnowledgeProposal.incident_id == incident.id).limit(1)
        )
    ).scalar_one_or_none()

    if existing_prop:
        existing_prop.title = str(kb_draft["title"])[:255]
        existing_prop.content = str(kb_draft["content"])
        existing_prop.created_by = created_by
        if existing_prop.status not in ("approved_published",):
            existing_prop.status = "pending_review"
        return existing_prop

    prop = KnowledgeProposal(
        id=uuid.uuid4(),
        incident_id=incident.id,
        title=str(kb_draft["title"])[:255],
        category=str(kb_draft.get("category", "AIOps - Retours d'expérience"))[:120],
        content=str(kb_draft["content"]),
        entity_id=str(incident.entity_id or kb_draft.get("entity_id") or "0"),
        status="pending_review",
        created_by=created_by,
    )
    session.add(prop)
    return prop
