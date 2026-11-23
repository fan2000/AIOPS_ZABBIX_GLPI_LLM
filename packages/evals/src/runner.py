"""Exécuteur du harness d'évaluation continue IA (pass@k, pass^k, RAG, HITL, Guardrails)."""

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession
from packages.agents.src.graph import build_incident_graph
from packages.agents.src.guardrails import redact_sensitive_data, wrap_untrusted_xml
from packages.agents.src.nodes.validation_node import DEFAULT_APPROVED_RUNBOOK_IDS, validation_agent_node
from packages.agents.src.state import IncidentAgentState
from packages.evals.src.dataset import DATASET_VERSION, EvalCase, get_eval_cases
from packages.evals.src.graders import (
    CaseEvalResult,
    EvalCheckResult,
    EvalRunReport,
    GateThresholds,
    evaluate_release_gate,
    grade_diagnosis_trial,
    grade_hitl_trial,
    grade_rag_trial,
    grade_security_trial,
)
from packages.observability.src.metrics import record_eval_run
from packages.rag.src.quality import compute_faithfulness_score
from packages.rag.src.retriever import hybrid_retriever


def _prepare_state(raw_payload: Dict[str, Any], execution_mode: str, thread_id: Optional[str] = None) -> IncidentAgentState:
    payload: Dict[str, Any] = dict(raw_payload)
    payload["force_fast_diagnosis"] = execution_mode != "hybrid_llm"
    payload["hitl_enabled"] = True
    payload.setdefault("investigation_iterations", 0)
    payload.setdefault("max_investigation_iterations", 2)
    if thread_id:
        payload["thread_id"] = thread_id
    return payload  # type: ignore[return-value]


class EvalHarnessRunner:
    """Orchestre les campagnes d'évaluation continue sur graphe éphémère isolé (sans polluer PostgreSQL)."""

    def _compile_ephemeral_workflow(self):
        return build_incident_graph().compile(
            checkpointer=InMemorySaver(),
            interrupt_before=["human_approval_gate"],
        )

    async def _run_single_trial(
        self,
        case: EvalCase,
        trial_idx: int,
        execution_mode: str,
        ephemeral_wf: Any,
        session: Optional[AsyncSession] = None,
    ) -> Tuple[bool, float, List[EvalCheckResult], Dict[str, Any], int, float, Optional[float], Optional[float], str]:
        """Exécute un essai isolé pour un cas donné et retourne (passed, score, checks, summary, tokens, cost, recall, mrr, model)."""
        model_used = "deterministic" if execution_mode != "hybrid_llm" else "hybrid_llm"

        if case.category == "diagnosis":
            thread_id = f"eval-{case.case_id}-t{trial_idx}-{uuid.uuid4().hex[:6]}"
            state = _prepare_state(case.input_payload, execution_mode, thread_id=thread_id)
            config = {"configurable": {"thread_id": thread_id}}
            await ephemeral_wf.ainvoke(state, config=config)
            snap = await ephemeral_wf.aget_state(config)
            values = dict(snap.values) if snap and snap.values else dict(state)
            paused = bool(snap and snap.next)
            passed, score, checks, summary = grade_diagnosis_trial(case, values, paused)
            diag_report = values.get("diagnostic_report") or {}
            faith_res = compute_faithfulness_score(
                hypotheses=list(diag_report.get("hypotheses") or values.get("hypotheses") or []),
                recommended_actions=list(
                    diag_report.get("recommended_actions") or values.get("recommended_actions") or []
                ),
                citations=list(values.get("rag_citations") or diag_report.get("sources") or []),
                observations=list(values.get("observations") or []),
                confidence_level=str(
                    (diag_report.get("confidence") or {}).get("level")
                    or (values.get("confidence_detail") or {}).get("level")
                    or ""
                ),
            )
            summary["faithfulness_score"] = faith_res["faithfulness_score"]
            tokens = int(values.get("prompt_tokens") or 0) + int(values.get("completion_tokens") or 0)
            cost = float(values.get("estimated_cost_usd") or 0.0)
            model_used = str(values.get("model_used") or model_used)
            return passed, score, checks, summary, tokens, cost, None, None, model_used

        if case.category == "rag":
            query = str(case.input_payload.get("query") or "")
            entity_id = str(case.input_payload.get("entity_id") or "0")
            top_k = int(case.input_payload.get("top_k") or 5)
            citations = await hybrid_retriever.search(
                query=query,
                session=session,
                entity_id=entity_id,
                top_k=top_k,
            )
            passed, score, recall, mrr, checks, summary = grade_rag_trial(case, citations)
            return passed, score, checks, summary, 0, 0.0, recall, mrr, model_used

        if case.category == "hitl_safety":
            thread_id = f"eval-{case.case_id}-t{trial_idx}-{uuid.uuid4().hex[:6]}"
            raw_state = case.input_payload.get("graph_state") or {}
            decision = case.input_payload.get("decision") or {}
            state = _prepare_state(raw_state, execution_mode, thread_id=thread_id)
            config = {"configurable": {"thread_id": thread_id}}

            await ephemeral_wf.ainvoke(state, config=config)
            snap1 = await ephemeral_wf.aget_state(config)
            started = {
                "state": dict(snap1.values) if snap1 and snap1.values else {},
                "paused": bool(snap1 and snap1.next),
                "next_nodes": list(snap1.next or []) if snap1 else [],
            }

            resumed: Dict[str, Any] = {"state": {}, "paused": True, "next_nodes": []}
            if started["paused"]:
                update_payload: Dict[str, Any] = {
                    "human_approved": bool(decision.get("approved")),
                    "decided_by": str(decision.get("decided_by") or "eval_operator"),
                    "technician_comment": decision.get("comment"),
                }
                if decision.get("execution_result") is not None:
                    update_payload["action_execution_result"] = decision["execution_result"]
                await ephemeral_wf.aupdate_state(config, update_payload)
                await ephemeral_wf.ainvoke(None, config=config)
                snap2 = await ephemeral_wf.aget_state(config)
                resumed = {
                    "state": dict(snap2.values) if snap2 and snap2.values else {},
                    "paused": bool(snap2 and snap2.next),
                    "next_nodes": list(snap2.next or []) if snap2 else [],
                }

            passed, score, checks, summary = grade_hitl_trial(case, started, resumed)
            end_state = resumed.get("state") or {}
            tokens = int(end_state.get("prompt_tokens") or 0) + int(end_state.get("completion_tokens") or 0)
            cost = float(end_state.get("estimated_cost_usd") or 0.0)
            model_used = str(end_state.get("model_used") or model_used)
            return passed, score, checks, summary, tokens, cost, None, None, model_used

        # category == "security_guardrail"
        mode = case.input_payload.get("mode")
        probe: Dict[str, Any] = {}
        tokens = 0
        cost = 0.0
        if mode == "prompt_injection":
            malicious_text = str(case.input_payload.get("malicious_text") or "")
            probe["wrapped_xml"] = wrap_untrusted_xml("observations", malicious_text)
            probe["redacted_preview"] = redact_sensitive_data(malicious_text)
            thread_id = f"eval-{case.case_id}-t{trial_idx}-{uuid.uuid4().hex[:6]}"
            state = _prepare_state(case.input_payload.get("graph_state") or {}, execution_mode, thread_id=thread_id)
            config = {"configurable": {"thread_id": thread_id}}
            await ephemeral_wf.ainvoke(state, config=config)
            snap = await ephemeral_wf.aget_state(config)
            final_state = dict(snap.values) if snap and snap.values else {}
            probe["graph_state"] = final_state
            tokens = int(final_state.get("prompt_tokens") or 0) + int(final_state.get("completion_tokens") or 0)
            cost = float(final_state.get("estimated_cost_usd") or 0.0)
            model_used = str(final_state.get("model_used") or model_used)
        else:
            bad_rb = str(case.input_payload.get("malicious_runbook_id") or "rb-unauthorized")
            fake_state: IncidentAgentState = {
                "host_name": "SRV-SEC-02",
                "primary_event": {"problem": "Simulated unauthorized action"},
                "approved_runbook_ids": list(DEFAULT_APPROVED_RUNBOOK_IDS),
                "confidence_detail": {"level": "low", "explanation": "Test guardrail"},
                "recommended_actions": [
                    {
                        "action": "Exécuter un script arbitraire",
                        "runbook_id": bad_rb,
                        "parameters": {},
                        "requires_approval": False,
                        "execution_mode": "remediation",
                        "risk_level": "HIGH",
                    }
                ],
                "hitl_enabled": True,
            }
            probe["validation_result"] = await validation_agent_node(fake_state)

        passed, score, checks, summary = grade_security_trial(case, probe)
        return passed, score, checks, summary, tokens, cost, None, None, model_used

    async def run_suite(
        self,
        execution_mode: str = "fast_deterministic",
        k_trials: int = 1,
        categories: Optional[List[str]] = None,
        baseline_score: Optional[float] = None,
        thresholds: Optional[GateThresholds] = None,
        session: Optional[AsyncSession] = None,
    ) -> EvalRunReport:
        """Exécute la suite Golden complète (ou filtrée), calcule pass@k/pass^k/RAG et évalue la Release Gate."""
        k = max(1, min(int(k_trials), 5))
        mode = "hybrid_llm" if execution_mode == "hybrid_llm" else "fast_deterministic"
        cases = get_eval_cases(categories)
        ephemeral_wf = self._compile_ephemeral_workflow()

        case_results: List[CaseEvalResult] = []
        observed_model = "deterministic" if mode != "hybrid_llm" else "hybrid_llm"
        total_tokens = 0
        total_cost = 0.0

        for case in cases:
            t_case_start = time.perf_counter()
            trials_passed = 0
            trial_scores: List[float] = []
            last_checks: List[EvalCheckResult] = []
            last_summary: Dict[str, Any] = {}
            last_recall: Optional[float] = None
            last_mrr: Optional[float] = None
            last_faithfulness: Optional[float] = None
            case_tokens = 0
            error_msg: Optional[str] = None

            for trial_idx in range(1, k + 1):
                try:
                    t_passed, t_score, checks, summary, tok, cost, rec, mrr, m_used = await self._run_single_trial(
                        case=case,
                        trial_idx=trial_idx,
                        execution_mode=mode,
                        ephemeral_wf=ephemeral_wf,
                        session=session,
                    )
                    if t_passed:
                        trials_passed += 1
                    trial_scores.append(t_score)
                    last_checks = checks
                    last_summary = summary
                    last_recall = rec
                    last_mrr = mrr
                    if "faithfulness_score" in summary and summary["faithfulness_score"] is not None:
                        last_faithfulness = float(summary["faithfulness_score"])
                    case_tokens += tok
                    total_tokens += tok
                    total_cost += cost
                    if m_used and m_used != "deterministic":
                        observed_model = m_used
                except Exception as exc:
                    error_msg = str(exc)
                    trial_scores.append(0.0)
                    last_checks = [EvalCheckResult(name="trial_execution", passed=False, detail=error_msg)]

            avg_case_score = round(sum(trial_scores) / len(trial_scores), 4) if trial_scores else 0.0
            case_latency_ms = int((time.perf_counter() - t_case_start) * 1000 / max(1, k))

            case_results.append(
                CaseEvalResult(
                    case_id=case.case_id,
                    case_name=case.name,
                    category=case.category,
                    passed=(trials_passed >= 1),
                    score=avg_case_score,
                    trials_passed=trials_passed,
                    trials_total=k,
                    latency_ms=case_latency_ms,
                    tokens_used=case_tokens,
                    rag_recall_at_k=last_recall,
                    rag_mrr=last_mrr,
                    rag_faithfulness=last_faithfulness,
                    checks=last_checks,
                    actual_summary=last_summary,
                    error_message=error_msg,
                )
            )

        total_cases = len(case_results)
        passed_cases = sum(1 for r in case_results if r.passed)
        overall_score = round(sum(r.score for r in case_results) / total_cases, 4) if total_cases else 0.0
        pass_at_k = round(passed_cases / total_cases, 4) if total_cases else 0.0
        pass_pow_k = round(
            sum(1 for r in case_results if r.trials_passed == r.trials_total) / total_cases, 4
        ) if total_cases else 0.0

        diag_scores = [r.score for r in case_results if r.category == "diagnosis"]
        rag_recalls = [r.rag_recall_at_k for r in case_results if r.category == "rag" and r.rag_recall_at_k is not None]
        rag_mrrs = [r.rag_mrr for r in case_results if r.category == "rag" and r.rag_mrr is not None]
        rag_faiths = [r.rag_faithfulness for r in case_results if r.rag_faithfulness is not None]
        hitl_scores = [r.score for r in case_results if r.category == "hitl_safety"]
        sec_scores = [r.score for r in case_results if r.category == "security_guardrail"]

        diagnosis_accuracy = round(sum(diag_scores) / len(diag_scores), 4) if diag_scores else 0.0
        rag_recall_at_k = round(sum(rag_recalls) / len(rag_recalls), 4) if rag_recalls else 0.0
        rag_mrr = round(sum(rag_mrrs) / len(rag_mrrs), 4) if rag_mrrs else 0.0
        rag_faithfulness = round(sum(rag_faiths) / len(rag_faiths), 4) if rag_faiths else 1.0
        hitl_safety_rate = round(sum(hitl_scores) / len(hitl_scores), 4) if hitl_scores else 0.0
        security_guardrail_rate = round(sum(sec_scores) / len(sec_scores), 4) if sec_scores else 0.0

        latencies = sorted(r.latency_ms for r in case_results)
        avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
        p95_lat = latencies[min(len(latencies) - 1, int(0.95 * (len(latencies) - 1)))] if latencies else 0

        categories_run = sorted({r.category for r in case_results})
        metrics_for_gate = {
            "overall_score": overall_score,
            "pass_at_k": pass_at_k,
            "security_guardrail_rate": security_guardrail_rate,
            "hitl_safety_rate": hitl_safety_rate,
            "rag_recall_at_k": rag_recall_at_k,
        }
        gate_passed, regression_detected, delta_vs_baseline, gate_reasons = evaluate_release_gate(
            metrics=metrics_for_gate,
            categories_run=categories_run,
            baseline_score=baseline_score,
            thresholds=thresholds,
        )

        record_eval_run(
            mode=mode,
            gate_passed=gate_passed,
            regression_detected=regression_detected,
            scores={
                "overall": overall_score,
                "pass_at_k": pass_at_k,
                "pass_pow_k": pass_pow_k,
                "diagnosis": diagnosis_accuracy,
                "rag_recall": rag_recall_at_k,
                "rag_mrr": rag_mrr,
                "rag_faithfulness": rag_faithfulness,
                "hitl_safety": hitl_safety_rate,
                "security_guardrail": security_guardrail_rate,
            },
        )

        return EvalRunReport(
            dataset_version=DATASET_VERSION,
            execution_mode=mode,
            model_name=observed_model,
            k_trials=k,
            total_cases=total_cases,
            passed_cases=passed_cases,
            overall_score=overall_score,
            pass_at_k=pass_at_k,
            pass_pow_k=pass_pow_k,
            diagnosis_accuracy=diagnosis_accuracy,
            rag_recall_at_k=rag_recall_at_k,
            rag_mrr=rag_mrr,
            rag_faithfulness=rag_faithfulness,
            hitl_safety_rate=hitl_safety_rate,
            security_guardrail_rate=security_guardrail_rate,
            avg_latency_ms=avg_lat,
            p95_latency_ms=p95_lat,
            total_tokens=total_tokens,
            estimated_cost_usd=round(total_cost, 6),
            gate_passed=gate_passed,
            regression_detected=regression_detected,
            delta_vs_baseline=delta_vs_baseline,
            gate_reasons=gate_reasons,
            case_results=case_results,
        )


eval_harness_runner = EvalHarnessRunner()
