"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  Activity, 
  AlertTriangle, 
  BookOpen, 
  Bot, 
  Cpu, 
  GitBranch, 
  LayoutDashboard, 
  Terminal 
} from "lucide-react";

const NAV_ITEMS = [
  { name: "Tableau de Bord", href: "/", icon: LayoutDashboard },
  { name: "Incidents AIOps", href: "/incidents", icon: AlertTriangle },
  { name: "Knowledge Center", href: "/knowledge", icon: BookOpen },
  { name: "AI Operations", href: "/ai-operations", icon: Bot },
  { name: "Automation Center", href: "/automation", icon: Terminal },
  { name: "Flux & Architecture", href: "/architecture-flow", icon: GitBranch },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-navy-800 border-r border-navy-700 flex flex-col min-h-screen">
      <div className="p-6 border-b border-navy-700 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold">
          <Activity className="w-5 h-5 text-cyan-400" />
        </div>
        <div>
          <h1 className="text-base font-bold text-white leading-tight">AI IT Operations</h1>
          <p className="text-xs text-cyan-400 font-medium">Zabbix • GLPI • LangGraph</p>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                  : "text-slate-300 hover:bg-navy-700 hover:text-white"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-navy-700">
        <div className="p-3 rounded-lg bg-navy-900/60 border border-navy-700/60 text-xs">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span>Mode Plateforme</span>
            <span className="text-emerald-400 font-semibold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Actif
            </span>
          </div>
          <p className="text-slate-400">Ollama local & LangGraph</p>
        </div>
      </div>
    </aside>
  );
}
