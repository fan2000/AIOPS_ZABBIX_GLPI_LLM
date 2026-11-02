"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { 
  AlertTriangle, 
  ArrowLeft, 
  BookOpen, 
  CheckCircle2, 
  Cpu, 
  HelpCircle, 
  Play, 
  RotateCw, 
  ShieldAlert, 
  Terminal 
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
        body: jsonBody({
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

  function jsonBody(obj: any) {
    return JSON.stringify(obj);
  }

  if (!incident) {
    return (
      <div className="p-8 text-center text-slate-400">
        Chargement de l&apos;incident...
      </div>
    );
  }

  const analysis = incident.latest_analysis;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Retour et En-tête */}
      <div className="flex items-center justify-between">
        <Link
          href="/incidents"
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Retour aux incidents</span>
        </Link>
        <button
          onClick={handleReanalyze}
          disabled={analyzing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-navy-800 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10 transition-all disabled:opacity-50"
        >
          <RotateCw className={`w-3.5 h-3.5 ${analyzing ? "animate-spin" : ""}`} />
          <span>{analyzing ? "Analyse en cours..." : "Réanalyser avec LangGraph"}</span>
        </button>
      </div>

      <div className="p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm font-bold text-cyan-400">{incident.incident_number}</span>
            <span className="px-2 py-0.5 rounded text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
              {incident.severity}
            </span>
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-700 text-slate-300">
              {incident.status}
            </span>
          </div>
          <div className="text-xs text-slate-400">
            Ticket GLPI : <strong className="text-white font-mono">{incident.glpi_ticket_id ? `#${incident.glpi_ticket_id}` : "En cours"}</strong>
          </div>
        </div>
        <h2 className="text-xl font-bold text-white">{incident.title}</h2>
        <div className="flex flex-wrap items-center gap-6 text-xs text-slate-400 border-t border-navy-700 pt-3">
          <span>Hôte Zabbix : <strong className="text-slate-200">{incident.primary_asset_name}</strong></span>
          <span>Zabbix Host ID : <strong className="text-slate-200">{incident.zabbix_host_id}</strong></span>
          <span>Détecté le : {new Date(incident.opened_at).toLocaleString()}</span>
        </div>
      </div>

      {/* Grille : Événements Zabbix & Diagnostic IA */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Événements Zabbix liés */}
        <div className="p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              Événements Zabbix Corrélés ({incident.events_count})
            </h3>
          </div>
          <div className="space-y-2.5">
            {incident.events.map((ev: any, idx: number) => (
              <div key={idx} className="p-3 rounded-lg bg-navy-900 border border-navy-700/60 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-cyan-400 font-semibold">Event #{ev.event_id}</span>
                  <span className="text-slate-400">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                </div>
                <div className="text-slate-300 font-medium">Métrique : {ev.metric || "N/A"}</div>
                {ev.value !== null && (
                  <div className="text-slate-400">Valeur mesurée : <span className="text-rose-400 font-bold">{ev.value}</span></div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Diagnostic IA & Hypothèses */}
        <div className="p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Hypothèses de Diagnostic IA
          </h3>

          {!analysis ? (
            <p className="text-xs text-slate-400">Aucune analyse IA disponible. Cliquez sur &quot;Réanalyser&quot;.</p>
          ) : (
            <div className="space-y-3">
              <div className="p-3 rounded-lg bg-navy-900/80 border border-cyan-500/20 text-xs">
                <div className="text-cyan-400 font-semibold mb-1">Niveau de Confiance : {analysis.confidence_level}</div>
                <p className="text-slate-300">{analysis.confidence_explanation}</p>
              </div>

              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-slate-400 uppercase">Hypothèses formulées :</h4>
                {analysis.hypotheses.map((h: any, i: number) => (
                  <div key={i} className="p-2.5 rounded-lg bg-navy-900 border border-navy-700 text-xs space-y-1">
                    <div className="flex items-center justify-between font-semibold text-white">
                      <span>{h.description}</span>
                      <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">{h.status}</span>
                    </div>
                  </div>
                ))}
              </div>

              {analysis.checks && analysis.checks.length > 0 && (
                <div className="space-y-1 text-xs">
                  <h4 className="font-semibold text-slate-400 uppercase">Vérifications suggérées :</h4>
                  <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                    {analysis.checks.map((c: string, idx: number) => (
                      <li key={idx}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Module de Remédiation Contrôlée (Niveau 3) */}
      <div className="p-6 rounded-xl bg-navy-800 border border-cyan-500/40 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Terminal className="w-5 h-5 text-cyan-400" />
            Remédiation Contrôlée (Validation Technicien Niveau 3)
          </h3>
          <span className="text-xs text-slate-400">Sandbox sécurisée sans shell libre</span>
        </div>

        <p className="text-xs text-slate-300">
          L&apos;IA a identifié une action de remédiation préapprouvée. Validez pour déclencher son exécution dans l&apos;environnement restreint :
        </p>

        <div className="p-4 rounded-xl bg-navy-900 border border-navy-700 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="text-sm font-bold text-white">Redémarrer / Purger selon runbook catalogue</div>
            <div className="text-xs text-slate-400">Runbook : <code className="text-cyan-400">rb-win-service-restart</code> ou <code className="text-cyan-400">rb-disk-cleanup-logs</code></div>
          </div>
          <button
            onClick={() => handleExecuteRunbook("rb-collect-top-processes", {})}
            disabled={executingAction}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-bold bg-cyan-500 hover:bg-cyan-400 text-navy-900 transition-all disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-current" />
            <span>{executingAction ? "Exécution..." : "Approuver & Exécuter le Runbook"}</span>
          </button>
        </div>

        {/* Résultat d'exécution en direct */}
        {executionResult && (
          <div className="p-4 rounded-xl bg-navy-900 border border-emerald-500/40 space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-emerald-400">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Exécution réussie (Code retour: {executionResult.exit_code})
              </span>
              <span>Durée: {executionResult.duration_seconds}s</span>
            </div>
            <pre className="p-3 rounded bg-black/60 font-mono text-[11px] text-slate-300 overflow-x-auto">
              {executionResult.stdout}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
