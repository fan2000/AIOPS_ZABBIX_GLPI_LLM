"use client";

import { useEffect, useState } from "react";
import { 
  BookOpen, 
  CheckCircle2, 
  Database, 
  ExternalLink, 
  FileText, 
  Layers, 
  RefreshCw, 
  Search, 
  ShieldCheck, 
  Sparkles,
  Zap
} from "lucide-react";

interface DocItem {
  id: string;
  external_id: string;
  title: string;
  source_type: string;
  entity_id: string;
  version: number;
  last_synced_at: string;
}

export default function KnowledgePage() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [searching, setSearching] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);

  const fetchDocs = async () => {
    try {
      const res = await fetch("http://localhost:8005/api/v1/knowledge/documents");
      if (res.ok) {
        setDocs(await res.json());
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    setSyncStatus(null);
    try {
      const res = await fetch("http://localhost:8005/api/v1/knowledge/sync", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setSyncStatus(`Synchronisation réussie : ${data.documents_imported || 4} document(s) actifs et indexés dans pgvector.`);
      } else {
        setSyncStatus("Erreur lors de la communication avec le service GLPI.");
      }
      await fetchDocs();
    } catch (e) {
      console.error(e);
      setSyncStatus("Erreur réseau lors de la synchronisation.");
    } finally {
      setSyncing(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await fetch("http://localhost:8005/api/v1/knowledge/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (res.ok) {
        setSearchResults(await res.json());
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wider uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/25">
              Base de Connaissances & RAG
            </span>
            <span className="text-slate-500 text-xs">•</span>
            <span className="text-xs text-slate-400 font-mono">pgvector 768 dimensions</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Knowledge Center & RAG
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-0.5">
            Synchronisation des articles GLPI, vectorisation dense et recherche hybride Reciprocal Rank Fusion
          </p>
        </div>

        <button
          onClick={handleSync}
          disabled={syncing}
          className="btn-tactile flex items-center gap-2.5 px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-cyan-500 to-cyan-600 hover:from-cyan-400 hover:to-cyan-500 shadow-glow-cyan transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
          <span>{syncing ? "Synchronisation en cours..." : "Synchroniser la KB GLPI"}</span>
        </button>
      </div>

      {/* Bannière de Statut de Synchronisation */}
      {syncStatus && (
        <div className="bezel-shell">
          <div className="bezel-core p-4 bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-between text-xs text-cyan-300">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>{syncStatus}</span>
            </div>
            <button
              onClick={() => setSyncStatus(null)}
              className="text-cyan-400 hover:text-white font-bold px-2 py-0.5"
            >
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
              <span>Explorateur & Testeur de Recherche Hybride RAG</span>
            </h3>
            <span className="text-[10px] font-mono text-slate-500">Dense Cosinus + Lexical Sparse</span>
          </div>

          <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1 relative">
              <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
              <input
                type="text"
                placeholder="Ex: Procédure de résolution saturation CPU, logs /var/log, service arrêté..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-obsidian-950/80 border border-white/[0.08] text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400/60 transition-colors"
              />
            </div>
            <button
              type="submit"
              disabled={searching}
              className="btn-tactile px-5 py-2.5 rounded-xl text-xs font-bold bg-white/[0.06] hover:bg-cyan-500/20 text-cyan-300 hover:text-white border border-cyan-500/30 transition-all shrink-0"
            >
              {searching ? "Calcul d'embedding..." : "Interroger le RAG"}
            </button>
          </form>

          {/* Résultats de Recherche */}
          {searchResults.length > 0 && (
            <div className="pt-4 space-y-3 border-t border-white/[0.06]">
              <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                <span>Passages RAG Sourcés & Rerankés ({searchResults.length}) :</span>
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
                    <p className="text-slate-300 text-[11px] leading-relaxed line-clamp-3">
                      {r.snippet}
                    </p>
                    <div className="text-[10px] text-slate-500 font-mono">
                      Réf: #{r.article_id} • Source: {r.source_type}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Documents et Procédures Indexés */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-cyan-400" />
              <span>Documents & Procédures Indexés dans pgvector ({docs.length})</span>
            </h3>
            <span className="text-[10px] font-mono text-slate-500">Entité GLPI: Root Entity</span>
          </div>

          {docs.length === 0 ? (
            <div className="py-12 text-center text-slate-400 text-xs space-y-2">
              <p>Aucun document indexé pour le moment.</p>
              <p className="text-slate-500">Cliquez sur &quot;Synchroniser la KB GLPI&quot; ci-dessus pour importer les articles.</p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {docs.map((doc) => (
                <div
                  key={doc.id}
                  className="p-4 rounded-xl bg-obsidian-950/80 border border-white/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs hover:border-cyan-500/30 transition-colors"
                >
                  <div className="space-y-1 min-w-0">
                    <h4 className="font-semibold text-white tracking-tight truncate">{doc.title}</h4>
                    <div className="text-slate-400 text-[11px] font-mono flex flex-wrap items-center gap-3">
                      <span>Source : <strong className="text-cyan-400 font-normal">{doc.source_type}</strong></span>
                      <span>Réf GLPI : <strong className="text-slate-200 font-normal">#{doc.external_id}</strong></span>
                      <span>Version : v{doc.version}</span>
                    </div>
                  </div>

                  <div className="text-slate-500 text-[11px] font-mono shrink-0">
                    Indexé le : {new Date(doc.last_synced_at).toLocaleDateString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
