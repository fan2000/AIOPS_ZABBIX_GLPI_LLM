"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FilePlus2,
  GitBranch,
  Network,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  Sparkles,
  Terminal,
} from "lucide-react";
import { apiFetch, getAuthToken } from "@/lib/api";

interface QualityMetrics {
  total_incidents: number;
  total_analyzed_incidents: number;
  citation_coverage_rate: number;
  avg_relevance_score: number;
  avg_faithfulness_score: number;
  insufficient_evidence_rate: number;
  latest_eval_recall_at_5: number | null;
  latest_eval_mrr: number | null;
  gaps_count: number;
  critical_gaps_count: number;
}

interface KnowledgeGapItem {
  family_key: string;
  sample_incident_id: string;
  sample_title: string;
  recommended_kb_title: string;
  entity_id: string;
  category: string;
  inferred_os: string;
  inferred_service: string;
  incident_count: number;
  analyzed_count: number;
  affected_hosts: string[];
  max_severity: string;
  avg_rag_score: number;
  citation_coverage_rate: number;
  insufficient_evidence_rate: number;
  avg_faithfulness_score: number;
  priority_score: number;
  priority_level: "CRITICAL" | "HIGH" | "MEDIUM";
  has_pending_proposal: boolean;
}

interface GraphNode {
  id: string;
  type: "asset" | "service" | "incident" | "kb_article" | "runbook";
  label: string;
  metadata: Record<string, any>;
}

interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

interface OperationalGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  matched_node_ids: string[];
  stats: {
    assets: number;
    services: number;
    incidents: number;
    kb_articles: number;
    runbooks: number;
    edges: number;
  };
}

const NODE_TYPE_STYLES: Record<string, { label: string; badge: string; icon: any }> = {
  asset: {
    label: "Actif CMDB",
    badge: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
    icon: Server,
  },
  service: {
    label: "Service / Domaine",
    badge: "bg-purple-500/15 text-purple-300 border-purple-500/30",
    icon: Network,
  },
  incident: {
    label: "Incident",
    badge: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    icon: ShieldAlert,
  },
  kb_article: {
    label: "Article KB",
    badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    icon: BookOpen,
  },
  runbook: {
    label: "Runbook",
    badge: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    icon: Terminal,
  },
};

export function KnowledgeQualityPanel({
  onProposalCreated,
}: {
  onProposalCreated?: () => void;
}) {
  const [metrics, setMetrics] = useState<QualityMetrics | null>(null);
  const [gaps, setGaps] = useState<KnowledgeGapItem[]>([]);
  const [graph, setGraph] = useState<OperationalGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [graphQuery, setGraphQuery] = useState("");
  const [nodeTypeFilter, setNodeTypeFilter] = useState<string>("all");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [draftingKey, setDraftingKey] = useState<string | null>(null);
  const [panelBanner, setPanelBanner] = useState<{ kind: "info" | "error"; text: string } | null>(null);

  const loadQualityAndGaps = async () => {
    try {
      const res = await apiFetch("/api/v1/knowledge/gaps?limit=25");
      if (res.ok) {
        const data = await res.json();
        setMetrics(data.metrics || null);
        setGaps(data.gaps || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const loadGraph = async (q?: string) => {
    try {
      const params = new URLSearchParams();
      if (q && q.trim()) params.set("q", q.trim());
      const res = await apiFetch(`/api/v1/knowledge/graph${params.toString() ? `?${params.toString()}` : ""}`);
      if (res.ok) {
        const data: OperationalGraph = await res.json();
        setGraph(data);
        if (data.nodes.length > 0) {
          const preferred = data.matched_node_ids?.[0] || data.nodes[0].id;
          setSelectedNodeId((prev) =>
            prev && data.nodes.some((n) => n.id === prev) ? prev : preferred
          );
        } else {
          setSelectedNodeId(null);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const loadAll = async () => {
    setLoading(true);
    await Promise.all([loadQualityAndGaps(), loadGraph(graphQuery)]);
    setLoading(false);
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleDraftProposal = async (gap: KnowledgeGapItem) => {
    if (!getAuthToken()) {
      setPanelBanner({
        kind: "error",
        text: "Authentification opérateur/admin requise pour créer un brouillon KB dans la file de validation.",
      });
      return;
    }
    setDraftingKey(gap.family_key);
    setPanelBanner(null);
    try {
      const res = await apiFetch("/api/v1/knowledge/gaps/draft-proposal", {
        method: "POST",
        body: JSON.stringify({
          incident_id: gap.sample_incident_id,
          title: gap.recommended_kb_title,
          family_key: gap.family_key,
          category: `AIOps - Gap (${gap.category})`,
          inferred_os: gap.inferred_os,
          affected_hosts: gap.affected_hosts,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setPanelBanner({
          kind: "info",
          text: `Brouillon "${data.title}" ajouté en file de validation KB (statut: ${data.status}).`,
        });
        await loadQualityAndGaps();
        if (onProposalCreated) onProposalCreated();
      } else {
        setPanelBanner({
          kind: "error",
          text: data.detail || `Échec création brouillon (HTTP ${res.status})`,
        });
      }
    } catch {
      setPanelBanner({ kind: "error", text: "Erreur réseau lors de la création du brouillon KB." });
    } finally {
      setDraftingKey(null);
    }
  };

  const handleGraphSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    await loadGraph(graphQuery);
  };

  const handleGraphReset = async () => {
    setGraphQuery("");
    setNodeTypeFilter("all");
    await loadGraph("");
  };

  const nodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const n of graph?.nodes || []) map.set(n.id, n);
    return map;
  }, [graph]);

  const filteredNodes = useMemo(() => {
    if (!graph) return [];
    if (nodeTypeFilter === "all") return graph.nodes;
    return graph.nodes.filter((n) => n.type === nodeTypeFilter);
  }, [graph, nodeTypeFilter]);

  const selectedNode = selectedNodeId ? nodeMap.get(selectedNodeId) || null : null;
  const selectedNeighbors = useMemo(() => {
    if (!graph || !selectedNodeId) return [];
    const items: Array<{ direction: "sortant" | "entrant"; relation: string; other: GraphNode }> = [];
    for (const edge of graph.edges) {
      if (edge.source === selectedNodeId) {
        const target = nodeMap.get(edge.target);
        if (target) items.push({ direction: "sortant", relation: edge.relation, other: target });
      } else if (edge.target === selectedNodeId) {
        const src = nodeMap.get(edge.source);
        if (src) items.push({ direction: "entrant", relation: edge.relation, other: src });
      }
    }
    return items;
  }, [graph, nodeMap, selectedNodeId]);

  return (
    <div className="space-y-6">
      {panelBanner && (
        <div
          className={`p-3.5 rounded-xl border text-xs flex items-center justify-between gap-3 ${
            panelBanner.kind === "error"
              ? "bg-rose-500/10 border-rose-500/30 text-rose-200"
              : "bg-emerald-500/10 border-emerald-500/30 text-emerald-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {panelBanner.kind === "error" ? (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            )}
            <span>{panelBanner.text}</span>
          </div>
          <button onClick={() => setPanelBanner(null)} className="text-[11px] font-mono opacity-70 hover:opacity-100">
            Fermer
          </button>
        </div>
      )}

      {/* Bandeau KPI Qualité RAG */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <div className="p-4 rounded-xl bg-obsidian-950/90 border border-white/[0.08] space-y-1">
          <div className="text-[10px] font-mono uppercase text-slate-400">Recall@5 (Eval)</div>
          <div className="text-2xl font-black text-cyan-400">
            {metrics?.latest_eval_recall_at_5 !== null && metrics?.latest_eval_recall_at_5 !== undefined
              ? `${Math.round(metrics.latest_eval_recall_at_5 * 100)}%`
              : "N/A"}
          </div>
          <div className="text-[11px] text-slate-500 font-mono">
            MRR : {metrics?.latest_eval_mrr !== null && metrics?.latest_eval_mrr !== undefined ? metrics.latest_eval_mrr.toFixed(2) : "—"}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-obsidian-950/90 border border-white/[0.08] space-y-1">
          <div className="text-[10px] font-mono uppercase text-slate-400">Faithfulness (Fidélité)</div>
          <div className="text-2xl font-black text-emerald-400">
            {metrics ? `${Math.round(metrics.avg_faithfulness_score * 100)}%` : "—"}
          </div>
          <div className="text-[11px] text-slate-500 font-mono">Ancrage factuel citations</div>
        </div>

        <div className="p-4 rounded-xl bg-obsidian-950/90 border border-white/[0.08] space-y-1">
          <div className="text-[10px] font-mono uppercase text-slate-400">Couverture Citations</div>
          <div className="text-2xl font-black text-purple-400">
            {metrics ? `${Math.round(metrics.citation_coverage_rate * 100)}%` : "—"}
          </div>
          <div className="text-[11px] text-slate-500 font-mono">
            {metrics?.total_analyzed_incidents ?? 0} incidents analysés
          </div>
        </div>

        <div className="p-4 rounded-xl bg-obsidian-950/90 border border-white/[0.08] space-y-1">
          <div className="text-[10px] font-mono uppercase text-slate-400">Score Pertinence Moy.</div>
          <div className="text-2xl font-black text-white">
            {metrics ? metrics.avg_relevance_score.toFixed(2) : "—"}
          </div>
          <div className="text-[11px] text-slate-500 font-mono">
            Preuves insuff. : {metrics ? `${Math.round(metrics.insufficient_evidence_rate * 100)}%` : "—"}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-obsidian-950/90 border border-amber-500/25 space-y-1">
          <div className="text-[10px] font-mono uppercase text-amber-300">Knowledge Gaps Actifs</div>
          <div className="text-2xl font-black text-amber-400">{metrics?.gaps_count ?? 0}</div>
          <div className="text-[11px] text-rose-300 font-mono">
            {metrics?.critical_gaps_count ?? 0} critique(s)
          </div>
        </div>
      </div>

      {/* Table prioritaire des Knowledge Gaps */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-amber-400" />
                <span>Détection Automatique des Knowledge Gaps ({gaps.length})</span>
              </h3>
              <p className="text-xs text-slate-400">
                Familles d&apos;incidents récurrentes sans citation RAG fiable ou classées &quot;insufficient_evidence&quot;, priorisées pour rédaction KB.
              </p>
            </div>
            <button
              onClick={loadAll}
              disabled={loading}
              className="btn-tactile inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/[0.05] hover:bg-white/[0.1] text-slate-200 border border-white/[0.1]"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Recalculer</span>
            </button>
          </div>

          {gaps.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
              Aucun déficit documentaire majeur détecté sur votre périmètre.
            </div>
          ) : (
            <div className="space-y-2.5">
              {gaps.map((gap) => (
                <div
                  key={gap.family_key}
                  className="p-4 rounded-xl bg-obsidian-950/85 border border-white/[0.06] flex flex-col lg:flex-row lg:items-center justify-between gap-4 text-xs"
                >
                  <div className="space-y-1.5 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold border ${
                          gap.priority_level === "CRITICAL"
                            ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                            : gap.priority_level === "HIGH"
                            ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                            : "bg-slate-500/15 text-slate-300 border-slate-500/30"
                        }`}
                      >
                        {gap.priority_level} • {gap.priority_score}/100
                      </span>
                      <span className="font-bold text-white truncate">{gap.sample_title}</span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-slate-400">
                      <span className="text-cyan-300">{gap.incident_count} incident(s)</span>
                      <span>•</span>
                      <span>Sévérité max : {gap.max_severity}</span>
                      <span>•</span>
                      <span>Citations : {Math.round(gap.citation_coverage_rate * 100)}%</span>
                      <span>•</span>
                      <span>RAG moy. : {gap.avg_rag_score.toFixed(2)}</span>
                      <span>•</span>
                      <span className="text-rose-300">
                        Insuff. preuves : {Math.round(gap.insufficient_evidence_rate * 100)}%
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
                      <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-cyan-300">
                        os:{gap.inferred_os}
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-purple-300">
                        cat:{gap.category}
                      </span>
                      {gap.inferred_service && gap.inferred_service !== "general" && (
                        <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-emerald-300">
                          svc:{gap.inferred_service}
                        </span>
                      )}
                      {gap.affected_hosts.slice(0, 4).map((h) => (
                        <span
                          key={h}
                          className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-slate-300"
                        >
                          {h}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {gap.has_pending_proposal ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-mono text-[11px]">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Brouillon en file</span>
                      </span>
                    ) : (
                      <button
                        onClick={() => handleDraftProposal(gap)}
                        disabled={draftingKey === gap.family_key}
                        className="btn-tactile inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 font-semibold disabled:opacity-50"
                      >
                        <FilePlus2 className="w-3.5 h-3.5" />
                        <span>
                          {draftingKey === gap.family_key ? "Génération..." : "Générer brouillon KB"}
                        </span>
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Explorateur GraphRAG léger opérationnel */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-cyan-400" />
                <span>GraphRAG Opérationnel (Actifs ↔ Services ↔ Incidents ↔ KB ↔ Runbooks)</span>
              </h3>
              <p className="text-xs text-slate-400">
                Navigation contextuelle multi-sauts entre infrastructure CMDB, incidents récurrents, articles cités et runbooks.
              </p>
            </div>

            <form onSubmit={handleGraphSearch} className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={graphQuery}
                  onChange={(e) => setGraphQuery(e.target.value)}
                  placeholder="Filtrer (ex: SRV-TEST-01, cpu, spooler)..."
                  className="pl-8 pr-3 py-1.5 rounded-lg bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/50 w-64"
                />
              </div>
              <button
                type="submit"
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40"
              >
                Focaliser
              </button>
              {graphQuery && (
                <button
                  type="button"
                  onClick={handleGraphReset}
                  className="px-2.5 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white border border-white/[0.08]"
                >
                  Réinitialiser
                </button>
              )}
            </form>
          </div>

          {graph && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
                <button
                  onClick={() => setNodeTypeFilter("all")}
                  className={`px-2.5 py-1 rounded-lg border ${
                    nodeTypeFilter === "all"
                      ? "bg-white/10 text-white border-white/25"
                      : "bg-obsidian-950 text-slate-400 border-white/[0.06]"
                  }`}
                >
                  Tous ({graph.nodes.length})
                </button>
                {(["asset", "service", "incident", "kb_article", "runbook"] as const).map((tp) => {
                  const cfg = NODE_TYPE_STYLES[tp];
                  const count =
                    tp === "asset"
                      ? graph.stats.assets
                      : tp === "service"
                      ? graph.stats.services
                      : tp === "incident"
                      ? graph.stats.incidents
                      : tp === "kb_article"
                      ? graph.stats.kb_articles
                      : graph.stats.runbooks;
                  return (
                    <button
                      key={tp}
                      onClick={() => setNodeTypeFilter(tp)}
                      className={`px-2.5 py-1 rounded-lg border ${
                        nodeTypeFilter === tp
                          ? cfg.badge
                          : "bg-obsidian-950 text-slate-400 border-white/[0.06]"
                      }`}
                    >
                      {cfg.label} ({count})
                    </button>
                  );
                })}
                <span className="ml-auto text-slate-400">{graph.stats.edges} relation(s) typée(s)</span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                <div className="lg:col-span-5 max-h-[380px] overflow-y-auto space-y-1.5 pr-1">
                  {filteredNodes.length === 0 ? (
                    <div className="py-8 text-center text-xs text-slate-500">
                      Aucun nœud correspondant au filtre dans le graphe.
                    </div>
                  ) : (
                    filteredNodes.map((node) => {
                      const st = NODE_TYPE_STYLES[node.type] || NODE_TYPE_STYLES.service;
                      const Icon = st.icon;
                      const active = node.id === selectedNodeId;
                      return (
                        <button
                          key={node.id}
                          onClick={() => setSelectedNodeId(node.id)}
                          className={`w-full text-left p-2.5 rounded-xl border text-xs transition-colors flex items-center gap-2.5 ${
                            active
                              ? "bg-cyan-500/15 border-cyan-500/40 text-white"
                              : "bg-obsidian-950/80 border-white/[0.06] text-slate-300 hover:border-white/20"
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5 shrink-0 text-cyan-400" />
                          <div className="min-w-0 flex-1">
                            <div className="font-semibold truncate">{node.label}</div>
                            <div className="text-[10px] font-mono text-slate-400 flex items-center gap-2">
                              <span>{st.label}</span>
                              {node.metadata?.severity && <span>• {node.metadata.severity}</span>}
                              {node.metadata?.os && <span>• {node.metadata.os}</span>}
                            </div>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>

                <div className="lg:col-span-7 p-4 rounded-xl bg-obsidian-950/90 border border-white/[0.08] space-y-3">
                  {!selectedNode ? (
                    <div className="py-12 text-center text-xs text-slate-500">
                      Sélectionnez un nœud du graphe pour explorer ses relations multi-entités.
                    </div>
                  ) : (
                    <>
                      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-white/[0.06]">
                        <div>
                          <div className="text-[10px] font-mono uppercase text-cyan-400">
                            {NODE_TYPE_STYLES[selectedNode.type]?.label || selectedNode.type}
                          </div>
                          <h4 className="text-sm font-bold text-white">{selectedNode.label}</h4>
                        </div>
                        <span className="text-[10px] font-mono text-slate-400 bg-white/[0.04] px-2 py-0.5 rounded border border-white/[0.08]">
                          {selectedNeighbors.length} connexion(s)
                        </span>
                      </div>

                      {Object.keys(selectedNode.metadata || {}).length > 0 && (
                        <div className="flex flex-wrap gap-1.5 text-[10px] font-mono">
                          {Object.entries(selectedNode.metadata)
                            .filter(([, val]) => val !== null && val !== undefined && val !== "")
                            .slice(0, 6)
                            .map(([k, val]) => (
                              <span
                                key={k}
                                className="px-2 py-0.5 rounded bg-black/50 border border-white/[0.07] text-slate-300"
                              >
                                {k}: {String(val)}
                              </span>
                            ))}
                        </div>
                      )}

                      <div className="space-y-1.5 max-h-[250px] overflow-y-auto">
                        {selectedNeighbors.length === 0 ? (
                          <div className="text-xs text-slate-500 italic">Aucune relation directe enregistrée.</div>
                        ) : (
                          selectedNeighbors.map((nb, idx) => {
                            const cfg = NODE_TYPE_STYLES[nb.other.type] || NODE_TYPE_STYLES.service;
                            return (
                              <button
                                key={`${nb.relation}-${nb.other.id}-${idx}`}
                                onClick={() => setSelectedNodeId(nb.other.id)}
                                className="w-full text-left p-2.5 rounded-lg bg-black/40 border border-white/[0.06] hover:border-cyan-500/40 transition-colors flex flex-wrap items-center justify-between gap-2 text-xs"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className="px-2 py-0.5 rounded font-mono text-[10px] bg-white/[0.06] text-amber-300 shrink-0">
                                    {nb.relation}
                                  </span>
                                  <span className="text-white font-medium truncate">{nb.other.label}</span>
                                </div>
                                <span className={`px-2 py-0.5 rounded font-mono text-[10px] border shrink-0 ${cfg.badge}`}>
                                  {cfg.label}
                                </span>
                              </button>
                            );
                          })
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
