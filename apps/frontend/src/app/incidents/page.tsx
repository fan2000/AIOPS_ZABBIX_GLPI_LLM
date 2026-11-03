"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { 
  AlertCircle, 
  AlertOctagon, 
  AlertTriangle, 
  ArrowRight, 
  Clock, 
  Database, 
  Filter, 
  RefreshCw, 
  Search, 
  Server, 
  ShieldAlert, 
  Sparkles,
  Ticket
} from "lucide-react";

interface Incident {
  id: string;
  incident_number: string;
  title: string;
  severity: string;
  status: string;
  primary_asset_name: string;
  glpi_ticket_id?: string;
  opened_at: string;
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIncidents = async () => {
    setLoading(true);
    setError(null);
    try {
      let url = "http://localhost:8005/api/v1/incidents?limit=50";
      if (severityFilter) url += `&severity=${encodeURIComponent(severityFilter)}`;
      if (statusFilter) url += `&status=${encodeURIComponent(statusFilter)}`;
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setIncidents(Array.isArray(data) ? data : []);
      } else {
        setError(`Erreur API Gateway (${res.status} ${res.statusText})`);
      }
    } catch (e: any) {
      setError("Connexion à l'API Gateway impossible sur le port 8005. Vérifiez que le service backend est actif.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
  }, [severityFilter, statusFilter]);

  const filtered = incidents.filter((i) =>
    i.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    i.primary_asset_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    i.incident_number.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wider uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/25">
              Console de Gestion
            </span>
            <span className="text-slate-500 text-xs">•</span>
            <span className="text-xs text-slate-400 font-mono">Suivi Multi-Critères</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Console des Incidents IT
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-0.5">
            Tri, filtrage chronologique, détection de corrélation et liaison CMDB GLPI
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchIncidents()}
            className="btn-tactile flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium text-slate-300 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${loading ? "animate-spin" : ""}`} />
            <span>Actualiser</span>
          </button>
        </div>
      </div>

      {/* Message d'erreur élégant avec retry */}
      {error && (
        <div className="bezel-shell">
          <div className="bezel-core p-4 bg-amber-500/10 border border-amber-500/30 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
              <span className="text-xs text-amber-300">{error}</span>
            </div>
            <button
              onClick={() => fetchIncidents()}
              className="btn-tactile px-3 py-1 bg-amber-500/20 hover:bg-amber-500/30 rounded-lg text-amber-200 text-xs font-semibold"
            >
              Réessayer
            </button>
          </div>
        </div>
      )}

      {/* Barre de Filtres Raffinée (Linear-Tier) */}
      <div className="bezel-shell">
        <div className="bezel-core p-3 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[220px] relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Rechercher par équipement, numéro, ticket GLPI ou alerte..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg bg-obsidian-950/80 border border-white/[0.08] text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400/60 transition-colors"
            />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-obsidian-950/80 border border-white/[0.08] text-xs text-slate-300 focus:outline-none focus:border-cyan-400/60"
            >
              <option value="">Toutes les gravités</option>
              <option value="HIGH">High (Critique)</option>
              <option value="DISASTER">Disaster (Majeur)</option>
              <option value="AVERAGE">Average (Moyen)</option>
              <option value="WARNING">Warning (Avertissement)</option>
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-obsidian-950/80 border border-white/[0.08] text-xs text-slate-300 focus:outline-none focus:border-cyan-400/60"
            >
              <option value="">Tous les statuts</option>
              <option value="OPEN">Ouvert</option>
              <option value="CORRELATED">Corrélé</option>
              <option value="WAITING_APPROVAL">En attente d&apos;approbation</option>
              <option value="RECOVERY_OBSERVED">Recovery observé</option>
              <option value="RESOLVED">Résolu</option>
            </select>
          </div>
        </div>
      </div>

      {/* Liste des Incidents (Cartes Double-Bezel) */}
      <div className="space-y-3">
        {loading ? (
          <div className="bezel-shell">
            <div className="bezel-core p-12 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
              <span>Chargement des incidents depuis la passerelle AIOps...</span>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="bezel-shell">
            <div className="bezel-core p-16 text-center text-slate-400 text-xs space-y-2">
              <p className="text-sm text-slate-300">Aucun incident ne correspond aux critères de filtre.</p>
              <p className="text-slate-500">Modifiez votre recherche ou réinitialisez les sélecteurs de gravité.</p>
            </div>
          </div>
        ) : (
          filtered.map((inc) => (
            <div
              key={inc.id}
              className="bezel-shell group"
            >
              <div className="bezel-core p-4 md:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-2 flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className="font-mono text-xs font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-0.5 rounded border border-cyan-500/20">
                      {inc.incident_number}
                    </span>
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
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/[0.05] border border-white/[0.08] text-slate-300">
                      {inc.status}
                    </span>
                  </div>

                  <h4 className="text-sm md:text-base font-semibold text-white tracking-tight truncate">
                    {inc.title}
                  </h4>

                  <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <Server className="w-3.5 h-3.5 text-slate-500" />
                      <strong>{inc.primary_asset_name}</strong>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Ticket className="w-3.5 h-3.5 text-cyan-500" />
                      <span>Ticket GLPI: </span>
                      <strong className="text-cyan-300 font-mono">
                        {inc.glpi_ticket_id ? `#${inc.glpi_ticket_id}` : "En liaison..."}
                      </strong>
                    </span>
                    <span className="flex items-center gap-1.5 text-slate-500 font-mono text-[11px]">
                      <Clock className="w-3.5 h-3.5" />
                      {new Date(inc.opened_at).toLocaleTimeString()}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <Link
                    href={`/incidents/${inc.id}`}
                    className="btn-tactile inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 shadow-glow-cyan transition-all"
                  >
                    <span>Détail & Diagnostic</span>
                    <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                  </Link>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
