"""Rate Limiter avec Redis et fallback mémoire en fenêtre glissante (CWE-770)."""

import time
from typing import Dict, List, Optional


class InMemoryRateLimiter:
    """Fallback en mémoire pour environnements de test ou sans Redis avec nettoyage anti-fuite mémoire."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()

    def _cleanup_stale_keys(self, now: float) -> None:
        """Purge les clients inactifs pour prévenir les fuites de mémoire (CWE-770)."""
        cutoff = now - self.window_seconds
        stale = [k for k, timestamps in self._history.items() if not timestamps or max(timestamps) <= cutoff]
        for k in stale:
            del self._history[k]

    def is_allowed(self, client_key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        # Purge périodique si l'historique grandit
        if len(self._history) > 500 and (now - self._last_cleanup) > 30:
            self._cleanup_stale_keys(now)
            self._last_cleanup = now

        timestamps = self._history.get(client_key, [])
        # Nettoyage des requêtes hors fenêtre
        valid_timestamps = [t for t in timestamps if t > cutoff]

        if len(valid_timestamps) >= self.max_requests:
            self._history[client_key] = valid_timestamps
            return False

        valid_timestamps.append(now)
        self._history[client_key] = valid_timestamps
        return True


default_limiter = InMemoryRateLimiter(max_requests=300, window_seconds=60)
auth_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
