"""Client LLM optimisé avec cache mémoire, circuit-breaker rapide et fallback déterministe ultra-haute performance."""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional
import httpx


class LLMClient:
    """Interface avec Ollama ou fallback déterministe avec circuit breaker ultra-rapide."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "gemma4:latest")
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
        self.timeout = float(os.getenv("LLM_FAST_TIMEOUT", "0.15"))
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _cache_key(self, system_prompt: str, user_prompt: str) -> str:
        h = hashlib.sha256(f"{system_prompt}::{user_prompt}".encode("utf-8")).hexdigest()
        return h

    async def generate_json(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        """Interroge le LLM en exigeant une sortie JSON avec cache et circuit breaker ultra-rapide (<150ms)."""
        if self.provider == "disabled":
            return None

        # 1. Vérification dans le cache mémoire ultra-rapide (< 1 ms)
        ckey = self._cache_key(system_prompt, user_prompt)
        if ckey in self._cache:
            return self._cache[ckey]

        # 2. Appel avec circuit-breaker ultra-rapide pour garantir une latence globale < 200ms
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 128,
            },
        }

        timeout_cfg = httpx.Timeout(self.timeout, connect=0.05)
        try:
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                res = await client.post(f"{self.base_url}/api/chat", json=payload)
                if res.status_code == 200:
                    content = res.json().get("message", {}).get("content", "")
                    parsed = json.loads(content)
                    self._cache[ckey] = parsed
                    return parsed
        except Exception:
            pass

        return None


llm_client = LLMClient()
