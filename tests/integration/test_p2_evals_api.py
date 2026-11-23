"""Tests d'intégration API P2 #8 : Routes /api/v1/evals/*, RBAC et persistance."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from apps.api.src.main import app
from database.connection import get_db_session
from packages.evals.src.graders import CaseEvalResult, EvalCheckResult, EvalRunReport


def _mock_result(scalar=None, all_rows=None):
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar.return_value = scalar
    res.scalars.return_value.all.return_value = all_rows or []
    res.all.return_value = all_rows or []
    return res


def _fake_session(side_effects):
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute.side_effect = side_effects
    return session


def _sample_report() -> EvalRunReport:
    return EvalRunReport(
        dataset_version="1.0.0",
        execution_mode="fast_deterministic",
        model_name="deterministic",
        k_trials=1,
        total_cases=14,
        passed_cases=14,
        overall_score=1.0,
        pass_at_k=1.0,
        pass_pow_k=1.0,
        diagnosis_accuracy=1.0,
        rag_recall_at_k=1.0,
        rag_mrr=1.0,
        hitl_safety_rate=1.0,
        security_guardrail_rate=1.0,
        avg_latency_ms=12,
        p95_latency_ms=25,
        total_tokens=0,
        estimated_cost_usd=0.0,
        gate_passed=True,
        regression_detected=False,
        delta_vs_baseline=0.02,
        gate_reasons=[],
        case_results=[
            CaseEvalResult(
                case_id="eval-diag-disk-linux",
                case_name="Saturation disque /var/log (Linux)",
                category="diagnosis",
                passed=True,
                score=1.0,
                trials_passed=1,
                trials_total=1,
                latency_ms=12,
                checks=[EvalCheckResult(name="runbook_match", passed=True, detail="ok")],
                actual_summary={"runbook_id": "rb-disk-cleanup-logs"},
            )
        ],
    )


def test_evals_dataset_endpoint():
    """GET /api/v1/evals/dataset expose le Golden Dataset v1.0.0 avec les 14 scénarios."""
    client = TestClient(app)
    resp = client.get("/api/v1/evals/dataset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dataset_version"] == "1.0.0"
    assert body["total_cases"] == 14
    assert body["categories"]["diagnosis"] == 7
    assert body["categories"]["rag"] == 3
    assert body["categories"]["hitl_safety"] == 2
    assert body["categories"]["security_guardrail"] == 2


def test_evals_run_viewer_forbidden():
    """Un utilisateur viewer reçoit HTTP 403 sur POST /api/v1/evals/run."""
    viewer = AuthenticatedUserContext(
        id=uuid4(),
        username="viewer_noc",
        role="viewer",
        permissions=["incident:read"],
        allowed_entities=["*"],
    )
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_db_session] = lambda: _fake_session([])

    try:
        client = TestClient(app)
        resp = client.post("/api/v1/evals/run", json={"execution_mode": "fast_deterministic", "k_trials": 1})
        assert resp.status_code == 403
        assert "Opérateur ou administrateur requis" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_evals_run_operator_persists_and_returns_report(monkeypatch):
    """POST /api/v1/evals/run par un opérateur exécute le runner, persiste AIEvalRun/AuditLog et retourne 201."""
    operator = AuthenticatedUserContext(
        id=uuid4(),
        username="op_eval",
        role="operator",
        permissions=["incident:read", "runbook:execute"],
        allowed_entities=["*"],
    )
    session = _fake_session([_mock_result(scalar=0.98)])
    monkeypatch.setattr(
        "apps.api.src.routers.evals.eval_harness_runner.run_suite",
        AsyncMock(return_value=_sample_report()),
    )

    app.dependency_overrides[get_current_user] = lambda: operator
    app.dependency_overrides[get_db_session] = lambda: session

    try:
        client = TestClient(app)
        resp = client.post("/api/v1/evals/run", json={"execution_mode": "fast_deterministic", "k_trials": 1})
        assert resp.status_code == 201
        body = resp.json()
        assert body["triggered_by"] == "op_eval"
        assert body["overall_score"] == 1.0
        assert body["pass_at_k"] == 1.0
        assert body["gate_passed"] is True
        assert body["regression_detected"] is False
        assert len(body["case_results"]) == 1
        assert session.add.call_count == 3  # AIEvalRun + AIEvalCaseResult + AuditLog
    finally:
        app.dependency_overrides.clear()


def test_evals_summary_runs_and_detail():
    """GET /summary, /runs et /runs/{id} retournent l'historique et le détail des scénarios."""
    run_id = uuid4()
    now = datetime.now(timezone.utc)
    fake_run = SimpleNamespace(
        id=run_id,
        dataset_version="1.0.0",
        execution_mode="fast_deterministic",
        model_name="deterministic",
        triggered_by="admin",
        k_trials=2,
        total_cases=14,
        passed_cases=14,
        overall_score=1.0,
        pass_at_k=1.0,
        pass_pow_k=1.0,
        diagnosis_accuracy=1.0,
        rag_recall_at_k=1.0,
        rag_mrr=1.0,
        hitl_safety_rate=1.0,
        security_guardrail_rate=1.0,
        avg_latency_ms=10,
        p95_latency_ms=20,
        total_tokens=0,
        estimated_cost_usd=0.0,
        gate_passed=True,
        regression_detected=False,
        delta_vs_baseline=0.0,
        gate_reasons=[],
        started_at=now,
        finished_at=now,
    )
    fake_case = SimpleNamespace(
        id=uuid4(),
        case_id="eval-diag-disk-linux",
        case_name="Saturation disque /var/log (Linux)",
        category="diagnosis",
        passed=True,
        score=1.0,
        trials_passed=2,
        trials_total=2,
        latency_ms=10,
        tokens_used=0,
        rag_recall_at_k=None,
        rag_mrr=None,
        checks=[{"name": "runbook_match", "passed": True, "detail": "ok"}],
        actual_summary={"runbook_id": "rb-disk-cleanup-logs"},
        error_message=None,
    )

    session = _fake_session(
        [
            # /summary: recent_rows, baseline_score, total_runs
            _mock_result(all_rows=[fake_run]),
            _mock_result(scalar=1.0),
            _mock_result(scalar=1),
            # /runs
            _mock_result(all_rows=[fake_run]),
            # /runs/{id}: run_row, cases
            _mock_result(scalar=fake_run),
            _mock_result(all_rows=[fake_case]),
        ]
    )
    app.dependency_overrides[get_db_session] = lambda: session

    try:
        client = TestClient(app)
        r_sum = client.get("/api/v1/evals/summary")
        assert r_sum.status_code == 200
        assert r_sum.json()["total_runs"] == 1
        assert r_sum.json()["latest_run"]["id"] == str(run_id)

        r_runs = client.get("/api/v1/evals/runs")
        assert r_runs.status_code == 200
        assert len(r_runs.json()) == 1

        r_det = client.get(f"/api/v1/evals/runs/{run_id}")
        assert r_det.status_code == 200
        assert r_det.json()["case_results"][0]["case_id"] == "eval-diag-disk-linux"
    finally:
        app.dependency_overrides.clear()
