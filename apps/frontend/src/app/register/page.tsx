"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  UserPlus,
} from "lucide-react";
import { register } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const checks = useMemo(
    () => [
      { label: "Au moins 10 caractères", ok: password.length >= 10 },
      { label: "Une minuscule (a-z)", ok: /[a-z]/.test(password) },
      { label: "Une majuscule (A-Z)", ok: /[A-Z]/.test(password) },
      { label: "Un chiffre (0-9)", ok: /[0-9]/.test(password) },
      { label: "Un caractère spécial (!@#$...)", ok: /[^A-Za-z0-9]/.test(password) },
    ],
    [password]
  );

  const allRulesValid = checks.every((c) => c.ok);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!allRulesValid) {
      setError("Le mot de passe ne respecte pas les critères de sécurité minimaux.");
      return;
    }
    if (password !== confirmPassword) {
      setError("La confirmation du mot de passe ne correspond pas.");
      return;
    }
    setLoading(true);
    try {
      await register({
        username: username.trim(),
        email: email.trim(),
        password,
        full_name: fullName.trim() || undefined,
      });
      router.replace("/");
    } catch (err: any) {
      setError(err?.message || "Impossible de créer le compte.");
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
          <h1 className="text-2xl font-black tracking-tight text-white">Création de Compte AIOps</h1>
          <p className="text-xs font-mono text-slate-400 mt-1">
            Accès initial RBAC <span className="text-cyan-300">viewer</span> actif immédiatement
          </p>
        </div>
      </div>

      <div className="bezel-shell">
        <div className="bezel-core p-7 space-y-5">
          <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <UserPlus className="w-4 h-4 text-cyan-400" />
              <span>Inscription (Sign-Up)</span>
            </h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              Rôle initial : viewer
            </span>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-200 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-300 block">Nom complet</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="ex: Nadia Benali"
                className="w-full px-3.5 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-400"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-300 block">
                Identifiant <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                required
                minLength={3}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ex: n.benali"
                className="w-full px-3.5 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-400"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-300 block">
                Email professionnel <span className="text-rose-400">*</span>
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="n.benali@entreprise.local"
                className="w-full px-3.5 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-400"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-300 block">
                Mot de passe <span className="text-rose-400">*</span>
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full px-3.5 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-400"
              />
            </div>

            <div className="p-2.5 rounded-xl bg-black/40 border border-white/[0.06] grid grid-cols-1 gap-1">
              {checks.map((c) => (
                <div
                  key={c.label}
                  className={`flex items-center gap-1.5 text-[10px] font-mono ${
                    c.ok ? "text-emerald-400" : "text-slate-500"
                  }`}
                >
                  <CheckCircle2 className={`w-3 h-3 ${c.ok ? "text-emerald-400" : "text-slate-600"}`} />
                  <span>{c.label}</span>
                </div>
              ))}
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-300 block">
                Confirmer le mot de passe <span className="text-rose-400">*</span>
              </label>
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full px-3.5 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-400"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !allRulesValid}
              className="w-full btn-tactile py-2.5 px-4 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-colors disabled:opacity-50"
            >
              {loading ? "Création du compte..." : "Créer mon compte"}
            </button>
          </form>

          <p className="text-[11px] text-slate-400 leading-relaxed">
            Votre compte démarre avec le rôle <strong className="text-slate-200">viewer</strong> (entité racine <code>0</code>). Un administrateur peut vous promouvoir <strong className="text-cyan-300">operator</strong> ou <strong className="text-purple-300">admin</strong> depuis l&apos;annuaire IAM.
          </p>

          <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between text-xs">
            <span className="text-slate-400">Déjà inscrit ?</span>
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 font-semibold text-cyan-400 hover:text-cyan-300"
            >
              <KeyRound className="w-3.5 h-3.5" />
              <span>Se connecter</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
