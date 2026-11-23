"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Bot,
  ExternalLink,
  GitBranch,
  KeyRound,
  LayoutDashboard,
  LogOut,
  ShieldCheck,
  Terminal,
  UserCheck,
  UserCog,
  Users,
} from "lucide-react";
import {
  API_BASE_URL,
  AuthUserSummary,
  apiFetch,
  getStoredAuthUser,
  logout,
} from "@/lib/api";

const NAV_ITEMS = [
  { name: "Tableau de Bord", href: "/", icon: LayoutDashboard, badge: "NOC" },
  { name: "Incidents AIOps", href: "/incidents", icon: AlertTriangle },
  { name: "Knowledge Center", href: "/knowledge", icon: BookOpen, badge: "RAG" },
  { name: "AI Operations", href: "/ai-operations", icon: Bot, badge: "9 Agents" },
  { name: "Automation Center", href: "/automation", icon: Terminal, badge: "Niv.3" },
  { name: "Flux & Architecture", href: "/architecture-flow", icon: GitBranch },
  { name: "Mon Profil & MFA", href: "/profile", icon: UserCog, badge: "2FA" },
];

export function Navigation() {
  const pathname = usePathname();
  const router = useRouter();
  const [authUser, setAuthUser] = useState<AuthUserSummary | null>(null);
  const [liveLatencyMs, setLiveLatencyMs] = useState<number | null>(null);
  const [llmOnline, setLlmOnline] = useState<boolean>(false);

  useEffect(() => {
    setAuthUser(getStoredAuthUser());
    const syncAuth = () => setAuthUser(getStoredAuthUser());
    window.addEventListener("aiops-auth-changed", syncAuth);

    const fetchTelemetry = async () => {
      try {
        const res = await apiFetch("/api/v1/ai/status");
        if (res.ok) {
          const data = await res.json();
          setLiveLatencyMs(typeof data.avg_latency_ms === "number" ? data.avg_latency_ms : null);
          setLlmOnline(Boolean(data.llm_health?.online));
        }
      } catch {
        // Silencieux si API indisponible
      }
    };
    fetchTelemetry();
    const timer = setInterval(fetchTelemetry, 15000);
    return () => {
      window.removeEventListener("aiops-auth-changed", syncAuth);
      clearInterval(timer);
    };
  }, []);

  const handleLogout = async () => {
    await logout(false);
    router.replace("/login");
  };

  const navLinks =
    authUser?.role?.toLowerCase() === "admin"
      ? [
          ...NAV_ITEMS,
          { name: "Utilisateurs & Rôles", href: "/admin/users", icon: Users, badge: "IAM" },
        ]
      : NAV_ITEMS;

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
          Supervision &amp; Pilotage
        </div>
        {navLinks.map((item) => {
          const Icon = item.icon;
          const isActive =
            pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));
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
                <div
                  className={`p-1 rounded-lg transition-colors ${
                    isActive
                      ? "text-cyan-400 bg-cyan-500/20"
                      : "text-slate-400 group-hover:text-slate-200"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <span className="font-medium tracking-tight">{item.name}</span>
              </div>

              {item.badge && (
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold transition-all ${
                    isActive
                      ? "bg-cyan-500/25 text-cyan-300 border border-cyan-500/40"
                      : "bg-white/[0.04] text-slate-400 border border-white/[0.06] group-hover:text-slate-300"
                  }`}
                >
                  {item.badge}
                </span>
              )}

              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-r-full bg-cyan-400 shadow-[0_0_8px_#38bdf8]"></div>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Session Opérateur JWT + Statut Réel */}
      <div className="p-4 border-t border-white/[0.06] space-y-3">
        <div className="bezel-shell">
          <div className="bezel-core p-3 space-y-2">
            {authUser ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <Link
                    href="/profile"
                    className="flex items-center gap-1.5 text-emerald-400 hover:text-emerald-300 font-semibold truncate"
                  >
                    <UserCheck className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{authUser.username}</span>
                  </Link>
                  <button
                    onClick={handleLogout}
                    title="Se déconnecter"
                    className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-white/[0.05] transition-colors"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <span>
                    Rôle : <strong className="text-cyan-400 uppercase">{authUser.role}</strong>
                  </span>
                  <span
                    className={
                      authUser.mfa_enabled ? "text-emerald-400 font-semibold" : "text-amber-400"
                    }
                  >
                    {authUser.mfa_enabled ? "2FA ✓" : "Sans 2FA"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
                  <span>Entités : {(authUser.allowed_entities || ["0"]).join(",")}</span>
                  <Link href="/profile" className="text-cyan-400 hover:underline">
                    Profil
                  </Link>
                </div>
              </div>
            ) : (
              <Link
                href="/login"
                className="w-full btn-tactile flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white/[0.04] hover:bg-cyan-500/15 border border-white/[0.08] text-[11px] font-medium text-slate-200"
              >
                <span className="flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Connexion (Sign-In)</span>
                </span>
                <span className="text-[10px] text-cyan-400 font-mono">→</span>
              </Link>
            )}
          </div>
        </div>

        <div className="bezel-shell">
          <div className="bezel-core p-3 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 text-[11px] font-medium flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                Orchestrateur IA
              </span>
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                {llmOnline ? "LLM Live" : "Hybride"}
              </span>
            </div>

            <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-slate-400 font-mono">
              <span className="text-slate-400">Latence moy.</span>
              <span className="text-cyan-400 font-semibold">
                {liveLatencyMs !== null ? `${liveLatencyMs} ms` : "—"}
              </span>
            </div>

            <div className="flex items-center justify-between pt-1 text-[11px]">
              <a
                href={`${API_BASE_URL}/docs`}
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
