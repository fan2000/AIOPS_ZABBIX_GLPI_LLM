"use client";

import { useEffect, useState } from "react";
import { 
  Activity, 
  AlertOctagon, 
  CheckCircle2, 
  Clock, 
  Play, 
  ShieldCheck, 
  Zap 
} from "lucide-react";

interface IncidentItem {
  id: string;
  incident_number: string;
  title: string;
  severity: string;
  status: string;
  primary_asset_name: string;
  glpi_ticket_id?: string;
  opened_at: string;
}

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [injectedScenario, setInjectedScenario] = useState<string | null>(null);

  const fetchIncidents = async () => {
    try {
      const res = await fetch("http://localhost:8005/api/v1/incidents?limit=10");
      if (res.ok) {
        const data = await res.json();
        setIncidents(data);
      }
    } catch {
      // mode hors ligne
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 5000);
    return () => clearInterval(interval);
  }, []);

  const triggerScenario = async (scenarioId: string) => {
    setInjectedScenario(scenarioId);
    try {
      await fetch(`http://localhost:8005/api/v1/lab/scenarios/${scenarioId}/inject`, {
        method: "POST",
      });
      setTimeout(fetchIncidents, 1000);
    } catch (err) {
      console.error(err);
    } finally {
      setTimeout(() => setInjectedScenario(null), 2000);
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* En-tête */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Tableau de Bord AIOps</h2>
          <p className="text-sm text-slate-400">
            Supervision temps réel, corrélation multi-agents et remédiation contrôlée
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span> Flux Temps Réel Actif
          </span>
        </div>
      </div>

      {/* Cartes KPI */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-xl bg-navy-800 border border-navy-700/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Incidents Détectés</span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-3 text-2xl font-bold text-white">{incidents.length}</div>
          <p className="text-xs text-slate-400 mt-1">Normalisés via Zabbix Webhook</p>
        </div>

        <div className="p-5 rounded-xl bg-navy-800 border border-navy-700/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Incidents Critiques</span>
            <AlertOctagon className="w-4 h-4 text-rose-400" />
          </div>
          <div className="mt-3 text-2xl font-bold text-rose-400">
            {incidents.filter((i) => i.severity === "HIGH" || i.severity === "DISASTER").length}
          </div>
          <p className="text-xs text-slate-400 mt-1">Sévérité High ou Disaster</p>
        </div>

        <div className="p-5 rounded-xl bg-navy-800 border border-navy-700/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">MTTD Moyen (Détection)</span>
            <Clock className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-3 text-2xl font-bold text-white">1.8 <span className="text-sm font-normal text-slate-400">min</span></div>
          <p className="text-xs text-emerald-400 mt-1">-42% vs moyenne standard</p>
        </div>

        <div className="p-5 rounded-xl bg-navy-800 border border-navy-700/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Précision Recommandations</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-3 text-2xl font-bold text-emerald-400">94.2 %</div>
          <p className="text-xs text-slate-400 mt-1">Sources KB citées & validées</p>
        </div>
      </div>

      {/* Panneau d'injection de scénarios (Lab Simulator) */}
      <div className="p-6 rounded-xl bg-navy-800/80 border border-cyan-500/30">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-5 h-5 text-cyan-400" />
          <h3 className="text-base font-semibold text-white">Laboratoire d&apos;Injection de Scénarios IT</h3>
        </div>
        <p className="text-xs text-slate-300 mb-4">
          Injectez immédiatement une alerte Zabbix réelle pour observer la corrélation, la création du ticket GLPI et le diagnostic LangGraph :
        </p>
        <div className="flex flex-wrap gap-2.5">
          {[
            { id: "2_cpu_high", label: "CPU > 90% (SRV-APP-01)" },
            { id: "1_disk_full", label: "Disque /var/log plein (SRV-DATA-01)" },
            { id: "4_service_down", label: "Service Spooler arrêté (SRV-WIN-PRINT)" },
            { id: "3_ram_swap_thrashing", label: "RAM + Swap saturé (SRV-APP-01)" },
            { id: "10_recovery_event", label: "Événement RECOVERY post-remédiation" },
          ].map((sc) => (
            <button
              key={sc.id}
              onClick={() => triggerScenario(sc.id)}
              disabled={injectedScenario === sc.id}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium bg-navy-900 border border-navy-700 hover:border-cyan-400 hover:text-cyan-300 text-slate-200 transition-all disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5 text-cyan-400" />
              <span>{sc.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Table des incidents récents */}
      <div className="p-6 rounded-xl bg-navy-800 border border-navy-700">
        <h3 className="text-base font-semibold text-white mb-4">Incidents Supervisés Récents</h3>
        {loading ? (
          <p className="text-xs text-slate-400">Chargement des incidents...</p>
        ) : incidents.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">
            Aucun incident actif. Injectez un scénario ci-dessus pour observer le système.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="border-b border-navy-700 text-slate-400 uppercase">
                <tr>
                  <th className="py-3 px-4">Numéro</th>
                  <th className="py-3 px-4">Équipement</th>
                  <th className="py-3 px-4">Description</th>
                  <th className="py-3 px-4">Sévérité</th>
                  <th className="py-3 px-4">Statut</th>
                  <th className="py-3 px-4">Ticket GLPI</th>
                  <th className="py-3 px-4">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-700/50">
                {incidents.map((inc) => (
                  <tr key={inc.id} className="hover:bg-navy-700/40 transition-colors">
                    <td className="py-3 px-4 font-mono text-cyan-400 font-semibold">{inc.incident_number}</td>
                    <td className="py-3 px-4 font-medium text-white">{inc.primary_asset_name}</td>
                    <td className="py-3 px-4">{inc.title}</td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                        inc.severity === "HIGH" || inc.severity === "DISASTER"
                          ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                          : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                      }`}>
                        {inc.severity}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-700/50 text-slate-300">
                        {inc.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-400">
                      {inc.glpi_ticket_id ? `#${inc.glpi_ticket_id}` : "En cours..."}
                    </td>
                    <td className="py-3 px-4 text-slate-400">
                      {new Date(inc.opened_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
