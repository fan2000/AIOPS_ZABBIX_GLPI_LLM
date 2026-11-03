"""Point d'entrée principal du worker d'orchestration des incidents."""

import asyncio
import sys
from services.incident_worker.src.worker import incident_worker

if __name__ == "__main__":
    print("🚀 [AIOps Incident Worker] Démarrage du consommateur Redis Streams & Orchestrateur...", flush=True)
    try:
        asyncio.run(incident_worker.start())
    except KeyboardInterrupt:
        print("🛑 [AIOps Incident Worker] Arrêt du worker.", flush=True)
    except Exception as exc:
        print(f"💥 [AIOps Incident Worker] Exception non interceptée: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
