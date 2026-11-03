"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  Activity, 
  AlertTriangle, 
  BookOpen, 
  Bot, 
  ExternalLink,
  GitBranch, 
  LayoutDashboard, 
  ShieldCheck,
  Terminal,
  Zap
} from "lucide-react";

const NAV_ITEMS = [
  { name: "Tableau de Bord", href: "/", icon: LayoutDashboard, badge: "NOC" },
  { name: "Incidents AIOps", href: "/incidents", icon: AlertTriangle },
  { name: "Knowledge Center", href: "/knowledge", icon: BookOpen, badge: "RAG" },
  { name: "AI Operations", href: "/ai-operations", icon: Bot, badge: "7 Agents" },
  { name: "Automation Center", href: "/automation", icon: Terminal, badge: "Niv.3" },
  { name: "Flux & Architecture", href: "/architecture-flow", icon: GitBranch },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <aside className="w-72 bg-obsidian-950/95 backdrop-blur-2xl border-r border-white/[0.08] flex flex-col min-h-screen shrink-0 select-none">
      {/* Brand Header avec Double-Bezel */}
      <div className="p-6 border-b border-white/[0.06]">
        <div className="flex items-center gap-3.5">
          <div className="relative group">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-cyan-500 to-indigo-500 rounded-xl blur-sm opacity-60 group-hover:opacity-100 transition duration-300"></div>
            <div className="relative w-10 h-10 rounded-xl bg-obsidian-900 border border-white/20 text-cyan-400 flex items-center justify-center font-bold shadow-bevel">
              <Activity className="w-5 h-5 text-cyan-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-white tracking-tight">AI IT Operations</h1>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-semibold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                PRO
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono tracking-tight flex items-center gap-1.5 mt-0.5">
              <span>Zabbix</span>
              <span className="text-slate-600">•</span>
              <span>GLPI 10</span>
              <span className="text-slate-600">•</span>
              <span className="text-cyan-400">LangGraph</span>
            </p>
          </div>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-5 space-y-1.5">
        <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
          Supervision & Pilotage
        </div>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group relative flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 ${
                isActive
                  ? "bg-gradient-to-r from-cyan-500/15 to-transparent text-white border border-cyan-500/30 shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)]"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] border border-transparent"
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`p-1 rounded-lg transition-colors ${
                  isActive ? "text-cyan-400 bg-cyan-500/20" : "text-slate-400 group-hover:text-slate-200"
                }`}>
                  <Icon className="w-4 h-4" />
                </div>
                <span className="font-medium tracking-tight">{item.name}</span>
              </div>

              {item.badge && (
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold transition-all ${
                  isActive 
                    ? "bg-cyan-500/25 text-cyan-300 border border-cyan-500/40" 
                    : "bg-white/[0.04] text-slate-400 border border-white/[0.06] group-hover:text-slate-300"
                }`}>
                  {item.badge}
                </span>
              )}

              {/* Barre lumineuse d'accent active */}
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-r-full bg-cyan-400 shadow-[0_0_8px_#38bdf8]"></div>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer System Status avec Architecture Double-Bezel */}
      <div className="p-4 border-t border-white/[0.06]">
        <div className="bezel-shell">
          <div className="bezel-core p-3 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 text-[11px] font-medium flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                Orchestrateur IA
              </span>
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Opérationnel
              </span>
            </div>

            <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-slate-400 font-mono">
              <span className="text-slate-400">Fast-Path</span>
              <span className="text-cyan-400 font-semibold">57 ms</span>
            </div>

            <div className="flex items-center justify-between pt-1 text-[11px]">
              <a
                href="http://localhost:8005/docs"
                target="_blank"
                rel="noreferrer"
                className="text-slate-400 hover:text-cyan-300 transition-colors inline-flex items-center gap-1"
              >
                <span>API Swagger</span>
                <ExternalLink className="w-3 h-3" />
              </a>
              <span className="text-[10px] text-slate-400">v1.0.0</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
