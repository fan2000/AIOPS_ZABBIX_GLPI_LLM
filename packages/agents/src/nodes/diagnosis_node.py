"""Nœud Agent Diagnostic : Formulation des hypothèses et calibration de la confiance."""

from typing import Any, Dict, List
from packages.agents.src.llm_client import llm_client
from packages.agents.src.state import IncidentAgentState


async def diagnosis_agent_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Établit les hypothèses de cause racine et les contrôles recommandés."""
    observations = state.get("observations", [])
    citations = state.get("rag_citations", [])
    primary_event = state.get("primary_event", {})
    problem = primary_event.get("problem", "")
    host_name = state.get("host_name", "Serveur")

    # Si citations disponibles, on tente une inférence LLM structurée
    system_prompt = (
        "Tu es un expert AIOps. Analyse l'incident à partir des observations et sources fournies. "
        "Retourne STRICTEMENT un JSON valide avec : 'hypotheses' (liste d'objets avec description, evidence, status), "
        "'checks' (liste de vérifications), 'confidence_level' (insufficient_evidence, low, moderate, high), "
        "'confidence_explanation' (texte)."
    )
    user_prompt = f"Hôte: {host_name}\nObservations:\n" + "\n".join(f"- {o}" for o in observations)
    if citations:
        user_prompt += "\nSources documentaires:\n" + "\n".join(
            f"- [{c.get('article_id')}] {c.get('title')}: {c.get('snippet')}" for c in citations
        )
    else:
        user_prompt += "\nAucune source documentaire spécifique trouvée."

    llm_output = await llm_client.generate_json(system_prompt, user_prompt)

    if llm_output and "hypotheses" in llm_output:
        return {
            "hypotheses": llm_output.get("hypotheses", []),
            "missing_info_checks": llm_output.get("checks", []),
            "confidence_detail": {
                "level": llm_output.get("confidence_level", "moderate"),
                "explanation": llm_output.get("confidence_explanation", "Diagnostic basé sur l'analyse LLM."),
            },
        }

    # Mode déterministe par défaut (sans LLM ou en cas de fallback)
    hypotheses = []
    checks = []
    conf_level = "insufficient_evidence"
    explanation = "Diagnostic initial basé sur les métriques et déclencheurs de supervision."

    if "cpu" in problem.lower():
        hypotheses.append({
            "description": "Processus consommateur ou boucle applicative saturant le CPU",
            "evidence": [obs for obs in observations if "cpu" in obs.lower() or "valeur" in obs.lower()],
            "status": "probable" if citations else "unconfirmed",
        })
        checks.extend(["Lister les 5 processus les plus consommateurs de CPU", "Examiner les journaux récents"])
        if citations:
            conf_level = "moderate"
            explanation = "Procédure de diagnostic CPU trouvée dans la base de connaissances."

    elif "disk" in problem.lower() or "espace" in problem.lower() or "fs" in problem.lower():
        hypotheses.append({
            "description": "Saturation de la partition par des journaux volumineux ou fichiers temporaires",
            "evidence": observations,
            "status": "probable",
        })
        checks.extend(["Vérifier l'arborescence des répertoires les plus volumineux", "Purger les fichiers logs archivés"])
        conf_level = "moderate" if citations else "low"
        explanation = "Alerte volumétrique standard."

    elif "service" in problem.lower() or "down" in problem.lower():
        hypotheses.append({
            "description": "Arrêt inopiné du service système ou crash applicatif",
            "evidence": observations,
            "status": "confirmed",
        })
        checks.extend(["Consulter le journal d'événements du service", "Vérifier les dépendances réseau"])
        conf_level = "high"
        explanation = "Arrêt de service vérifié par la sonde de supervision."
    else:
        hypotheses.append({
            "description": f"Anomalie détectée par le déclencheur : {problem}",
            "evidence": observations,
            "status": "unconfirmed",
        })
        checks.append("Inspecter l'état global de l'équipement")

    return {
        "hypotheses": hypotheses,
        "missing_info_checks": checks,
        "confidence_detail": {
            "level": conf_level,
            "explanation": explanation,
        },
    }
