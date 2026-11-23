"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Clock,
  Copy,
  Cpu,
  MessageSquarePlus,
  PauseCircle,
  Play,
  RotateCw,
  SearchCheck,
  Server,
  ShieldCheck,
  Terminal,
  ThumbsDown,
  ThumbsUp,
  Ticket,
  XCircle,
} from "lucide-react";
import { apiFetch, getAuthToken } from "@/lib/api";

function cleanDisplay(val: any, fallback: string = "N/A"): string {
  if (val === null || val === undefined) return fallback;
  const s = String(val).trim();
  if (/^\{[A-Z0-9_\.]+\}$/.test(s)) return fallback;
  return s;
}

export default function IncidentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  const incidentId = resolvedParams.id;

  const [incident, setIncident] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [executingAction, setExecutingAction] = useState(false);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [selectedRunbook, setSelectedRunbook] = useState("rb-collect-top-processes");
  const [copied, setCopied] = useState(false);

  // Human-in-the-Loop LangGraph
  const [hitlComment, setHitlComment] = useState("");
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [hitlMessage, setHitlMessage] = useState<string | null>(null);

  // Feedback technicien -> KB Proposal
  const [fbAccepted, setFbAccepted] = useState(true);
  const [fbRating, setFbRating] = useState(5);
  const [fbNotes, setFbNotes] = useState("");
  const [fbSubmitting, setFbSubmitting] = useState(false);
  const [fbMessage, setFbMessage] = useState<string | null>(null);

  const fetchDetail = async () => {
    try {
      const res = await apiFetch(`/api/v1/incidents/${incidentId}`);
      if (res.ok) {
        setIncident(await res.json());
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchDetail();
    const interval = setInterval(fetchDetail, 4000);
    return () => clearInterval(interval);
  }, [incidentId]);

  const handleReanalyze = async () => {
    setAnalyzing(true);
    try {
      await apiFetch(`/api/v1/incidents/${incidentId}/analyze`, { method: "POST" });
      await fetchDetail();
    } catch (err) {
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleExecuteRunbook = async (runbookId: string, paramsObj: any) => {
    setExecutingAction(true);
    try {
      const res = await apiFetch("/api/v1/actions/execute", {
        method: "POST",
        body: JSON.stringify({
          runbook_id: runbookId,
          incident_id: incidentId,
          parameters: paramsObj || {},
          approved_by_user_id: "technician-ui",
        }),
      });
      if (res.ok) {
        setExecutionResult(await res.json());
        await fetchDetail();
      } else {
        const err = await res.json().catch(() => ({}));
        setFbMessage(err.detail || `Exécution refusée (HTTP ${res.status}) — connectez-vous dans le menu latéral.`);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setExecutingAction(false);
    }
  };

  const handleFeedbackSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!getAuthToken()) {
      setFbMessage("Connectez-vous via Session Opérateur (menu gauche) pour enregistrer un feedback certifié.");
      return;
    }
    setFbSubmitting(true);
    setFbMessage(null);
    try {
      const res = await apiFetch(`/api/v1/incidents/${incidentId}/feedback`, {
        method: "POST",
        body: JSON.stringify({
          is_recommendation_accepted: fbAccepted,
          rating_score: fbRating,
          feedback_notes: fbNotes,
          generate_kb_proposal: true,
        }),
      });
      if (res.ok) {
        const d = await res.json();
        setFbMessage(
          `Feedback enregistré et proposition KB mise à jour (#${d.proposal_id?.slice(0, 8)} — visible dans Knowledge Center).`
        );
        setFbNotes("");
        await fetchDetail();
      } else {
        const err = await res.json().catch(() => ({}));
        setFbMessage(err.detail || `Erreur feedback HTTP ${res.status}`);
      }
    } catch {
      setFbMessage("Erreur réseau lors de l'envoi du feedback.");
    } finally {
      setFbSubmitting(false);
    }
  };

  const copyOutput = () => {
    if (executionResult?.stdout) {
      navigator.clipboard.writeText(executionResult.stdout);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleHitlDecision = async (approvalId: string, approved: boolean) => {
    setDecidingId(approvalId);
    setHitlMessage(null);
    try {
      const res = await apiFetch(`/api/v1/actions/approvals/${approvalId}/decide`, {
        method: "POST",
        body: JSON.stringify({
          approved,
          comment: hitlComment,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.execution) {
          setExecutionResult(data.execution);
        }
        setHitlComment("");
        setHitlMessage(
          approved
            ? "Action approuvée, exécutée en sandbox et graphe LangGraph repris jusqu'au feedback final."
            : "Action rejetée avec traçabilité et graphe LangGraph clôturé."
        );
        await fetchDetail();
      } else {
        const err = await res.json().catch(() => ({}));
        setHitlMessage(err.detail || `Décision refusée (HTTP ${res.status}) — connectez-vous en tant qu'opérateur/admin.`);
      }
    } catch {
      setHitlMessage("Erreur réseau lors de la soumission de la décision HITL.");
    } finally {
      setDecidingId(null);
    }
  };

  if (!incident) {
    return (
      <div className="py-24 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
        <RotateCw className="w-4 h-4 animate-spin text-cyan-400" />
        <span>Chargement des détails de l&apos;incident #{incidentId.slice(0, 8)}...</span>
      </div>
    );
  }

  const analysis = incident.latest_analysis;
  const ragSources = analysis?.knowledge_sources || [];
  const approvals: any[] = incident.approvals || [];
  const pendingApprovals = approvals.filter((a) => a.status === "pending_approval");
  const pastApprovals = approvals.filter((a) => a.status !== "pending_approval");
  const investigationFindings: string[] = analysis?.investigation_findings || incident.investigation_findings || [];
  const executions: any[] = incident.executions || [];
  const isHitlPaused = incident.hitl_state === "waiting_human_approval" || pendingApprovals.length > 0;
  const activeThreadId = pendingApprovals[0]?.thread_id || approvals[0]?.thread_id || null;

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Barre supérieure */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <Link
          href="/incidents"
          className="btn-tactile inline-flex items-center gap-2 text-xs font-medium text-slate-400 hover:text-white transition-colors"
        >
          <div className="w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center">
            <ArrowLeft className="w-3.5 h-3.5" />
          </div>
          <span>Retour à la console</span>
        </Link>

        <button
          onClick={handleReanalyze}
          disabled={analyzing}
          className="btn-tactile flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-white/[0.04] hover:bg-white/[0.08] border border-cyan-500/30 text-cyan-300 transition-all disabled:opacity-50"
        >
          <RotateCw className={`w-3.5 h-3.5 ${analyzing ? "animate-spin" : ""}`} />
          <span>{analyzing ? "Analyse LangGraph en cours..." : "Réanalyser avec LangGraph"}</span>
        </button>
      </div>

      {/* Identité de l'Incident */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-bold text-cyan-400 bg-cyan-500/10 px-3 py-1 rounded-lg border border-cyan-500/30">
                {incident.incident_number}
              </span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-500/15 text-amber-400 border border-amber-500/30">
                {incident.severity}
              </span>
              <span className="px-2.5 py-1 rounded text-xs font-mono font-medium bg-white/[0.05] border border-white/[0.08] text-slate-300">
                {incident.status}
              </span>
            </div>

            <div className="text-xs text-slate-400 flex items-center gap-2">
              <Ticket className="w-4 h-4 text-cyan-400" />
              <span>Ticket GLPI :</span>
              <span className="text-cyan-300 font-mono font-bold">
                {incident.glpi_ticket_id ? `#${incident.glpi_ticket_id}` : "Non lié"}
              </span>
            </div>
          </div>

          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight">
            {cleanDisplay(incident.title, "Incident IT")}
          </h2>

          <div className="flex flex-wrap items-center gap-6 text-xs text-slate-400 border-t border-white/[0.06] pt-4 font-mono">
            <span className="flex items-center gap-1.5 text-slate-300 font-sans">
              <Server className="w-3.5 h-3.5 text-slate-500" />
              <span>Hôte Zabbix :</span>
              <strong className="text-white font-medium">{cleanDisplay(incident.primary_asset_name, "SRV-TEST-01")}</strong>
            </span>
            <span>Host ID : <strong className="text-cyan-400">{cleanDisplay(incident.zabbix_host_id)}</strong></span>
            <span>Entité : <strong className="text-slate-200">{incident.entity_id || "0"}</strong></span>
            <span className="flex items-center gap-1 text-slate-500">
              <Clock className="w-3.5 h-3.5" />
              <span>Détecté : {new Date(incident.opened_at).toLocaleString()}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Grille Bento : Événements & Diagnostic IA */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bezel-shell">
          <div className="bezel-core p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                <span>Événements Zabbix Corrélés ({incident.events_count})</span>
              </h3>
              <span className="text-[10px] font-mono text-slate-500">Fenêtre 15 min</span>
            </div>

            <div className="space-y-2.5">
              {incident.events.map((ev: any, idx: number) => (
                <div
                  key={idx}
                  className="p-3.5 rounded-xl bg-obsidian-950/80 border border-white/[0.06] text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-cyan-400 font-bold">
                      Event #{cleanDisplay(ev.event_id, `EVT-${idx + 1}`)}
                    </span>
                    <span className="text-[11px] font-mono text-slate-500">
                      {new Date(ev.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-slate-300 font-medium">
                    Métrique : <span className="font-mono text-slate-200">{ev.metric || "N/A"}</span>
                  </div>
                  {ev.value !== null && (
                    <div className="text-slate-400 flex items-center gap-2">
                      <span>Valeur relevée :</span>
                      <span className="font-mono font-bold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
                        {ev.value}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bezel-shell">
          <div className="bezel-core p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span>Diagnostic IA & Citations RAG</span>
              </h3>
              <span className="text-[10px] font-mono text-cyan-400">
                {analysis?.execution_mode || "LangGraph Swarm"} ({analysis?.duration_ms ?? 0}ms)
              </span>
            </div>

            {!analysis ? (
              <div className="py-10 text-center text-slate-400 text-xs">
                Aucune analyse IA disponible. Cliquez sur &quot;Réanalyser avec LangGraph&quot;.
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/25 space-y-1">
                  <div className="flex items-center justify-between text-xs font-bold text-cyan-300">
                    <span>Niveau de Confiance :</span>
                    <span className="font-mono uppercase tracking-wider">{analysis.confidence_level}</span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">{analysis.confidence_explanation}</p>
                  <div className="text-[10px] font-mono text-slate-400 pt-1">
                    Modèle: {analysis.model} • Tokens: {(analysis.prompt_tokens || 0) + (analysis.completion_tokens || 0)}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                    Hypothèses Qualifiées :
                  </div>
                  {analysis.hypotheses.map((h: any, i: number) => (
                    <div
                      key={i}
                      className="p-3 rounded-xl bg-obsidian-950/80 border border-white/[0.06] text-xs flex items-center justify-between gap-2"
                    >
                      <span className="text-slate-200 font-medium">{h.description}</span>
                      <span className="text-[9px] uppercase font-mono font-bold px-2 py-0.5 rounded bg-white/[0.05] border border-white/[0.08] text-slate-300 shrink-0">
                        {h.status}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Sources RAG persistées */}
                <div className="space-y-2 pt-2 border-t border-white/[0.06]">
                  <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Sources Knowledge Center Persistées ({ragSources.length}) :</span>
                  </div>
                  {ragSources.length === 0 ? (
                    <p className="text-[11px] text-slate-500 italic">Aucune citation RAG associée à ce diagnostic.</p>
                  ) : (
                    ragSources.map((src: any, sIdx: number) => (
                      <div key={sIdx} className="p-2.5 rounded-lg bg-obsidian-950/90 border border-cyan-500/20 text-[11px] space-y-1">
                        <div className="flex items-center justify-between font-semibold text-cyan-300">
                          <span className="truncate">#{src.article_id} — {src.title}</span>
                          <span className="font-mono text-[10px]">{src.relevance_score}</span>
                        </div>
                        <p className="text-slate-400 line-clamp-2">{src.snippet}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Investigation Lecture Seule (si déclenchée par confiance insuffisante) */}
      {investigationFindings.length > 0 && (
        <div className="bezel-shell">
          <div className="bezel-core p-5 space-y-3 border border-sky-500/20 rounded-2xl">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <SearchCheck className="w-4 h-4 text-sky-400" />
                <span>Investigation Complémentaire Lecture Seule ({investigationFindings.length})</span>
              </h3>
              <span className="text-[10px] font-mono text-sky-300 bg-sky-500/10 px-2.5 py-0.5 rounded-full border border-sky-500/25">
                Agent d&apos;Investigation Borné
              </span>
            </div>
            <ul className="space-y-1.5 text-xs text-slate-300">
              {investigationFindings.map((finding, idx) => (
                <li key={idx} className="p-2.5 rounded-lg bg-obsidian-950/80 border border-white/[0.06] font-mono text-[11px]">
                  {finding}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Human-in-the-Loop LangGraph Checkpoint Gate */}
      {(pendingApprovals.length > 0 || isHitlPaused || hitlMessage || pastApprovals.length > 0) && (
        <div className="bezel-shell">
          <div
            className={`bezel-core p-6 space-y-4 rounded-2xl border ${
              isHitlPaused
                ? "border-amber-500/40 bg-amber-500/[0.03]"
                : "border-white/[0.08]"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-2.5">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center border ${
                    pendingApprovals.length > 0
                      ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
                      : "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                  }`}
                >
                  {pendingApprovals.length > 0 ? (
                    <PauseCircle className="w-4 h-4" />
                  ) : (
                    <ShieldCheck className="w-4 h-4" />
                  )}
                </div>
                <div>
                  <h3 className="text-base font-bold text-white tracking-tight">
                    Validation Human-in-the-Loop LangGraph {pendingApprovals.length > 0 ? "(Workflow En Pause)" : ""}
                  </h3>
                  <p className="text-xs text-slate-400">
                    Checkpointer PostgreSQL persistant • Reprise atomique sur décision opérateur/admin
                  </p>
                </div>
              </div>
              {activeThreadId && (
                <span className="text-[10px] font-mono px-2.5 py-1 rounded-lg bg-obsidian-950 border border-white/[0.08] text-cyan-300">
                  thread: {activeThreadId}
                </span>
              )}
            </div>

            {hitlMessage && (
              <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/25 text-xs text-cyan-200">
                {hitlMessage}
              </div>
            )}

            {pendingApprovals.map((app) => (
              <div
                key={app.id}
                className="p-4 rounded-xl bg-obsidian-950/90 border border-amber-500/30 space-y-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-amber-300 bg-amber-500/15 px-2.5 py-1 rounded border border-amber-500/30">
                      {app.runbook_identifier}
                    </span>
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
                      Risque: {app.risk_level || "MEDIUM"}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400">
                    Checkpoint: {app.checkpoint_id ? String(app.checkpoint_id).slice(0, 12) : "persisted"}
                  </span>
                </div>

                <p className="text-xs text-slate-200">{app.action_summary || app.runbook_identifier}</p>

                {app.parameters && Object.keys(app.parameters).length > 0 && (
                  <pre className="p-2.5 rounded-lg bg-black/60 border border-white/[0.06] font-mono text-[11px] text-cyan-200 overflow-x-auto">
                    {JSON.stringify(app.parameters, null, 2)}
                  </pre>
                )}

                <div className="flex flex-col sm:flex-row gap-3 pt-1">
                  <input
                    type="text"
                    value={hitlComment}
                    onChange={(e) => setHitlComment(e.target.value)}
                    placeholder="Commentaire opérateur / motif d'approbation ou de rejet..."
                    className="flex-1 bg-obsidian-900 border border-white/[0.12] rounded-xl px-3 py-2 text-xs text-white outline-none focus:border-cyan-500/50"
                  />
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleHitlDecision(app.id, true)}
                      disabled={decidingId === app.id}
                      className="btn-tactile inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>{decidingId === app.id ? "Reprise..." : "Approuver & Reprendre"}</span>
                    </button>
                    <button
                      onClick={() => handleHitlDecision(app.id, false)}
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

            {pastApprovals.length > 0 && (
              <div className="space-y-2 pt-1">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  Historique des décisions HITL ({pastApprovals.length})
                </div>
                {pastApprovals.map((app) => (
                  <div
                    key={app.id}
                    className="p-3 rounded-xl bg-obsidian-950/70 border border-white/[0.06] flex flex-wrap items-center justify-between gap-2 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-mono text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${
                          app.status === "approved"
                            ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                            : "bg-rose-500/15 text-rose-300 border-rose-500/30"
                        }`}
                      >
                        {app.status}
                      </span>
                      <span className="font-mono text-cyan-300">{app.runbook_identifier}</span>
                    </div>
                    <span className="text-[11px] font-mono text-slate-400">
                      par {app.decided_by_user || "N/A"}{app.rejection_reason ? ` • ${app.rejection_reason}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {executions.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-white/[0.06]">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  Exécutions Sandbox Enregistrées ({executions.length})
                </div>
                {executions.slice(0, 3).map((ex) => (
                  <div key={ex.id} className="p-3 rounded-xl bg-black/50 border border-white/[0.06] text-xs space-y-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-cyan-300 font-semibold">{ex.runbook_identifier}</span>
                      <span className="font-mono text-[11px] text-emerald-300">
                        {ex.execution_status} (exit {ex.exit_code ?? "-"}) • {ex.approved_by}
                      </span>
                    </div>
                    {ex.stdout && (
                      <pre className="text-[10px] font-mono text-slate-300 whitespace-pre-wrap line-clamp-3 pt-1">
                        {ex.stdout}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Module Remédiation Niveau 3 */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400">
                <Terminal className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white tracking-tight">
                  Remédiation Contrôlée (Validation Technicien Niveau 3)
                </h3>
                <p className="text-xs text-slate-400">Sandbox isolée avec traçabilité d&apos;audit infalsifiable</p>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-obsidian-950/80 border border-white/[0.08] flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">Runbook Certifié du Catalogue :</label>
              <select
                value={selectedRunbook}
                onChange={(e) => setSelectedRunbook(e.target.value)}
                className="w-full bg-obsidian-900 border border-white/[0.12] text-white rounded-xl p-2.5 text-xs outline-none"
              >
                <option value="rb-collect-top-processes">rb-collect-top-processes : Collecte top processus</option>
                <option value="rb-win-service-restart">rb-win-service-restart : Redémarrage service Windows</option>
                <option value="rb-linux-service-restart">rb-linux-service-restart : Redémarrage service systemd</option>
                <option value="rb-disk-cleanup-logs">rb-disk-cleanup-logs : Purge préventive logs</option>
              </select>
            </div>
            <button
              onClick={() => {
                let p: any = {};
                if (selectedRunbook === "rb-win-service-restart") p = { service_name: "Spooler" };
                if (selectedRunbook === "rb-linux-service-restart") p = { service_name: "nginx" };
                handleExecuteRunbook(selectedRunbook, p);
              }}
              disabled={executingAction}
              className="btn-tactile inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{executingAction ? "Exécution..." : "Approuver & Exécuter"}</span>
            </button>
          </div>

          {executionResult && (
            <div className="p-4 rounded-xl bg-black/80 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-emerald-400 font-mono">
                  Code retour : {executionResult.exit_code} • {executionResult.duration_seconds}s
                </span>
                <button onClick={copyOutput} className="text-slate-400 hover:text-white">
                  <Copy className="w-3.5 h-3.5" />
                </button>
              </div>
              <pre className="p-3 rounded bg-obsidian-950 font-mono text-[11px] text-cyan-200 overflow-x-auto whitespace-pre-wrap">
                {executionResult.stdout || "(Sortie vide)"}
              </pre>
            </div>
          )}
        </div>
      </div>

      {/* Feedback Technicien -> Boucle KB GLPI */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <MessageSquarePlus className="w-4 h-4 text-cyan-400" />
              <span>Feedback Opérateur & Enrichissement Base de Connaissances (Boucle P0)</span>
            </h3>
            {incident.kb_proposal && (
              <Link
                href="/knowledge"
                className="text-[11px] font-mono px-2.5 py-1 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25"
              >
                Proposition KB : {incident.kb_proposal.status}
              </Link>
            )}
          </div>

          <form onSubmit={handleFeedbackSubmit} className="space-y-3 text-xs">
            <div className="flex flex-wrap items-center gap-4">
              <button
                type="button"
                onClick={() => setFbAccepted(true)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-semibold ${
                  fbAccepted
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    : "bg-obsidian-950 text-slate-400 border-white/[0.08]"
                }`}
              >
                <ThumbsUp className="w-3.5 h-3.5" />
                <span>Diagnostic pertinent</span>
              </button>
              <button
                type="button"
                onClick={() => setFbAccepted(false)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-semibold ${
                  !fbAccepted
                    ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                    : "bg-obsidian-950 text-slate-400 border-white/[0.08]"
                }`}
              >
                <ThumbsDown className="w-3.5 h-3.5" />
                <span>À corriger</span>
              </button>

              <label className="flex items-center gap-2 text-slate-300 ml-auto">
                <span>Note (1–5) :</span>
                <select
                  value={fbRating}
                  onChange={(e) => setFbRating(Number(e.target.value))}
                  className="bg-obsidian-900 border border-white/[0.12] rounded-lg px-2 py-1 text-white"
                >
                  {[5, 4, 3, 2, 1].map((n) => (
                    <option key={n} value={n}>
                      {n}/5
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <textarea
              rows={2}
              value={fbNotes}
              onChange={(e) => setFbNotes(e.target.value)}
              placeholder="Note technique sur la cause racine réelle ou les commandes ayant résolu l'incident (enrichira automatiquement la fiche KB)..."
              className="w-full p-3 rounded-xl bg-obsidian-950/90 border border-white/[0.08] text-slate-200 placeholder-slate-500 outline-none focus:border-cyan-400"
            />

            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-[11px] text-slate-400">
                {fbMessage || (copied ? "Sortie copiée." : "Génère/actualise une fiche KB en attente d'approbation.")}
              </span>
              <button
                type="submit"
                disabled={fbSubmitting}
                className="btn-tactile px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold disabled:opacity-50"
              >
                {fbSubmitting ? "Envoi..." : "Enregistrer Feedback & Générer Fiche KB"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
