"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Database,
  Layers,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { apiFetch, getAuthToken } from "@/lib/api";
import { KnowledgeQualityPanel } from "@/components/KnowledgeQualityPanel";

interface DocItem {
  id: string;
  external_id: string;
  title: string;
  source_type: string;
  entity_id: string;
  version: number;
  last_synced_at: string;
}

interface DocChunkItem {
  id: string;
  chunk_index: number;
  chunk_text: string;
  metadata_fields?: Record<string, any>;
  embedding_model: string;
  embedding_version: number;
  is_fallback_embedding: boolean;
}

interface DlqItem {
  id: string;
  source_type: string;
  external_id: string;
  entity_id: string;
  title: string;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error?: string | null;
  updated_at?: string | null;
}

interface KbStats {
  documents_count: number;
  chunks_count: number;
  fallback_chunks_count: number;
  real_embedding_chunks_count: number;
  contextual_chunks_count?: number;
  chunk_overlap_pct?: number;
  pending_proposals_count: number;
  dlq_pending_count?: number;
  hnsw_index_active: boolean;
  gin_index_active: boolean;
  fts_bilingual_active?: boolean;
  metadata_gin_index_active?: boolean;
  embedding_model: string;
  embedding_provider?: string;
  embedding_version?: number;
  embedding_circuit_state?: string;
  embedding_batch_size?: number;
}

interface KbProposalItem {
  id: string;
  incident_id: string;
  title: string;
  category: string;
  content: string;
  entity_id: string;
  status: string;
  created_by: string;
  reviewed_by?: string | null;
  glpi_kb_id?: string | null;
  created_at: string;
}

interface SyncJobItem {
  id: string;
  source: string;
  status: string;
  documents_imported: number;
  chunks_indexed: number;
  started_at: string;
  finished_at?: string | null;
  error_message?: string | null;
}

const SOURCE_FILTERS = [
  { value: "", label: "Toutes sources" },
  { value: "glpi_kb", label: "GLPI KB" },
  { value: "resolved_ticket", label: "Tickets résolus" },
  { value: "runbook_doc", label: "Runbooks" },
  { value: "wiki", label: "Wiki" },
];

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState<"documents" | "proposals" | "jobs" | "dlq" | "quality">("documents");
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [stats, setStats] = useState<KbStats | null>(null);
  const [proposals, setProposals] = useState<KbProposalItem[]>([]);
  const [syncJobs, setSyncJobs] = useState<SyncJobItem[]>([]);
  const [dlqItems, setDlqItems] = useState<DlqItem[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [osFilter, setOsFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [siteFilter, setSiteFilter] = useState<string>("");
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);
  const [docChunksMap, setDocChunksMap] = useState<Record<string, DocChunkItem[]>>({});
  const [reindexing, setReindexing] = useState(false);
  const [reindexingContextual, setReindexingContextual] = useState(false);
  const [retryingDlq, setRetryingDlq] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [searching, setSearching] = useState(false);
  const [banner, setBanner] = useState<{ kind: "info" | "error"; text: string } | null>(null);

  const loadAll = async () => {
    try {
      const requests: Promise<Response>[] = [
        apiFetch("/api/v1/knowledge/documents"),
        apiFetch("/api/v1/knowledge/stats"),
        apiFetch("/api/v1/knowledge/proposals"),
        apiFetch("/api/v1/knowledge/sync-jobs"),
      ];
      if (getAuthToken()) {
        requests.push(apiFetch("/api/v1/knowledge/dlq"));
      }
      const [docsRes, statsRes, propRes, jobsRes, dlqRes] = await Promise.all(requests);
      if (docsRes.ok) setDocs(await docsRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
      if (propRes.ok) setProposals(await propRes.json());
      if (jobsRes.ok) setSyncJobs(await jobsRes.json());
      if (dlqRes && dlqRes.ok) {
        setDlqItems(await dlqRes.json());
      } else {
        setDlqItems([]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadAll();
    const handler = () => loadAll();
    window.addEventListener("aiops-auth-changed", handler);
    return () => window.removeEventListener("aiops-auth-changed", handler);
  }, []);

  const handleSync = async () => {
    if (!getAuthToken()) {
      setBanner({
        kind: "error",
        text: "Authentification opérateur/admin requise (connectez-vous via Session Opérateur dans le menu de gauche).",
      });
      return;
    }
    setSyncing(true);
    setBanner(null);
    try {
      const res = await apiFetch("/api/v1/knowledge/sync", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setBanner({
          kind: "info",
          text: `Synchronisation réussie : ${data.documents_imported} document(s) et ${data.chunks_indexed} chunk(s) indexés dans pgvector.`,
        });
      } else {
        const err = await res.json().catch(() => ({}));
        setBanner({ kind: "error", text: err.detail || `Erreur synchronisation (HTTP ${res.status})` });
      }
      await loadAll();
    } catch {
      setBanner({ kind: "error", text: "Erreur réseau lors de la synchronisation." });
    } finally {
      setSyncing(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const payload: Record<string, any> = { query, top_k: 6 };
      if (sourceFilter) {
        payload.source_types = [sourceFilter];
      }
      if (osFilter) {
        payload.os = osFilter;
      }
      if (categoryFilter) {
        payload.category = categoryFilter;
      }
      if (siteFilter.trim()) {
        payload.site_code = siteFilter.trim().toUpperCase();
      }
      const res = await apiFetch("/api/v1/knowledge/search", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setSearchResults(await res.json());
      } else {
        const err = await res.json().catch(() => ({}));
        setBanner({ kind: "error", text: err.detail || "Recherche refusée" });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  };

  const handleInspectDoc = async (docId: string) => {
    if (expandedDocId === docId) {
      setExpandedDocId(null);
      return;
    }
    setExpandedDocId(docId);
    if (docChunksMap[docId]) return;
    try {
      const res = await apiFetch(`/api/v1/knowledge/documents/${docId}`);
      if (res.ok) {
        const detail = await res.json();
        setDocChunksMap((prev) => ({ ...prev, [docId]: detail.chunks || [] }));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleReindexFallback = async () => {
    if (!getAuthToken()) {
      setBanner({
        kind: "error",
        text: "Authentification opérateur/admin requise pour réindexer les chunks fallback.",
      });
      return;
    }
    setReindexing(true);
    try {
      const res = await apiFetch("/api/v1/knowledge/reindex-fallback", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setBanner({
          kind: data.failed > 0 ? "error" : "info",
          text: `Réindexation fallback : ${data.reindexed ?? 0}/${data.processed ?? 0} document(s) convertis${
            data.failed > 0 ? ` (${data.failed} placé(s) en DLQ : provider hors ligne)` : ""
          }.`,
        });
        await loadAll();
      } else {
        setBanner({ kind: "error", text: data.detail || `Erreur réindexation HTTP ${res.status}` });
      }
    } finally {
      setReindexing(false);
    }
  };

  const handleReindexContextual = async () => {
    if (!getAuthToken()) {
      setBanner({
        kind: "error",
        text: "Authentification opérateur/admin requise pour réindexer en mode contextuel v2.",
      });
      return;
    }
    setReindexingContextual(true);
    try {
      const res = await apiFetch("/api/v1/knowledge/reindex-contextual", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setDocChunksMap({});
        setBanner({
          kind: "info",
          text: `Réindexation contextuelle v2 : ${data.reindexed ?? 0}/${data.processed ?? 0} document(s) enrichis.`,
        });
        await loadAll();
      } else {
        setBanner({ kind: "error", text: data.detail || `Erreur réindexation contextuelle HTTP ${res.status}` });
      }
    } finally {
      setReindexingContextual(false);
    }
  };

  const handleRetryDlq = async () => {
    if (!getAuthToken()) {
      setBanner({ kind: "error", text: "Authentification opérateur/admin requise." });
      return;
    }
    setRetryingDlq(true);
    try {
      const res = await apiFetch("/api/v1/knowledge/dlq/retry", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setBanner({
          kind: data.failed > 0 ? "error" : "info",
          text: `Relance DLQ : ${data.resolved ?? 0}/${data.processed ?? 0} résolu(s), ${data.failed ?? 0} échec(s).`,
        });
        await loadAll();
      } else {
        setBanner({ kind: "error", text: data.detail || `Erreur relance DLQ HTTP ${res.status}` });
      }
    } finally {
      setRetryingDlq(false);
    }
  };

  const handleProposalAction = async (proposalId: string, decision: "approve" | "reject") => {
    if (!getAuthToken()) {
      setBanner({
        kind: "error",
        text: "Authentification opérateur/admin requise pour valider ou rejeter une proposition KB.",
      });
      return;
    }
    try {
      const res = await apiFetch(`/api/v1/knowledge/proposals/${proposalId}/${decision}`, {
        method: "POST",
        body: JSON.stringify({ publish_to_glpi: true }),
      });
      if (res.ok) {
        const payload = await res.json();
        setBanner({
          kind: "info",
          text:
            decision === "approve"
              ? `Proposition approuvée et indexée dans pgvector (Doc #${payload.indexed_document_id?.slice(0, 8)}).`
              : "Proposition rejetée.",
        });
        await loadAll();
      } else {
        const err = await res.json().catch(() => ({}));
        setBanner({ kind: "error", text: err.detail || `Erreur HTTP ${res.status}` });
      }
    } catch {
      setBanner({ kind: "error", text: "Erreur réseau sur décision KB." });
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wider uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/25">
              Base de Connaissances & RAG Hybride
            </span>
            <span className="text-slate-500 text-xs">•</span>
            <span className="text-xs text-slate-400 font-mono">
              {stats?.embedding_model || "pgvector 768d"}
            </span>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Knowledge Center & RAG
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-0.5">
            Indexation pgvector HNSW + Full-Text GIN RRF, isolation multi-entités GLPI et boucle Feedback IA
          </p>
        </div>

        <button
          onClick={handleSync}
          disabled={syncing}
          className="btn-tactile flex items-center gap-2.5 px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 shadow-glow-cyan transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
          <span>{syncing ? "Synchronisation..." : "Synchroniser la KB GLPI"}</span>
        </button>
      </div>

      {/* Barre de santé RAG Production */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="bezel-shell">
            <div className="bezel-core p-3.5 flex items-center justify-between text-xs">
              <div>
                <div className="text-slate-400 text-[10px] uppercase font-mono">Index pgvector HNSW</div>
                <div className={`font-bold mt-0.5 ${stats.hnsw_index_active ? "text-emerald-400" : "text-amber-400"}`}>
                  {stats.hnsw_index_active ? "ACTIF (Cosinus)" : "INACTIF"}
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                  {stats.embedding_provider || "ollama"} v{stats.embedding_version ?? 1} • circuit {stats.embedding_circuit_state || "closed"}
                </div>
              </div>
              <Database className="w-4 h-4 text-cyan-400 shrink-0" />
            </div>
          </div>

          <div className="bezel-shell">
            <div className="bezel-core p-3.5 flex items-center justify-between text-xs">
              <div>
                <div className="text-slate-400 text-[10px] uppercase font-mono">FTS GIN Bilingue (FR+EN)</div>
                <div className={`font-bold mt-0.5 ${(stats.fts_bilingual_active ?? stats.gin_index_active) ? "text-emerald-400" : "text-amber-400"}`}>
                  {stats.fts_bilingual_active ? "ACTIF (FR+EN+RRF)" : stats.gin_index_active ? "ACTIF (Simple RRF)" : "INACTIF"}
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                  {stats.documents_count} doc(s) • batch {stats.embedding_batch_size ?? 32}
                </div>
              </div>
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            </div>
          </div>

          <div className="bezel-shell">
            <div className="bezel-core p-3.5 flex items-center justify-between gap-2 text-xs">
              <div>
                <div className="text-slate-400 text-[10px] uppercase font-mono">Chunks Vectorisés</div>
                <div className="font-bold text-white mt-0.5 font-mono">
                  {stats.chunks_count} ({stats.real_embedding_chunks_count} réels / {stats.fallback_chunks_count} fb)
                </div>
                <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                  Contextual v2: <strong className="text-cyan-300">{stats.contextual_chunks_count ?? 0}</strong> • overlap{" "}
                  {stats.chunk_overlap_pct ?? 18}% • GIN JSONB {stats.metadata_gin_index_active ? "OK" : "-"}
                </div>
                <div className="flex flex-wrap items-center gap-3 mt-1">
                  {stats.fallback_chunks_count > 0 && (
                    <button
                      onClick={handleReindexFallback}
                      disabled={reindexing}
                      className="inline-flex items-center gap-1 text-[10px] font-mono font-semibold text-amber-300 hover:text-amber-200 underline underline-offset-2 disabled:opacity-50"
                    >
                      <RotateCcw className={`w-3 h-3 ${reindexing ? "animate-spin" : ""}`} />
                      <span>{reindexing ? "Réindexation..." : "Réindexer Fallbacks"}</span>
                    </button>
                  )}
                  <button
                    onClick={handleReindexContextual}
                    disabled={reindexingContextual}
                    className="inline-flex items-center gap-1 text-[10px] font-mono font-semibold text-cyan-300 hover:text-cyan-200 underline underline-offset-2 disabled:opacity-50"
                  >
                    <Sparkles className={`w-3 h-3 ${reindexingContextual ? "animate-spin" : ""}`} />
                    <span>{reindexingContextual ? "Enrichissement..." : "Réindexer Contextuel"}</span>
                  </button>
                </div>
              </div>
              <BookOpen className="w-4 h-4 text-blue-400 shrink-0" />
            </div>
          </div>

          <div className="bezel-shell">
            <div className="bezel-core p-3.5 flex items-center justify-between text-xs">
              <div>
                <div className="text-slate-400 text-[10px] uppercase font-mono">Propositions &amp; DLQ RAG</div>
                <div className="font-bold text-amber-400 mt-0.5 font-mono">
                  {stats.pending_proposals_count} KB • {stats.dlq_pending_count ?? 0} DLQ
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                  {(stats.dlq_pending_count ?? 0) > 0 ? "Reprise DLQ requise" : "Aucune corruption index"}
                </div>
              </div>
              <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
            </div>
          </div>
        </div>
      )}

      {banner && (
        <div className="bezel-shell">
          <div
            className={`bezel-core p-4 flex items-center justify-between text-xs border ${
              banner.kind === "error"
                ? "bg-rose-500/10 border-rose-500/30 text-rose-300"
                : "bg-cyan-500/10 border-cyan-500/30 text-cyan-300"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{banner.text}</span>
            </div>
            <button onClick={() => setBanner(null)} className="font-bold px-2 py-0.5">
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Moteur de Recherche Hybride RAG */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Search className="w-4 h-4 text-cyan-400" />
              <span>Recherche Hybride Native (pgvector HNSW + FTS RRF)</span>
            </h3>
            <span className="text-[10px] font-mono text-slate-400">Isolation multi-entités active</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {SOURCE_FILTERS.map((sf) => (
              <button
                key={sf.value || "all"}
                type="button"
                onClick={() => setSourceFilter(sf.value)}
                className={`px-2.5 py-1 rounded-lg font-mono text-[10px] border transition-colors ${
                  sourceFilter === sf.value
                    ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-300"
                    : "bg-obsidian-950/70 border-white/[0.08] text-slate-400 hover:text-white"
                }`}
              >
                {sf.label}
              </button>
            ))}

            <select
              value={osFilter}
              onChange={(e) => setOsFilter(e.target.value)}
              className="bg-obsidian-950/90 border border-white/[0.1] rounded-lg px-2.5 py-1 font-mono text-[10px] text-slate-200 outline-none focus:border-cyan-500/50"
            >
              <option value="">Tous OS</option>
              <option value="linux">Linux</option>
              <option value="windows">Windows</option>
              <option value="network">Réseau / IOS</option>
            </select>

            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="bg-obsidian-950/90 border border-white/[0.1] rounded-lg px-2.5 py-1 font-mono text-[10px] text-slate-200 outline-none focus:border-cyan-500/50"
            >
              <option value="">Toutes catégories</option>
              <option value="cpu">CPU</option>
              <option value="disk">Disque</option>
              <option value="memory">Mémoire / Swap</option>
              <option value="service">Service</option>
              <option value="network">Réseau</option>
              <option value="database">Base de données</option>
            </select>

            <input
              type="text"
              value={siteFilter}
              onChange={(e) => setSiteFilter(e.target.value)}
              placeholder="Site (ex: DC-PAR-1)"
              className="bg-obsidian-950/90 border border-white/[0.1] rounded-lg px-2.5 py-1 font-mono text-[10px] text-slate-200 placeholder-slate-500 w-32 outline-none focus:border-cyan-500/50"
            />
          </div>

          <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1 relative">
              <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
              <input
                type="text"
                placeholder="Ex: Saturation CPU, /var/log disque plein, service arrêté..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-obsidian-950/80 border border-white/[0.08] text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400/60"
              />
            </div>
            <button
              type="submit"
              disabled={searching}
              className="btn-tactile px-5 py-2.5 rounded-xl text-xs font-bold bg-white/[0.06] hover:bg-cyan-500/20 text-cyan-300 hover:text-white border border-cyan-500/30 transition-all shrink-0"
            >
              {searching ? "Recherche SQL RRF..." : "Interroger le RAG"}
            </button>
          </form>

          {searchResults.length > 0 && (
            <div className="pt-4 space-y-3 border-t border-white/[0.06]">
              <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                <span>Passages RAG Sourcés ({searchResults.length}) :</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {searchResults.map((r, i) => (
                  <div
                    key={i}
                    className="p-4 rounded-xl bg-obsidian-950/80 border border-white/[0.06] text-xs space-y-2 hover:border-cyan-500/30 transition-colors"
                  >
                    <div className="flex items-center justify-between font-semibold text-white">
                      <span className="truncate">{r.title}</span>
                      <span className="text-[10px] text-cyan-400 font-mono bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20 shrink-0 ml-2">
                        Score: {r.relevance_score}
                      </span>
                    </div>
                    <p className="text-slate-300 text-[11px] leading-relaxed line-clamp-3">{r.snippet}</p>
                    <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500 font-mono">
                      <span>Réf: #{r.article_id} • {r.source_type}</span>
                      {r.metadata?.os && (
                        <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-cyan-300">
                          os:{r.metadata.os}
                        </span>
                      )}
                      {r.metadata?.category && r.metadata.category !== "general" && (
                        <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-purple-300">
                          {r.metadata.category}
                        </span>
                      )}
                      {r.metadata?.service && r.metadata.service !== "general" && (
                        <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-emerald-300">
                          {r.metadata.service}
                        </span>
                      )}
                      {r.metadata?.site_code && r.metadata.site_code !== "GLOBAL" && (
                        <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-amber-300">
                          {r.metadata.site_code}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Onglets Documents / Propositions KB / Jobs Sync / DLQ */}
      <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.08] pb-2">
        <button
          onClick={() => setActiveTab("documents")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-colors ${
            activeTab === "documents"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Documents Indexés ({docs.length})
        </button>
        <button
          onClick={() => setActiveTab("proposals")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-colors ${
            activeTab === "proposals"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Propositions KB — Feedback IA ({proposals.length})
        </button>
        <button
          onClick={() => setActiveTab("jobs")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-colors ${
            activeTab === "jobs"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Historique Sync ({syncJobs.length})
        </button>
        <button
          onClick={() => setActiveTab("dlq")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-colors ${
            activeTab === "dlq"
              ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
              : "text-slate-400 hover:text-white"
          }`}
        >
          DLQ Embeddings ({dlqItems.filter((d) => d.status === "pending_retry").length})
        </button>
        <button
          onClick={() => setActiveTab("quality")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-colors ${
            activeTab === "quality"
              ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Qualité RAG, Gaps &amp; GraphRAG
        </button>
      </div>

      {activeTab === "documents" && (
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-3">
            {docs.length === 0 ? (
              <div className="py-10 text-center text-slate-400 text-xs">
                Aucun document indexé sur votre portée d&apos;entité.
              </div>
            ) : (
              docs.map((doc) => {
                const isOpen = expandedDocId === doc.id;
                const docChunks = docChunksMap[doc.id] || [];
                return (
                  <div
                    key={doc.id}
                    className="p-4 rounded-xl bg-obsidian-950/80 border border-white/[0.06] space-y-3 text-xs"
                  >
                    <div
                      onClick={() => handleInspectDoc(doc.id)}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer"
                    >
                      <div className="flex items-start gap-2.5 min-w-0">
                        {isOpen ? (
                          <ChevronDown className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                        )}
                        <div className="space-y-1 min-w-0">
                          <h4 className="font-semibold text-white tracking-tight truncate">{doc.title}</h4>
                          <div className="text-slate-400 text-[11px] font-mono flex flex-wrap items-center gap-3">
                            <span>Source : <strong className="text-cyan-400 font-normal">{doc.source_type}</strong></span>
                            <span>Réf : <strong className="text-slate-200 font-normal">#{doc.external_id}</strong></span>
                            <span>Entité : {doc.entity_id}</span>
                            <span>v{doc.version}</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-cyan-300">
                          Inspecter chunks
                        </span>
                        <div className="text-slate-500 text-[11px] font-mono">
                          Indexé : {new Date(doc.last_synced_at).toLocaleDateString()}
                        </div>
                      </div>
                    </div>

                    {isOpen && (
                      <div className="pt-3 border-t border-white/[0.06] space-y-2">
                        <div className="text-[10px] font-mono uppercase text-slate-400 flex items-center gap-1.5">
                          <Layers className="w-3.5 h-3.5 text-cyan-400" />
                          <span>Chunks vectorisés ({docChunks.length})</span>
                        </div>
                        {docChunks.length === 0 ? (
                          <div className="text-[11px] text-slate-500 italic">Chargement ou aucun chunk enregistré.</div>
                        ) : (
                          docChunks.map((ch) => (
                            <div key={ch.id} className="p-2.5 rounded-lg bg-black/50 border border-white/[0.06] space-y-1">
                              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px]">
                                <span className="text-cyan-300">
                                  Chunk #{ch.chunk_index} • {ch.embedding_model} (v{ch.embedding_version})
                                </span>
                                <span
                                  className={`px-2 py-0.5 rounded border ${
                                    ch.is_fallback_embedding
                                      ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                                      : "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                  }`}
                                >
                                  {ch.is_fallback_embedding ? "Fallback Hash" : "Vecteur Réel"}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-300 line-clamp-3">{ch.chunk_text}</p>
                              {ch.metadata_fields && Object.keys(ch.metadata_fields).length > 0 && (
                                <div className="flex flex-wrap gap-1.5 pt-1 font-mono text-[10px]">
                                  {ch.metadata_fields.os && (
                                    <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-cyan-300">
                                      os:{ch.metadata_fields.os}
                                    </span>
                                  )}
                                  {ch.metadata_fields.category && (
                                    <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-purple-300">
                                      cat:{ch.metadata_fields.category}
                                    </span>
                                  )}
                                  {ch.metadata_fields.service && ch.metadata_fields.service !== "general" && (
                                    <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-emerald-300">
                                      svc:{ch.metadata_fields.service}
                                    </span>
                                  )}
                                  {ch.metadata_fields.section && (
                                    <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-slate-300">
                                      sec:{ch.metadata_fields.section}
                                    </span>
                                  )}
                                  {ch.metadata_fields.site_code && (
                                    <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-amber-300">
                                      site:{ch.metadata_fields.site_code}
                                    </span>
                                  )}
                                  {ch.metadata_fields.has_code_block && (
                                    <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/30 text-cyan-200">
                                      code
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {activeTab === "proposals" && (
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-4">
            {proposals.length === 0 ? (
              <div className="py-10 text-center text-slate-400 text-xs">
                Aucune proposition générée pour le moment. Diagnostiquez ou notez un incident pour alimenter cette file.
              </div>
            ) : (
              proposals.map((prop) => (
                <div
                  key={prop.id}
                  className="p-4 rounded-xl bg-obsidian-950/80 border border-white/[0.08] space-y-3 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="space-y-0.5">
                      <h4 className="font-bold text-white text-sm">{prop.title}</h4>
                      <div className="text-[11px] font-mono text-slate-400">
                        Auteur: {prop.created_by} • Entité: {prop.entity_id}
                        {prop.glpi_kb_id ? ` • GLPI KB #${prop.glpi_kb_id}` : ""}
                      </div>
                    </div>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase border ${
                        prop.status === "approved_published"
                          ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                          : prop.status === "rejected"
                          ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                          : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                      }`}
                    >
                      {prop.status}
                    </span>
                  </div>

                  <div className="p-3 rounded-lg bg-black/40 border border-white/[0.05] text-slate-300 text-[11px] leading-relaxed whitespace-pre-line">
                    {prop.content.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()}
                  </div>

                  {prop.status === "pending_review" && (
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => handleProposalAction(prop.id, "approve")}
                        className="btn-tactile inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 font-semibold"
                      >
                        <ThumbsUp className="w-3.5 h-3.5" />
                        <span>Approuver & Publier (GLPI + RAG)</span>
                      </button>
                      <button
                        onClick={() => handleProposalAction(prop.id, "reject")}
                        className="btn-tactile inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 font-semibold"
                      >
                        <ThumbsDown className="w-3.5 h-3.5" />
                        <span>Rejeter</span>
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {activeTab === "jobs" && (
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-2.5">
            {syncJobs.length === 0 ? (
              <div className="py-10 text-center text-slate-400 text-xs">Aucun job enregistré.</div>
            ) : (
              syncJobs.map((job) => (
                <div
                  key={job.id}
                  className="p-3.5 rounded-xl bg-obsidian-950/80 border border-white/[0.06] flex flex-wrap items-center justify-between gap-3 text-xs font-mono"
                >
                  <div className="flex items-center gap-2.5">
                    <Clock className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="text-white font-semibold">{job.source}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] uppercase ${
                        job.status === "completed"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : "bg-rose-500/15 text-rose-400"
                      }`}
                    >
                      {job.status}
                    </span>
                  </div>
                  <div className="text-slate-400">
                    Docs: <strong className="text-white">{job.documents_imported}</strong> • Chunks:{" "}
                    <strong className="text-cyan-400">{job.chunks_indexed}</strong> •{" "}
                    {new Date(job.started_at).toLocaleString()}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {activeTab === "dlq" && (
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
              <div>
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <span>Dead-Letter Queue Embeddings (Garde Anti-Corruption)</span>
                </h4>
                <p className="text-xs text-slate-400">
                  Documents mis en file d&apos;attente lorsque le fournisseur d&apos;embeddings production est indisponible.
                </p>
              </div>
              <button
                onClick={handleRetryDlq}
                disabled={retryingDlq}
                className="btn-tactile inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 disabled:opacity-50"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${retryingDlq ? "animate-spin" : ""}`} />
                <span>{retryingDlq ? "Relance..." : "Relancer la DLQ"}</span>
              </button>
            </div>

            {dlqItems.length === 0 ? (
              <div className="py-8 text-center text-slate-400 text-xs">
                {getAuthToken()
                  ? "Aucun document en attente dans la DLQ embeddings."
                  : "Connectez-vous en tant qu'opérateur/admin dans le menu latéral pour inspecter la DLQ."}
              </div>
            ) : (
              dlqItems.map((item) => (
                <div
                  key={item.id}
                  className="p-3.5 rounded-xl bg-obsidian-950/80 border border-white/[0.06] space-y-1.5 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-white">{item.title}</span>
                    <span
                      className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded border ${
                        item.status === "resolved"
                          ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                          : "bg-amber-500/15 text-amber-300 border-amber-500/30"
                      }`}
                    >
                      {item.status} ({item.attempts}/{item.max_attempts})
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    Source: {item.source_type} • Réf: #{item.external_id} • Entité: {item.entity_id}
                  </div>
                  {item.last_error && (
                    <div className="text-[11px] font-mono text-rose-300 bg-rose-500/10 p-2 rounded border border-rose-500/20">
                      {item.last_error}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {activeTab === "quality" && <KnowledgeQualityPanel onProposalCreated={loadAll} />}
    </div>
  );
}
