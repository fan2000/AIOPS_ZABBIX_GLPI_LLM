"""Gestion des connexions asynchrones PostgreSQL avec SQLAlchemy 2.0."""

import os
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from packages.domain.models.database import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aiops_user:aiops_secure_password@localhost:5435/aiops_db"
)

# Configuration du pool SQLAlchemy haute disponibilité (HA / Patroni / PgBouncer)
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "15"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_recycle=DB_POOL_RECYCLE,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dépendance FastAPI injectant une session asynchrone sécurisée."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_database() -> None:
    """Initialise le schéma, active l'extension pgvector et applique les migrations idempotentes P0."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            async with conn.begin_nested():
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                except Exception:
                    pass  # Si l'utilisateur n'a pas les droits superuser

        await conn.run_sync(Base.metadata.create_all)

        if conn.dialect.name == "postgresql":
            ddl_statements = [
                """ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_entities JSONB DEFAULT '["0"]'::jsonb;""",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(150);",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(255);",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_recovery_codes JSONB DEFAULT '[]'::jsonb;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;",
                "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100) DEFAULT 'nomic-embed-text';",
                "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_version INTEGER DEFAULT 1;",
                "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS is_fallback_embedding BOOLEAN DEFAULT FALSE;",
                "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk_text, ''))) STORED;",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS title_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title, ''))) STORED;",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_search_tsv_gin ON knowledge_chunks USING gin (search_tsv);",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_title_tsv_gin ON knowledge_documents USING gin (title_tsv);",
                "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS search_tsv_multi tsvector GENERATED ALWAYS AS (to_tsvector('french', coalesce(chunk_text, '')) || to_tsvector('english', coalesce(chunk_text, '')) || to_tsvector('simple', coalesce(chunk_text, ''))) STORED;",
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS title_tsv_multi tsvector GENERATED ALWAYS AS (to_tsvector('french', coalesce(title, '')) || to_tsvector('english', coalesce(title, '')) || to_tsvector('simple', coalesce(title, ''))) STORED;",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_search_tsv_multi_gin ON knowledge_chunks USING gin (search_tsv_multi);",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_title_tsv_multi_gin ON knowledge_documents USING gin (title_tsv_multi);",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_metadata_fields_gin ON knowledge_chunks USING gin (metadata_fields jsonb_path_ops);",
                "ALTER TABLE ai_analysis_runs ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(30) DEFAULT 'deterministic';",
                "ALTER TABLE ai_analysis_runs ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER DEFAULT 0;",
                "ALTER TABLE ai_analysis_runs ADD COLUMN IF NOT EXISTS completion_tokens INTEGER DEFAULT 0;",
                "ALTER TABLE ai_analysis_runs ADD COLUMN IF NOT EXISTS estimated_cost_usd DOUBLE PRECISION DEFAULT 0.0;",
                "ALTER TABLE ai_analysis_runs ADD COLUMN IF NOT EXISTS agent_telemetry JSONB DEFAULT '{}'::jsonb;",
                "ALTER TABLE ai_analysis_runs ADD COLUMN IF NOT EXISTS validation_passed BOOLEAN DEFAULT TRUE;",
                "ALTER TABLE ai_analysis_runs ADD COLUMN IF NOT EXISTS blocked_actions_count INTEGER DEFAULT 0;",
                "ALTER TABLE action_approvals ADD COLUMN IF NOT EXISTS thread_id VARCHAR(128);",
                "ALTER TABLE action_approvals ADD COLUMN IF NOT EXISTS checkpoint_id VARCHAR(128);",
                "ALTER TABLE action_approvals ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20) DEFAULT 'MEDIUM';",
                "ALTER TABLE action_approvals ADD COLUMN IF NOT EXISTS action_summary TEXT;",
                "ALTER TABLE action_approvals ADD COLUMN IF NOT EXISTS execution_id UUID;",
                "CREATE INDEX IF NOT EXISTS ix_action_approvals_thread_id ON action_approvals (thread_id);",
            ]
            for stmt in ddl_statements:
                async with conn.begin_nested():
                    try:
                        await conn.execute(text(stmt))
                    except Exception as ddl_err:
                        print(f"Avertissement migration DDL ({stmt[:55]}...): {ddl_err}")
