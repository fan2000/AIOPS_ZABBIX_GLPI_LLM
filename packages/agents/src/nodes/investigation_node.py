"""Nœud Agent Investigation (Lecture Seule) : Enquête conditionnelle bornée si preuves insuffisantes."""

import asyncio
import time
from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.connectors.zabbix.src.client import zabbix_client
from packages.observability.src.metrics import record_agent_execution, record_investigation_loop
from packages.rag.src.retriever import hybrid_retriever


def _infer_topology_hint(host_name: str, asset_info: Dict[str, Any]) -> str:
    h = (host_name or "").upper()
    if any(k in h for k in ("RTR", "CORE", "SW-", "FW", "WAF", "GATEWAY")):
        return f"Rôle topologique déduit pour {host_name} : Équipement d'infrastructure réseau critique."
    if any(k in h for k in ("SCADA", "OT-", "PLC")):
        return f"Rôle topologique déduit pour {host_name} : Segment industriel OT isolé."
    if asset_info.get("site_code"):
        return f"Contexte site identifié : {asset_info['site_code']}."
    return ""


async def investigation_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Enrichit les preuves en lecture seule (Zabbix host, RAG élargi, contexte site) sans action destructive."""
    t0 = time.perf_counter()
    iteration = int(state.get("investigation_iterations") or 0) + 1
    observations: List[str] = list(state.get("observations") or [])
    findings: List[str] = list(state.get("investigation_findings") or [])
    citations: List[Dict[str, Any]] = list(state.get("rag_citations") or [])
    asset_info: Dict[str, Any] = dict(state.get("asset_info") or {})

    primary_event = state.get("primary_event", {}) or {}
    problem = str(primary_event.get("problem", ""))
    host_name = str(state.get("host_name", ""))
    zabbix_host_id = str(state.get("zabbix_host_id") or "")
    entity_id = str(state.get("entity_id") or "0")

    new_evidence_found = False

    # 1. Contexte topologique lecture seule (au premier passage uniquement)
    if iteration == 1:
        topo_hint = _infer_topology_hint(host_name, asset_info)
        if topo_hint and topo_hint not in observations:
            observations.append(topo_hint)
            findings.append(topo_hint)
            new_evidence_found = True

    # 2. Sonde Zabbix get_host en lecture seule (si ID numérique non encore sondé)
    if zabbix_host_id.isdigit() and not asset_info.get("zabbix_probed"):
        asset_info["zabbix_probed"] = True
        try:
            zbx_host = await asyncio.wait_for(zabbix_client.get_host(zabbix_host_id), timeout=1.5)
            if zbx_host:
                desc = zbx_host.get("description") or ""
                if desc:
                    asset_info["operatingsystem"] = asset_info.get("operatingsystem") or str(desc)[:90]
                    note = f"Investigation Zabbix : description hôte = {str(desc)[:120]}"
                    observations.append(note)
                    findings.append(note)
                    new_evidence_found = True
        except Exception:
            pass

    # 3. Recherche RAG élargie si aucune citation n'avait été remontée
    if not citations and problem and not bool(state.get("skip_rag_lookup", False)):
        os_hint = str(asset_info.get("operatingsystem") or "")
        expanded_query = f"{problem} {os_hint} diagnostic erreur procédure".strip()
        try:
            extra = await hybrid_retriever.search(query=expanded_query, entity_id=entity_id, top_k=3)
            if extra:
                citations = [c.model_dump(mode="json") for c in extra]
                note = f"Investigation RAG élargie : {len(citations)} source(s) documentaire(s) trouvée(s)."
                observations.append(note)
                findings.append(note)
                new_evidence_found = True
        except Exception:
            pass

    # 4. Fin anticipée anti-burn si aucune nouvelle preuve exploitable n'a été découverte
    exhausted = not new_evidence_found
    outcome = "evidence_found" if new_evidence_found else "exhausted"
    record_investigation_loop(outcome)

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("investigation_agent", outcome)

    return {
        "investigation_iterations": iteration,
        "investigation_findings": findings,
        "investigation_exhausted": exhausted,
        "observations": observations,
        "rag_citations": citations,
        "asset_info": asset_info,
        "agent_telemetry": {
            "Investigation Agent": {
                "duration_ms": dur_ms,
                "status": "ok",
                "iteration": iteration,
                "outcome": outcome,
                "findings": findings,
            }
        },
    }
