"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Code2,
  Cpu,
  Lock,
  PauseCircle,
  Play,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Timer,
  UserCheck,
  XCircle,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

interface RunbookItem {
  id: string;
  name: string;
  description: string;
  runner_type: string;
  target_os: string;
  timeout_seconds: number;
  required_role: string;
  parameter_schema: any;
}

interface PendingApprovalItem {
  id: string;
  incident_id: string;
  incident_number?: string;
  incident_title?: string;
  primary_asset_name?: string;
  entity_id?: string;
  runbook_identifier: string;
  parameters: Record<string, any>;
  status: string;
  thread_id?: string | null;
  checkpoint_id?: string | null;
  risk_level?: string;
  action_summary?: string;
  requested_at?: string | null;
}

export default function AutomationPage() {
  const [runbooks, setRunbooks] = useState<RunbookItem[]>([]);
  const [approvals, setApprovals] = useState<PendingApprovalItem[]>([]);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [decisionMessage, setDecisionMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadAutomationData = async () => {
    try {
      const [rbRes, appRes] = await Promise.all([
        apiFetch("/api/v1/actions/runbooks"),
        apiFetch("/api/v1/actions/approvals?status=pending_approval"),
      ]);
      if (rbRes.ok) {
        setRunbooks(await rbRes.json());
      }
      if (appRes.ok) {
        setApprovals(await appRes.json());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAutomationData();
    const interval = setInterval(loadAutomationData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDecision = async (approvalId: string, approved: boolean) => {
    setDecidingId(approvalId);
    setDecisionMessage(null);
    try {
      const res = await apiFetch(`/api/v1/actions/approvals/${approvalId}/decide`, {
        method: "POST",
        body: JSON.stringify({
          approved,
          comment: comments[approvalId] || "",
        }),
      });
      if (res.ok) {
        setDecisionMessage(
          approved
            ? "Action approuvée, exécutée en sandbox et graphe LangGraph repris."
            : "Action rejetée et graphe LangGraph clôturé."
        );
        await loadAutomationData();
      } else {
        const err = await res.json().catch(() => ({}));
        setDecisionMessage(err.detail || `Décision refusée (HTTP ${res.status}) — authentification opérateur/admin requise.`);
      }
    } catch {
      setDecisionMessage("Erreur réseau lors de la soumission de la décision HITL.");
    } finally {
      setDecidingId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wider uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/25">
              Catalogue Certifié
            </span>
            <span className="text-slate-500 text-xs">•</span>
            <span className="text-xs text-slate-400 font-mono">Sandbox Déclarative Niveau 3</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Automation Center & Runbooks
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-0.5">
            Catalogue des procédures autorisées, validation de schéma JSON et politique d&apos;exécution contrôlée
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-mono font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/25">
            <PauseCircle className="w-4 h-4 text-amber-400" />
            <span>{approvals.length} HITL En Attente</span>
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Zéro Shell Libre</span>
          </span>
        </div>
      </div>

      {/* File d'Approbation Human-in-the-Loop LangGraph */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-300">
                <UserCheck className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white tracking-tight">
                  File d&apos;Approbation Human-in-the-Loop LangGraph ({approvals.length})
                </h3>
                <p className="text-xs text-slate-400">
                  Workflows suspendus sur checkpoint PostgreSQL avant exécution Niveau 3 (MEDIUM / HIGH)
                </p>
              </div>
            </div>
            <button
              onClick={loadAutomationData}
              className="btn-tactile inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-200"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Actualiser</span>
            </button>
          </div>

          {decisionMessage && (
            <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/25 text-xs text-cyan-200">
              {decisionMessage}
            </div>
          )}

          {approvals.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-400">
              Aucune remédiation LangGraph en attente d&apos;approbation humaine.
            </div>
          ) : (
            <div className="space-y-3">
              {approvals.map((app) => (
                <div
                  key={app.id}
                  className="p-4 rounded-xl bg-obsidian-950/90 border border-amber-500/30 space-y-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/incidents/${app.incident_id}`}
                        className="font-mono text-xs font-bold text-cyan-300 hover:text-cyan-200 underline underline-offset-2"
                      >
                        {app.incident_number || app.incident_id.slice(0, 8)}
                      </Link>
                      <span className="text-xs font-semibold text-white">
                        {app.incident_title || "Incident AIOps"}
                      </span>
                      {app.primary_asset_name && (
                        <span className="text-[11px] font-mono text-slate-400">
                          • {app.primary_asset_name}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
                        {app.risk_level || "MEDIUM"}
                      </span>
                      <span className="font-mono text-xs text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/25">
                        {app.runbook_identifier}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-slate-300">{app.action_summary || app.runbook_identifier}</p>

                  {app.parameters && Object.keys(app.parameters).length > 0 && (
                    <pre className="p-2 rounded bg-black/60 border border-white/[0.06] font-mono text-[11px] text-cyan-200 overflow-x-auto">
                      {JSON.stringify(app.parameters, null, 2)}
                    </pre>
                  )}

                  <div className="flex flex-col sm:flex-row gap-2.5">
                    <input
                      type="text"
                      value={comments[app.id] || ""}
                      onChange={(e) => setComments((prev) => ({ ...prev, [app.id]: e.target.value }))}
                      placeholder="Commentaire opérateur / motif décision..."
                      className="flex-1 bg-obsidian-900 border border-white/[0.12] rounded-xl px-3 py-2 text-xs text-white outline-none focus:border-cyan-500/50"
                    />
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleDecision(app.id, true)}
                        disabled={decidingId === app.id}
                        className="btn-tactile inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>{decidingId === app.id ? "Reprise..." : "Approuver"}</span>
                      </button>
                      <button
                        onClick={() => handleDecision(app.id, false)}
                        disabled={decidingId === app.id}
                        className="btn-tactile inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-rose-200 bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/30 disabled:opacity-50"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>Rejeter</span>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Grille des Runbooks (Double-Bezel Architecture) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {loading ? (
          <div className="col-span-2 py-16 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
            <span>Chargement du catalogue de runbooks...</span>
          </div>
        ) : (
          runbooks.map((rb) => {
            const hasParams = rb.parameter_schema?.properties && Object.keys(rb.parameter_schema.properties).length > 0;
            return (
              <div
                key={rb.id}
                className="bezel-shell group"
              >
                <div className="bezel-core p-6 space-y-4 h-full flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded border border-cyan-500/20">
                        {rb.id}
                      </span>
                      <span className="text-[10px] uppercase font-mono font-bold px-2 py-0.5 rounded bg-white/[0.05] border border-white/[0.08] text-slate-300">
                        {rb.runner_type}
                      </span>
                    </div>

                    <h4 className="text-base font-bold text-white tracking-tight">
                      {rb.name}
                    </h4>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      {rb.description}
                    </p>

                    {hasParams && (
                      <div className="p-3 rounded-lg bg-obsidian-950/80 border border-white/[0.06] text-xs space-y-1">
                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                          Paramètres du schéma :
                        </span>
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {Object.keys(rb.parameter_schema.properties).map((prop) => (
                            <span
                              key={prop}
                              className="px-2 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-cyan-300 font-mono text-[11px]"
                            >
                              {prop}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="pt-4 border-t border-white/[0.06] flex flex-wrap items-center justify-between text-xs text-slate-400 font-mono gap-2">
                    <span className="flex items-center gap-1.5">
                      <Server className="w-3.5 h-3.5 text-slate-500" />
                      <span>OS : </span>
                      <strong className="text-slate-200 capitalize font-normal">{rb.target_os}</strong>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5 text-amber-500" />
                      <span>Rôle : </span>
                      <strong className="text-amber-400 font-normal">{rb.required_role}</strong>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Timer className="w-3.5 h-3.5 text-cyan-500" />
                      <span>Timeout : </span>
                      <strong className="text-slate-200 font-normal">{rb.timeout_seconds}s</strong>
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
