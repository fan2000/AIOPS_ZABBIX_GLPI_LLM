"""Client LLM hybride orienté production (Ollama + OpenAI-compatible, cache Redis+LRU, disjoncteur, FinOps)."""

import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional
import httpx

from packages.agents.src.guardrails import estimate_cost_usd, estimate_tokens
from packages.connectors.redis_streams import redis_streams

_ORIG_ASYNC_CLIENT = httpx.AsyncClient


def _strip_json_fences(raw: str) -> str:
    txt = (raw or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


class LLMClient:
    """Interface LLM résiliente avec routage par sévérité, quota journalier, cache et circuit breaker."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        daily_token_budget: Optional[int] = None,
        max_cache_size: int = 512,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "gemma4:latest")
        self.escalation_model = os.getenv("LLM_ESCALATION_MODEL", "").strip()
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("LLM_TIMEOUT", "15.0"))
        )
        self.connect_timeout = float(os.getenv("LLM_CONNECT_TIMEOUT", "0.5"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "768"))
        self.daily_token_budget = (
            daily_token_budget
            if daily_token_budget is not None
            else int(os.getenv("LLM_DAILY_TOKEN_BUDGET", "500000"))
        )
        self.max_cache_size = max_cache_size

        # Cache LRU borné (mémoire locale)
        self._cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

        # Disjoncteur (Closed -> Open -> Half-Open)
        self._failure_count: int = 0
        self._failure_threshold: int = 2
        self._last_fail_ts: float = 0.0
        self._circuit_cooldown_sec: float = float(os.getenv("LLM_CIRCUIT_COOLDOWN", "30.0"))

        # Suivi quota local (si Redis indisponible)
        self._local_quota_day: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._local_quota_tokens: int = 0

        # Pool HTTP réutilisable + cache sonde santé (TTL 10s)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._pool_loop: Optional[asyncio.AbstractEventLoop] = None
        self._health_cache: Optional[Dict[str, Any]] = None
        self._health_cache_ts: float = 0.0
        self._health_cache_ttl: float = float(os.getenv("LLM_HEALTH_CACHE_TTL", "10.0"))

    async def _get_pooled_client(self) -> Optional[httpx.AsyncClient]:
        """Retourne un client HTTP poolé lié à la boucle asyncio courante (None si httpx mocké)."""
        if httpx.AsyncClient is not _ORIG_ASYNC_CLIENT:
            return None
        loop = asyncio.get_running_loop()
        if self._http_client is None or self._http_client.is_closed or self._pool_loop is not loop:
            self._http_client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16)
            )
            self._pool_loop = loop
        return self._http_client

    def _cache_key(self, model: str, system_prompt: str, user_prompt: str) -> str:
        return hashlib.sha256(f"{self.provider}:{model}:{system_prompt}::{user_prompt}".encode("utf-8")).hexdigest()

    def _select_model(self, severity: str) -> str:
        if self.escalation_model and severity.upper() in ("HIGH", "DISASTER"):
            return self.escalation_model
        return self.model_name

    def get_circuit_state(self) -> str:
        if self._failure_count < self._failure_threshold:
            return "closed"
        if (time.monotonic() - self._last_fail_ts) < self._circuit_cooldown_sec:
            return "open"
        return "half_open"

    def _is_circuit_open(self) -> bool:
        state = self.get_circuit_state()
        if state == "half_open":
            self._failure_count = self._failure_threshold - 1
            return False
        return state == "open"

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_fail_ts = time.monotonic()
        self._health_cache = None

    def _record_success(self) -> None:
        self._failure_count = 0
        self._last_fail_ts = 0.0
        self._health_cache = None

    def _cache_put(self, key: str, value: Dict[str, Any]) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self.max_cache_size:
            self._cache.popitem(last=False)

    async def _check_quota_available(self) -> bool:
        if self.daily_token_budget <= 0:
            return False
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._local_quota_day != today:
            self._local_quota_day = today
            self._local_quota_tokens = 0
        try:
            r_client = await redis_streams.get_client()
            if r_client is not None:
                val = await r_client.get(f"aiops:llm:quota:{today}")
                if val is not None and int(val) >= self.daily_token_budget:
                    return False
        except Exception:
            pass
        return self._local_quota_tokens < self.daily_token_budget

    async def _increment_quota(self, tokens: int) -> None:
        if tokens <= 0:
            return
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._local_quota_day != today:
            self._local_quota_day = today
            self._local_quota_tokens = 0
        self._local_quota_tokens += tokens
        try:
            r_client = await redis_streams.get_client()
            if r_client is not None:
                qkey = f"aiops:llm:quota:{today}"
                await r_client.incrby(qkey, tokens)
                await r_client.expire(qkey, 172800)
        except Exception:
            pass

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        severity: str = "AVERAGE",
    ) -> Dict[str, Any]:
        """Exécute une inférence JSON structurée avec traçabilité complète (mode, tokens, coût, latence)."""
        t0 = time.perf_counter()
        active_model = self._select_model(severity)

        if self.provider == "disabled":
            return {
                "data": None,
                "mode": "deterministic_disabled",
                "model": active_model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error_reason": "provider_disabled",
            }

        # 1. Cache LRU mémoire
        ckey = self._cache_key(active_model, system_prompt, user_prompt)
        if ckey in self._cache:
            self._cache.move_to_end(ckey)
            return {
                "data": self._cache[ckey],
                "mode": "cache_hit_memory",
                "model": active_model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error_reason": None,
            }

        # 2. Cache Redis distribué
        redis_key = f"aiops:llm:{active_model}:{ckey}"
        try:
            r_client = await redis_streams.get_client()
            if r_client is not None:
                cached = await r_client.get(redis_key)
                if cached:
                    parsed_cached = json.loads(cached)
                    if isinstance(parsed_cached, dict):
                        self._cache_put(ckey, parsed_cached)
                        return {
                            "data": parsed_cached,
                            "mode": "cache_hit_redis",
                            "model": active_model,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "estimated_cost_usd": 0.0,
                            "latency_ms": int((time.perf_counter() - t0) * 1000),
                            "error_reason": None,
                        }
        except Exception:
            pass

        # 3. Garde FinOps & Circuit Breaker
        if not await self._check_quota_available():
            return {
                "data": None,
                "mode": "quota_exceeded_fallback",
                "model": active_model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error_reason": "daily_token_budget_exceeded",
            }

        if self._is_circuit_open():
            return {
                "data": None,
                "mode": "circuit_open_fallback",
                "model": active_model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error_reason": "circuit_breaker_open",
            }

        # 4. Inférence LLM réelle (pool HTTP réutilisable en prod, AsyncClient direct si patché en test)
        timeout_cfg = httpx.Timeout(self.timeout, connect=self.connect_timeout)
        error_reason = "llm_unavailable"
        try:
            pooled = await self._get_pooled_client()
            if pooled is not None:
                res, parsed, p_tok, c_tok, error_reason = await self._call_llm_endpoint(
                    pooled, active_model, system_prompt, user_prompt, timeout_cfg
                )
            else:
                async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                    res, parsed, p_tok, c_tok, error_reason = await self._call_llm_endpoint(
                        client, active_model, system_prompt, user_prompt, timeout_cfg
                    )

            if isinstance(parsed, dict):
                self._record_success()
                cost_usd = estimate_cost_usd(self.provider, active_model, p_tok, c_tok)
                await self._increment_quota(p_tok + c_tok)
                self._cache_put(ckey, parsed)
                try:
                    r_client = await redis_streams.get_client()
                    if r_client is not None:
                        await r_client.setex(redis_key, 300, json.dumps(parsed))
                except Exception:
                    pass
                return {
                    "data": parsed,
                    "mode": "llm_live",
                    "model": active_model,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "estimated_cost_usd": cost_usd,
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "error_reason": None,
                }
        except httpx.TimeoutException:
            self._record_failure()
            error_reason = "timeout"
        except json.JSONDecodeError:
            self._record_failure()
            error_reason = "invalid_json"
        except Exception:
            self._record_failure()
            error_reason = "connection_error"

        return {
            "data": None,
            "mode": "deterministic_fallback",
            "model": active_model,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_usd": 0.0,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error_reason": error_reason,
        }

    async def _call_llm_endpoint(
        self,
        client: httpx.AsyncClient,
        active_model: str,
        system_prompt: str,
        user_prompt: str,
        timeout_cfg: httpx.Timeout,
    ) -> tuple[Optional[httpx.Response], Optional[Dict[str, Any]], int, int, str]:
        if self.provider == "openai_compatible":
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {
                "model": active_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": self.max_tokens,
            }
            res = await client.post(
                f"{self.openai_base_url}/chat/completions", json=payload, headers=headers, timeout=timeout_cfg
            )
            if res.status_code == 200:
                body = res.json()
                content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
                parsed = json.loads(_strip_json_fences(content))
                usage = body.get("usage", {})
                p_tok = int(usage.get("prompt_tokens") or estimate_tokens(system_prompt + user_prompt))
                c_tok = int(usage.get("completion_tokens") or estimate_tokens(content))
                return res, parsed, p_tok, c_tok, ""
            self._record_failure()
            return res, None, 0, 0, f"http_{res.status_code}"

        payload = {
            "model": active_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": self.max_tokens,
            },
        }
        res = await client.post(f"{self.base_url}/api/chat", json=payload, timeout=timeout_cfg)
        if res.status_code == 200:
            body = res.json()
            content = body.get("message", {}).get("content", "")
            parsed = json.loads(_strip_json_fences(content))
            p_tok = int(body.get("prompt_eval_count") or estimate_tokens(system_prompt + user_prompt))
            c_tok = int(body.get("eval_count") or estimate_tokens(content))
            return res, parsed, p_tok, c_tok, ""
        self._record_failure()
        return res, None, 0, 0, f"http_{res.status_code}"

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        severity: str = "AVERAGE",
    ) -> Optional[Dict[str, Any]]:
        """Méthode rétro-compatible retournant le dictionnaire JSON généré ou None."""
        res = await self.generate_structured(system_prompt, user_prompt, severity=severity)
        return res.get("data")

    async def check_health(self, force: bool = False) -> Dict[str, Any]:
        """Vérifie la disponibilité live du serveur d'inférence avec cache TTL 10s non bloquant."""
        circuit = self.get_circuit_state()
        if self.provider == "disabled":
            return {
                "online": False,
                "provider": "disabled",
                "model": self.model_name,
                "circuit_state": circuit,
                "available_models": [],
            }
        if self.provider == "openai_compatible":
            return {
                "online": bool(self.api_key) and circuit != "open",
                "provider": "openai_compatible",
                "model": self.model_name,
                "circuit_state": circuit,
                "available_models": [self.model_name],
            }

        now_mono = time.monotonic()
        if (
            not force
            and self._health_cache is not None
            and (now_mono - self._health_cache_ts) < self._health_cache_ttl
            and httpx.AsyncClient is _ORIG_ASYNC_CLIENT
        ):
            return {**self._health_cache, "circuit_state": circuit}

        t_cfg = httpx.Timeout(1.0, connect=0.4)
        try:
            pooled = await self._get_pooled_client()
            if pooled is not None:
                r = await pooled.get(f"{self.base_url}/api/tags", timeout=t_cfg)
            else:
                async with httpx.AsyncClient(timeout=t_cfg) as client:
                    r = await client.get(f"{self.base_url}/api/tags")
            if r.status_code == 200:
                models = [m.get("name") for m in r.json().get("models", []) if isinstance(m, dict)]
                out = {
                    "online": True,
                    "provider": self.provider,
                    "model": self.model_name,
                    "circuit_state": circuit,
                    "available_models": models,
                }
                self._health_cache = out
                self._health_cache_ts = now_mono
                return out
        except Exception:
            pass

        out = {
            "online": False,
            "provider": self.provider,
            "model": self.model_name,
            "circuit_state": circuit,
            "available_models": [],
        }
        self._health_cache = out
        self._health_cache_ts = now_mono
        return out


llm_client = LLMClient()
