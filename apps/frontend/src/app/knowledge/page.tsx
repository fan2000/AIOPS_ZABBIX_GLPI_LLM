"use client";

import { useEffect, useState } from "react";
import { BookOpen, RefreshCw, Search, ShieldCheck } from "lucide-react";

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
    try {
      await fetch("http://localhost:8005/api/v1/knowledge/sync", { method: "POST" });
      await fetchDocs();
    } catch (e) {
      console.error(e);
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
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Knowledge Center & RAG</h2>
          <p className="text-sm text-slate-400">
            Articles GLPI, runbooks et base vectorielle pgvector
          </p>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-navy-900 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
          <span>{syncing ? "Synchronisation..." : "Synchroniser la KB GLPI"}</span>
        </button>
      </div>

      {/* Recherche sémantique RAG */}
      <div className="p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-4">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <Search className="w-4 h-4 text-cyan-400" />
          Testeur de Recherche Hybride RAG (Vecteur + Mots-clés)
        </h3>
        <form onSubmit={handleSearch} className="flex gap-3">
          <input
            type="text"
            placeholder="Ex: Procédure de résolution CPU élevé Windows..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 px-4 py-2.5 rounded-lg bg-navy-900 border border-navy-700 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-cyan-400"
          />
          <button
            type="submit"
            disabled={searching}
            className="px-4 py-2.5 rounded-lg text-xs font-bold bg-navy-700 hover:bg-navy-600 text-cyan-400 border border-cyan-500/30 transition-all"
          >
            {searching ? "Recherche..." : "Rechercher"}
          </button>
        </form>

        {searchResults.length > 0 && (
          <div className="pt-4 space-y-3 border-t border-navy-700">
            <h4 className="text-xs font-semibold text-slate-400 uppercase">Passages RAG Retrouvés :</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {searchResults.map((r, i) => (
                <div key={i} className="p-3.5 rounded-lg bg-navy-900 border border-navy-700 text-xs space-y-1.5">
                  <div className="flex items-center justify-between font-semibold text-white">
                    <span>{r.title}</span>
                    <span className="text-[10px] text-cyan-400 font-mono">Score: {r.relevance_score}</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">{r.snippet}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Documents indexés */}
      <div className="p-6 rounded-xl bg-navy-800 border border-navy-700 space-y-4">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-cyan-400" />
          Documents et Procédures Indexés ({docs.length})
        </h3>
        {docs.length === 0 ? (
          <p className="text-xs text-slate-400">Aucun document indexé pour l&apos;instant. Cliquez sur &quot;Synchroniser la KB GLPI&quot;.</p>
        ) : (
          <div className="space-y-2.5">
            {docs.map((doc) => (
              <div
                key={doc.id}
                className="p-3.5 rounded-lg bg-navy-900 border border-navy-700/60 flex items-center justify-between text-xs"
              >
                <div>
                  <h4 className="font-semibold text-white">{doc.title}</h4>
                  <div className="text-slate-400 text-[11px] mt-0.5">
                    Source: <span className="text-cyan-400 font-mono">{doc.source_type}</span> • Réf: #{doc.external_id} • Version: {doc.version}
                  </div>
                </div>
                <div className="text-slate-400 text-[11px]">
                  Synchro: {new Date(doc.last_synced_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
