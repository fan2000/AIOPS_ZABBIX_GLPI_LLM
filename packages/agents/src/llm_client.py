"""Client LLM pour l'inférence locale Ollama avec mode dégradé déterministe."""

import json
import os
from typing import Any, Dict, List, Optional
import httpx


class LLMClient:
    """Interface avec Ollama ou fallback déterministe conforme aux règles AIOps."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "gemma4:latest")
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()

    async def generate_json(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        """Interroge le LLM en exigeant une sortie JSON stricte."""
        if self.provider == "disabled":
            return None

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1},
        }

        timeout_cfg = httpx.Timeout(2.0, connect=0.5)
        try:
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                res = await client.post(f"{self.base_url}/api/chat", json=payload)
                if res.status_code == 200:
                    content = res.json().get("message", {}).get("content", "")
                    return json.loads(content)
        except Exception:
            pass

        return None


llm_client = LLMClient()
