"""Module d'observabilité et d'export de métriques Prometheus pour AIOps."""

import time
from typing import Dict
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Registre Prometheus partagé
REGISTRY = CollectorRegistry(auto_describe=True)

# Compteurs d'incidents
INCIDENTS_TOTAL = Counter(
    "aiops_incidents_total",
    "Nombre total d'incidents enregistrés dans la plateforme AIOps",
    ["status", "severity"],
    registry=REGISTRY,
)

# Compteurs d'événements Zabbix ingérés
EVENTS_INGESTED_TOTAL = Counter(
    "aiops_events_ingested_total",
    "Nombre total d'alertes et événements de supervision ingérés",
    ["source", "event_type"],
    registry=REGISTRY,
)

# Latence d'inférence LLM / Agents LangGraph
LLM_INFERENCE_LATENCY = Histogram(
    "aiops_llm_inference_latency_seconds",
    "Temps d'inférence des agents LangGraph et modèles LLM",
    ["agent", "model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=REGISTRY,
)

# Exécutions de remédiation
REMEDIATION_EXECUTIONS_TOTAL = Counter(
    "aiops_remediation_executions_total",
    "Nombre d'actions de remédiation exécutées",
    ["status", "runner_type"],
    registry=REGISTRY,
)

# Statut de connectivité des 12 services
SERVICES_HEALTH = Gauge(
    "aiops_service_up",
    "Statut de connectivité des services du système AIOps (1 = UP, 0 = DOWN)",
    ["service_name", "category"],
    registry=REGISTRY,
)

# Compteurs FinOps & Télémétrie LLM / Agents / RAG
LLM_TOKENS_TOTAL = Counter(
    "aiops_llm_tokens_total",
    "Nombre total de tokens consommés par les modèles LLM",
    ["model", "token_type"],
    registry=REGISTRY,
)

LLM_FALLBACK_TOTAL = Counter(
    "aiops_llm_fallback_total",
    "Nombre de bascules vers le moteur déterministe (circuit-breaker, timeout, quota)",
    ["reason"],
    registry=REGISTRY,
)

AGENT_EXECUTIONS_TOTAL = Counter(
    "aiops_agent_executions_total",
    "Nombre d'exécutions par nœud agent LangGraph",
    ["agent", "status"],
    registry=REGISTRY,
)

RAG_SEARCH_LATENCY = Histogram(
    "aiops_rag_search_latency_seconds",
    "Temps de latence de la recherche hybride RAG",
    ["engine"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=REGISTRY,
)

HITL_APPROVALS_TOTAL = Counter(
    "aiops_hitl_approvals_total",
    "Décisions Human-in-the-Loop sur les approbations de runbooks",
    ["decision", "risk_level"],
    registry=REGISTRY,
)

INVESTIGATION_LOOPS_TOTAL = Counter(
    "aiops_investigation_loops_total",
    "Itérations de l'agent d'investigation lecture seule",
    ["outcome"],
    registry=REGISTRY,
)

EVAL_RUNS_TOTAL = Counter(
    "aiops_eval_runs_total",
    "Nombre d'exécutions du harness d'évaluation continue IA",
    ["mode", "gate_status"],
    registry=REGISTRY,
)

EVAL_LATEST_SCORE = Gauge(
    "aiops_eval_latest_score",
    "Dernier score d'évaluation continue IA par dimension (0..1)",
    ["dimension"],
    registry=REGISTRY,
)

EVAL_REGRESSION_DETECTED = Gauge(
    "aiops_eval_regression_detected",
    "1 si une régression IA est détectée sur le dernier eval run",
    registry=REGISTRY,
)

RAG_EMBEDDINGS_TOTAL = Counter(
    "aiops_rag_embeddings_total",
    "Nombre d'opérations d'embeddings RAG par provider et statut",
    ["provider", "status"],
    registry=REGISTRY,
)

RAG_DLQ_PENDING = Gauge(
    "aiops_rag_dlq_pending",
    "Nombre de documents en attente dans la DLQ embeddings RAG",
    registry=REGISTRY,
)

RAG_FALLBACK_CHUNKS = Gauge(
    "aiops_rag_fallback_chunks",
    "Nombre de chunks vectorisés en fallback dans pgvector",
    registry=REGISTRY,
)

RAG_FAITHFULNESS_SCORE = Gauge(
    "aiops_rag_faithfulness_score",
    "Score de fidélité factuelle des diagnostics et recommandations RAG (0..1)",
    registry=REGISTRY,
)

RAG_CITATION_COVERAGE = Gauge(
    "aiops_rag_citation_coverage_ratio",
    "Part des diagnostics IA appuyés par au moins une citation RAG (0..1)",
    registry=REGISTRY,
)

RAG_KNOWLEDGE_GAPS_COUNT = Gauge(
    "aiops_rag_knowledge_gaps_total",
    "Nombre de familles d'incidents identifiées comme Knowledge Gaps prioritaires",
    registry=REGISTRY,
)


def record_incident_created(status: str = "OPEN", severity: str = "HIGH") -> None:
    """Incrémente le compteur d'incidents."""
    INCIDENTS_TOTAL.labels(status=status.upper(), severity=severity.upper()).inc()


def record_event_ingested(source: str = "zabbix", event_type: str = "PROBLEM") -> None:
    """Incrémente le compteur d'événements ingérés."""
    EVENTS_INGESTED_TOTAL.labels(source=source, event_type=event_type).inc()


def record_remediation_execution(status: str = "SUCCESS", runner_type: str = "powershell") -> None:
    """Incrémente le compteur de remédiations."""
    REMEDIATION_EXECUTIONS_TOTAL.labels(status=status.upper(), runner_type=runner_type).inc()


def record_llm_inference(
    agent: str,
    model: str,
    latency_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Enregistre la latence d'inférence LLM et la consommation de tokens."""
    LLM_INFERENCE_LATENCY.labels(agent=agent, model=model).observe(max(0.0, latency_seconds))
    if prompt_tokens > 0:
        LLM_TOKENS_TOTAL.labels(model=model, token_type="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        LLM_TOKENS_TOTAL.labels(model=model, token_type="completion").inc(completion_tokens)


def record_llm_fallback(reason: str) -> None:
    """Incrémente le compteur de fallback déterministe LLM."""
    LLM_FALLBACK_TOTAL.labels(reason=reason).inc()


def record_agent_execution(agent: str, status: str = "success") -> None:
    """Incrémente le compteur d'exécution d'un agent LangGraph."""
    AGENT_EXECUTIONS_TOTAL.labels(agent=agent, status=status).inc()


def record_rag_search(engine: str, latency_seconds: float) -> None:
    """Enregistre la latence du moteur de recherche RAG."""
    RAG_SEARCH_LATENCY.labels(engine=engine).observe(max(0.0, latency_seconds))


def record_rag_embedding(provider: str, status: str) -> None:
    """Incrémente le compteur d'opérations d'embeddings RAG."""
    RAG_EMBEDDINGS_TOTAL.labels(provider=(provider or "ollama").lower(), status=status.lower()).inc()


def set_rag_index_health(dlq_pending: int, fallback_chunks: int) -> None:
    """Met à jour les jauges Prometheus DLQ et fallbacks pgvector."""
    RAG_DLQ_PENDING.set(max(0, int(dlq_pending)))
    RAG_FALLBACK_CHUNKS.set(max(0, int(fallback_chunks)))


def set_rag_quality_metrics(faithfulness: float, citation_coverage: float, gaps_count: int) -> None:
    """Met à jour les jauges Prometheus de qualité RAG (Faithfulness, couverture citations, gaps)."""
    RAG_FAITHFULNESS_SCORE.set(max(0.0, min(1.0, float(faithfulness))))
    RAG_CITATION_COVERAGE.set(max(0.0, min(1.0, float(citation_coverage))))
    RAG_KNOWLEDGE_GAPS_COUNT.set(max(0, int(gaps_count)))


def record_hitl_decision(decision: str, risk_level: str = "MEDIUM") -> None:
    """Enregistre une décision ou mise en attente Human-in-the-Loop."""
    HITL_APPROVALS_TOTAL.labels(decision=decision.lower(), risk_level=risk_level.upper()).inc()


def record_investigation_loop(outcome: str) -> None:
    """Incrémente le compteur d'itérations de l'agent d'investigation."""
    INVESTIGATION_LOOPS_TOTAL.labels(outcome=outcome.lower()).inc()


def record_eval_run(
    mode: str,
    gate_passed: bool,
    regression_detected: bool,
    scores: Dict[str, float],
) -> None:
    """Met à jour les compteurs et jauges Prometheus d'évaluation continue IA."""
    gate_status = "passed" if gate_passed else "failed"
    EVAL_RUNS_TOTAL.labels(mode=mode or "fast_deterministic", gate_status=gate_status).inc()
    EVAL_REGRESSION_DETECTED.set(1 if regression_detected else 0)
    for dimension, value in (scores or {}).items():
        EVAL_LATEST_SCORE.labels(dimension=dimension).set(max(0.0, min(1.0, float(value))))


def set_service_health(service_name: str, category: str, is_up: bool) -> None:
    """Met à jour la jauge d'état du service."""
    SERVICES_HEALTH.labels(service_name=service_name, category=category).set(1 if is_up else 0)


def export_metrics_text() -> bytes:
    """Génère le flux textuel Prometheus standard."""
    return generate_latest(REGISTRY)
