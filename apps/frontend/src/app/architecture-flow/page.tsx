"use client";

import { useEffect, useState } from "react";
import { 
  Activity, 
  ArrowRight, 
  Bot, 
  BrainCircuit, 
  CheckCircle2, 
  Clock, 
  Cpu, 
  Database, 
  ExternalLink, 
  Layers, 
  Network, 
  RefreshCw, 
  Server, 
  ShieldCheck, 
  Sparkles, 
  Terminal, 
  UserCheck, 
  Zap 
} from "lucide-react";

interface PipelineNode {
  id: string;
  name: string;
  category: string;
  status: "idle" | "running" | "completed" | "waiting_approval";
  latency: string;
  description: string;
}

const DEFAULT_NODES: PipelineNode[] = [
  {
    id: "zabbix",
    name: "Zabbix Server 7.0",
    category: "Supervision IT",
    status: "completed",
    latency: "12ms",
    description: "Détection du trigger et émission du webhook signé HMAC-SHA256 vers la Gateway",
  },
  {
    id: "gateway",
    name: "FastAPI Gateway",
    category: "Ingestion & Sécurité",
    status: "completed",
    latency: "18ms",
    description: "Validation HMAC, normalisation et vérification d'idempotence des événements",
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
    description: "Coordination des 7 agents (Incident, Corrélation, RAG, Diagnostic, Résolution...)",
  },
  {
    id: "glpi",
    name: "GLPI REST API",
    category: "ITSM & CMDB",
    status: "completed",
    latency: "85ms",
    description: "Liaison équipement CMDB, création ticket d'incident et suivi privé enrichi",
  },
  {
    id: "rag",
    name: "pgvector RAG Engine",
    category: "Recherche Connaissances",
    status: "completed",
    latency: "45ms",
    description: "Recherche hybride (dense cosinus pgvector + sparse textuel) et citations KB",
  },
  {
    id: "technician",
    name: "Technicien Opérateur",
    category: "Validation Humaine",
    status: "waiting_approval",
    latency: "En attente",
    description: "Validation explicite Niveau 3 requise avant exécution de l'action de remédiation",
  },
  {
    id: "remediation",
    name: "Moteur de Runbooks",
    category: "Remédiation Contrôlée",
    status: "idle",
    latency: "--",
    description: "Exécution sandboxée (PowerShell/SSH/Ansible) et vérification de retour d'état Zabbix",
  },
];

const NODE_ICONS: Record<string, React.ReactNode> = {
  zabbix: <Server className="w-4 h-4 text-rose-400" />,
  gateway: <ShieldCheck className="w-4 h-4 text-cyan-400" />,
  redis: <Database className="w-4 h-4 text-amber-400" />,
  orchestrator: <BrainCircuit className="w-4 h-4 text-purple-400" />,
  glpi: <Layers className="w-4 h-4 text-blue-400" />,
  rag: <Cpu className="w-4 h-4 text-emerald-400" />,
  technician: <UserCheck className="w-4 h-4 text-yellow-400" />,
  remediation: <Terminal className="w-4 h-4 text-indigo-400" />,
};

export default function ArchitectureFlowPage() {
  const [nodes, setNodes] = useState<PipelineNode[]>(DEFAULT_NODES);
  const [selectedNode, setSelectedNode] = useState<PipelineNode>(DEFAULT_NODES[3]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [sites, setSites] = useState<any[]>([
    {
      site_code: "PAR-DC1",
      name: "Datacenter Principal Paris (Core)",
      role: "PRIMARY_DC",
      network_zones: ["CORE", "DMZ", "MANAGEMENT"],
      zabbix_proxy: "zbx-proxy-par-dc1",
      glpi_entity_id: "1",
      ha_mode: "Active-Active Cluster",
      wan_redundancy: "Dual MPLS + SD-WAN IPsec",
      status: "ONLINE",
      active_incidents: 0,
    },
    {
      site_code: "LYN-DC2",
      name: "Datacenter Secours Lyon (PRA / DR)",
      role: "DR_FAILOVER_DC",
      network_zones: ["CORE", "DMZ", "DR_REPLICA"],
      zabbix_proxy: "zbx-proxy-lyn-dc2",
      glpi_entity_id: "2",
      ha_mode: "Active-Standby / Streaming Replication",
      wan_redundancy: "Dual Fiber + BGP Multi-Homing",
      status: "ONLINE",
      active_incidents: 0,
    },
    {
      site_code: "MAR-EDGE-01",
      name: "Site Régional & Industriel Marseille (Edge / OT)",
      role: "REGIONAL_BRANCH_OT",
      network_zones: ["EDGE", "OT"],
      zabbix_proxy: "zbx-proxy-mar-edge-01",
      glpi_entity_id: "3",
      ha_mode: "Local Proxy Buffer (Offline Resilient 72h)",
      wan_redundancy: "SD-WAN + 5G LTE Failover",
      status: "ONLINE",
      active_incidents: 0,
    },
    {
      site_code: "CLD-EU-WEST",
      name: "Zone Cloud Hybride Europe (Kubernetes VPC)",
      role: "HYBRID_CLOUD_VPC",
      network_zones: ["CLOUD", "DMZ"],
      zabbix_proxy: "zbx-proxy-cld-eu-west",
      glpi_entity_id: "4",
      ha_mode: "Multi-AZ Auto-Scaling Group (3 AZs)",
      wan_redundancy: "Direct Connect + VPN BGP",
      status: "ONLINE",
      active_incidents: 0,
    },
  ]);
  const [readinessScore, setReadinessScore] = useState<number>(100);

  const fetchFlowStatus = async () => {
    try {
      setIsRefreshing(true);
      const [resFlow, resTopo, resProd] = await Promise.all([
        fetch("http://localhost:8005/api/v1/system/flow-status").catch(() => null),
        fetch("http://localhost:8005/api/v1/system/multi-site-topology").catch(() => null),
        fetch("http://localhost:8005/api/v1/system/production-readiness").catch(() => null),
      ]);
      if (resFlow && resFlow.ok) {
        const data = await resFlow.json();
        if (data.nodes && data.nodes.length > 0) {
          setNodes(data.nodes);
          setSelectedNode((prev) => data.nodes.find((n: PipelineNode) => n.id === prev.id) || data.nodes[0]);
        }
      }
      if (resTopo && resTopo.ok) {
        const topoData = await resTopo.json();
        if (topoData.sites) setSites(topoData.sites);
      }
      if (resProd && resProd.ok) {
        const prodData = await resProd.json();
        if (prodData.overall_score) setReadinessScore(prodData.overall_score);
      }
    } catch (e) {
      console.error("Erreur flux d'architecture:", e);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchFlowStatus();
    const interval = setInterval(fetchFlowStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status: PipelineNode["status"]) => {
    switch (status) {
      case "completed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            COMPLETED
          </span>
        );
      case "waiting_approval":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            WAITING L3
          </span>
        );
      case "running":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-spin"></span>
            RUNNING
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold font-mono bg-slate-800 text-slate-400 border border-slate-700">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
            IDLE
          </span>
        );
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold font-mono tracking-wider bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Network className="w-3 h-3" />
              TEMPS RÉEL & TOPOLOGIE EN Transit
            </span>
          </div>
          <h2 className="text-3xl font-extrabold text-white tracking-tight">Flux d&apos;Architecture AIOps</h2>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Suivi temps réel de la progression d&apos;un incident à travers la chaîne de traitement : de l&apos;alerte Zabbix à la remédiation validée en sandbox.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchFlowStatus}
            disabled={isRefreshing}
            className="btn-tactile inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-obsidian-850 hover:bg-obsidian-800 border border-obsidian-700/60 text-xs font-medium text-slate-300 hover:text-white"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-cyan-400" : ""}`} />
            <span>Actualiser</span>
          </button>

          <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-xl bg-obsidian-900/80 border border-obsidian-750/70 shadow-bevel">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
            </span>
            <span className="text-xs font-mono font-medium text-slate-300">Topologie Live</span>
          </div>
        </div>
      </div>

      {/* Main Grid: 2 Cols for Topologie Nodes, 1 Col for Selected Node Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Schéma de flux interactif */}
        <div className="lg:col-span-2 bezel-shell">
          <div className="bezel-core space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-obsidian-750/70">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                  <Layers className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Pipeline des 8 Nœuds de Traitement</h3>
                  <p className="text-xs text-slate-400">Cliquez sur un composant pour inspecter ses contrats et métriques</p>
                </div>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Ordre 1 &rarr; 8
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              {nodes.map((node, index) => {
                const isSelected = selectedNode?.id === node.id;
                const icon = NODE_ICONS[node.id] || <Activity className="w-4 h-4 text-cyan-400" />;

                return (
                  <div
                    key={node.id}
                    onClick={() => setSelectedNode(node)}
                    className={`btn-tactile p-4 rounded-xl border text-left cursor-pointer flex flex-col justify-between transition-all duration-200 ${
                      isSelected
                        ? "bg-obsidian-900 border-cyan-400/80 shadow-glow-cyan"
                        : "bg-obsidian-950/80 border-obsidian-750/70 hover:border-obsidian-600 hover:bg-obsidian-900/60"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2.5">
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-md bg-obsidian-800 text-[10px] font-mono font-bold text-slate-400 flex items-center justify-center border border-obsidian-700/60">
                            {index + 1}
                          </span>
                          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                            {node.category}
                          </span>
                        </div>
                        {getStatusBadge(node.status)}
                      </div>

                      <div className="flex items-center gap-2 mt-1">
                        <div className="w-7 h-7 rounded-lg bg-obsidian-850 border border-obsidian-700/60 flex items-center justify-center shrink-0">
                          {icon}
                        </div>
                        <h4 className="text-sm font-bold text-white tracking-tight">
                          {node.name}
                        </h4>
                      </div>

                      <p className="text-xs text-slate-400 mt-2 line-clamp-2 leading-relaxed">
                        {node.description}
                      </p>
                    </div>

                    <div className="mt-4 pt-2.5 border-t border-obsidian-800/80 flex items-center justify-between text-xs">
                      <span className="text-slate-400 flex items-center gap-1 font-mono">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <strong className="text-slate-200 font-bold">{node.latency}</strong>
                      </span>
                      <span className={`text-[11px] font-semibold flex items-center gap-1 ${isSelected ? "text-cyan-400" : "text-slate-400"}`}>
                        Inspecter <ArrowRight className="w-3 h-3" />
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Détail du composant sélectionné */}
        <div className="bezel-shell">
          <div className="bezel-core space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-obsidian-750/70">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                  <Activity className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Inspecteur de Nœud</h3>
                  <p className="text-xs text-slate-400">Propriétés & garanties de service</p>
                </div>
              </div>
            </div>

            {selectedNode && (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-obsidian-950/90 border border-obsidian-750/70 shadow-inner-bevel space-y-3">
                  <div>
                    <span className="text-[10px] font-mono uppercase tracking-wider text-cyan-400 font-semibold">
                      {selectedNode.category}
                    </span>
                    <h4 className="text-lg font-extrabold text-white mt-0.5 tracking-tight flex items-center gap-2">
                      {NODE_ICONS[selectedNode.id]}
                      {selectedNode.name}
                    </h4>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed">
                    {selectedNode.description}
                  </p>

                  <div className="pt-3 border-t border-obsidian-800 space-y-2 text-xs font-mono">
                    <div className="flex justify-between items-center py-1 border-b border-obsidian-850">
                      <span className="text-slate-400 font-sans">Statut :</span>
                      {getStatusBadge(selectedNode.status)}
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-obsidian-850">
                      <span className="text-slate-400 font-sans">Temps de traitement :</span>
                      <span className="text-cyan-400 font-bold">{selectedNode.latency}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-obsidian-850">
                      <span className="text-slate-400 font-sans">Résilience :</span>
                      <span className="text-emerald-400 font-sans font-semibold">Reprise automatique</span>
                    </div>
                    <div className="flex justify-between items-center py-1">
                      <span className="text-slate-400 font-sans">Contrat I/O :</span>
                      <span className="text-slate-300">Pydantic v2 Typé</span>
                    </div>
                  </div>
                </div>

                {/* Sécurité & Immutabilité */}
                <div className="p-4 rounded-xl bg-cyan-950/20 border border-cyan-500/20 text-xs text-slate-300 space-y-2">
                  <div className="font-bold text-white flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0" />
                    Garantie d&apos;Intégrité AIOps
                  </div>
                  <p className="text-slate-300 leading-relaxed text-[11px]">
                    Chaque transition d&apos;état entre les nœuds est consignée de manière immuable dans PostgreSQL et indexée avec un identifiant de corrélation unique partagé.
                  </p>
                </div>

                {/* Documentation technique rapide */}
                <div className="p-3.5 rounded-xl bg-obsidian-950/60 border border-obsidian-800 text-xs text-slate-400 space-y-1.5">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">
                    Passage de Contexte
                  </span>
                  <p className="text-[11px] leading-relaxed">
                    Les données transitent au format JSON normalisé selon la spécification RFC 7946 / AIOps Standard Event Schema.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Fédération Multi-Sites, Réseaux Complexes & Haute Disponibilité (PROD) */}
      <div className="bezel-shell">
        <div className="bezel-core space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-obsidian-750/70">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">
                  Fédération Multi-Sites, Topologies Réseaux Complexes & Haute Disponibilité (HA / DR)
                </h3>
                <p className="text-xs text-slate-400">
                  Supervision distribuée par Proxies Zabbix, cloisonnement Multi-Entités GLPI, corrélation anti-tempête WAN et continuité RPO=0 / RTO&lt;15s
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                PROD READINESS : {readinessScore}/100
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {sites.map((site) => (
              <div
                key={site.site_code}
                className="p-4 rounded-xl bg-obsidian-950/90 border border-obsidian-750/70 hover:border-cyan-500/40 transition-all space-y-3 flex flex-col justify-between"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
                      {site.site_code}
                    </span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                      {site.status}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-white leading-snug">{site.name}</h4>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {(site.network_zones || []).map((z: string) => (
                      <span
                        key={z}
                        className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-white/[0.05] text-slate-300 border border-white/[0.08]"
                      >
                        Zone {z}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="pt-3 border-t border-obsidian-800 space-y-1.5 text-[11px] font-mono text-slate-400">
                  <div className="flex justify-between">
                    <span className="font-sans">Proxy Zabbix :</span>
                    <span className="text-slate-200">{site.zabbix_proxy}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-sans">Entité GLPI :</span>
                    <span className="text-cyan-400 font-bold">Entité #{site.glpi_entity_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-sans">Mode HA :</span>
                    <span className="text-emerald-400 truncate max-w-[140px]" title={site.ha_mode}>
                      {site.ha_mode}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-sans">Liens WAN :</span>
                    <span className="text-slate-300 truncate max-w-[140px]" title={site.wan_redundancy}>
                      {site.wan_redundancy}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
