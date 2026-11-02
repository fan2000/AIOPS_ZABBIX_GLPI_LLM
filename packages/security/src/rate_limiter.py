"""Rate Limiter avec Redis et fallback mémoire en fenêtre glissante."""

import time
from typing import Dict, List, Optional


class InMemoryRateLimiter:
    """Fallback en mémoire pour environnements de test ou sans Redis."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}

    def is_allowed(self, client_key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        timestamps = self._history.get(client_key, [])
        # Nettoyage des requêtes hors fenêtre
        valid_timestamps = [t for t in timestamps if t > cutoff]
        self._history[client_key] = valid_timestamps

        if len(valid_timestamps) >= self.max_requests:
            return False

        self._history[client_key].append(now)
        return True


default_limiter = InMemoryRateLimiter(max_requests=300, window_seconds=60)
