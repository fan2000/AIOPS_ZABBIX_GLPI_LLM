"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { 
  Activity,
  AlertCircle,
  AlertOctagon, 
  AlertTriangle, 
  ArrowLeft, 
  BookOpen, 
  CheckCircle2, 
  Clock,
  Copy,
  Cpu, 
  ExternalLink,
  HelpCircle, 
  Layers,
  Play, 
  RotateCw, 
  Server,
  ShieldAlert, 
  ShieldCheck,
  Terminal,
  Ticket,
  Zap
} from "lucide-react";

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

  const fetchDetail = async () => {
    try {
      const res = await fetch(`http://localhost:8005/api/v1/incidents/${incidentId}`);
      if (res.ok) {
        const data = await res.json();
        setIncident(data);
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
      await fetch(`http://localhost:8005/api/v1/incidents/${incidentId}/analyze`, {
        method: "POST",
      });
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
      const res = await fetch("http://localhost:8005/api/v1/actions/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          runbook_id: runbookId,
          incident_id: incidentId,
          parameters: paramsObj || {},
          approved_by_user_id: "technician-ui",
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setExecutionResult(data);
        await fetchDetail();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setExecutingAction(false);
    }
  };

  const copyOutput = () => {
    if (executionResult?.stdout) {
      navigator.clipboard.writeText(executionResult.stdout);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
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

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Barre d'Action Supérieure & Retour */}
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

        <div className="flex items-center gap-2.5">
          <button
            onClick={handleReanalyze}
            disabled={analyzing}
            className="btn-tactile flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-white/[0.04] hover:bg-white/[0.08] border border-cyan-500/30 text-cyan-300 transition-all disabled:opacity-50"
          >
            <RotateCw className={`w-3.5 h-3.5 ${analyzing ? "animate-spin" : ""}`} />
            <span>{analyzing ? "Analyse LangGraph en cours..." : "Réanalyser avec LangGraph"}</span>
          </button>
        </div>
      </div>

      {/* Carte d'Identité de l'Incident (Double-Bezel Architecture) */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-bold text-cyan-400 bg-cyan-500/10 px-3 py-1 rounded-lg border border-cyan-500/30">
                {incident.incident_number}
              </span>
              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                incident.severity === "HIGH" || incident.severity === "DISASTER"
                  ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                  : "bg-amber-500/15 text-amber-400 border border-amber-500/30"
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  incident.severity === "HIGH" || incident.severity === "DISASTER" ? "bg-rose-400 animate-ping" : "bg-amber-400"
                }`}></span>
                {incident.severity}
              </span>
              <span className="px-2.5 py-1 rounded text-xs font-mono font-medium bg-white/[0.05] border border-white/[0.08] text-slate-300">
                {incident.status}
              </span>
            </div>

            <div className="text-xs text-slate-400 flex items-center gap-2">
              <Ticket className="w-4 h-4 text-cyan-400" />
              <span>Ticket GLPI lié :</span>
              {incident.glpi_ticket_id ? (
                <span className="text-cyan-300 font-mono font-bold">#{incident.glpi_ticket_id}</span>
              ) : (
                <span className="text-slate-500 italic">Création en cours...</span>
              )}
            </div>
          </div>

          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight">
            {incident.title}
          </h2>

          <div className="flex flex-wrap items-center gap-6 text-xs text-slate-400 border-t border-white/[0.06] pt-4 font-mono">
            <span className="flex items-center gap-1.5 text-slate-300 font-sans">
              <Server className="w-3.5 h-3.5 text-slate-500" />
              <span>Hôte Zabbix :</span>
              <strong className="text-white font-medium">{incident.primary_asset_name}</strong>
            </span>
            <span>Host ID : <strong className="text-cyan-400">{incident.zabbix_host_id}</strong></span>
            <span className="flex items-center gap-1 text-slate-500">
              <Clock className="w-3.5 h-3.5" />
              <span>Détecté : {new Date(incident.opened_at).toLocaleString()}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Grille Bento : Événements Zabbix & Diagnostic IA */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Événements Zabbix Liés */}
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
                  className="p-3.5 rounded-xl bg-obsidian-950/80 border border-white/[0.06] text-xs space-y-1.5 hover:border-cyan-500/30 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-cyan-400 font-bold">Event #{ev.event_id}</span>
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

        {/* Diagnostic IA & Hypothèses */}
        <div className="bezel-shell">
          <div className="bezel-core p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span>Hypothèses de Diagnostic IA</span>
              </h3>
              <span className="text-[10px] font-mono text-cyan-400">LangGraph Swarm</span>
            </div>

            {!analysis ? (
              <div className="py-10 text-center text-slate-400 text-xs space-y-2">
                <p>Aucune analyse IA disponible pour cet incident.</p>
                <p className="text-slate-500">Cliquez sur &quot;Réanalyser avec LangGraph&quot; ci-dessus.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Score de Confiance */}
                <div className="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/25 space-y-1">
                  <div className="flex items-center justify-between text-xs font-bold text-cyan-300">
                    <span>Niveau de Confiance IA :</span>
                    <span className="font-mono uppercase tracking-wider">{analysis.confidence_level}</span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    {analysis.confidence_explanation}
                  </p>
                </div>

                {/* Hypothèses formulées */}
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

                {/* Vérifications suggérées */}
                {analysis.checks && analysis.checks.length > 0 && (
                  <div className="space-y-1.5 pt-2 border-t border-white/[0.06]">
                    <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      Vérifications Recommandées :
                    </div>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {analysis.checks.map((c: string, idx: number) => (
                        <li key={idx} className="flex items-start gap-2">
                          <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400 mt-0.5 shrink-0" />
                          <span>{c}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Module de Remédiation Contrôlée (Niveau 3) */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-glow-cyan">
                <Terminal className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white tracking-tight">
                  Remédiation Contrôlée (Validation Technicien Niveau 3)
                </h3>
                <p className="text-xs text-slate-400">
                  Sandbox isolée sans shell arbitraire avec traçabilité d&apos;audit infalsifiable
                </p>
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Sandbox Sécurisée
            </span>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed">
            L&apos;IA a identifié des runbooks déclaratifs sécurisés du catalogue. Sélectionnez une action préapprouvée et déclenchez son exécution contrôlée :
          </p>

          <div className="p-4 rounded-xl bg-obsidian-950/80 border border-white/[0.08] space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
              <div className="flex-1 space-y-1.5">
                <label className="text-xs font-semibold text-slate-300">
                  Runbook Certifié du Catalogue :
                </label>
                <select
                  value={selectedRunbook}
                  onChange={(e) => setSelectedRunbook(e.target.value)}
                  className="w-full bg-obsidian-900 border border-white/[0.12] text-white rounded-xl p-2.5 text-xs focus:ring-1 focus:ring-cyan-400 outline-none"
                >
                  <option value="rb-collect-top-processes">rb-collect-top-processes : Collecte des 10 processus les plus consommateurs</option>
                  <option value="rb-win-service-restart">rb-win-service-restart : Redémarrage de service supervisé</option>
                  <option value="rb-linux-service-restart">rb-linux-service-restart : Redémarrage service systemd</option>
                  <option value="rb-disk-cleanup-logs">rb-disk-cleanup-logs : Purge préventive des logs archivés</option>
                </select>
              </div>

              <div>
                <button
                  onClick={() => {
                    let p: any = {};
                    if (selectedRunbook === "rb-win-service-restart") p = { service_name: "Spooler" };
                    if (selectedRunbook === "rb-linux-service-restart") p = { service_name: "nginx" };
                    handleExecuteRunbook(selectedRunbook, p);
                  }}
                  disabled={executingAction}
                  className="btn-tactile group relative inline-flex items-center gap-3 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 shadow-glow-cyan transition-all disabled:opacity-50 shrink-0"
                >
                  <span>{executingAction ? "Exécution en cours..." : "Approuver & Exécuter"}</span>
                  <div className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center">
                    {executingAction ? (
                      <RotateCw className="w-3 h-3 text-white animate-spin" />
                    ) : (
                      <Play className="w-3 h-3 text-white fill-current group-hover:translate-x-0.5 transition-transform" />
                    )}
                  </div>
                </button>
              </div>
            </div>
          </div>

          {/* Résultat d'Exécution en Direct dans Console Professionnelle */}
          {executionResult && (
            <div className="bezel-shell">
              <div className="bezel-core p-4 space-y-3 bg-black/80">
                <div className="flex items-center justify-between text-xs pb-2 border-b border-white/[0.08]">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80"></span>
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80"></span>
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80"></span>
                    </div>
                    <span className="text-slate-400 font-mono text-[11px] ml-2">Console de Remédiation</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="inline-flex items-center gap-1.5 text-emerald-400 font-semibold font-mono text-[11px]">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Code retour : {executionResult.exit_code}
                    </span>
                    <span className="text-slate-500 font-mono text-[11px]">
                      Durée : {executionResult.duration_seconds}s
                    </span>
                    <button
                      onClick={copyOutput}
                      className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
                      title="Copier la sortie"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <pre className="p-3 rounded-lg bg-obsidian-950/90 font-mono text-[11px] text-cyan-200 overflow-x-auto whitespace-pre-wrap leading-relaxed border border-white/[0.04]">
                  {executionResult.stdout || "(Exécution terminée avec sortie vide)"}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
