"use client";

import { useState } from "react";
import { 
  Activity, 
  ArrowDown, 
  ArrowRight, 
  Bot, 
  CheckCircle2, 
  Clock, 
  Database, 
  Layers, 
  Server, 
  ShieldCheck, 
  Terminal, 
  UserCheck 
} from "lucide-react";

interface PipelineNode {
  id: string;
  name: string;
  category: string;
  status: "idle" | "running" | "completed" | "waiting_approval";
  latency: string;
  description: string;
}

const NODES_DATA: PipelineNode[] = [
  {
    id: "zabbix",
    name: "Zabbix Server 7.0",
    category: "Supervision IT",
    status: "completed",
    latency: "12ms",
    description: "Détection du trigger et émission du webhook signé HTTPS",
  },
  {
    id: "gateway",
    name: "FastAPI Gateway",
    category: "Ingestion & Sécurité",
    status: "completed",
    latency: "18ms",
    description: "Validation HMAC, normalisation et vérification d'idempotence",
  },
  {
    id: "redis",
    name: "Redis Streams",
    category: "Messagerie Asynchrone",
    status: "completed",
    latency: "4ms",
    description: "Stream 'zabbix:events' avec groupe de consommateurs 'orchestrator-group'",
  },
  {
    id: "orchestrator",
    name: "LangGraph Multi-Agents",
    category: "Orchestration IA",
    status: "completed",
    latency: "420ms",
    description: "Coordination des 7 agents (Incident, Corrélation, RAG, Diagnostic...)",
  },
  {
    id: "glpi",
    name: "GLPI REST API",
    category: "ITSM & CMDB",
    status: "completed",
    latency: "85ms",
    description: "Liaison équipement CMDB, création ticket et ajout du suivi privé",
  },
  {
    id: "rag",
    name: "pgvector RAG Engine",
    category: "Recherche Connaissances",
    status: "completed",
    latency: "45ms",
    description: "Recherche hybride (dense cosinus + sparse textuel) et citations KB",
  },
  {
    id: "technician",
    name: "Technicien Opérateur",
    category: "Validation Humaine",
    status: "waiting_approval",
    latency: "En attente",
    description: "Validation explicite Niveau 3 requise pour exécuter l'action",
  },
  {
    id: "remediation",
    name: "Moteur de Runbooks",
    category: "Remédiation Contrôlée",
    status: "idle",
    latency: "--",
    description: "Exécution sandboxée (PowerShell/SSH/Ansible) et vérification Zabbix",
  },
];

export default function ArchitectureFlowPage() {
  const [selectedNode, setSelectedNode] = useState<PipelineNode>(NODES_DATA[3]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-white">Flux d&apos;Architecture & Pipeline Temps Réel</h2>
        <p className="text-sm text-slate-400">
          Visualisation interactive de la progression réelle d&apos;un incident à travers la chaîne AIOps
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Schéma de flux interactif */}
        <div className="lg:col-span-2 p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-6">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            Topologie d&apos;Exécution de l&apos;Incident en Transit
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {NODES_DATA.map((node) => {
              const isSelected = selectedNode.id === node.id;
              return (
                <div
                  key={node.id}
                  onClick={() => setSelectedNode(node)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                    isSelected
                      ? "bg-navy-900 border-cyan-400 shadow-lg shadow-cyan-500/10"
                      : "bg-navy-900/60 border-navy-700 hover:border-slate-500"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{node.category}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      node.status === "completed"
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : node.status === "waiting_approval"
                        ? "bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse"
                        : "bg-slate-700 text-slate-300"
                    }`}>
                      {node.status}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-white">{node.name}</h4>
                  <div className="mt-3 flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-navy-700/60">
                    <span>Latence : <strong className="text-slate-200">{node.latency}</strong></span>
                    <span className="text-cyan-400 text-[11px]">Inspecter &rarr;</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Détail du composant sélectionné */}
        <div className="p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            Détail du Nœud Sélectionné
          </h3>

          <div className="p-4 rounded-xl bg-navy-900 border border-navy-700 space-y-3">
            <div>
              <span className="text-xs text-cyan-400 font-semibold">{selectedNode.category}</span>
              <h4 className="text-base font-bold text-white">{selectedNode.name}</h4>
            </div>

            <div className="text-xs text-slate-300 leading-relaxed">
              {selectedNode.description}
            </div>

            <div className="pt-3 border-t border-navy-700/80 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Statut opérationnel :</span>
                <span className="text-emerald-400 font-semibold uppercase">{selectedNode.status}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Temps de traitement :</span>
                <span className="text-white font-mono">{selectedNode.latency}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Tolérance de panne :</span>
                <span className="text-cyan-400 font-semibold">Reprise automatique</span>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-navy-900/60 border border-cyan-500/20 text-xs text-slate-300 space-y-2">
            <div className="font-semibold text-white flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              Garantie d&apos;Intégrité AIOps
            </div>
            <p>
              Chaque transition d&apos;état entre les nœuds est consignée de manière immuable dans PostgreSQL et indexée avec un identifiant de corrélation unique partagé.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
