"use client";

import { Activity, Bot, CheckCircle2, Cpu, ShieldCheck, Zap } from "lucide-react";

const AGENTS = [
  { name: "Incident Agent", role: "Collecte des symptômes et métriques brutes", status: "Actif", rate: "100%" },
  { name: "Correlation Agent", role: "Détection des dépendances et multi-triggers", status: "Actif", rate: "100%" },
  { name: "Knowledge Agent", role: "Interrogation RAG hybride et passages KB", status: "Actif", rate: "98.4%" },
  { name: "Diagnosis Agent", role: "Formulation des hypothèses et preuves", status: "Actif", rate: "96.1%" },
  { name: "Resolution Agent", role: "Sélection des runbooks catalogue et schéma", status: "Actif", rate: "99.2%" },
  { name: "Validation Agent", role: "Guardrail sécurité, blocage commandes libres", status: "Actif", rate: "100%" },
  { name: "Feedback Agent", role: "Capitalisation d'expérience vers KB GLPI", status: "Actif", rate: "95.0%" },
];

export default function AiOperationsPage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-white">AI Operations & LangGraph Swarm</h2>
        <p className="text-sm text-slate-400">
          Supervision des 7 agents autonomes, métriques des modèles et garde-fous de sécurité
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-navy-800 border border-navy-700">
          <span className="text-xs text-slate-400">Modèle Local Actif</span>
          <div className="mt-2 text-xl font-bold text-white flex items-center gap-2">
            <Cpu className="w-5 h-5 text-cyan-400" />
            <span>Ollama / Gemma 4</span>
          </div>
          <p className="text-xs text-slate-400 mt-1">Inférence JSON structurée</p>
        </div>

        <div className="p-5 rounded-xl bg-navy-800 border border-navy-700">
          <span className="text-xs text-slate-400">Latence Moyenne Diagnostic</span>
          <div className="mt-2 text-xl font-bold text-cyan-400">420 ms</div>
          <p className="text-xs text-slate-400 mt-1">Sur graphe complet LangGraph</p>
        </div>

        <div className="p-5 rounded-xl bg-navy-800 border border-navy-700">
          <span className="text-xs text-slate-400">Taux de Blocage Non-Autorisé</span>
          <div className="mt-2 text-xl font-bold text-emerald-400">100 %</div>
          <p className="text-xs text-slate-400 mt-1">Zéro commande arbitraire exécutée</p>
        </div>
      </div>

      <div className="p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-4">
        <h3 className="text-base font-bold text-white flex items-center gap-2">
          <Bot className="w-5 h-5 text-cyan-400" />
          Réseau des 7 Agents Spécialisés LangGraph
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {AGENTS.map((ag, idx) => (
            <div key={idx} className="p-4 rounded-xl bg-navy-900 border border-navy-700/60 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-white">{ag.name}</span>
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> {ag.status}
                </span>
              </div>
              <p className="text-xs text-slate-300">{ag.role}</p>
              <div className="pt-2 border-t border-navy-700/60 flex items-center justify-between text-xs text-slate-400">
                <span>Fiabilité opérationnelle</span>
                <strong className="text-cyan-400">{ag.rate}</strong>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
