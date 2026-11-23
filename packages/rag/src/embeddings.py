"""Service de génération d'embeddings vectoriels multi-providers haute fiabilité (batch, Redis, circuit-breaker, guard prod)."""

import asyncio
from collections import OrderedDict
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from packages.connectors.redis_streams import redis_streams
from packages.observability.src.metrics import record_rag_embedding


class EmbeddingsService:
    """Générateur d'embeddings multi-providers (Ollama / TEI / OpenAI-compat) avec batching et disjoncteur."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        dimension: int = 768,
        timeout_seconds: Optional[float] = None,
        allow_fallback: Optional[bool] = None,
        max_cache_size: int = 2048,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        self.provider = (provider or os.getenv("EMBEDDING_PROVIDER", "ollama")).strip().lower()
        resolved_url = base_url or os.getenv("EMBEDDING_BASE_URL") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.base_url = resolved_url.rstrip("/")
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.embedding_version = int(os.getenv("EMBEDDING_VERSION", "1"))
        self.dimension = int(os.getenv("EMBEDDING_DIMENSION", str(dimension)))
        self.api_key = api_key if api_key is not None else os.getenv("EMBEDDING_API_KEY")
        self.timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("EMBEDDING_TIMEOUT", "8.0"))
        )
        self.connect_timeout = float(os.getenv("EMBEDDING_CONNECT_TIMEOUT", "0.5"))
        self.batch_size = max(1, min(128, int(batch_size or os.getenv("EMBEDDING_BATCH_SIZE", "32"))))
        self.max_retries = max(
            0,
            int(max_retries if max_retries is not None else os.getenv("EMBEDDING_MAX_RETRIES", "1")),
        )
        self.max_cache_size = max_cache_size

        # En production, le fallback factice est désactivé sauf autorisation explicite
        if allow_fallback is not None:
            self.allow_fallback = allow_fallback
        else:
            env = os.getenv("ENVIRONMENT", "development").lower()
            explicit = os.getenv("ALLOW_FALLBACK_EMBEDDINGS")
            if explicit is not None:
                self.allow_fallback = explicit.lower() in ("true", "1", "yes")
            else:
                self.allow_fallback = env != "production"

        # Cache LRU borné (mémoire locale)
        self._cache: "OrderedDict[str, Tuple[List[float], Dict[str, Any]]]" = OrderedDict()

        # État du Circuit Breaker
        self._failure_count: int = 0
        self._failure_threshold: int = 2
        self._last_fail_ts: float = 0.0
        self._circuit_cooldown_sec: float = float(os.getenv("EMBEDDING_CIRCUIT_COOLDOWN", "30.0"))

    def _is_circuit_open(self) -> bool:
        if self._failure_count < self._failure_threshold:
            return False
        if (time.monotonic() - self._last_fail_ts) < self._circuit_cooldown_sec:
            return True
        # Fin du cooldown : passage en semi-ouvert pour réessayer
        self._failure_count = self._failure_threshold - 1
        return False

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_fail_ts = time.monotonic()

    def _record_success(self) -> None:
        self._failure_count = 0
        self._last_fail_ts = 0.0

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(
            f"{self.provider}:{self.model_name}:v{self.embedding_version}:{text}".encode("utf-8")
        ).hexdigest()

    def _cache_put(self, key: str, vec: List[float], meta: Dict[str, Any]) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (vec, meta)
        while len(self._cache) > self.max_cache_size:
            self._cache.popitem(last=False)

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _valid_vectors(self, vectors: Any, expected_count: int) -> Optional[List[List[float]]]:
        if not isinstance(vectors, list) or len(vectors) != expected_count:
            return None
        validated: List[List[float]] = []
        for vec in vectors:
            if not isinstance(vec, list) or len(vec) != self.dimension:
                return None
            validated.append([float(x) for x in vec])
        return validated

    async def _fetch_ollama_legacy(
        self,
        client: httpx.AsyncClient,
        texts: List[str],
        headers: Dict[str, str],
    ) -> Optional[List[List[float]]]:
        sem = asyncio.Semaphore(4)

        async def _one(txt: str) -> Optional[List[float]]:
            async with sem:
                res = await client.post(
                    f"{self.base_url}/api/embeddings",
                    headers=headers,
                    json={"model": self.model_name, "prompt": txt},
                )
                if res.status_code != 200:
                    return None
                vec = res.json().get("embedding")
                if isinstance(vec, list) and len(vec) == self.dimension:
                    return [float(x) for x in vec]
                return None

        results = await asyncio.gather(*[_one(t) for t in texts])
        if any(v is None for v in results):
            return None
        return [v for v in results if v is not None]

    async def _fetch_provider_batch_once(self, texts: List[str]) -> Optional[List[List[float]]]:
        timeout_cfg = httpx.Timeout(self.timeout, connect=min(self.connect_timeout, self.timeout))
        headers = self._build_headers()

        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            if self.provider == "tei":
                res = await client.post(
                    f"{self.base_url}/embed",
                    headers=headers,
                    json={"inputs": texts, "truncate": True},
                )
                if res.status_code == 200:
                    payload = res.json()
                    raw_vecs = payload.get("embeddings") if isinstance(payload, dict) else payload
                    return self._valid_vectors(raw_vecs, len(texts))
                return None

            if self.provider == "openai_compat":
                res = await client.post(
                    f"{self.base_url}/v1/embeddings",
                    headers=headers,
                    json={"model": self.model_name, "input": texts},
                )
                if res.status_code == 200:
                    data = res.json().get("data")
                    if isinstance(data, list) and len(data) == len(texts):
                        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
                        raw_vecs = [item.get("embedding") for item in ordered]
                        return self._valid_vectors(raw_vecs, len(texts))
                return None

            # Par défaut : Ollama (/api/embed batch natif, repli /api/embeddings si 404)
            res = await client.post(
                f"{self.base_url}/api/embed",
                headers=headers,
                json={"model": self.model_name, "input": texts},
            )
            if res.status_code == 200:
                return self._valid_vectors(res.json().get("embeddings"), len(texts))
            if res.status_code == 404:
                return await self._fetch_ollama_legacy(client, texts, headers)
            return None

    async def _fetch_provider_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Appelle le fournisseur d'embeddings par lot avec tentatives limitées et disjoncteur."""
        if not texts or self._is_circuit_open():
            return None

        attempts = 1 + self.max_retries
        for attempt in range(attempts):
            try:
                vecs = await self._fetch_provider_batch_once(texts)
                if vecs is not None:
                    self._record_success()
                    return vecs
            except Exception:
                pass

            self._record_failure()
            if self._is_circuit_open():
                break
            if attempt + 1 < attempts and self.timeout >= 0.5:
                await asyncio.sleep(0.1 * (2**attempt))
        return None

    async def get_embeddings_batch(
        self,
        texts: List[str],
        require_real: Optional[bool] = None,
    ) -> List[Tuple[List[float], Dict[str, Any]]]:
        """Vectorise une liste de textes en lot avec cache LRU/Redis, circuit-breaker et garde production strict."""
        if not texts:
            return []

        strict_real = require_real if require_real is not None else (not self.allow_fallback)
        resolved: Dict[int, Tuple[List[float], Dict[str, Any]]] = {}
        missing_by_hash: Dict[str, Tuple[str, List[int]]] = {}

        # 1. Passe mémoire (vides + LRU local)
        for idx, txt in enumerate(texts):
            if not txt or not txt.strip():
                resolved[idx] = (
                    [0.0] * self.dimension,
                    {
                        "provider": self.provider,
                        "model": self.model_name,
                        "version": self.embedding_version,
                        "is_fallback": True,
                        "cache_hit": False,
                    },
                )
                continue

            h = self._cache_key(txt)
            if h in self._cache:
                self._cache.move_to_end(h)
                vec, meta = self._cache[h]
                if not (strict_real and meta.get("is_fallback")):
                    record_rag_embedding(self.provider, "cache_hit")
                    resolved[idx] = (vec, {**meta, "cache_hit": True})
                    continue

            if h in missing_by_hash:
                missing_by_hash[h][1].append(idx)
            else:
                missing_by_hash[h] = (txt, [idx])

        # 2. Passe Redis distribuée par lot (vecteurs réels uniquement)
        if missing_by_hash:
            try:
                r_client = await redis_streams.get_client()
                if r_client is not None:
                    hashes = list(missing_by_hash.keys())
                    redis_keys = [f"aiops:emb:{self.provider}:{self.model_name}:v{self.embedding_version}:{h}" for h in hashes]
                    raw_values = await r_client.mget(redis_keys)
                    if isinstance(raw_values, list):
                        for h, cached_raw in zip(hashes, raw_values):
                            if not cached_raw:
                                continue
                            parsed = json.loads(cached_raw)
                            if isinstance(parsed, list) and len(parsed) == self.dimension:
                                meta = {
                                    "provider": self.provider,
                                    "model": self.model_name,
                                    "version": self.embedding_version,
                                    "is_fallback": False,
                                    "cache_hit": True,
                                }
                                self._cache_put(h, parsed, meta)
                                record_rag_embedding(self.provider, "cache_hit")
                                _, idxs = missing_by_hash.pop(h)
                                for i in idxs:
                                    resolved[i] = (parsed, meta)
            except Exception:
                pass

        # 3. Lots HTTP vers le provider pour les éléments encore manquants
        if missing_by_hash:
            pending_items = list(missing_by_hash.items())  # [(h, (txt, idxs)), ...]
            for start in range(0, len(pending_items), self.batch_size):
                chunk_items = pending_items[start : start + self.batch_size]
                chunk_texts = [item[1][0] for item in chunk_items]
                fetched_vecs = await self._fetch_provider_batch(chunk_texts)

                if fetched_vecs is not None:
                    try:
                        r_client = await redis_streams.get_client()
                    except Exception:
                        r_client = None

                    for (h, (_, idxs)), vec in zip(chunk_items, fetched_vecs):
                        meta = {
                            "provider": self.provider,
                            "model": self.model_name,
                            "version": self.embedding_version,
                            "is_fallback": False,
                            "cache_hit": False,
                        }
                        self._cache_put(h, vec, meta)
                        record_rag_embedding(self.provider, "real")
                        if r_client is not None:
                            try:
                                r_key = f"aiops:emb:{self.provider}:{self.model_name}:v{self.embedding_version}:{h}"
                                await r_client.setex(r_key, 86400, json.dumps(vec))
                            except Exception:
                                pass
                        for i in idxs:
                            resolved[i] = (vec, meta)
                else:
                    if strict_real:
                        record_rag_embedding(self.provider, "failed")
                        raise RuntimeError(
                            f"Embedding provider ({self.provider}/{self.model_name}) indisponible en mode production strict"
                        )
                    for h, (txt, idxs) in chunk_items:
                        vec = self._generate_deterministic_fallback(txt)
                        meta = {
                            "provider": self.provider,
                            "model": f"{self.model_name}-feature-hash-fallback",
                            "version": self.embedding_version,
                            "is_fallback": True,
                            "cache_hit": False,
                        }
                        self._cache_put(h, vec, meta)
                        record_rag_embedding(self.provider, "fallback")
                        for i in idxs:
                            resolved[i] = (vec, meta)

        return [resolved[i] for i in range(len(texts))]

    async def get_embedding_with_metadata(
        self,
        text: str,
        require_real: Optional[bool] = None,
    ) -> Tuple[List[float], Dict[str, Any]]:
        """Génère un vecteur normalisé avec ses métadonnées de provenance (modèle réel vs fallback)."""
        items = await self.get_embeddings_batch([text], require_real=require_real)
        return items[0]

    async def get_embedding(self, text: str) -> List[float]:
        """Point d'entrée rétro-compatible retournant uniquement le vecteur d'embedding."""
        vec, _ = await self.get_embedding_with_metadata(text)
        return vec

    def get_health_status(self) -> Dict[str, Any]:
        """Retourne l'état opérationnel du service d'embeddings pour observabilité."""
        return {
            "provider": self.provider,
            "model": self.model_name,
            "version": self.embedding_version,
            "dimension": self.dimension,
            "allow_fallback": self.allow_fallback,
            "circuit_state": "open" if self._is_circuit_open() else "closed",
            "failure_count": self._failure_count,
            "batch_size": self.batch_size,
            "cache_entries": len(self._cache),
        }

    def _generate_deterministic_fallback(self, text: str) -> List[float]:
        """Projection signée (feature hashing n-grammes + trigrammes) normalisée L2 pour mode hors-ligne."""
        tokens = re.findall(r"[a-zA-Z0-9_À-ÿ]+", text.lower())
        if not tokens:
            return [0.0] * self.dimension

        vector = [0.0] * self.dimension
        features: List[Tuple[str, float]] = []
        for tok in tokens:
            features.append((f"w:{tok}", 2.0))
            if len(tok) >= 3:
                for i in range(len(tok) - 2):
                    features.append((f"c3:{tok[i:i+3]}", 0.5))

        for feat, weight in features:
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vector[bucket] += sign * weight

        norm = sum(x * x for x in vector) ** 0.5 or 1.0
        return [round(x / norm, 6) for x in vector]


embeddings_service = EmbeddingsService()
