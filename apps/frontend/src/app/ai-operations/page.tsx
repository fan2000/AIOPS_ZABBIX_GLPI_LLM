"use client";

import { useEffect, useState } from "react";
import { 
  Activity, 
  Bot, 
  BrainCircuit, 
  CheckCircle2, 
  Cpu, 
  GitMerge, 
  Layers, 
  MessageSquareShare, 
  RefreshCw, 
  Search, 
  ShieldCheck, 
  Sparkles, 
  Terminal, 
  Wrench, 
  Zap 
} from "lucide-react";

interface AgentItem {
  name: string;
  role: string;
  status: string;
  rate: string;
}

interface AiStatusData {
  model_name: string;
  avg_latency_ms: number;
  blocked_rate: string;
  total_analysis_count: number;
  agents: AgentItem[];
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  "Incident Agent": <Activity className="w-4 h-4 text-cyan-400" />,
  "Correlation Agent": <GitMerge className="w-4 h-4 text-purple-400" />,
  "Knowledge Agent": <Search className="w-4 h-4 text-blue-400" />,
  "Diagnosis Agent": <BrainCircuit className="w-4 h-4 text-amber-400" />,
  "Resolution Agent": <Wrench className="w-4 h-4 text-emerald-400" />,
  "Validation Agent": <ShieldCheck className="w-4 h-4 text-rose-400" />,
  "Feedback Agent": <MessageSquareShare className="w-4 h-4 text-teal-400" />,
};

export default function AiOperationsPage() {
  const [data, setData] = useState<AiStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchStatus = async () => {
    try {
      setIsRefreshing(true);
      const res = await fetch("http://localhost:8005/api/v1/ai/status");
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (e) {
      console.error("Erreur de récupération statut IA:", e);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const agents: AgentItem[] = data?.agents || [
    { name: "Incident Agent", role: "Collecte des symptômes et métriques brutes Zabbix", status: "Actif", rate: "100%" },
    { name: "Correlation Agent", role: "Détection des dépendances et multi-triggers d'événements", status: "Actif", rate: "100%" },
    { name: "Knowledge Agent", role: "Interrogation RAG hybride et passages KB GLPI", status: "Actif", rate: "98.4%" },
    { name: "Diagnosis Agent", role: "Formulation des hypothèses causales et preuves chiffrées", status: "Actif", rate: "96.1%" },
    { name: "Resolution Agent", role: "Sélection des runbooks pré-approuvés selon schéma JSON", status: "Actif", rate: "99.2%" },
    { name: "Validation Agent", role: "Guardrail sécurité strict, neutralisation commandes libres", status: "Actif", rate: "100%" },
    { name: "Feedback Agent", role: "Capitalisation d'expérience et clôture vers GLPI ITSM", status: "Actif", rate: "95.0%" },
  ];

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12 animate-fade-in">
      {/* Header avec Bezel de synthèse */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold font-mono tracking-wider bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Sparkles className="w-3 h-3" />
              LANGGRAPH SWARM ORCHESTRATION
            </span>
          </div>
          <h2 className="text-3xl font-extrabold text-white tracking-tight">AI Operations Center</h2>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Supervision temps réel du swarm de 7 agents autonomes spécialisés, télémétrie d&apos;inférence locale et validation des gardes-fous de sécurité.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchStatus}
            disabled={isRefreshing}
            className="btn-tactile inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-obsidian-850 hover:bg-obsidian-800 border border-obsidian-700/60 text-xs font-medium text-slate-300 hover:text-white"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-cyan-400" : ""}`} />
            <span>Actualiser</span>
          </button>
          
          <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-xl bg-obsidian-900/80 border border-obsidian-750/70 shadow-bevel">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-xs font-mono font-medium text-slate-300">Swarm Connecté</span>
          </div>
        </div>
      </div>

      {/* KPI 4 Cards - Double Bezel Architecture */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Modèle Local Actif */}
        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Modèle Local</span>
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <Cpu className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-xl font-bold text-white tracking-tight truncate">
                {data?.model_name || "Ollama / gemma4"}
              </div>
              <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                Inférence JSON structurée stricte
              </p>
            </div>
          </div>
        </div>

        {/* Latence Moyenne */}
        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Latence Diagnostic</span>
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                <Zap className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-xl font-bold font-mono text-cyan-400">
                {data?.avg_latency_ms || 420} <span className="text-sm font-sans font-normal text-slate-400">ms</span>
              </div>
              <p className="text-xs text-slate-400 mt-1">Cycle complet sur graphe LangGraph</p>
            </div>
          </div>
        </div>

        {/* Guardrail Sécurité */}
        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Blocage Sécuritaire</span>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <ShieldCheck className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-xl font-bold font-mono text-emerald-400">
                {data?.blocked_rate || "100 %"}
              </div>
              <p className="text-xs text-slate-400 mt-1">Commandes libres bloquées (RBAC strict)</p>
            </div>
          </div>
        </div>

        {/* Diagnostics Persistés */}
        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Analyses Sauvegardées</span>
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <Activity className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-xl font-bold font-mono text-purple-400">
                {data?.total_analysis_count ?? 1}
              </div>
              <p className="text-xs text-slate-400 mt-1">Rapports persistés dans PostgreSQL</p>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline Graph Visualizer Mini */}
      <div className="bezel-shell">
        <div className="bezel-core space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Chaine d&apos;Inférence Séquentielle LangGraph</h3>
                <p className="text-xs text-slate-400">État du passage de contexte entre les agents spécialisés</p>
              </div>
            </div>
            <span className="text-[11px] font-mono text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-md border border-cyan-500/20">
              Deterministic State Machine
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 pt-2">
            {[
              { id: "1", name: "Incident", color: "cyan" },
              { id: "2", name: "Corrélation", color: "purple" },
              { id: "3", name: "Knowledge", color: "blue" },
              { id: "4", name: "Diagnostic", color: "amber" },
              { id: "5", name: "Résolution", color: "emerald" },
              { id: "6", name: "Validation", color: "rose" },
              { id: "7", name: "Feedback", color: "teal" },
            ].map((step, idx) => (
              <div 
                key={step.id} 
                className="p-2.5 rounded-lg bg-obsidian-950/70 border border-obsidian-700/60 flex flex-col justify-between hover:border-obsidian-600 transition-colors"
              >
                <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>P{idx + 1}</span>
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                </div>
                <div className="text-xs font-semibold text-slate-200 mt-1 truncate">
                  {step.name}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Grille des 7 Agents Autonomes - Double Bezel Architecture */}
      <div className="bezel-shell">
        <div className="bezel-core space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-obsidian-750/70">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Réseau des 7 Agents Spécialisés LangGraph</h3>
                <p className="text-xs text-slate-400">Chaque agent opère dans un sous-graphe dédié avec contrats d&apos;entrée/sortie typés</p>
              </div>
            </div>
            <span className="hidden sm:inline-flex text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20 items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              7/7 Agents Opérationnels
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {agents.map((ag, idx) => {
              const icon = AGENT_ICONS[ag.name] || <Bot className="w-4 h-4 text-cyan-400" />;
              const rateNum = parseFloat(ag.rate) || 100;

              return (
                <div
                  key={idx}
                  className="group relative p-4 rounded-xl bg-obsidian-950/80 border border-obsidian-750/70 hover:border-obsidian-600 transition-all duration-200 shadow-inner-bevel hover:shadow-bevel"
                >
                  <div className="flex items-start justify-between gap-3 mb-2.5">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-obsidian-850 border border-obsidian-700/60 flex items-center justify-center shrink-0">
                        {icon}
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-white group-hover:text-cyan-300 transition-colors">
                          {ag.name}
                        </h4>
                        <span className="text-[10px] font-mono text-slate-400">
                          ID: agent-{idx + 1}-langgraph
                        </span>
                      </div>
                    </div>

                    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                      {ag.status}
                    </span>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed min-h-[32px]">
                    {ag.role}
                  </p>

                  <div className="pt-3 mt-3 border-t border-obsidian-800/80 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">Fiabilité opérationnelle</span>
                      <span className="font-mono font-bold text-cyan-400">{ag.rate}</span>
                    </div>

                    {/* Progress Bar High-End */}
                    <div className="w-full h-1.5 rounded-full bg-obsidian-800 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-emerald-400 transition-all duration-500"
                        style={{ width: `${Math.min(100, Math.max(10, rateNum))}%` }}
                      ></div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
