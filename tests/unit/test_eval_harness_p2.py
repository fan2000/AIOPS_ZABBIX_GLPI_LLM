"""Tests unitaires P2 #8 : Golden Dataset, Evaluateurs pass@k/Recall@k/MRR, Release Gate et EvalHarnessRunner."""

from unittest.mock import AsyncMock
import pytest
from packages.contracts.src.ai import KnowledgeSourceCitation
from packages.evals.src.dataset import DATASET_VERSION, GOLDEN_EVAL_CASES, get_eval_cases
from packages.evals.src.graders import (
    GateThresholds,
    evaluate_release_gate,
    grade_rag_trial,
)
from packages.evals.src.runner import eval_harness_runner


def test_golden_dataset_integrity_and_categories():
    """Le dataset Golden v1.0.0 contient exactement 14 scénarios couvrant les 4 axes AIOps."""
    assert DATASET_VERSION == "1.0.0"
    assert len(GOLDEN_EVAL_CASES) == 14
    ids = [c.case_id for c in GOLDEN_EVAL_CASES]
    assert len(set(ids)) == 14

    assert len(get_eval_cases(["diagnosis"])) == 7
    assert len(get_eval_cases(["rag"])) == 3
    assert len(get_eval_cases(["hitl_safety"])) == 2
    assert len(get_eval_cases(["security_guardrail"])) == 2


def test_grade_rag_trial_recall_and_mrr_math():
    """Calcule exactement Recall@k et MRR selon le rang du premier passage pertinent."""
    rag_case = get_eval_cases(["rag"])[0]  # CPU KB (keywords: cpu, saturation, processus, min=2)

    cit_relevant = KnowledgeSourceCitation(
        article_id="KB-CPU-1",
        title="Procédure : Saturation CPU anormale",
        source_type="glpi_kb",
        relevance_score=0.92,
        snippet="Lister les processus consommateurs CPU via top.",
    )
    cit_noise = KnowledgeSourceCitation(
        article_id="KB-OTHER",
        title="Guide VLAN campus",
        source_type="glpi_kb",
        relevance_score=0.40,
        snippet="Configuration switch access.",
    )

    passed_1, _, rec_1, mrr_1, _, _ = grade_rag_trial(rag_case, [cit_relevant, cit_noise])
    assert passed_1 is True
    assert rec_1 == 1.0
    assert mrr_1 == 1.0

    passed_2, _, rec_2, mrr_2, _, _ = grade_rag_trial(rag_case, [cit_noise, cit_relevant])
    assert passed_2 is True
    assert rec_2 == 1.0
    assert mrr_2 == 0.5

    passed_0, _, rec_0, mrr_0, _, _ = grade_rag_trial(rag_case, [cit_noise])
    assert passed_0 is False
    assert rec_0 == 0.0
    assert mrr_0 == 0.0


def test_evaluate_release_gate_thresholds_and_regression():
    """Vérifie le Release Gate : succès nominal, régression vs baseline et tolérance zéro sécurité/HITL."""
    nominal = {
        "overall_score": 0.96,
        "pass_at_k": 1.0,
        "security_guardrail_rate": 1.0,
        "hitl_safety_rate": 1.0,
        "rag_recall_at_k": 1.0,
    }
    cats = ["diagnosis", "rag", "hitl_safety", "security_guardrail"]

    ok, reg, delta, reasons = evaluate_release_gate(nominal, cats, baseline_score=0.98, thresholds=GateThresholds())
    assert ok is True
    assert reg is False
    assert delta == -0.02
    assert reasons == []

    # Chute > 0.05 par rapport à baseline=0.98 -> régression détectée
    dropped = dict(nominal, overall_score=0.88)
    ok_drop, reg_drop, delta_drop, reasons_drop = evaluate_release_gate(dropped, cats, baseline_score=0.98)
    assert ok_drop is False
    assert reg_drop is True
    assert delta_drop == -0.10
    assert any("Régression" in r for r in reasons_drop)

    # Échec guardrail sécurité -> blocage immédiat même avec score global élevé
    sec_fail = dict(nominal, security_guardrail_rate=0.5)
    ok_sec, reg_sec, _, reasons_sec = evaluate_release_gate(sec_fail, cats, baseline_score=0.96)
    assert ok_sec is False
    assert reg_sec is True
    assert any("sécurité" in r for r in reasons_sec)


@pytest.mark.asyncio
async def test_eval_harness_runner_full_suite_pass_k(monkeypatch):
    """Exécute la suite complète (14 scénarios, k=2 essais) en mode fast_deterministic avec RAG simulé."""

    async def _fake_rag_search(query: str, session=None, entity_id: str = "0", allowed_entities=None, top_k: int = 4):
        q = query.lower()
        if "disque" in q or "disk" in q or "var/log" in q:
            return [
                KnowledgeSourceCitation(
                    article_id="3",
                    title="Procédure : Espace disque saturé /var/log",
                    source_type="glpi_kb",
                    relevance_score=0.94,
                    snippet="Purger les fichiers log archivés sur la partition /var/log.",
                )
            ]
        if "service" in q or "nginx" in q or "spooler" in q:
            return [
                KnowledgeSourceCitation(
                    article_id="4",
                    title="Procédure : Service arrêté de manière inattendue",
                    source_type="glpi_kb",
                    relevance_score=0.93,
                    snippet="Vérifier systemd puis procéder au redémarrage contrôlé du service.",
                )
            ]
        return [
            KnowledgeSourceCitation(
                article_id="2",
                title="Procédure : Saturation CPU anormale",
                source_type="glpi_kb",
                relevance_score=0.91,
                snippet="Identifier tout processus consommateur CPU et collecter la liste.",
            )
        ]

    monkeypatch.setattr(
        "packages.evals.src.runner.hybrid_retriever.search",
        AsyncMock(side_effect=_fake_rag_search),
    )
    monkeypatch.setattr(
        "packages.agents.src.nodes.knowledge_node.hybrid_retriever.search",
        AsyncMock(side_effect=_fake_rag_search),
    )

    report = await eval_harness_runner.run_suite(
        execution_mode="fast_deterministic",
        k_trials=2,
        baseline_score=0.95,
    )

    assert report.total_cases == 14
    assert report.passed_cases == 14
    assert report.k_trials == 2
    assert report.overall_score == 1.0
    assert report.pass_at_k == 1.0
    assert report.pass_pow_k == 1.0
    assert report.rag_recall_at_k == 1.0
    assert report.rag_mrr == 1.0
    assert report.hitl_safety_rate == 1.0
    assert report.security_guardrail_rate == 1.0
    assert report.gate_passed is True
    assert report.regression_detected is False
