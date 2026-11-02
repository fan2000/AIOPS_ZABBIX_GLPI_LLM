"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Play, ShieldAlert, Terminal } from "lucide-react";

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
      <div>
        <h2 className="text-2xl font-bold text-white">Automation Center & Runbooks</h2>
        <p className="text-sm text-slate-400">
          Catalogue des procédures automatisées autorisées et règles d&apos;exécution contrôlée
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {loading ? (
          <p className="text-xs text-slate-400">Chargement des runbooks...</p>
        ) : (
          runbooks.map((rb) => (
            <div
              key={rb.id}
              className="p-5 rounded-xl bg-navy-800 border border-navy-700 space-y-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-cyan-400">{rb.id}</span>
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-slate-700 text-slate-300">
                  {rb.runner_type}
                </span>
              </div>
              <h4 className="text-sm font-bold text-white">{rb.name}</h4>
              <p className="text-xs text-slate-300 leading-relaxed">{rb.description}</p>
              <div className="pt-3 border-t border-navy-700/80 flex items-center justify-between text-xs text-slate-400">
                <span>OS Cible : <strong className="text-slate-200 capitalize">{rb.target_os}</strong></span>
                <span>Rôle Requis : <strong className="text-amber-400">{rb.required_role}</strong></span>
                <span>Timeout : <strong className="text-slate-200">{rb.timeout_seconds}s</strong></span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
