"""Tests unitaires P2 #9 : Qualité RAG (Faithfulness), Knowledge Gaps & GraphRAG léger."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from packages.rag.src.graph_rag import build_operational_graph
from packages.rag.src.quality import (
    clean_incident_title,
    compute_faithfulness_score,
    detect_knowledge_gaps,
    normalize_incident_family,
)


def _mock_result(scalar=None, all_rows=None):
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar.return_value = scalar
    res.scalars.return_value.all.return_value = all_rows or []
    res.all.return_value = all_rows or []
    return res


def test_normalize_incident_family_deduplicates_variants():
    """Regroupe les variantes d'hôtes, pourcentages, nombres et suffixes répétés dans une famille unique."""
    f1 = normalize_incident_family("CPU utilization above 90% sur SRV-TEST-01", "SRV-TEST-01")
    f2 = normalize_incident_family("CPU utilization above 95% sur SRV-TEST-01 sur SRV-TEST-01", "SRV-TEST-01")
    f3 = normalize_incident_family("CPU utilization above 88% on SRV-PROD-99", "SRV-PROD-99")
    assert f1 == f2 == f3
    assert "cpu utilization" in f1
    assert clean_incident_title("CPU utilization above 90% sur SRV-TEST-01 sur SRV-TEST-01", "SRV-TEST-01") == (
        "CPU utilization above 90%"
    )


def test_compute_faithfulness_score_grounded_vs_ungrounded():
    """Score élevé si ancré sur citations RAG, pénalité stricte si confiance haute sans citation."""
    grounded = compute_faithfulness_score(
        hypotheses=[{"description": "Saturation CPU causée par un processus Java ou boucle applicative sur Linux"}],
        recommended_actions=[{"action": "Collecter le top processus avec top et systemctl status"}],
        citations=[
            {
                "title": "Procédure : Saturation CPU anormale",
                "snippet": "Identifier le processus consommateur via top et vérifier les services systemd sur Linux.",
            }
        ],
        confidence_level="high",
    )
    assert grounded["citation_grounded"] is True
    assert grounded["ungrounded_high_confidence"] is False
    assert grounded["faithfulness_score"] >= 0.7

    ungrounded = compute_faithfulness_score(
        hypotheses=[{"description": "Redémarrer le noyau immédiatement sans preuve documentaire"}],
        recommended_actions=[{"action": "Exécuter purge complète"}],
        citations=[],
        confidence_level="high",
    )
    assert ungrounded["citation_grounded"] is False
    assert ungrounded["ungrounded_high_confidence"] is True
    assert ungrounded["faithfulness_score"] == 0.0

    honest_abstain = compute_faithfulness_score(
        hypotheses=[{"description": "Anomalie inconnue sans procédure KB correspondante"}],
        recommended_actions=[{"action": "Escalader au support N2"}],
        citations=[],
        confidence_level="insufficient_evidence",
    )
    assert honest_abstain["ungrounded_high_confidence"] is False
    assert honest_abstain["faithfulness_score"] >= 0.75


@pytest.mark.asyncio
async def test_detect_knowledge_gaps_prioritizes_uncovered_families():
    """Priorise les familles d'incidents récurrentes sans citation RAG / insufficient_evidence."""
    now = datetime.now(timezone.utc)
    inc_cpu = SimpleNamespace(
        id=uuid4(),
        incident_number="INC-CPU-1",
        title="CPU utilization above 90% sur SRV-LINUX-01",
        severity="HIGH",
        primary_asset_name="SRV-LINUX-01",
        entity_id="0",
        opened_at=now,
    )
    inc_gap_1 = SimpleNamespace(
        id=uuid4(),
        incident_number="INC-Z99-1",
        title="Anomalie propriétaire obscure Z99 sur CORE-RTR-842",
        severity="DISASTER",
        primary_asset_name="CORE-RTR-842",
        entity_id="0",
        opened_at=now,
    )
    inc_gap_2 = SimpleNamespace(
        id=uuid4(),
        incident_number="INC-Z99-2",
        title="Anomalie propriétaire obscure Z99 sur CORE-RTR-843",
        severity="DISASTER",
        primary_asset_name="CORE-RTR-843",
        entity_id="0",
        opened_at=now,
    )

    run_cpu = SimpleNamespace(
        id=uuid4(),
        incident_id=inc_cpu.id,
        confidence_level="high",
        hypotheses=[{"description": "Saturation CPU Linux liée à un processus applicatif"}],
        checks=["Collecte top OK"],
    )
    run_gap_1 = SimpleNamespace(
        id=uuid4(),
        incident_id=inc_gap_1.id,
        confidence_level="insufficient_evidence",
        hypotheses=[{"description": "Anomalie obscure Z99 non documentée"}],
        checks=["Aucune correspondance KB"],
    )
    run_gap_2 = SimpleNamespace(
        id=uuid4(),
        incident_id=inc_gap_2.id,
        confidence_level="insufficient_evidence",
        hypotheses=[{"description": "Anomalie obscure Z99 non documentée"}],
        checks=["Aucune correspondance KB"],
    )

    rec_cpu = SimpleNamespace(
        id=uuid4(),
        analysis_run_id=run_cpu.id,
        action_text="Collecter les processus top sur Linux",
    )
    src_cpu = SimpleNamespace(
        id=uuid4(),
        recommendation_id=rec_cpu.id,
        source_title="Procédure : Saturation CPU anormale",
        snippet="Vérifier les processus via top et charge système CPU Linux.",
        relevance_score=0.92,
    )
    eval_row = SimpleNamespace(rag_recall_at_k=1.0, rag_mrr=1.0)

    session = AsyncMock()
    session.execute.side_effect = [
        _mock_result(all_rows=[inc_cpu, inc_gap_1, inc_gap_2]),  # Incident
        _mock_result(scalar=eval_row),  # AIEvalRun
        _mock_result(all_rows=[run_cpu, run_gap_1, run_gap_2]),  # AIAnalysisRun
        _mock_result(all_rows=[rec_cpu]),  # AIRecommendation
        _mock_result(all_rows=[src_cpu]),  # RecommendationSource
        _mock_result(all_rows=[]),  # KnowledgeProposal
    ]

    result = await detect_knowledge_gaps(session=session, entity_scope=["0"], min_relevance=0.45, limit=10)
    assert result["metrics"]["total_incidents"] == 3
    assert result["metrics"]["total_analyzed_incidents"] == 3
    assert result["metrics"]["latest_eval_recall_at_5"] == 1.0
    assert result["metrics"]["gaps_count"] == 1
    gap = result["gaps"][0]
    assert gap["incident_count"] == 2
    assert gap["max_severity"] == "DISASTER"
    assert gap["citation_coverage_rate"] == 0.0
    assert gap["insufficient_evidence_rate"] == 1.0
    assert gap["priority_level"] in ("CRITICAL", "HIGH")
    assert len(gap["affected_hosts"]) == 2


@pytest.mark.asyncio
async def test_build_operational_graph_links_entities_and_2hop_focus():
    """Construit le graphe Asset-Service-Incident-KB-Runbook et filtre en 2 sauts autour du focus."""
    now = datetime.now(timezone.utc)
    asset_win = SimpleNamespace(
        id=uuid4(),
        name="SRV-WIN-PRINT",
        os_name="Windows Server 2022",
        ip_address="10.0.0.21",
        entity_id="0",
        tags={"service": "spooler"},
    )
    rb_win = SimpleNamespace(
        id=uuid4(),
        identifier="rb-win-service-restart",
        name="Restart Windows Service",
        description="Redémarre un service Windows comme Spooler via PowerShell",
        target_os="windows",
        runner_type="powershell",
    )
    doc_svc = SimpleNamespace(
        id=uuid4(),
        external_id="KB-303",
        title="Procédure : Service arrêté (Spooler Windows)",
        source_type="glpi_kb",
        entity_id="0",
        raw_content="<p>Restart-Service Spooler sous Windows</p>",
    )
    chunk_svc = SimpleNamespace(
        document_id=doc_svc.id,
        chunk_index=0,
        metadata_fields={"os": "windows", "category": "service", "service": "spooler", "services": ["spooler"]},
    )
    inc1 = SimpleNamespace(
        id=uuid4(),
        incident_number="INC-WIN-01",
        title="Windows Print Spooler service is stopped sur SRV-WIN-PRINT",
        severity="HIGH",
        status="OPEN",
        primary_asset_name="SRV-WIN-PRINT",
        entity_id="0",
        opened_at=now,
    )
    inc2 = SimpleNamespace(
        id=uuid4(),
        incident_number="INC-WIN-02",
        title="Windows Print Spooler service is stopped sur SRV-WIN-PRINT",
        severity="HIGH",
        status="OPEN",
        primary_asset_name="SRV-WIN-PRINT",
        entity_id="0",
        opened_at=now,
    )
    run1 = SimpleNamespace(id=uuid4(), incident_id=inc1.id, confidence_level="high")
    rec1 = SimpleNamespace(id=uuid4(), analysis_run_id=run1.id, runbook_id="rb-win-service-restart")
    src1 = SimpleNamespace(
        id=uuid4(),
        recommendation_id=rec1.id,
        article_reference="KB-303",
        source_title="Procédure : Service arrêté (Spooler Windows)",
    )

    session = AsyncMock()
    session.execute.side_effect = [
        _mock_result(all_rows=[asset_win]),  # Asset
        _mock_result(all_rows=[rb_win]),  # Runbook
        _mock_result(all_rows=[doc_svc]),  # KnowledgeDocument
        _mock_result(all_rows=[chunk_svc]),  # KnowledgeChunk
        _mock_result(all_rows=[inc1, inc2]),  # Incident
        _mock_result(all_rows=[run1]),  # AIAnalysisRun
        _mock_result(all_rows=[rec1]),  # AIRecommendation
        _mock_result(all_rows=[src1]),  # RecommendationSource
    ]

    full = await build_operational_graph(session=session, entity_scope=["0"])
    assert full["stats"]["assets"] >= 1
    assert full["stats"]["services"] >= 1
    assert full["stats"]["incidents"] == 2
    assert full["stats"]["kb_articles"] >= 1
    assert full["stats"]["runbooks"] >= 1

    relations = {e["relation"] for e in full["edges"]}
    assert {"AFFECTS_ASSET", "HOSTS_SERVICE", "SIMILAR_INCIDENT", "CITED_BY", "REMEDIATED_BY", "COVERS_SERVICE"} <= relations

    session_focus = AsyncMock()
    session_focus.execute.side_effect = [
        _mock_result(all_rows=[asset_win]),
        _mock_result(all_rows=[rb_win]),
        _mock_result(all_rows=[doc_svc]),
        _mock_result(all_rows=[chunk_svc]),
        _mock_result(all_rows=[inc1, inc2]),
        _mock_result(all_rows=[run1]),
        _mock_result(all_rows=[rec1]),
        _mock_result(all_rows=[src1]),
    ]
    focused = await build_operational_graph(session=session_focus, entity_scope=["0"], asset_name="SRV-WIN-PRINT")
    assert "asset:SRV-WIN-PRINT" in focused["matched_node_ids"]
    assert focused["stats"]["edges"] >= 3
