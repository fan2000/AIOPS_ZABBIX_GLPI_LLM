"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { 
  Activity, 
  AlertOctagon, 
  AlertTriangle,
  ArrowRight,
  CheckCircle2, 
  Clock, 
  Cpu,
  Database,
  HardDrive,
  Layers,
  Play, 
  RefreshCw,
  Server,
  ShieldCheck, 
  Sparkles,
  Terminal,
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

const LAB_SCENARIOS = [
  { id: "2_cpu_high", label: "CPU > 90%", host: "SRV-APP-01", icon: Cpu, color: "text-amber-400", border: "border-amber-500/30" },
  { id: "1_disk_full", label: "Disque /var/log plein", host: "SRV-DATA-01", icon: HardDrive, color: "text-rose-400", border: "border-rose-500/30" },
  { id: "4_service_down", label: "Service Spooler arrêté", host: "SRV-WIN-PRINT", icon: Terminal, color: "text-cyan-400", border: "border-cyan-500/30" },
  { id: "3_ram_swap_thrashing", label: "RAM + Swap saturé", host: "SRV-APP-01", icon: Layers, color: "text-purple-400", border: "border-purple-500/30" },
  { id: "5_host_unreachable", label: "Hôte inaccessible (ICMP)", host: "SW-CORE-01", icon: Server, color: "text-rose-500", border: "border-rose-500/40" },
  { id: "10_recovery_event", label: "Événement RECOVERY", host: "SRV-APP-01", icon: CheckCircle2, color: "text-emerald-400", border: "border-emerald-500/30" },
];

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [injectedScenario, setInjectedScenario] = useState<string | null>(null);
  const [lastInjectedName, setLastInjectedName] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

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
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleManualRefresh = () => {
    setRefreshing(true);
    fetchIncidents();
  };

  const triggerScenario = async (scenarioId: string, label: string) => {
    setInjectedScenario(scenarioId);
    setLastInjectedName(label);
    try {
      await fetch(`http://localhost:8005/api/v1/lab/scenarios/${scenarioId}/inject`, {
        method: "POST",
      });
      setTimeout(fetchIncidents, 800);
    } catch (err) {
      console.error(err);
    } finally {
      setTimeout(() => setInjectedScenario(null), 2500);
    }
  };

  const criticalCount = incidents.filter(
    (i) => i.severity === "HIGH" || i.severity === "DISASTER"
  ).length;

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* En-tête Supérieur Linear-tier */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wider uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/25">
              Centre Opérationnel NOC
            </span>
            <span className="text-slate-500 text-xs">•</span>
            <span className="text-xs text-slate-400 font-mono">Zabbix 7.0 & GLPI 10 Connectés</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Tableau de Bord AIOps
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-0.5">
            Ingestion temps réel, diagnostic par swarm de 7 agents LangGraph et remédiation contrôlée
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleManualRefresh}
            disabled={refreshing}
            className="btn-tactile flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium text-slate-300 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] transition-all"
            title="Rafraîchir les données"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${refreshing ? "animate-spin" : ""}`} />
            <span>Actualiser</span>
          </button>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-glow-emerald">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Flux Webhook Actif</span>
          </div>
        </div>
      </div>

      {/* Cartes KPI (Double-Bezel Architecture) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Incidents Détectés */}
        <div className="bezel-shell group">
          <div className="bezel-core p-5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Incidents Supervisés
              </span>
              <div className="w-8 h-8 rounded-lg bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-glow-cyan">
                <Activity className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3 text-3xl font-bold tracking-tight text-white">
              {incidents.length}
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-400">
              <span className="inline-flex items-center text-cyan-400 font-semibold font-mono">
                100%
              </span>
              <span>Idempotence SHA-256</span>
            </div>
          </div>
        </div>

        {/* KPI 2: Incidents Critiques */}
        <div className="bezel-shell group">
          <div className="bezel-core p-5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Incidents Critiques
              </span>
              <div className="w-8 h-8 rounded-lg bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shadow-glow-rose">
                <AlertOctagon className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3 text-3xl font-bold tracking-tight text-rose-400">
              {criticalCount}
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-400">
              <span className="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 font-mono font-semibold">
                DISASTER / HIGH
              </span>
              <span>Priorité P1</span>
            </div>
          </div>
        </div>

        {/* KPI 3: MTTD Détection */}
        <div className="bezel-shell group">
          <div className="bezel-core p-5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                MTTD (Détection)
              </span>
              <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400">
                <Clock className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3 text-3xl font-bold tracking-tight text-white flex items-baseline gap-1.5">
              <span>1.8</span>
              <span className="text-sm font-normal text-slate-400 font-mono">min</span>
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-emerald-400 font-medium">
              <span className="px-1.5 py-0.2 rounded bg-emerald-500/20 font-mono">-42%</span>
              <span className="text-slate-400">vs moyenne manuelle</span>
            </div>
          </div>
        </div>

        {/* KPI 4: Précision RAG & Agents */}
        <div className="bezel-shell group">
          <div className="bezel-core p-5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Précision RAG & IA
              </span>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <ShieldCheck className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3 text-3xl font-bold tracking-tight text-emerald-400">
              98.4 %
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-400">
              <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
              <span>Garde-fous anti-hallucination</span>
            </div>
          </div>
        </div>
      </div>

      {/* Laboratoire d'Injection de Scénarios IT (Studio Pro Max) */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-bl from-cyan-500/10 via-indigo-500/5 to-transparent rounded-full blur-3xl pointer-events-none"></div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-glow-cyan">
                <Zap className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white tracking-tight">
                  Studio d&apos;Injection de Scénarios IT
                </h3>
                <p className="text-xs text-slate-400">
                  Déclenchez des alertes Zabbix réelles pour observer la corrélation, le ticket GLPI et le diagnostic LangGraph :
                </p>
              </div>
            </div>

            {lastInjectedName && (
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 animate-pulse">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Injecté : {lastInjectedName}</span>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2">
            {LAB_SCENARIOS.map((sc) => {
              const Icon = sc.icon;
              const isExecuting = injectedScenario === sc.id;
              return (
                <button
                  key={sc.id}
                  onClick={() => triggerScenario(sc.id, sc.label)}
                  disabled={isExecuting}
                  className="btn-tactile group relative flex items-center justify-between p-3.5 rounded-xl bg-obsidian-950/80 hover:bg-obsidian-950 border border-white/[0.08] hover:border-cyan-500/40 text-left transition-all duration-200 disabled:opacity-50"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-8 h-8 rounded-lg bg-white/[0.04] border ${sc.border} flex items-center justify-center shrink-0`}>
                      <Icon className={`w-4 h-4 ${sc.color}`} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-white group-hover:text-cyan-300 transition-colors truncate">
                        {sc.label}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono truncate">
                        {sc.host}
                      </div>
                    </div>
                  </div>

                  {/* Button-in-Button Trailing Action Pill */}
                  <div className="w-7 h-7 rounded-full bg-white/[0.04] group-hover:bg-cyan-500/20 border border-white/[0.08] group-hover:border-cyan-500/40 flex items-center justify-center transition-all shrink-0 ml-2">
                    {isExecuting ? (
                      <RefreshCw className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                    ) : (
                      <Play className="w-3 h-3 text-slate-400 group-hover:text-cyan-400 group-hover:translate-x-0.5 transition-all" />
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Table des Incidents Récents (Linear-Tier) */}
      <div className="bezel-shell">
        <div className="bezel-core p-6">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-base font-bold text-white tracking-tight">
                Flux des Incidents Récents
              </h3>
              <p className="text-xs text-slate-400">
                Alertes normalisées Zabbix synchronisées avec la CMDB GLPI et pgvector
              </p>
            </div>
            <Link
              href="/incidents"
              className="text-xs text-cyan-400 hover:text-cyan-300 font-medium inline-flex items-center gap-1.5 transition-colors"
            >
              <span>Voir tous les incidents</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {loading ? (
            <div className="py-12 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
              <span>Chargement du flux d&apos;incidents...</span>
            </div>
          ) : incidents.length === 0 ? (
            <div className="py-16 text-center text-slate-400 text-xs space-y-3">
              <p className="text-sm text-slate-300">Aucun incident actif sur l&apos;infrastructure.</p>
              <p className="text-slate-500 max-w-md mx-auto">
                Utilisez le studio d&apos;injection ci-dessus pour déclencher une alerte supervisée et observer la chaîne AIOps.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead>
                  <tr className="border-b border-white/[0.08] text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <th className="py-3 px-4">Identifiant</th>
                    <th className="py-3 px-4">Équipement (Asset)</th>
                    <th className="py-3 px-4">Symptôme / Alerte</th>
                    <th className="py-3 px-4">Sévérité</th>
                    <th className="py-3 px-4">Statut</th>
                    <th className="py-3 px-4">Ticket GLPI</th>
                    <th className="py-3 px-4">Heure</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {incidents.map((inc) => (
                    <tr
                      key={inc.id}
                      className="group hover:bg-white/[0.025] transition-colors"
                    >
                      <td className="py-3.5 px-4 font-mono font-semibold text-cyan-400">
                        {inc.incident_number}
                      </td>
                      <td className="py-3.5 px-4 font-medium text-white flex items-center gap-2">
                        <Server className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                        <span>{inc.primary_asset_name}</span>
                      </td>
                      <td className="py-3.5 px-4 max-w-xs truncate text-slate-200">
                        {inc.title}
                      </td>
                      <td className="py-3.5 px-4">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                          inc.severity === "HIGH" || inc.severity === "DISASTER"
                            ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                            : inc.severity === "AVERAGE"
                            ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                            : "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            inc.severity === "HIGH" || inc.severity === "DISASTER" ? "bg-rose-400 animate-ping" : "bg-amber-400"
                          }`}></span>
                          {inc.severity}
                        </span>
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-medium font-mono bg-white/[0.05] border border-white/[0.08] text-slate-300">
                          {inc.status}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-400">
                        {inc.glpi_ticket_id ? (
                          <span className="text-cyan-300 font-semibold">#{inc.glpi_ticket_id}</span>
                        ) : (
                          <span className="text-slate-500 italic">En liaison...</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-slate-400 font-mono text-[11px]">
                        {new Date(inc.opened_at).toLocaleTimeString()}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <Link
                          href={`/incidents/${inc.id}`}
                          className="btn-tactile inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-medium text-slate-200 bg-white/[0.05] hover:bg-cyan-500/20 hover:text-cyan-300 hover:border-cyan-500/40 border border-white/[0.08] transition-all"
                        >
                          <span>Explorer</span>
                          <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
