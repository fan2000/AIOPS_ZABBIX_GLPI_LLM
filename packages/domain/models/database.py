"""Modèles de données SQLAlchemy 2.0 pour PostgreSQL et pgvector."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    Vector = None  # type: ignore


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    permissions: Mapped[List[str]] = mapped_column(JSONB, default=list)

    users: Mapped[List["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(150))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    glpi_user_id: Mapped[Optional[str]] = mapped_column(String(50))
    allowed_entities: Mapped[List[str]] = mapped_column(JSONB, default=lambda: ["0"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(255))
    mfa_recovery_codes: Mapped[List[str]] = mapped_column(JSONB, default=list)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    role: Mapped[Role] = relationship(back_populates="users")
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="user")
    sessions: Mapped[List["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSession(Base):
    """Sessions d'authentification actives et rotation sécurisée des Refresh Tokens."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_type: Mapped[str] = mapped_column(String(50), nullable=False)  # zabbix, glpi, ollama
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    zabbix_host_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    glpi_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    entity_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    os_name: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN", index=True)
    primary_asset_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    zabbix_host_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    glpi_ticket_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    events_count: Mapped[int] = mapped_column(Integer, default=1)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), index=True)
    recovery_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    incident_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    events: Mapped[List["IncidentEvent"]] = relationship(back_populates="incident")
    correlations: Mapped[List["IncidentCorrelation"]] = relationship(back_populates="incident")
    analysis_runs: Mapped[List["AIAnalysisRun"]] = relationship(back_populates="incident")
    executions: Mapped[List["ActionExecution"]] = relationship(back_populates="incident")


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    zabbix_event_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    zabbix_trigger_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    host_name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_key: Mapped[Optional[str]] = mapped_column(String(100))
    metric_value: Mapped[Optional[float]] = mapped_column(Float)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    idempotency_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    incident: Mapped[Incident] = relationship(back_populates="events")


class IncidentCorrelation(Base):
    __tablename__ = "incident_correlations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    correlated_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    incident: Mapped[Incident] = relationship(back_populates="correlations")


class GlpiTicketLink(Base):
    __tablename__ = "glpi_ticket_links"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    glpi_ticket_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(50), default="0")
    glpi_status: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # glpi_kb, ticket, runbook
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    chunks: Mapped[List["KnowledgeChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    metadata_fields: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    embedding_model: Mapped[str] = mapped_column(String(100), default="nomic-embed-text")
    embedding_version: Mapped[int] = mapped_column(Integer, default=1)
    is_fallback_embedding: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    # Embedding vector (dim 768)
    if HAS_PGVECTOR and Vector is not None:
        embedding: Mapped[Optional[Any]] = mapped_column(Vector(768))
    else:
        embedding: Mapped[Optional[Any]] = mapped_column(JSONB)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class KnowledgeSyncJob(Base):
    __tablename__ = "knowledge_sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="running")
    documents_imported: Mapped[int] = mapped_column(Integer, default=0)
    chunks_indexed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class AIAnalysisRun(Base):
    __tablename__ = "ai_analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(30), default="deterministic")
    execution_status: Mapped[str] = mapped_column(String(30), default="completed")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    hypotheses: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    checks: Mapped[List[str]] = mapped_column(JSONB, default=list)
    confidence_level: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    agent_telemetry: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked_actions_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    incident: Mapped[Incident] = relationship(back_populates="analysis_runs")
    recommendations: Mapped[List["AIRecommendation"]] = relationship(back_populates="analysis_run")


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_analysis_runs.id"), nullable=False, index=True)
    action_text: Mapped[str] = mapped_column(Text, nullable=False)
    runbook_id: Mapped[Optional[str]] = mapped_column(String(100))
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    execution_mode: Mapped[str] = mapped_column(String(30), default="read_only")
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)

    analysis_run: Mapped[AIAnalysisRun] = relationship(back_populates="recommendations")
    sources: Mapped[List["RecommendationSource"]] = relationship(back_populates="recommendation")


class RecommendationSource(Base):
    __tablename__ = "recommendation_sources"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_recommendations.id"), nullable=False, index=True)
    article_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)

    recommendation: Mapped[AIRecommendation] = relationship(back_populates="sources")


class Runbook(Base):
    __tablename__ = "runbooks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    runner_type: Mapped[str] = mapped_column(String(50), nullable=False)  # powershell, bash_ssh, ansible
    target_os: Mapped[str] = mapped_column(String(50), nullable=False)     # windows, linux, all
    template_command: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_schema: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    required_role: Mapped[str] = mapped_column(String(50), default="operator")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ActionApproval(Base):
    __tablename__ = "action_approvals"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    runbook_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval")  # pending_approval, approved, rejected
    thread_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    checkpoint_id: Mapped[Optional[str]] = mapped_column(String(128))
    risk_level: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    action_summary: Mapped[Optional[str]] = mapped_column(Text)
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_by_user: Mapped[Optional[str]] = mapped_column(String(100))
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255))


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    runbook_identifier: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    approved_by: Mapped[str] = mapped_column(String(100), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(30), default="running")
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    post_check_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_details: Mapped[Optional[str]] = mapped_column(Text)

    incident: Mapped[Incident] = relationship(back_populates="executions")


class IncidentFeedback(Base):
    __tablename__ = "incident_feedback"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    technician_username: Mapped[str] = mapped_column(String(100), nullable=False)
    is_recommendation_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rating_score: Mapped[Optional[int]] = mapped_column(Integer)
    feedback_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class KnowledgeProposal(Base):
    """Proposition d'article de base de connaissances générée par le Feedback Agent et validée par l'équipe."""
    __tablename__ = "knowledge_proposals"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="AIOps - Retours d'expérience")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_review", index=True)
    created_by: Mapped[str] = mapped_column(String(100), default="feedback-agent")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))
    glpi_kb_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), index=True)

    user: Mapped[Optional[User]] = relationship(back_populates="audit_logs")


class LangGraphCheckpoint(Base):
    """Persistance PostgreSQL des checkpoints LangGraph (threads HITL durables)."""
    __tablename__ = "langgraph_checkpoints"

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(128), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    parent_checkpoint_id: Mapped[Optional[str]] = mapped_column(String(128))
    checkpoint_type: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    metadata_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class LangGraphCheckpointWrite(Base):
    """Persistance des écritures intermédiaires d'un checkpoint LangGraph."""
    __tablename__ = "langgraph_checkpoint_writes"

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(128), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(128), nullable=False)
    value_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    task_path: Mapped[str] = mapped_column(String(255), default="")


class AIEvalRun(Base):
    """Exécution du harness d'évaluation continue IA (pass@k, pass^k, RAG Recall/MRR, release gate)."""
    __tablename__ = "ai_eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), default="fast_deterministic", nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), default="deterministic")
    triggered_by: Mapped[str] = mapped_column(String(100), default="system")
    k_trials: Mapped[int] = mapped_column(Integer, default=1)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    pass_at_k: Mapped[float] = mapped_column(Float, default=0.0)
    pass_pow_k: Mapped[float] = mapped_column(Float, default=0.0)
    diagnosis_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    rag_recall_at_k: Mapped[float] = mapped_column(Float, default=0.0)
    rag_mrr: Mapped[float] = mapped_column(Float, default=0.0)
    hitl_safety_rate: Mapped[float] = mapped_column(Float, default=0.0)
    security_guardrail_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    gate_passed: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    regression_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    delta_vs_baseline: Mapped[Optional[float]] = mapped_column(Float)
    gate_reasons: Mapped[List[str]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    case_results: Mapped[List["AIEvalCaseResult"]] = relationship(
        back_populates="eval_run",
        cascade="all, delete-orphan",
    )


class AIEvalCaseResult(Base):
    """Résultat détaillé d'un scénario d'évaluation dans un run du Eval Harness."""
    __tablename__ = "ai_eval_case_results"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_eval_runs.id"), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    case_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    trials_passed: Mapped[int] = mapped_column(Integer, default=0)
    trials_total: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    rag_recall_at_k: Mapped[Optional[float]] = mapped_column(Float)
    rag_mrr: Mapped[Optional[float]] = mapped_column(Float)
    checks: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    actual_summary: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    eval_run: Mapped[AIEvalRun] = relationship(back_populates="case_results")


class KnowledgeEmbeddingDLQ(Base):
    """File de reprise (Dead-Letter Queue) des documents dont les embeddings production ont échoué."""
    __tablename__ = "knowledge_embedding_dlq"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(50), default="0", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_retry", index=True)  # pending_retry, resolved, exhausted
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
