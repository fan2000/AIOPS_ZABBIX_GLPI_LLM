"use client";

import { Fragment, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

interface EvalCheckItem {
  name: string;
  passed: boolean;
  detail: string;
}

interface EvalCaseItem {
  id: string;
  case_id: string;
  case_name: string;
  category: string;
  passed: boolean;
  score: number;
  trials_passed: number;
  trials_total: number;
  latency_ms: number;
  tokens_used: number;
  rag_recall_at_k?: number | null;
  rag_mrr?: number | null;
  checks: EvalCheckItem[];
  actual_summary?: Record<string, any>;
  error_message?: string | null;
}

interface EvalRunItem {
  id: string;
  dataset_version: string;
  execution_mode: string;
  model_name: string;
  triggered_by: string;
  k_trials: number;
  total_cases: number;
  passed_cases: number;
  overall_score: number;
  pass_at_k: number;
  pass_pow_k: number;
  diagnosis_accuracy: number;
  rag_recall_at_k: number;
  rag_mrr: number;
  hitl_safety_rate: number;
  security_guardrail_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  total_tokens: number;
  estimated_cost_usd: number;
  gate_passed: boolean;
  regression_detected: boolean;
  delta_vs_baseline?: number | null;
  gate_reasons: string[];
  started_at?: string | null;
  finished_at?: string | null;
  case_results?: EvalCaseItem[];
}

interface EvalSummaryResponse {
  dataset_version: string;
  latest_run: EvalRunItem | null;
  baseline_score: number | null;
  total_runs: number;
  history: EvalRunItem[];
}

const CATEGORY_STYLES: Record<string, string> = {
  diagnosis: "bg-cyan-500/10 text-cyan-300 border-cyan-500/25",
  rag: "bg-blue-500/10 text-blue-300 border-blue-500/25",
  hitl_safety: "bg-amber-500/10 text-amber-300 border-amber-500/25",
  security_guardrail: "bg-rose-500/10 text-rose-300 border-rose-500/25",
};

function pct(val: number | undefined | null): string {
  if (val === undefined || val === null || Number.isNaN(val)) return "0%";
  return `${Math.round(val * 100)}%`;
}

export function EvalHarnessPanel() {
  const [summary, setSummary] = useState<EvalSummaryResponse | null>(null);
  const [activeRun, setActiveRun] = useState<EvalRunItem | null>(null);
  const [mode, setMode] = useState<"fast_deterministic" | "hybrid_llm">("fast_deterministic");
  const [kTrials, setKTrials] = useState<number>(1);
  const [running, setRunning] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [expandedCase, setExpandedCase] = useState<string | null>(null);

  const loadRunDetail = async (runId: string) => {
    setLoadingDetail(true);
    try {
      const res = await apiFetch(`/api/v1/evals/runs/${runId}`);
      if (res.ok) {
        setActiveRun(await res.json());
      }
    } catch (e) {
      console.error("Erreur chargement détail eval run:", e);
    } finally {
      setLoadingDetail(false);
    }
  };

  const fetchSummary = async (selectLatest: boolean = true) => {
    try {
      const res = await apiFetch("/api/v1/evals/summary");
      if (res.ok) {
        const data: EvalSummaryResponse = await res.json();
        setSummary(data);
        if (selectLatest && data.latest_run?.id) {
          await loadRunDetail(data.latest_run.id);
        }
      }
    } catch (e) {
      console.error("Erreur chargement summary evals:", e);
    }
  };

  useEffect(() => {
    fetchSummary(true);
  }, []);

  const handleRunEval = async () => {
    setRunning(true);
    setErrorMsg(null);
    try {
      const res = await apiFetch("/api/v1/evals/run", {
        method: "POST",
        body: JSON.stringify({
          execution_mode: mode,
          k_trials: kTrials,
        }),
      });
      if (res.ok) {
        const runData: EvalRunItem = await res.json();
        setActiveRun(runData);
        await fetchSummary(false);
      } else {
        const err = await res.json().catch(() => ({}));
        if (res.status === 401 || res.status === 403) {
          setErrorMsg(err.detail || `Accès refusé (HTTP ${res.status}) — authentification opérateur/admin requise.`);
        } else if (res.status === 429) {
          setErrorMsg(err.detail || "Limite de débit atteinte (HTTP 429). Patientez quelques instants.");
        } else {
          setErrorMsg(err.detail || `Erreur d'exécution Eval Harness (HTTP ${res.status}).`);
        }
      }
    } catch {
      setErrorMsg("Erreur réseau lors du déclenchement de l'évaluation continue.");
    } finally {
      setRunning(false);
    }
  };

  const cases = activeRun?.case_results || [];
  const safetyCombined = activeRun
    ? (activeRun.security_guardrail_rate + activeRun.hitl_safety_rate) / 2
    : 0;

  return (
    <div className="bezel-shell">
      <div className="bezel-core p-6 space-y-6">
        {/* En-tête Release Gate & Contrôles */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-obsidian-750/70">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shrink-0">
              <FlaskConical className="w-5 h-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-bold text-white">
                  Évaluation Continue Automatisée (Eval Harness)
                </h3>
                <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-obsidian-950 border border-white/[0.08] text-cyan-300">
                  Dataset v{summary?.dataset_version || activeRun?.dataset_version || "1.0.0"}
                </span>
                {!activeRun ? (
                  <span className="font-mono text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-slate-500/15 text-slate-300 border border-slate-500/30">
                    AUCUN RUN
                  </span>
                ) : activeRun.gate_passed && !activeRun.regression_detected ? (
                  <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    <ShieldCheck className="w-3 h-3" />
                    GATE PASS
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-rose-500/15 text-rose-300 border border-rose-500/30">
                    <ShieldAlert className="w-3 h-3" />
                    REGRESSION / FAIL
                  </span>
                )}
                {activeRun?.delta_vs_baseline !== null && activeRun?.delta_vs_baseline !== undefined && (
                  <span
                    className={`font-mono text-[10px] px-2 py-0.5 rounded border ${
                      activeRun.delta_vs_baseline >= 0
                        ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                        : "bg-rose-500/10 text-rose-300 border-rose-500/25"
                    }`}
                  >
                    delta vs baseline: {activeRun.delta_vs_baseline >= 0 ? "+" : ""}
                    {(activeRun.delta_vs_baseline * 100).toFixed(1)}%
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Benchmark pass@k / pass^k, rappel RAG RRF (Recall@4 &amp; MRR), sûreté HITL et guardrails OWASP LLM01
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "fast_deterministic" | "hybrid_llm")}
              className="bg-obsidian-950 border border-white/[0.12] rounded-xl px-3 py-2 text-xs text-slate-200 font-mono outline-none focus:border-cyan-500/50"
            >
              <option value="fast_deterministic">fast_deterministic</option>
              <option value="hybrid_llm">hybrid_llm</option>
            </select>

            <select
              value={kTrials}
              onChange={(e) => setKTrials(Number(e.target.value))}
              className="bg-obsidian-950 border border-white/[0.12] rounded-xl px-3 py-2 text-xs text-slate-200 font-mono outline-none focus:border-cyan-500/50"
            >
              <option value={1}>k=1 essai</option>
              <option value={3}>k=3 essais</option>
            </select>

            <button
              onClick={handleRunEval}
              disabled={running}
              className="btn-tactile inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 disabled:opacity-50"
            >
              {running ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              <span>{running ? "Évaluation..." : "Lancer l'Évaluation"}</span>
            </button>
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-200 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* 5 Tuiles KPI */}
        {activeRun ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <div className="p-4 rounded-xl bg-obsidian-950/90 border border-obsidian-750/70">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Score Global</div>
              <div className="text-2xl font-bold font-mono text-cyan-400 mt-1">{pct(activeRun.overall_score)}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                {activeRun.passed_cases}/{activeRun.total_cases} scénarios validés
              </div>
            </div>

            <div className="p-4 rounded-xl bg-obsidian-950/90 border border-obsidian-750/70">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">pass@k / pass^k</div>
              <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">
                {pct(activeRun.pass_at_k)}{" "}
                <span className="text-sm text-slate-400">/ {pct(activeRun.pass_pow_k)}</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">k={activeRun.k_trials} • Moy {activeRun.avg_latency_ms}ms</div>
            </div>

            <div className="p-4 rounded-xl bg-obsidian-950/90 border border-obsidian-750/70">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Diagnostic Acc.</div>
              <div className="text-2xl font-bold font-mono text-amber-300 mt-1">
                {pct(activeRun.diagnosis_accuracy)}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">P95: {activeRun.p95_latency_ms} ms</div>
            </div>

            <div className="p-4 rounded-xl bg-obsidian-950/90 border border-obsidian-750/70">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">RAG Recall@4 / MRR</div>
              <div className="text-2xl font-bold font-mono text-blue-400 mt-1">
                {pct(activeRun.rag_recall_at_k)}{" "}
                <span className="text-sm text-slate-300">/ {activeRun.rag_mrr.toFixed(2)}</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">Recherche hybride RRF</div>
            </div>

            <div className="p-4 rounded-xl bg-obsidian-950/90 border border-obsidian-750/70">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Sécurité &amp; HITL</div>
              <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">{pct(safetyCombined)}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                OWASP: {pct(activeRun.security_guardrail_rate)} • HITL: {pct(activeRun.hitl_safety_rate)}
              </div>
            </div>
          </div>
        ) : (
          <div className="py-8 text-center rounded-xl bg-obsidian-950/70 border border-white/[0.06] text-xs text-slate-400">
            Lancez une première campagne d&apos;évaluation pour mesurer les métriques pass@k, RAG Recall@4, HITL et Guardrails.
          </div>
        )}

        {/* Alertes Release Gate si présentes */}
        {activeRun && activeRun.gate_reasons && activeRun.gate_reasons.length > 0 && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 space-y-1.5">
            <div className="text-xs font-bold text-rose-300 flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4" />
              <span>Alertes Release Gate / Régression</span>
            </div>
            <ul className="list-disc list-inside text-xs text-rose-200 space-y-0.5">
              {activeRun.gate_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Historique récent cliquable */}
        {summary && summary.history && summary.history.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider mr-1">
              Historique ({summary.total_runs}) :
            </span>
            {summary.history.slice(0, 6).map((h) => {
              const selected = activeRun?.id === h.id;
              return (
                <button
                  key={h.id}
                  onClick={() => loadRunDetail(h.id)}
                  className={`px-2.5 py-1 rounded-lg font-mono text-[11px] border transition-colors ${
                    selected
                      ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-200"
                      : "bg-obsidian-950/80 border-white/[0.08] text-slate-300 hover:border-white/[0.2]"
                  }`}
                >
                  {h.gate_passed ? "PASS" : "FAIL"} • {pct(h.overall_score)} (k={h.k_trials}, {h.execution_mode === "hybrid_llm" ? "LLM" : "Fast"})
                </button>
              );
            })}
          </div>
        )}

        {/* Tableau détaillé des scénarios */}
        {cases.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-obsidian-750/70 bg-obsidian-950/70">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06] text-xs text-slate-300">
              <span className="font-semibold flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-cyan-400" />
                <span>Détail des {cases.length} Scénarios Golden</span>
              </span>
              {loadingDetail && <span className="font-mono text-[11px] text-cyan-400">Chargement...</span>}
            </div>
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-wider text-slate-400 font-mono">
                  <th className="py-2.5 px-3">Scénario</th>
                  <th className="py-2.5 px-3">Catégorie</th>
                  <th className="py-2.5 px-3">Statut</th>
                  <th className="py-2.5 px-3">Score</th>
                  <th className="py-2.5 px-3">Essais</th>
                  <th className="py-2.5 px-3 text-right">Latence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {cases.map((c) => {
                  const isOpen = expandedCase === c.case_id;
                  const catBadge = CATEGORY_STYLES[c.category] || "bg-white/[0.05] text-slate-300 border-white/[0.1]";
                  return (
                    <Fragment key={c.case_id}>
                      <tr
                        onClick={() => setExpandedCase(isOpen ? null : c.case_id)}
                        className="hover:bg-white/[0.03] cursor-pointer transition-colors"
                      >
                        <td className="py-2.5 px-3">
                          <div className="flex items-center gap-2">
                            {isOpen ? (
                              <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            )}
                            <div>
                              <div className="font-semibold text-white">{c.case_name}</div>
                              <div className="font-mono text-[10px] text-slate-400">{c.case_id}</div>
                            </div>
                          </div>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`font-mono text-[10px] px-2 py-0.5 rounded border ${catBadge}`}>
                            {c.category}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          {c.passed ? (
                            <span className="inline-flex items-center gap-1 text-emerald-400 font-mono font-bold text-[11px]">
                              <CheckCircle2 className="w-3.5 h-3.5" /> PASS
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-rose-400 font-mono font-bold text-[11px]">
                              <XCircle className="w-3.5 h-3.5" /> FAIL
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono font-bold text-cyan-300">{pct(c.score)}</td>
                        <td className="py-2.5 px-3 font-mono text-slate-300">
                          {c.trials_passed}/{c.trials_total}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400 text-right">{c.latency_ms} ms</td>
                      </tr>
                      {isOpen && (
                        <tr className="bg-black/40">
                          <td colSpan={6} className="p-3.5 space-y-2">
                            <div className="text-[10px] font-mono uppercase text-slate-400 flex items-center gap-1.5">
                              <Sparkles className="w-3 h-3 text-cyan-400" />
                              <span>Vérifications déterministes ({c.checks.length})</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {c.checks.map((chk, idx) => (
                                <div
                                  key={idx}
                                  className="p-2 rounded-lg bg-obsidian-950 border border-white/[0.06] flex items-start gap-2 text-[11px]"
                                >
                                  {chk.passed ? (
                                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                                  ) : (
                                    <XCircle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
                                  )}
                                  <div className="min-w-0">
                                    <div className="font-mono font-semibold text-slate-200">{chk.name}</div>
                                    <div className="text-slate-400 break-words">{chk.detail}</div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
