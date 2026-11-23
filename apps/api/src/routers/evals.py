"""Routes API d'évaluation continue IA (Eval Harness : Dataset Golden, Exécution pass@k, Historique)."""

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from database.connection import get_db_session
from packages.domain.models.database import AIEvalCaseResult, AIEvalRun, AuditLog
from packages.evals.src.dataset import DATASET_VERSION, GOLDEN_EVAL_CASES
from packages.evals.src.persistence import get_latest_baseline_score, persist_eval_report
from packages.evals.src.runner import eval_harness_runner
from packages.security.src.rate_limiter import default_limiter

router = APIRouter(prefix="/api/v1/evals", tags=["AI Evaluation Harness"])


class EvalRunRequest(BaseModel):
    """Paramètres d'exécution d'une campagne d'évaluation continue."""

    execution_mode: Literal["fast_deterministic", "hybrid_llm"] = "fast_deterministic"
    k_trials: int = Field(1, ge=1, le=5)
    categories: Optional[List[str]] = None


def _serialize_eval_run(row: AIEvalRun) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "dataset_version": row.dataset_version,
        "execution_mode": row.execution_mode,
        "model_name": row.model_name,
        "triggered_by": row.triggered_by,
        "k_trials": row.k_trials,
        "total_cases": row.total_cases,
        "passed_cases": row.passed_cases,
        "overall_score": row.overall_score,
        "pass_at_k": row.pass_at_k,
        "pass_pow_k": row.pass_pow_k,
        "diagnosis_accuracy": row.diagnosis_accuracy,
        "rag_recall_at_k": row.rag_recall_at_k,
        "rag_mrr": row.rag_mrr,
        "hitl_safety_rate": row.hitl_safety_rate,
        "security_guardrail_rate": row.security_guardrail_rate,
        "avg_latency_ms": row.avg_latency_ms,
        "p95_latency_ms": row.p95_latency_ms,
        "total_tokens": row.total_tokens,
        "estimated_cost_usd": row.estimated_cost_usd,
        "gate_passed": row.gate_passed,
        "regression_detected": row.regression_detected,
        "delta_vs_baseline": row.delta_vs_baseline,
        "gate_reasons": row.gate_reasons or [],
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _serialize_case_result(c: AIEvalCaseResult) -> Dict[str, Any]:
    return {
        "id": str(c.id),
        "case_id": c.case_id,
        "case_name": c.case_name,
        "category": c.category,
        "passed": c.passed,
        "score": c.score,
        "trials_passed": c.trials_passed,
        "trials_total": c.trials_total,
        "latency_ms": c.latency_ms,
        "tokens_used": c.tokens_used,
        "rag_recall_at_k": c.rag_recall_at_k,
        "rag_mrr": c.rag_mrr,
        "checks": c.checks or [],
        "actual_summary": c.actual_summary or {},
        "error_message": c.error_message,
    }


@router.get("/dataset")
async def get_eval_dataset() -> Dict[str, Any]:
    """Expose le jeu de scénarios Golden de référence et ses catégories."""
    counts = dict(Counter(case.category for case in GOLDEN_EVAL_CASES))
    return {
        "dataset_version": DATASET_VERSION,
        "total_cases": len(GOLDEN_EVAL_CASES),
        "categories": counts,
        "cases": [case.model_dump() for case in GOLDEN_EVAL_CASES],
    }


@router.get("/summary")
async def get_eval_summary(
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retourne le dernier run, le score baseline validé et l'historique récent des évaluations."""
    recent_rows = list(
        (
            await session.execute(
                select(AIEvalRun).order_by(desc(AIEvalRun.started_at)).limit(10)
            )
        ).scalars().all()
    )
    baseline_score = await get_latest_baseline_score(session, "fast_deterministic")
    total_runs = (await session.execute(select(func.count(AIEvalRun.id)))).scalar() or len(recent_rows)

    latest_run = _serialize_eval_run(recent_rows[0]) if recent_rows else None
    return {
        "dataset_version": DATASET_VERSION,
        "latest_run": latest_run,
        "baseline_score": baseline_score,
        "total_runs": int(total_runs),
        "history": [_serialize_eval_run(r) for r in recent_rows],
    }


@router.get("/runs")
async def list_eval_runs(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Liste les campagnes d'évaluation récentes."""
    rows = (
        await session.execute(select(AIEvalRun).order_by(desc(AIEvalRun.started_at)).limit(limit))
    ).scalars().all()
    return [_serialize_eval_run(r) for r in rows]


@router.get("/runs/{run_id}")
async def get_eval_run_detail(
    run_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retourne le détail complet d'une campagne d'évaluation et de ses scénarios."""
    run_row = (
        await session.execute(select(AIEvalRun).where(AIEvalRun.id == run_id))
    ).scalar_one_or_none()
    if not run_row:
        raise HTTPException(status_code=404, detail="Campagne d'évaluation introuvable")

    cases = (
        await session.execute(
            select(AIEvalCaseResult)
            .where(AIEvalCaseResult.eval_run_id == run_id)
            .order_by(AIEvalCaseResult.category, AIEvalCaseResult.case_id)
        )
    ).scalars().all()

    out = _serialize_eval_run(run_row)
    out["case_results"] = [_serialize_case_result(c) for c in cases]
    return out


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def trigger_eval_run(
    payload: EvalRunRequest,
    request: Request,
    current_user: AuthenticatedUserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Lance une campagne d'évaluation continue IA (opérateur/admin requis), persiste les métriques et audite l'action."""
    if not current_user.has_sufficient_role("operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rôle insuffisant ({current_user.role}). Opérateur ou administrateur requis.",
        )

    client_ip = request.client.host if request.client else "unknown"
    if not default_limiter.is_allowed(f"eval_run:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de campagnes d'évaluation déclenchées. Veuillez patienter.",
        )

    started_at = datetime.now(timezone.utc)
    baseline_score = await get_latest_baseline_score(session, payload.execution_mode)

    report = await eval_harness_runner.run_suite(
        execution_mode=payload.execution_mode,
        k_trials=payload.k_trials,
        categories=payload.categories,
        baseline_score=baseline_score,
        session=session,
    )
    finished_at = datetime.now(timezone.utc)

    run_row, case_rows = await persist_eval_report(
        session=session,
        report=report,
        triggered_by=current_user.username,
        started_at=started_at,
        finished_at=finished_at,
    )

    session.add(
        AuditLog(
            id=uuid4(),
            user_id=current_user.id,
            action="AI_EVAL_RUN_EXECUTED",
            resource_type="AIEvalRun",
            resource_id=str(run_row.id),
            details={
                "execution_mode": report.execution_mode,
                "k_trials": report.k_trials,
                "overall_score": report.overall_score,
                "pass_at_k": report.pass_at_k,
                "pass_pow_k": report.pass_pow_k,
                "gate_passed": report.gate_passed,
                "regression_detected": report.regression_detected,
            },
        )
    )
    await session.commit()

    out = _serialize_eval_run(run_row)
    out["case_results"] = [_serialize_case_result(c) for c in case_rows]
    return out
