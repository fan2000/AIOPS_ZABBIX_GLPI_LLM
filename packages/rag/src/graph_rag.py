"""GraphRAG léger opérationnel reliant Actifs CMDB, Services, Incidents, KB et Runbooks."""

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from packages.domain.models.database import (
    AIAnalysisRun,
    AIRecommendation,
    Asset,
    Incident,
    KnowledgeChunk,
    KnowledgeDocument,
    RecommendationSource,
    Runbook,
)
from packages.rag.src.chunker import extract_operational_metadata
from packages.rag.src.quality import clean_incident_title, normalize_incident_family


async def build_operational_graph(
    session: AsyncSession,
    entity_scope: List[str],
    focus_query: Optional[str] = None,
    asset_name: Optional[str] = None,
    limit_incidents: int = 50,
) -> Dict[str, Any]:
    """Construit le graphe relationnel typé Asset ↔ Service ↔ Incidents ↔ Articles KB ↔ Runbooks."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges_seen: Set[Tuple[str, str, str]] = set()
    edges: List[Dict[str, str]] = []

    def _add_node(node_id: str, node_type: str, label: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "type": node_type,
                "label": label,
                "metadata": dict(metadata or {}),
            }

    def _add_edge(source: str, target: str, relation: str) -> None:
        if not source or not target or source == target:
            return
        if source not in nodes or target not in nodes:
            return
        key = (source, target, relation)
        if key not in edges_seen:
            edges_seen.add(key)
            edges.append({"source": source, "target": target, "relation": relation})

    def _ensure_service_node(service_name: str) -> Optional[str]:
        clean = (service_name or "").strip().lower()
        if not clean or clean == "general":
            return None
        svc_id = f"service:{clean}"
        _add_node(svc_id, "service", clean, {"domain": clean})
        return svc_id

    # 1. Actifs CMDB
    assets: List[Asset] = []
    try:
        asset_stmt = select(Asset)
        if "*" not in entity_scope:
            asset_stmt = asset_stmt.where(Asset.entity_id.in_(entity_scope))
        assets = list((await session.execute(asset_stmt.limit(100))).scalars().all())
    except Exception:
        assets = []

    asset_id_by_name: Dict[str, str] = {}
    for asset in assets:
        upper_name = str(asset.name or "").strip().upper()
        if not upper_name:
            continue
        nid = f"asset:{upper_name}"
        asset_id_by_name[upper_name] = nid
        _add_node(
            nid,
            "asset",
            asset.name,
            {
                "in_cmdb": True,
                "os_name": asset.os_name,
                "ip_address": asset.ip_address,
                "entity_id": asset.entity_id,
            },
        )
        tags = asset.tags or {}
        if isinstance(tags, dict):
            svc_tag = tags.get("service")
            if isinstance(svc_tag, str):
                svc_nid = _ensure_service_node(svc_tag)
                if svc_nid:
                    _add_edge(nid, svc_nid, "HOSTS_SERVICE")

    # 2. Runbooks certifiés
    runbooks: List[Runbook] = []
    try:
        runbooks = list(
            (await session.execute(select(Runbook).where(Runbook.is_enabled == True).limit(50))).scalars().all()  # noqa: E712
        )
    except Exception:
        runbooks = []

    for rb in runbooks:
        rb_nid = f"runbook:{rb.identifier}"
        meta = extract_operational_metadata(title=rb.name, text=f"{rb.description} {rb.identifier}", source_type="runbook_doc")
        _add_node(
            rb_nid,
            "runbook",
            rb.identifier,
            {
                "name": rb.name,
                "target_os": rb.target_os,
                "runner_type": rb.runner_type,
                "category": meta.get("category", "general"),
            },
        )
        for svc_candidate in meta.get("services") or ([meta["category"]] if meta.get("category") != "general" else []):
            svc_nid = _ensure_service_node(str(svc_candidate))
            if svc_nid:
                _add_edge(rb_nid, svc_nid, "COVERS_SERVICE")

    # 3. Documents KB
    docs: List[KnowledgeDocument] = []
    try:
        doc_stmt = select(KnowledgeDocument)
        if "*" not in entity_scope:
            doc_stmt = doc_stmt.where(KnowledgeDocument.entity_id.in_(entity_scope))
        docs = list((await session.execute(doc_stmt.limit(100))).scalars().all())
    except Exception:
        docs = []

    chunk_meta_by_doc: Dict[Any, Dict[str, Any]] = {}
    if docs:
        try:
            doc_ids = [d.id for d in docs]
            chunks = (
                await session.execute(
                    select(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(doc_ids), KnowledgeChunk.chunk_index == 0)
                )
            ).scalars().all()
            for ch in chunks:
                if isinstance(ch.metadata_fields, dict):
                    chunk_meta_by_doc[ch.document_id] = ch.metadata_fields
        except Exception:
            pass

    kb_nid_by_ref: Dict[str, str] = {}
    for doc in docs:
        if not (doc.raw_content or "").strip() and str(doc.title).strip().lower() == "home":
            continue
        ref = str(doc.external_id or doc.id)
        kb_nid = f"kb:{ref}"
        kb_nid_by_ref[ref] = kb_nid
        meta = chunk_meta_by_doc.get(doc.id) or extract_operational_metadata(
            title=doc.title, text=doc.raw_content, source_type=doc.source_type
        )
        _add_node(
            kb_nid,
            "kb_article",
            doc.title,
            {
                "document_id": str(doc.id),
                "external_id": ref,
                "source_type": doc.source_type,
                "entity_id": doc.entity_id,
                "os": meta.get("os", "all"),
                "category": meta.get("category", "general"),
                "service": meta.get("service", "general"),
            },
        )
        svc_targets = list(meta.get("services") or [])
        if meta.get("category") and meta["category"] != "general":
            svc_targets.append(meta["category"])
        for svc in svc_targets:
            svc_nid = _ensure_service_node(str(svc))
            if svc_nid:
                _add_edge(kb_nid, svc_nid, "COVERS_SERVICE")

    # 4. Incidents + runs IA + recommandations + citations
    incidents: List[Incident] = []
    try:
        inc_stmt = select(Incident)
        if "*" not in entity_scope:
            inc_stmt = inc_stmt.where(Incident.entity_id.in_(entity_scope))
        incidents = list(
            (await session.execute(inc_stmt.order_by(desc(Incident.opened_at)).limit(limit_incidents))).scalars().all()
        )
    except Exception:
        incidents = []

    inc_ids = [i.id for i in incidents]
    latest_run_by_inc: Dict[Any, AIAnalysisRun] = {}
    if inc_ids:
        try:
            runs = (
                await session.execute(
                    select(AIAnalysisRun)
                    .where(AIAnalysisRun.incident_id.in_(inc_ids))
                    .order_by(desc(AIAnalysisRun.created_at))
                )
            ).scalars().all()
            for r in runs:
                if r.incident_id not in latest_run_by_inc:
                    latest_run_by_inc[r.incident_id] = r
        except Exception:
            pass

    run_ids = [r.id for r in latest_run_by_inc.values()]
    recs_by_run: Dict[Any, List[AIRecommendation]] = {}
    if run_ids:
        try:
            for rec in (
                await session.execute(select(AIRecommendation).where(AIRecommendation.analysis_run_id.in_(run_ids)))
            ).scalars().all():
                recs_by_run.setdefault(rec.analysis_run_id, []).append(rec)
        except Exception:
            pass

    rec_ids = [rec.id for lst in recs_by_run.values() for rec in lst]
    sources_by_rec: Dict[Any, List[RecommendationSource]] = {}
    if rec_ids:
        try:
            for src in (
                await session.execute(
                    select(RecommendationSource).where(RecommendationSource.recommendation_id.in_(rec_ids))
                )
            ).scalars().all():
                sources_by_rec.setdefault(src.recommendation_id, []).append(src)
        except Exception:
            pass

    canonical_inc_by_family: Dict[str, str] = {}
    for inc in incidents:
        inc_nid = f"incident:{inc.id}"
        fam_key = normalize_incident_family(inc.title, inc.primary_asset_name)
        meta = extract_operational_metadata(
            title=clean_incident_title(inc.title, inc.primary_asset_name),
            text=inc.title,
        )
        run = latest_run_by_inc.get(inc.id)
        _add_node(
            inc_nid,
            "incident",
            f"{inc.incident_number} • {clean_incident_title(inc.title, inc.primary_asset_name)}",
            {
                "incident_id": str(inc.id),
                "incident_number": inc.incident_number,
                "severity": inc.severity,
                "status": inc.status,
                "entity_id": inc.entity_id,
                "family_key": fam_key,
                "category": meta.get("category", "general"),
                "confidence_level": run.confidence_level if run else "unanalyzed",
            },
        )

        # Lien Incident -> Asset (crée un nœud Asset synthétique si absent de CMDB)
        host_upper = str(inc.primary_asset_name or "").strip().upper()
        asset_nid: Optional[str] = None
        if host_upper:
            asset_nid = asset_id_by_name.get(host_upper) or f"asset:{host_upper}"
            if asset_nid not in nodes:
                _add_node(
                    asset_nid,
                    "asset",
                    inc.primary_asset_name,
                    {"in_cmdb": False, "entity_id": inc.entity_id},
                )
            asset_id_by_name[host_upper] = asset_nid
            _add_edge(inc_nid, asset_nid, "AFFECTS_ASSET")

        # Lien Incident & Asset -> Service / Domaine
        svc_candidates = list(meta.get("services") or [])
        if meta.get("category") and meta["category"] != "general":
            svc_candidates.append(meta["category"])
        for svc in svc_candidates:
            svc_nid = _ensure_service_node(str(svc))
            if svc_nid:
                _add_edge(inc_nid, svc_nid, "IMPACTS_SERVICE")
                if asset_nid:
                    _add_edge(asset_nid, svc_nid, "HOSTS_SERVICE")

        # Incidents similaires (topologie étoile sur le représentant canonique de famille)
        if fam_key not in canonical_inc_by_family:
            canonical_inc_by_family[fam_key] = inc_nid
        else:
            _add_edge(inc_nid, canonical_inc_by_family[fam_key], "SIMILAR_INCIDENT")

        # Liens Runbook & Articles KB cités
        if run is not None:
            for rec in recs_by_run.get(run.id, []):
                if rec.runbook_id:
                    rb_nid = f"runbook:{rec.runbook_id}"
                    if rb_nid not in nodes:
                        _add_node(rb_nid, "runbook", rec.runbook_id, {"identifier": rec.runbook_id})
                    _add_edge(inc_nid, rb_nid, "REMEDIATED_BY")
                for src in sources_by_rec.get(rec.id, []):
                    ref = str(src.article_reference or "").strip()
                    if not ref:
                        continue
                    kb_nid = kb_nid_by_ref.get(ref) or f"kb:{ref}"
                    if kb_nid not in nodes:
                        _add_node(
                            kb_nid,
                            "kb_article",
                            src.source_title,
                            {"external_id": ref, "source_type": "citation"},
                        )
                    _add_edge(inc_nid, kb_nid, "CITED_BY")

    # 5. Extraction sous-graphe à 2 sauts si focus_query ou asset_name est fourni
    matched_ids: List[str] = []
    if focus_query or asset_name:
        terms: List[str] = []
        if asset_name:
            terms.append(asset_name.strip().lower())
        if focus_query:
            terms.extend(t for t in focus_query.strip().lower().split() if len(t) >= 2)

        for nid, nd in nodes.items():
            haystack = f"{nd['label']} {nd.get('type', '')} {' '.join(str(v) for v in (nd.get('metadata') or {}).values())}".lower()
            if asset_name and nd["type"] == "asset" and asset_name.strip().lower() in nd["label"].lower():
                matched_ids.append(nid)
            elif terms and any(term in haystack for term in terms):
                matched_ids.append(nid)

        if matched_ids:
            adj: Dict[str, Set[str]] = {}
            for e in edges:
                adj.setdefault(e["source"], set()).add(e["target"])
                adj.setdefault(e["target"], set()).add(e["source"])

            visited: Set[str] = set(matched_ids)
            queue: deque[Tuple[str, int]] = deque((nid, 0) for nid in matched_ids)
            while queue:
                cur, depth = queue.popleft()
                if depth >= 2:
                    continue
                for nb in adj.get(cur, ()):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append((nb, depth + 1))

            nodes = {nid: nd for nid, nd in nodes.items() if nid in visited}
            edges = [e for e in edges if e["source"] in visited and e["target"] in visited]
        else:
            nodes = {}
            edges = []

    node_list = list(nodes.values())
    stats = {
        "assets": sum(1 for n in node_list if n["type"] == "asset"),
        "services": sum(1 for n in node_list if n["type"] == "service"),
        "incidents": sum(1 for n in node_list if n["type"] == "incident"),
        "kb_articles": sum(1 for n in node_list if n["type"] == "kb_article"),
        "runbooks": sum(1 for n in node_list if n["type"] == "runbook"),
        "edges": len(edges),
    }
    return {
        "nodes": node_list,
        "edges": edges,
        "matched_node_ids": matched_ids,
        "stats": stats,
        "focus": {"query": focus_query, "asset": asset_name},
    }
