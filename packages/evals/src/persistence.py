"""Helpers de persistance PostgreSQL pour les campagnes d'évaluation continue AI."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from packages.domain.models.database import AIEvalCaseResult, AIEvalRun
from packages.evals.src.graders import EvalRunReport


async def get_latest_baseline_score(
    session: AsyncSession,
    execution_mode: str,
) -> Optional[float]:
    """Récupère le score du dernier run réussi (gate_passed=True) pour le mode donné."""
    stmt = (
        select(AIEvalRun.overall_score)
        .where(AIEvalRun.gate_passed == True, AIEvalRun.execution_mode == execution_mode)  # noqa: E712
        .order_by(desc(AIEvalRun.started_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def persist_eval_report(
    session: AsyncSession,
    report: EvalRunReport,
    triggered_by: str,
    started_at: datetime,
    finished_at: Optional[datetime] = None,
) -> Tuple[AIEvalRun, List[AIEvalCaseResult]]:
    """Enregistre un EvalRunReport complet (AIEvalRun + AIEvalCaseResult) dans PostgreSQL."""
    done_at = finished_at or datetime.now(timezone.utc)
    run_row = AIEvalRun(
        id=uuid.uuid4(),
        dataset_version=report.dataset_version,
        execution_mode=report.execution_mode,
        model_name=report.model_name,
        triggered_by=triggered_by,
        k_trials=report.k_trials,
        total_cases=report.total_cases,
        passed_cases=report.passed_cases,
        overall_score=report.overall_score,
        pass_at_k=report.pass_at_k,
        pass_pow_k=report.pass_pow_k,
        diagnosis_accuracy=report.diagnosis_accuracy,
        rag_recall_at_k=report.rag_recall_at_k,
        rag_mrr=report.rag_mrr,
        hitl_safety_rate=report.hitl_safety_rate,
        security_guardrail_rate=report.security_guardrail_rate,
        avg_latency_ms=report.avg_latency_ms,
        p95_latency_ms=report.p95_latency_ms,
        total_tokens=report.total_tokens,
        estimated_cost_usd=report.estimated_cost_usd,
        gate_passed=report.gate_passed,
        regression_detected=report.regression_detected,
        delta_vs_baseline=report.delta_vs_baseline,
        gate_reasons=report.gate_reasons,
        started_at=started_at,
        finished_at=done_at,
    )
    session.add(run_row)
    await session.flush()

    case_rows: List[AIEvalCaseResult] = []
    for cr in report.case_results:
        case_row = AIEvalCaseResult(
            id=uuid.uuid4(),
            eval_run_id=run_row.id,
            case_id=cr.case_id,
            case_name=cr.case_name,
            category=cr.category,
            passed=cr.passed,
            score=cr.score,
            trials_passed=cr.trials_passed,
            trials_total=cr.trials_total,
            latency_ms=cr.latency_ms,
            tokens_used=cr.tokens_used,
            rag_recall_at_k=cr.rag_recall_at_k,
            rag_mrr=cr.rag_mrr,
            checks=[c.model_dump() for c in cr.checks],
            actual_summary=cr.actual_summary,
            error_message=cr.error_message,
        )
        session.add(case_row)
        case_rows.append(case_row)
    return run_row, case_rows
