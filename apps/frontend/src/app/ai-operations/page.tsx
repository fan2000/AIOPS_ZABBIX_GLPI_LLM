"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  Bot,
  BrainCircuit,
  Coins,
  Cpu,
  Database,
  GitMerge,
  Layers,
  MessageSquareShare,
  PauseCircle,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Wrench,
  Zap,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { EvalHarnessPanel } from "@/components/EvalHarnessPanel";

interface AgentItem {
  name: string;
  role: string;
  status: string;
  rate: string;
  avg_duration_ms?: number;
  telemetry_runs?: number;
  last_mode?: string | null;
}

interface LlmHealth {
  online: boolean;
  provider: string;
  model: string;
  circuit_state: string;
  available_models?: string[];
}

interface HitlStatusData {
  checkpointer: string;
  persistent: boolean;
  pending_approvals: number;
  approved_total: number;
  rejected_total: number;
}

interface AiStatusData {
  telemetry_source?: string;
  model_name: string;
  llm_health?: LlmHealth;
  avg_latency_ms: number;
  p95_latency_ms?: number;
  blocked_rate: string;
  blocked_actions_total?: number;
  total_analysis_count: number;
  total_prompt_tokens?: number;
  total_completion_tokens?: number;
  total_estimated_cost_usd?: number;
  execution_modes?: Record<string, number>;
  hitl_status?: HitlStatusData;
  agents: AgentItem[];
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  "Incident Agent": <Activity className="w-4 h-4 text-cyan-400" />,
  "Correlation Agent": <GitMerge className="w-4 h-4 text-purple-400" />,
  "Knowledge Agent": <Search className="w-4 h-4 text-blue-400" />,
  "Diagnosis Agent": <BrainCircuit className="w-4 h-4 text-amber-400" />,
  "Investigation Agent": <Search className="w-4 h-4 text-sky-400" />,
  "Resolution Agent": <Wrench className="w-4 h-4 text-emerald-400" />,
  "Validation Agent": <ShieldCheck className="w-4 h-4 text-rose-400" />,
  "Human Approval Gate": <ShieldAlert className="w-4 h-4 text-amber-400" />,
  "Feedback Agent": <MessageSquareShare className="w-4 h-4 text-teal-400" />,
};

export default function AiOperationsPage() {
  const [data, setData] = useState<AiStatusData | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchStatus = async () => {
    try {
      setIsRefreshing(true);
      const res = await apiFetch("/api/v1/ai/status");
      if (res.ok) {
        setData(await res.json());
      }
    } catch (e) {
      console.error("Erreur de récupération statut IA:", e);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const agents = data?.agents || [];
  const llmHealth = data?.llm_health;
  const totalTokens = (data?.total_prompt_tokens || 0) + (data?.total_completion_tokens || 0);

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold font-mono tracking-wider bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Sparkles className="w-3 h-3" />
              LANGGRAPH SWARM ORCHESTRATION — P0 TELEMETRY
            </span>
          </div>
          <h2 className="text-3xl font-extrabold text-white tracking-tight">AI Operations Center</h2>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Télémétrie SQL temps réel des 7 agents LangGraph, routage LLM hybride avec circuit-breaker, guardrails OWASP et suivi FinOps.
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
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  llmHealth?.online ? "bg-emerald-400" : "bg-amber-400"
                }`}
              ></span>
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  llmHealth?.online ? "bg-emerald-500" : "bg-amber-500"
                }`}
              ></span>
            </span>
            <span className="text-xs font-mono font-medium text-slate-300">
              {llmHealth?.online
                ? "LLM Online"
                : `Fallback Déterministe (CB: ${llmHealth?.circuit_state || "closed"})`}
            </span>
          </div>
        </div>
      </div>

      {/* KPI Cards réelles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Moteur & Modèle</span>
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <Cpu className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-lg font-bold text-white tracking-tight truncate">
                {data?.model_name || "Chargement..."}
              </div>
              <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${llmHealth?.online ? "bg-emerald-400" : "bg-amber-400"}`}></span>
                {llmHealth?.online ? "Inférence structurée active" : "Repli déterministe opérationnel"}
              </p>
            </div>
          </div>
        </div>

        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Latence Réelle (Moy / P95)</span>
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                <Zap className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-xl font-bold font-mono text-cyan-400">
                {data?.avg_latency_ms ?? 0} <span className="text-xs font-normal text-slate-400">ms</span>
                <span className="text-slate-500 mx-1.5">/</span>
                <span className="text-amber-300 text-base">{data?.p95_latency_ms ?? 0} ms</span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                {data?.total_analysis_count ?? 0} diagnostics persistés en base
              </p>
            </div>
          </div>
        </div>

        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Guardrails OWASP & Runbooks</span>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <ShieldCheck className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-xl font-bold font-mono text-emerald-400">
                {data?.blocked_rate || "N/A"}
              </div>
              <p className="text-xs text-slate-400 mt-1">
                {data?.blocked_actions_total ?? 0} action(s) non autorisée(s) neutralisée(s)
              </p>
            </div>
          </div>
        </div>

        <div className="bezel-shell">
          <div className="bezel-core h-full flex flex-col justify-between p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">FinOps & Tokens</span>
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <Coins className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-xl font-bold font-mono text-purple-400">
                {totalTokens.toLocaleString()} <span className="text-xs font-normal text-slate-400">tok</span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Coût estimé : ${(data?.total_estimated_cost_usd ?? 0).toFixed(4)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* État Checkpointer PostgreSQL & Approbations HITL */}
      {data?.hitl_status && (
        <div className="bezel-shell">
          <div className="bezel-core p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center border ${
                  data.hitl_status.persistent
                    ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                    : "bg-amber-500/15 border-amber-500/30 text-amber-300"
                }`}
              >
                <Database className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-white flex items-center gap-2">
                  <span>Human-in-the-Loop LangGraph Persistant</span>
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-obsidian-950 border border-white/[0.08] text-cyan-300">
                    checkpointer: {data.hitl_status.checkpointer}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Décisions tracées : <strong className="text-emerald-300">{data.hitl_status.approved_total}</strong> approuvée(s) •{" "}
                  <strong className="text-rose-300">{data.hitl_status.rejected_total}</strong> rejetée(s)
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-mono font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/25">
                <PauseCircle className="w-3.5 h-3.5 text-amber-400" />
                <span>{data.hitl_status.pending_approvals} en pause HITL</span>
              </span>
              <Link
                href="/automation"
                className="btn-tactile px-3 py-1.5 rounded-xl text-xs font-semibold bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300"
              >
                File HITL &amp; Runbooks →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Répartition des modes d'exécution */}
      {data?.execution_modes && Object.keys(data.execution_modes).length > 0 && (
        <div className="bezel-shell">
          <div className="bezel-core p-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-slate-300 font-semibold">
              <Layers className="w-4 h-4 text-cyan-400" />
              <span>Modes d&apos;exécution observés :</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.execution_modes).map(([mode, count]) => (
                <span
                  key={mode}
                  className="px-2.5 py-1 rounded-lg bg-obsidian-950/90 border border-white/[0.08] font-mono text-[11px] text-cyan-300"
                >
                  {mode}: <strong className="text-white">{count}</strong>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Grille des 9 Agents avec métriques réelles */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-obsidian-750/70">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Télémétrie Réelle des 9 Agents LangGraph</h3>
                <p className="text-xs text-slate-400">Statistiques agrégées depuis `ai_analysis_runs.agent_telemetry`</p>
              </div>
            </div>
            <span className="hidden sm:inline-flex text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20 items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              {agents.length}/9 Agents Trackés
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {agents.map((ag, idx) => {
              const icon = AGENT_ICONS[ag.name] || <Bot className="w-4 h-4 text-cyan-400" />;
              const hasTelemetry = (ag.telemetry_runs || 0) > 0;
              const rateNum = parseFloat(ag.rate);
              const barPct = Number.isFinite(rateNum) ? Math.min(100, Math.max(5, rateNum)) : 0;

              return (
                <div
                  key={idx}
                  className="group relative p-4 rounded-xl bg-obsidian-950/80 border border-obsidian-750/70 hover:border-obsidian-600 transition-all duration-200"
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
                          {ag.telemetry_runs ?? 0} exéc. tracée(s) • Moy: {ag.avg_duration_ms ?? 0} ms
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
                      <span className="text-slate-400">
                        {hasTelemetry ? "Fiabilité mesurée" : "Aucune exécution tracée post-P0"}
                      </span>
                      <span className="font-mono font-bold text-cyan-400">{ag.rate}</span>
                    </div>

                    <div className="w-full h-1.5 rounded-full bg-obsidian-800 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-emerald-400 transition-all duration-500"
                        style={{ width: `${barPct}%` }}
                      ></div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Évaluation Continue Automatisée (Eval Harness P2) */}
      <EvalHarnessPanel />
    </div>
  );
}
