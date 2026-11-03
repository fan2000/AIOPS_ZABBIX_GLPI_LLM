"use client";

import { useEffect, useState } from "react";
import { 
  CheckCircle2, 
  Code2, 
  Cpu, 
  Lock, 
  Play, 
  RefreshCw, 
  Server, 
  ShieldAlert, 
  ShieldCheck, 
  Terminal, 
  Timer, 
  UserCheck 
} from "lucide-react";

interface RunbookItem {
  id: string;
  name: string;
  description: string;
  runner_type: string;
  target_os: string;
  timeout_seconds: number;
  required_role: string;
  parameter_schema: any;
}

export default function AutomationPage() {
  const [runbooks, setRunbooks] = useState<RunbookItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchRunbooks = async () => {
      try {
        const res = await fetch("http://localhost:8005/api/v1/actions/runbooks");
        if (res.ok) {
          setRunbooks(await res.json());
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchRunbooks();
  }, []);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wider uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/25">
              Catalogue Certifié
            </span>
            <span className="text-slate-500 text-xs">•</span>
            <span className="text-xs text-slate-400 font-mono">Sandbox Déclarative Niveau 3</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Automation Center & Runbooks
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-0.5">
            Catalogue des procédures autorisées, validation de schéma JSON et politique d&apos;exécution contrôlée
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Zéro Shell Libre</span>
          </span>
        </div>
      </div>

      {/* Grille des Runbooks (Double-Bezel Architecture) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {loading ? (
          <div className="col-span-2 py-16 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
            <span>Chargement du catalogue de runbooks...</span>
          </div>
        ) : (
          runbooks.map((rb) => {
            const hasParams = rb.parameter_schema?.properties && Object.keys(rb.parameter_schema.properties).length > 0;
            return (
              <div
                key={rb.id}
                className="bezel-shell group"
              >
                <div className="bezel-core p-6 space-y-4 h-full flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded border border-cyan-500/20">
                        {rb.id}
                      </span>
                      <span className="text-[10px] uppercase font-mono font-bold px-2 py-0.5 rounded bg-white/[0.05] border border-white/[0.08] text-slate-300">
                        {rb.runner_type}
                      </span>
                    </div>

                    <h4 className="text-base font-bold text-white tracking-tight">
                      {rb.name}
                    </h4>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      {rb.description}
                    </p>

                    {hasParams && (
                      <div className="p-3 rounded-lg bg-obsidian-950/80 border border-white/[0.06] text-xs space-y-1">
                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                          Paramètres du schéma :
                        </span>
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {Object.keys(rb.parameter_schema.properties).map((prop) => (
                            <span
                              key={prop}
                              className="px-2 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-cyan-300 font-mono text-[11px]"
                            >
                              {prop}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="pt-4 border-t border-white/[0.06] flex flex-wrap items-center justify-between text-xs text-slate-400 font-mono gap-2">
                    <span className="flex items-center gap-1.5">
                      <Server className="w-3.5 h-3.5 text-slate-500" />
                      <span>OS : </span>
                      <strong className="text-slate-200 capitalize font-normal">{rb.target_os}</strong>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5 text-amber-500" />
                      <span>Rôle : </span>
                      <strong className="text-amber-400 font-normal">{rb.required_role}</strong>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Timer className="w-3.5 h-3.5 text-cyan-500" />
                      <span>Timeout : </span>
                      <strong className="text-slate-200 font-normal">{rb.timeout_seconds}s</strong>
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
