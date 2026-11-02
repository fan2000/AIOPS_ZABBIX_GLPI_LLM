"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, Filter, Search } from "lucide-react";

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

  useEffect(() => {
    const fetchIncidents = async () => {
      try {
        let url = "http://localhost:8005/api/v1/incidents?limit=50";
        if (severityFilter) url += `&severity=${severityFilter}`;
        if (statusFilter) url += `&status=${statusFilter}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          setIncidents(data);
        }
      } catch (e) {
        console.error(e);
      }
    };
    fetchIncidents();
  }, [severityFilter, statusFilter]);

  const filtered = incidents.filter((i) =>
    i.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    i.primary_asset_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    i.incident_number.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Console des Incidents IT</h2>
          <p className="text-sm text-slate-400">
            Gestion consolidée des alertes Zabbix et des tickets GLPI associés
          </p>
        </div>
      </div>

      {/* Barre de filtres */}
      <div className="p-4 rounded-xl bg-navy-800 border border-navy-700 flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[200px] relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Rechercher par équipement, alerte ou ticket..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-navy-900 border border-navy-700 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-cyan-400"
          />
        </div>

        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-navy-900 border border-navy-700 text-xs text-slate-200 focus:outline-none focus:border-cyan-400"
        >
          <option value="">Toutes les gravités</option>
          <option value="HIGH">High</option>
          <option value="DISASTER">Disaster</option>
          <option value="AVERAGE">Average</option>
          <option value="WARNING">Warning</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-navy-900 border border-navy-700 text-xs text-slate-200 focus:outline-none focus:border-cyan-400"
        >
          <option value="">Tous les statuts</option>
          <option value="OPEN">Ouvert</option>
          <option value="CORRELATED">Corrélé</option>
          <option value="WAITING_APPROVAL">En attente d&apos;approbation</option>
          <option value="RECOVERY_OBSERVED">Recovery observé</option>
          <option value="RESOLVED">Résolu</option>
        </select>
      </div>

      {/* Liste des incidents */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm bg-navy-800 rounded-xl border border-navy-700">
            Aucun incident ne correspond aux critères.
          </div>
        ) : (
          filtered.map((inc) => (
            <div
              key={inc.id}
              className="p-5 rounded-xl bg-navy-800 border border-navy-700 hover:border-cyan-500/40 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
            >
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-xs font-bold text-cyan-400">{inc.incident_number}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    inc.severity === "HIGH" || inc.severity === "DISASTER"
                      ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                      : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                  }`}>
                    {inc.severity}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-700/60 text-slate-300">
                    {inc.status}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white">{inc.title}</h4>
                <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
                  <span>Équipement: <strong className="text-slate-200">{inc.primary_asset_name}</strong></span>
                  <span>Ticket GLPI: <strong className="text-cyan-400 font-mono">{inc.glpi_ticket_id ? `#${inc.glpi_ticket_id}` : "En cours"}</strong></span>
                  <span>Détecté à: {new Date(inc.opened_at).toLocaleTimeString()}</span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <Link
                  href={`/incidents/${inc.id}`}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 transition-all"
                >
                  <span>Détail & Diagnostic</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
