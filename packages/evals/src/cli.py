"""Interface CLI CI/CD pour le Release Gate du harness d'évaluation continue AIOps."""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from database.connection import async_session_maker
from packages.evals.src.persistence import get_latest_baseline_score, persist_eval_report
from packages.evals.src.runner import eval_harness_runner


async def _run_cli(
    mode: str,
    k_trials: int,
    categories: Optional[List[str]],
    persist: bool,
    json_out: Optional[str],
) -> int:
    started_at = datetime.now(timezone.utc)
    baseline_score: Optional[float] = None
    report = None

    try:
        async with async_session_maker() as session:
            baseline_score = await get_latest_baseline_score(session, mode)
            report = await eval_harness_runner.run_suite(
                execution_mode=mode,
                k_trials=k_trials,
                categories=categories,
                baseline_score=baseline_score,
                session=session,
            )
            if persist:
                await persist_eval_report(
                    session=session,
                    report=report,
                    triggered_by="cli",
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                )
                await session.commit()
    except Exception:
        if report is None:
            report = await eval_harness_runner.run_suite(
                execution_mode=mode,
                k_trials=k_trials,
                categories=categories,
                baseline_score=baseline_score,
                session=None,
            )

    print(
        f"\n[AIOps Eval Harness v{report.dataset_version}] mode={report.execution_mode} k={report.k_trials} "
        f"| passed={report.passed_cases}/{report.total_cases} | overall={report.overall_score:.2f} "
        f"| pass@k={report.pass_at_k:.2f} | pass^k={report.pass_pow_k:.2f} "
        f"| rag_recall={report.rag_recall_at_k:.2f} | mrr={report.rag_mrr:.2f} "
        f"| faith={report.rag_faithfulness:.2f} "
        f"| sec={report.security_guardrail_rate:.2f} | hitl={report.hitl_safety_rate:.2f}"
    )
    for cr in report.case_results:
        badge = "PASS" if cr.passed else "FAIL"
        print(
            f"  [{badge}] {cr.case_id:<38} ({cr.category:<18}) "
            f"score={cr.score:.2f} trials={cr.trials_passed}/{cr.trials_total} ({cr.latency_ms}ms)"
        )
    if report.gate_reasons:
        print("Release Gate Reasons:")
        for reason in report.gate_reasons:
            print(f"  - {reason}")
    print(f"RELEASE GATE: {'PASSED' if report.gate_passed else 'FAILED'}\n")

    if json_out:
        Path(json_out).write_text(report.model_dump_json(indent=2), encoding="utf-8")

    return 0 if report.gate_passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Exécute le harness d'évaluation continue AIOps (Release Gate).")
    parser.add_argument("--mode", choices=["fast_deterministic", "hybrid_llm"], default="fast_deterministic")
    parser.add_argument("--k", type=int, default=1, help="Nombre d'essais par scénario (pass@k / pass^k)")
    parser.add_argument("--categories", type=str, default="", help="Catégories séparées par virgules")
    parser.add_argument("--persist", action="store_true", help="Persiste le run dans PostgreSQL (ai_eval_runs)")
    parser.add_argument("--json-out", type=str, default=None, help="Chemin optionnel d'export JSON")
    args = parser.parse_args()

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] or None
    exit_code = asyncio.run(_run_cli(args.mode, args.k, cats, args.persist, args.json_out))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
