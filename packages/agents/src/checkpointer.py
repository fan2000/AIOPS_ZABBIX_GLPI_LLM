"""Checkpointer LangGraph asynchrone natif PostgreSQL (SQLAlchemy 2.0 + asyncpg) avec repli mémoire."""

from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Sequence, Tuple
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import asc, delete, desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from database.connection import async_session_maker
from packages.domain.models.database import LangGraphCheckpoint, LangGraphCheckpointWrite


class PostgresAsyncCheckpointSaver(BaseCheckpointSaver):
    """Persiste l'état complet et les écritures en attente des graphes HITL LangGraph dans PostgreSQL."""

    def __init__(self) -> None:
        super().__init__()
        self._fallback_memory = InMemorySaver(serde=self.serde)

    def _is_postgres(self, session: Any) -> bool:
        bind = getattr(session, "bind", None)
        dialect = getattr(bind, "dialect", None) if bind is not None else None
        return getattr(dialect, "name", "") == "postgresql"

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Charge le dernier checkpoint (ou celui spécifié) et ses pending_writes depuis PostgreSQL."""
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        requested_id = get_checkpoint_id(config)

        try:
            async with async_session_maker() as session:
                if not self._is_postgres(session):
                    return await self._fallback_memory.aget_tuple(config)

                stmt = select(LangGraphCheckpoint).where(
                    LangGraphCheckpoint.thread_id == thread_id,
                    LangGraphCheckpoint.checkpoint_ns == checkpoint_ns,
                )
                if requested_id:
                    stmt = stmt.where(LangGraphCheckpoint.checkpoint_id == str(requested_id))
                else:
                    stmt = stmt.order_by(desc(LangGraphCheckpoint.checkpoint_id)).limit(1)

                row = (await session.execute(stmt)).scalar_one_or_none()
                if row is None:
                    return await self._fallback_memory.aget_tuple(config)

                w_stmt = (
                    select(LangGraphCheckpointWrite)
                    .where(
                        LangGraphCheckpointWrite.thread_id == thread_id,
                        LangGraphCheckpointWrite.checkpoint_ns == checkpoint_ns,
                        LangGraphCheckpointWrite.checkpoint_id == row.checkpoint_id,
                    )
                    .order_by(
                        asc(LangGraphCheckpointWrite.task_path),
                        asc(LangGraphCheckpointWrite.task_id),
                        asc(LangGraphCheckpointWrite.idx),
                    )
                )
                write_rows = (await session.execute(w_stmt)).scalars().all()

                checkpoint: Checkpoint = self.serde.loads_typed(
                    (row.checkpoint_type, bytes(row.checkpoint_blob))
                )
                metadata: CheckpointMetadata = self.serde.loads_typed(
                    (row.metadata_type, bytes(row.metadata_blob))
                )
                pending_writes = [
                    (
                        w.task_id,
                        w.channel,
                        self.serde.loads_typed((w.value_type, bytes(w.value_blob))),
                    )
                    for w in write_rows
                ]

                resolved_config: RunnableConfig = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": row.checkpoint_id,
                    }
                }
                parent_config: Optional[RunnableConfig] = (
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": row.parent_checkpoint_id,
                        }
                    }
                    if row.parent_checkpoint_id
                    else None
                )

                return CheckpointTuple(
                    config=resolved_config,
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=parent_config,
                    pending_writes=pending_writes,
                )
        except Exception:
            return await self._fallback_memory.aget_tuple(config)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Liste les checkpoints enregistrés pour un thread."""
        if not config:
            return
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))

        try:
            async with async_session_maker() as session:
                if not self._is_postgres(session):
                    async for item in self._fallback_memory.alist(config, filter=filter, before=before, limit=limit):
                        yield item
                    return

                stmt = select(LangGraphCheckpoint).where(
                    LangGraphCheckpoint.thread_id == thread_id,
                    LangGraphCheckpoint.checkpoint_ns == checkpoint_ns,
                )
                before_id = get_checkpoint_id(before) if before else None
                if before_id:
                    stmt = stmt.where(LangGraphCheckpoint.checkpoint_id < str(before_id))
                stmt = stmt.order_by(desc(LangGraphCheckpoint.checkpoint_id))
                if limit is not None:
                    stmt = stmt.limit(limit)

                rows = (await session.execute(stmt)).scalars().all()
                for row in rows:
                    checkpoint: Checkpoint = self.serde.loads_typed(
                        (row.checkpoint_type, bytes(row.checkpoint_blob))
                    )
                    metadata: CheckpointMetadata = self.serde.loads_typed(
                        (row.metadata_type, bytes(row.metadata_blob))
                    )
                    if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                        continue
                    yield CheckpointTuple(
                        config={
                            "configurable": {
                                "thread_id": thread_id,
                                "checkpoint_ns": checkpoint_ns,
                                "checkpoint_id": row.checkpoint_id,
                            }
                        },
                        checkpoint=checkpoint,
                        metadata=metadata,
                        parent_config=(
                            {
                                "configurable": {
                                    "thread_id": thread_id,
                                    "checkpoint_ns": checkpoint_ns,
                                    "checkpoint_id": row.parent_checkpoint_id,
                                }
                            }
                            if row.parent_checkpoint_id
                            else None
                        ),
                        pending_writes=[],
                    )
                return
        except Exception:
            async for item in self._fallback_memory.alist(config, filter=filter, before=before, limit=limit):
                yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Sauvegarde ou met à jour un checkpoint complet dans PostgreSQL."""
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        cp_type, cp_blob = self.serde.dumps_typed(checkpoint)
        meta_type, meta_blob = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))

        try:
            async with async_session_maker() as session:
                if not self._is_postgres(session):
                    return await self._fallback_memory.aput(config, checkpoint, metadata, new_versions)

                stmt = (
                    pg_insert(LangGraphCheckpoint)
                    .values(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=checkpoint_id,
                        parent_checkpoint_id=str(parent_checkpoint_id) if parent_checkpoint_id else None,
                        checkpoint_type=cp_type,
                        checkpoint_blob=cp_blob,
                        metadata_type=meta_type,
                        metadata_blob=meta_blob,
                    )
                    .on_conflict_do_update(
                        index_elements=["thread_id", "checkpoint_ns", "checkpoint_id"],
                        set_={
                            "checkpoint_type": cp_type,
                            "checkpoint_blob": cp_blob,
                            "metadata_type": meta_type,
                            "metadata_blob": meta_blob,
                        },
                    )
                )
                await session.execute(stmt)
                await session.commit()
                return {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                }
        except Exception:
            return await self._fallback_memory.aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persiste les écritures intermédiaires associées à un checkpoint."""
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])

        try:
            async with async_session_maker() as session:
                if not self._is_postgres(session):
                    await self._fallback_memory.aput_writes(config, writes, task_id, task_path=task_path)
                    return

                for raw_idx, (channel, val) in enumerate(writes):
                    mapped_idx = int(WRITES_IDX_MAP.get(channel, raw_idx))
                    val_type, val_blob = self.serde.dumps_typed(val)
                    ins = pg_insert(LangGraphCheckpointWrite).values(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=checkpoint_id,
                        task_id=str(task_id),
                        idx=mapped_idx,
                        channel=str(channel),
                        value_type=val_type,
                        value_blob=val_blob,
                        task_path=str(task_path or ""),
                    )
                    if mapped_idx >= 0:
                        stmt = ins.on_conflict_do_nothing(
                            index_elements=["thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"]
                        )
                    else:
                        stmt = ins.on_conflict_do_update(
                            index_elements=["thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"],
                            set_={
                                "channel": str(channel),
                                "value_type": val_type,
                                "value_blob": val_blob,
                            },
                        )
                    await session.execute(stmt)
                await session.commit()
        except Exception:
            await self._fallback_memory.aput_writes(config, writes, task_id, task_path=task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        """Supprime tous les checkpoints et writes d'un thread donné."""
        try:
            async with async_session_maker() as session:
                if self._is_postgres(session):
                    await session.execute(
                        delete(LangGraphCheckpointWrite).where(LangGraphCheckpointWrite.thread_id == str(thread_id))
                    )
                    await session.execute(
                        delete(LangGraphCheckpoint).where(LangGraphCheckpoint.thread_id == str(thread_id))
                    )
                    await session.commit()
        except Exception:
            pass
        await self._fallback_memory.adelete_thread(thread_id)

    # Délégations synchrones requises par BaseCheckpointSaver
    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        return self._fallback_memory.get_tuple(config)

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        return self._fallback_memory.list(config, filter=filter, before=before, limit=limit)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self._fallback_memory.put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self._fallback_memory.put_writes(config, writes, task_id, task_path=task_path)


postgres_checkpointer = PostgresAsyncCheckpointSaver()
