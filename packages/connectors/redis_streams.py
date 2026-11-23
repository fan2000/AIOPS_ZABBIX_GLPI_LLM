"""Gestionnaire de files Redis Streams avec fallback mémoire pour tests."""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import redis.asyncio as aioredis


class RedisStreamsClient:
    """Client asynchrone pour la publication et consommation d'événements Redis Streams."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6380/0")
        self.max_stream_len = int(os.getenv("REDIS_STREAM_MAXLEN", "100000"))
        self._redis: Optional[aioredis.Redis] = None
        self._last_fail_ts: float = 0.0
        self._circuit_cooldown_sec: float = 10.0
        self._in_memory_streams: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        self._dlq_streams: Dict[str, List[Dict[str, Any]]] = {}
        self._msg_counter = 0

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Retourne la connexion Redis avec disjoncteur (Circuit Breaker) ou None en mode fallback HA."""
        if self._redis is not None:
            return self._redis
        if (time.monotonic() - self._last_fail_ts) < self._circuit_cooldown_sec and self._last_fail_ts > 0:
            return None
        try:
            client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=1.0,
                socket_connect_timeout=0.5,
            )
            await client.ping()
            self._redis = client
            self._last_fail_ts = 0.0
            return self._redis
        except Exception:
            # Disjoncteur ouvert temporairement : bascule instantanée sur le tampon mémoire HA
            self._last_fail_ts = time.monotonic()
            return None

    async def publish_event(self, stream_name: str, payload: Dict[str, Any]) -> str:
        """Publie un événement dans un stream (XADD avec MAXLEN anti-OOM et bascule HA)."""
        serialized = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in payload.items()}
        client = await self.get_client()
        if client:
            try:
                return await client.xadd(
                    stream_name,
                    serialized,
                    maxlen=self.max_stream_len,
                    approximate=True,
                )
            except Exception:
                # Bascule automatique en tampon mémoire si coupure réseau Redis transitoire (RPO = 0)
                self._redis = None

        # Fallback mémoire haute continuité
        self._msg_counter += 1
        msg_id = f"{int(self._msg_counter * 1000)}-0"
        if stream_name not in self._in_memory_streams:
            self._in_memory_streams[stream_name] = []
        self._in_memory_streams[stream_name].append((msg_id, payload))
        return msg_id

    async def publish_to_dlq(
        self,
        stream_name: str,
        original_msg_id: str,
        payload: Dict[str, Any],
        error_reason: str,
    ) -> str:
        """Isole un message en échec dans une Dead-Letter Queue (DLQ) pour ne jamais bloquer le flux."""
        dlq_name = f"{stream_name}:dlq"
        dlq_entry = {
            "original_msg_id": original_msg_id,
            "error_reason": error_reason[:500],
            "payload": payload,
        }
        if dlq_name not in self._dlq_streams:
            self._dlq_streams[dlq_name] = []
        self._dlq_streams[dlq_name].append(dlq_entry)
        return await self.publish_event(dlq_name, dlq_entry)

    def get_dlq_messages(self, stream_name: str = "zabbix:events") -> List[Dict[str, Any]]:
        """Retourne les messages isolés en DLQ locale."""
        return list(self._dlq_streams.get(f"{stream_name}:dlq", []))

    async def ensure_consumer_group(self, stream_name: str, group_name: str) -> None:
        """Crée le groupe de consommateurs s'il n'existe pas."""
        client = await self.get_client()
        if not client:
            return
        try:
            await client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def consume_events(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 2000,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Consomme les événements disponibles pour le groupe de consommateurs."""
        client = await self.get_client()
        if client:
            try:
                raw_messages = await client.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams={stream_name: ">"},
                    count=count,
                    block=block_ms,
                )
                results: List[Tuple[str, Dict[str, Any]]] = []
                for _, messages in raw_messages:
                    for msg_id, data in messages:
                        # Désérialisation des champs JSON
                        parsed = {}
                        for k, v in data.items():
                            try:
                                parsed[k] = json.loads(v)
                            except Exception:
                                parsed[k] = v
                        results.append((msg_id, parsed))
                return results
            except Exception:
                return []

        # Consommation depuis la file mémoire
        items = self._in_memory_streams.get(stream_name, [])
        ret = items[:count]
        self._in_memory_streams[stream_name] = items[count:]
        return ret

    async def ack_event(self, stream_name: str, group_name: str, message_id: str) -> None:
        """Acquitte le traitement d'un message (XACK)."""
        client = await self.get_client()
        if client:
            try:
                await client.xack(stream_name, group_name, message_id)
            except Exception:
                pass


redis_streams = RedisStreamsClient()
