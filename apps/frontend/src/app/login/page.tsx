"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  KeyRound,
  Lock,
  ShieldCheck,
  UserPlus,
} from "lucide-react";
import { login, verifyMfaLogin } from "@/lib/api";

function LoginFormContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams?.get("next") || "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaChallengeToken, setMfaChallengeToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaTargetUser, setMfaTargetUser] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handlePrimarySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const outcome = await login(username.trim(), password);
      if (outcome.mfaRequired && outcome.mfaChallengeToken) {
        setMfaChallengeToken(outcome.mfaChallengeToken);
        setMfaTargetUser(outcome.user?.username || username.trim());
        setMfaCode("");
      } else {
        router.replace(nextPath.startsWith("/") ? nextPath : "/");
      }
    } catch (err: any) {
      setError(err?.message || "Identifiants invalides");
    } finally {
      setLoading(false);
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mfaChallengeToken) return;
    setLoading(true);
    setError(null);
    try {
      await verifyMfaLogin(mfaChallengeToken, mfaCode);
      router.replace(nextPath.startsWith("/") ? nextPath : "/");
    } catch (err: any) {
      setError(err?.message || "Code MFA invalide ou expiré");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md space-y-6">
      <div className="text-center space-y-3">
        <div className="mx-auto w-14 h-14 rounded-2xl bg-obsidian-900 border border-cyan-500/40 flex items-center justify-center shadow-[0_0_24px_rgba(6,182,212,0.2)]">
          <Activity className="w-7 h-7 text-cyan-400" />
        </div>
        <div>
          <h1 className="text-2xl font-black tracking-tight text-white">AI IT Operations</h1>
          <p className="text-xs font-mono text-slate-400 mt-1">
            Authentification Zero-Trust • Zabbix • GLPI 10 • LangGraph
          </p>
        </div>
      </div>

      <div className="bezel-shell">
        <div className="bezel-core p-7 space-y-5">
          <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              {mfaChallengeToken ? (
                <>
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span>Vérification Double Facteur (MFA)</span>
                </>
              ) : (
                <>
                  <KeyRound className="w-4 h-4 text-cyan-400" />
                  <span>Connexion à la console NOC</span>
                </>
              )}
            </h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
              JWT + RBAC
            </span>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-200 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {!mfaChallengeToken ? (
            <form onSubmit={handlePrimarySubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 block">
                  Identifiant ou adresse email
                </label>
                <input
                  type="text"
                  required
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="ex: admin ou ops@aiops.local"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-400"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 block">
                  Mot de passe
                </label>
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-400"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full btn-tactile py-2.5 px-4 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
              >
                <Lock className="w-3.5 h-3.5" />
                <span>{loading ? "Authentification..." : "Se connecter"}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </form>
          ) : (
            <form onSubmit={handleMfaSubmit} className="space-y-4">
              <p className="text-xs text-slate-300 leading-relaxed">
                Compte <strong className="text-white">{mfaTargetUser}</strong> protégé par 2FA. Saisissez le code à 6 chiffres de votre application Authenticator ou un code de secours (<code className="text-cyan-300">XXXX-XXXX</code>).
              </p>

              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 block">
                  Code TOTP (6 chiffres) ou code de secours
                </label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="123456"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-obsidian-950 border border-emerald-500/40 text-sm font-mono tracking-widest text-center text-white outline-none focus:border-emerald-400"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setMfaChallengeToken(null);
                    setError(null);
                  }}
                  className="px-3.5 py-2.5 rounded-xl text-xs font-semibold border border-white/[0.1] text-slate-300 hover:text-white"
                >
                  Retour
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 btn-tactile py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs disabled:opacity-50"
                >
                  {loading ? "Validation..." : "Valider le second facteur"}
                </button>
              </div>
            </form>
          )}

          <div className="pt-4 border-t border-white/[0.06] flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="text-slate-400">Pas encore d&apos;accès ?</span>
            <Link
              href="/register"
              className="inline-flex items-center gap-1.5 font-semibold text-cyan-400 hover:text-cyan-300"
            >
              <UserPlus className="w-3.5 h-3.5" />
              <span>Créer un compte (Sign-Up)</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="text-xs font-mono text-slate-400">Chargement du portail d&apos;authentification...</div>
      }
    >
      <LoginFormContent />
    </Suspense>
  );
}
