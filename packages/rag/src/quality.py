"""Calcul déterministe de qualité RAG (Faithfulness, couverture citations) et détection des Knowledge Gaps."""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Set
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from packages.domain.models.database import (
    AIAnalysisRun,
    AIEvalRun,
    AIRecommendation,
    Incident,
    KnowledgeProposal,
    RecommendationSource,
)
from packages.observability.src.metrics import set_rag_quality_metrics
from packages.rag.src.chunker import extract_operational_metadata

_STOPWORDS: Set[str] = {
    "les",
    "des",
    "une",
    "dans",
    "pour",
    "avec",
    "sans",
    "sur",
    "par",
    "est",
    "sont",
    "ete",
    "qui",
    "que",
    "quoi",
    "cette",
    "cet",
    "ces",
    "aux",
    "pas",
    "plus",
    "non",
    "tout",
    "tous",
    "etre",
    "avoir",
    "faire",
    "vers",
    "entre",
    "apres",
    "avant",
    "afin",
    "selon",
    "via",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "over",
    "under",
    "are",
    "was",
    "were",
    "has",
    "have",
    "not",
}

_SEVERITY_WEIGHT: Dict[str, int] = {
    "DISASTER": 30,
    "HIGH": 24,
    "AVERAGE": 16,
    "WARNING": 10,
    "INFO": 6,
    "INFORMATION": 6,
}

_SEVERITY_ORDER: Dict[str, int] = {
    "DISASTER": 5,
    "HIGH": 4,
    "AVERAGE": 3,
    "WARNING": 2,
    "INFO": 1,
    "INFORMATION": 1,
}


def _fold_text(text: str) -> str:
    """Normalise en minuscules ASCII sans accents."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return stripped.lower()


def _extract_meaningful_tokens(text: str) -> Set[str]:
    """Extrait les tokens porteurs de sens (>= 3 caractères hors stopwords)."""
    folded = _fold_text(text)
    raw_tokens = re.findall(r"[a-z0-9_/-]{3,}", folded)
    tokens: Set[str] = set()
    for tok in raw_tokens:
        parts = [p for p in re.split(r"[/_-]+", tok) if len(p) >= 3]
        for p in parts:
            if p not in _STOPWORDS:
                tokens.add(p)
        clean_tok = tok.strip("/_-")
        if len(clean_tok) >= 3 and clean_tok not in _STOPWORDS:
            tokens.add(clean_tok)
    return tokens


def _token_matches_evidence(claim_tok: str, evidence_tokens: Set[str]) -> bool:
    if claim_tok in evidence_tokens:
        return True
    if len(claim_tok) >= 5:
        prefix = claim_tok[:5]
        return any(len(ev) >= 5 and ev[:5] == prefix for ev in evidence_tokens)
    return False


def compute_faithfulness_score(
    hypotheses: List[Dict[str, Any]],
    recommended_actions: List[Dict[str, Any]],
    citations: List[Dict[str, Any]],
    observations: Optional[List[str]] = None,
    confidence_level: str = "",
) -> Dict[str, Any]:
    """Évalue la fidélité factuelle (Faithfulness 0..1) des hypothèses et actions face aux preuves RAG."""
    claims: List[str] = []
    for h in hypotheses or []:
        if isinstance(h, dict):
            txt = str(h.get("description") or h.get("hypothesis") or "").strip()
        else:
            txt = str(h).strip()
        if txt:
            claims.append(txt)

    for a in recommended_actions or []:
        if isinstance(a, dict):
            txt = str(a.get("action") or a.get("action_text") or "").strip()
        else:
            txt = str(a).strip()
        if txt:
            claims.append(txt)

    citation_text_parts: List[str] = []
    for c in citations or []:
        if isinstance(c, dict):
            title = str(c.get("title") or c.get("source_title") or "")
            snippet = str(c.get("snippet") or "")
            citation_text_parts.append(f"{title} {snippet}".strip())
        else:
            title = str(getattr(c, "title", "") or getattr(c, "source_title", "") or "")
            snippet = str(getattr(c, "snippet", "") or "")
            citation_text_parts.append(f"{title} {snippet}".strip())

    obs_text = " ".join(str(o) for o in (observations or []) if o)
    evidence_text = f"{' '.join(citation_text_parts)} {obs_text}".strip()
    evidence_tokens = _extract_meaningful_tokens(evidence_text)
    obs_tokens = _extract_meaningful_tokens(obs_text)
    has_citations = len(citations or []) > 0
    conf = (confidence_level or "").strip().lower()

    if not claims:
        return {
            "faithfulness_score": 1.0,
            "grounded_claims": 0,
            "total_claims": 0,
            "citation_grounded": has_citations,
            "ungrounded_high_confidence": False,
        }

    if not has_citations:
        obs_supported = 0
        for claim in claims:
            c_toks = _extract_meaningful_tokens(claim)
            if c_toks and obs_tokens:
                hits = sum(1 for t in c_toks if _token_matches_evidence(t, obs_tokens))
                if hits >= 2 or (hits / len(c_toks)) >= 0.25:
                    obs_supported += 1

        if conf == "insufficient_evidence":
            base = 0.85 if obs_supported > 0 else 0.75
            return {
                "faithfulness_score": base,
                "grounded_claims": obs_supported,
                "total_claims": len(claims),
                "citation_grounded": False,
                "ungrounded_high_confidence": False,
            }
        if conf in ("high", "moderate"):
            score = round(min(0.35, 0.35 * (obs_supported / len(claims))), 4) if obs_tokens else 0.0
            return {
                "faithfulness_score": score,
                "grounded_claims": obs_supported,
                "total_claims": len(claims),
                "citation_grounded": False,
                "ungrounded_high_confidence": True,
            }
        score = round(0.5 if obs_supported > 0 else 0.25, 4)
        return {
            "faithfulness_score": score,
            "grounded_claims": obs_supported,
            "total_claims": len(claims),
            "citation_grounded": False,
            "ungrounded_high_confidence": False,
        }

    claim_scores: List[float] = []
    grounded_claims = 0
    for claim in claims:
        c_tokens = _extract_meaningful_tokens(claim)
        if not c_tokens:
            claim_scores.append(1.0)
            grounded_claims += 1
            continue
        matched = sum(1 for t in c_tokens if _token_matches_evidence(t, evidence_tokens))
        overlap = matched / len(c_tokens)
        if overlap >= 0.20 or matched >= 2:
            grounded_claims += 1
        claim_scores.append(min(1.0, overlap / 0.35))

    avg_score = round(sum(claim_scores) / len(claim_scores), 4) if claim_scores else 0.0
    return {
        "faithfulness_score": avg_score,
        "grounded_claims": grounded_claims,
        "total_claims": len(claims),
        "citation_grounded": True,
        "ungrounded_high_confidence": False,
    }


def clean_incident_title(title: str, primary_asset_name: str = "") -> str:
    """Nettoie les suffixes d'hôte répétés pour produire un titre canonique lisible."""
    cleaned = str(title or "").strip()
    if primary_asset_name:
        escaped = re.escape(primary_asset_name.strip())
        cleaned = re.sub(rf"(?:\s+(?:sur|on)\s+{escaped})+\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:\s+(?:sur|on)\s+[A-Za-z0-9_.-]{3,})+\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:")
    return cleaned or str(title or "Incident sans titre").strip()


def normalize_incident_family(title: str, primary_asset_name: str = "") -> str:
    """Normalise un libellé d'incident en clé de famille canonique (hôtes/nombres/accents masqués)."""
    base = clean_incident_title(title, primary_asset_name)
    folded = _fold_text(base)
    if primary_asset_name:
        folded = folded.replace(_fold_text(primary_asset_name.strip()), "<host>")
    folded = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<ip>", folded)
    folded = re.sub(r"\b\d+(?:[.,]\d+)?%?\b", "<n>", folded)
    folded = re.sub(r"[^a-z0-9<>/._\-\s]", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded or "unknown_incident_family"


async def detect_knowledge_gaps(
    session: AsyncSession,
    entity_scope: List[str],
    min_relevance: float = 0.45,
    limit: int = 20,
) -> Dict[str, Any]:
    """Analyse les incidents, runs IA et citations pour mesurer la qualité RAG et prioriser les Knowledge Gaps."""
    inc_stmt = select(Incident)
    if "*" not in entity_scope:
        inc_stmt = inc_stmt.where(Incident.entity_id.in_(entity_scope))
    inc_stmt = inc_stmt.order_by(desc(Incident.opened_at)).limit(250)
    incidents = list((await session.execute(inc_stmt)).scalars().all())

    latest_eval_recall: Optional[float] = None
    latest_eval_mrr: Optional[float] = None
    try:
        eval_row = (
            await session.execute(select(AIEvalRun).order_by(desc(AIEvalRun.started_at)).limit(1))
        ).scalar_one_or_none()
        if eval_row is not None:
            latest_eval_recall = round(float(eval_row.rag_recall_at_k), 4)
            latest_eval_mrr = round(float(eval_row.rag_mrr), 4)
    except Exception:
        pass

    if not incidents:
        set_rag_quality_metrics(0.0, 0.0, 0)
        return {
            "metrics": {
                "total_incidents": 0,
                "total_analyzed_incidents": 0,
                "citation_coverage_rate": 0.0,
                "avg_relevance_score": 0.0,
                "avg_faithfulness_score": 0.0,
                "insufficient_evidence_rate": 0.0,
                "latest_eval_recall_at_5": latest_eval_recall,
                "latest_eval_mrr": latest_eval_mrr,
                "gaps_count": 0,
                "critical_gaps_count": 0,
            },
            "gaps": [],
        }

    inc_ids = [inc.id for inc in incidents]
    latest_run_by_inc: Dict[Any, AIAnalysisRun] = {}
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
            recs = (
                await session.execute(
                    select(AIRecommendation).where(AIRecommendation.analysis_run_id.in_(run_ids))
                )
            ).scalars().all()
            for rec in recs:
                recs_by_run.setdefault(rec.analysis_run_id, []).append(rec)
        except Exception:
            pass

    rec_ids = [rec.id for rec_list in recs_by_run.values() for rec in rec_list]
    sources_by_rec: Dict[Any, List[RecommendationSource]] = {}
    if rec_ids:
        try:
            sources = (
                await session.execute(
                    select(RecommendationSource).where(RecommendationSource.recommendation_id.in_(rec_ids))
                )
            ).scalars().all()
            for src in sources:
                sources_by_rec.setdefault(src.recommendation_id, []).append(src)
        except Exception:
            pass

    pending_prop_inc_ids: Set[Any] = set()
    pending_prop_families: Set[str] = set()
    try:
        prop_stmt = select(KnowledgeProposal).where(KnowledgeProposal.status == "pending_review")
        if "*" not in entity_scope:
            prop_stmt = prop_stmt.where(KnowledgeProposal.entity_id.in_(entity_scope))
        for prop in (await session.execute(prop_stmt)).scalars().all():
            pending_prop_inc_ids.add(prop.incident_id)
            clean_p = re.sub(r"^Proc[ée]dure\s*:\s*", "", str(prop.title or ""), flags=re.IGNORECASE)
            pending_prop_families.add(normalize_incident_family(clean_p))
    except Exception:
        pass

    families: Dict[str, Dict[str, Any]] = {}
    total_analyzed = 0
    analyzed_with_citation = 0
    analyzed_insufficient = 0
    all_relevance_scores: List[float] = []
    all_faithfulness_scores: List[float] = []

    for inc in incidents:
        fam_key = normalize_incident_family(inc.title, inc.primary_asset_name)
        bucket = families.get(fam_key)
        if bucket is None:
            meta = extract_operational_metadata(title=clean_incident_title(inc.title, inc.primary_asset_name), text=inc.title)
            bucket = {
                "family_key": fam_key,
                "sample_incident_id": str(inc.id),
                "sample_title": clean_incident_title(inc.title, inc.primary_asset_name),
                "entity_id": inc.entity_id,
                "category": meta.get("category", "general"),
                "inferred_os": meta.get("os", "all"),
                "inferred_service": meta.get("service", "general"),
                "incident_ids": set(),
                "incident_count": 0,
                "analyzed_count": 0,
                "cited_count": 0,
                "insufficient_count": 0,
                "relevance_scores": [],
                "faithfulness_scores": [],
                "hosts": set(),
                "max_severity": str(inc.severity or "AVERAGE").upper(),
            }
            families[fam_key] = bucket

        bucket["incident_ids"].add(inc.id)
        bucket["incident_count"] += 1
        if inc.primary_asset_name:
            bucket["hosts"].add(inc.primary_asset_name)
        sev_upper = str(inc.severity or "AVERAGE").upper()
        if _SEVERITY_ORDER.get(sev_upper, 0) > _SEVERITY_ORDER.get(bucket["max_severity"], 0):
            bucket["max_severity"] = sev_upper

        run = latest_run_by_inc.get(inc.id)
        if run is None:
            continue

        total_analyzed += 1
        bucket["analyzed_count"] += 1
        recs = recs_by_run.get(run.id, [])
        cit_rows: List[RecommendationSource] = []
        for rec in recs:
            cit_rows.extend(sources_by_rec.get(rec.id, []))

        cit_dicts = [
            {
                "title": s.source_title,
                "snippet": s.snippet,
                "relevance_score": float(s.relevance_score or 0.0),
            }
            for s in cit_rows
        ]
        if cit_dicts:
            analyzed_with_citation += 1
            bucket["cited_count"] += 1
            for s in cit_rows:
                val = float(s.relevance_score or 0.0)
                all_relevance_scores.append(val)
                bucket["relevance_scores"].append(val)

        if str(run.confidence_level or "").lower() == "insufficient_evidence":
            analyzed_insufficient += 1
            bucket["insufficient_count"] += 1

        rec_dicts = [{"action_text": r.action_text} for r in recs]
        faith = compute_faithfulness_score(
            hypotheses=list(run.hypotheses or []),
            recommended_actions=rec_dicts,
            citations=cit_dicts,
            observations=list(run.checks or []),
            confidence_level=str(run.confidence_level or ""),
        )["faithfulness_score"]
        all_faithfulness_scores.append(faith)
        bucket["faithfulness_scores"].append(faith)

    gaps: List[Dict[str, Any]] = []
    for fam_key, b in families.items():
        ac = b["analyzed_count"]
        cit_cov = (b["cited_count"] / ac) if ac > 0 else 0.0
        insuff_rate = (b["insufficient_count"] / ac) if ac > 0 else 1.0
        avg_rel = (sum(b["relevance_scores"]) / len(b["relevance_scores"])) if b["relevance_scores"] else 0.0
        avg_faith = (sum(b["faithfulness_scores"]) / len(b["faithfulness_scores"])) if b["faithfulness_scores"] else 0.0

        is_gap = (
            ac == 0
            or avg_rel < min_relevance
            or cit_cov < 0.5
            or insuff_rate >= 0.4
        )
        if not is_gap:
            continue

        sev_score = _SEVERITY_WEIGHT.get(b["max_severity"], 10)
        freq_score = min(30.0, float(b["incident_count"]) * 6.0)
        missing_cit_score = (1.0 - cit_cov) * 20.0
        insuff_score = insuff_rate * 15.0
        rel_deficit = max(0.0, (min_relevance - avg_rel) / max(0.01, min_relevance)) * 5.0
        priority_score = round(min(100.0, sev_score + freq_score + missing_cit_score + insuff_score + rel_deficit), 1)

        if priority_score >= 70.0:
            priority_level = "CRITICAL"
        elif priority_score >= 45.0:
            priority_level = "HIGH"
        else:
            priority_level = "MEDIUM"

        has_pending = bool(b["incident_ids"] & pending_prop_inc_ids) or (fam_key in pending_prop_families)

        gaps.append(
            {
                "family_key": fam_key,
                "sample_incident_id": b["sample_incident_id"],
                "sample_title": b["sample_title"],
                "recommended_kb_title": f"Procédure : {b['sample_title']}"[:250],
                "entity_id": b["entity_id"],
                "category": b["category"],
                "inferred_os": b["inferred_os"],
                "inferred_service": b["inferred_service"],
                "incident_count": b["incident_count"],
                "analyzed_count": ac,
                "affected_hosts": sorted(b["hosts"]),
                "max_severity": b["max_severity"],
                "avg_rag_score": round(avg_rel, 4),
                "citation_coverage_rate": round(cit_cov, 4),
                "insufficient_evidence_rate": round(insuff_rate, 4),
                "avg_faithfulness_score": round(avg_faith, 4),
                "priority_score": priority_score,
                "priority_level": priority_level,
                "has_pending_proposal": has_pending,
            }
        )

    gaps.sort(key=lambda g: (-g["priority_score"], -g["incident_count"], g["family_key"]))

    global_cit_cov = round(analyzed_with_citation / total_analyzed, 4) if total_analyzed else 0.0
    global_avg_rel = round(sum(all_relevance_scores) / len(all_relevance_scores), 4) if all_relevance_scores else 0.0
    global_avg_faith = round(sum(all_faithfulness_scores) / len(all_faithfulness_scores), 4) if all_faithfulness_scores else 0.0
    global_insuff = round(analyzed_insufficient / total_analyzed, 4) if total_analyzed else 0.0
    critical_count = sum(1 for g in gaps if g["priority_level"] == "CRITICAL")

    set_rag_quality_metrics(global_avg_faith, global_cit_cov, len(gaps))

    return {
        "metrics": {
            "total_incidents": len(incidents),
            "total_analyzed_incidents": total_analyzed,
            "citation_coverage_rate": global_cit_cov,
            "avg_relevance_score": global_avg_rel,
            "avg_faithfulness_score": global_avg_faith,
            "insufficient_evidence_rate": global_insuff,
            "latest_eval_recall_at_5": latest_eval_recall,
            "latest_eval_mrr": latest_eval_mrr,
            "gaps_count": len(gaps),
            "critical_gaps_count": critical_count,
        },
        "gaps": gaps[:limit],
    }
