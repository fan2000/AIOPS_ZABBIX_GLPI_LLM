"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  KeyRound,
  Laptop,
  Lock,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
} from "lucide-react";
import {
  AuthUserSummary,
  apiFetch,
  fetchCurrentProfile,
  logout,
  setStoredAuthUser,
} from "@/lib/api";
import { QrCodeImage } from "@/components/QrCodeImage";

interface SessionItem {
  id: string;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  is_active: boolean;
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<AuthUserSummary | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [banner, setBanner] = useState<{ kind: "info" | "error"; text: string } | null>(null);

  // MFA Setup state
  const [mfaSetup, setMfaSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [enableCode, setEnableCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [disablePwd, setDisablePwd] = useState("");
  const [disableCode, setDisableCode] = useState("");

  // Password Change state
  const [curPwd, setCurPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmNewPwd, setConfirmNewPwd] = useState("");

  const loadData = async () => {
    const me = await fetchCurrentProfile();
    if (me) {
      setProfile(me);
      setFullName(me.full_name || "");
      setEmail(me.email || "");
    }
    const sessRes = await apiFetch("/api/v1/auth/sessions");
    if (sessRes.ok) {
      setSessions(await sessRes.json());
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const res = await apiFetch("/api/v1/auth/profile", {
      method: "PATCH",
      body: JSON.stringify({ full_name: fullName, email }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setProfile(data);
      setStoredAuthUser(data);
      setBanner({ kind: "info", text: "Profil mis à jour avec succès." });
    } else {
      setBanner({ kind: "error", text: data.detail || "Erreur lors de la mise à jour du profil." });
    }
  };

  const handleStartMfaSetup = async () => {
    setBanner(null);
    setRecoveryCodes(null);
    const res = await apiFetch("/api/v1/auth/mfa/setup", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setMfaSetup({ secret: data.secret, otpauth_uri: data.otpauth_uri });
    } else {
      setBanner({ kind: "error", text: data.detail || "Impossible d'initialiser la 2FA." });
    }
  };

  const handleEnableMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const res = await apiFetch("/api/v1/auth/mfa/enable", {
      method: "POST",
      body: JSON.stringify({ code: enableCode.trim() }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setMfaSetup(null);
      setEnableCode("");
      setRecoveryCodes(data.recovery_codes || []);
      setBanner({
        kind: "info",
        text: "Authentification 2FA activée ! Conservez vos codes de secours en lieu sûr.",
      });
      await loadData();
    } else {
      setBanner({ kind: "error", text: data.detail || "Code TOTP invalide." });
    }
  };

  const handleDisableMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const res = await apiFetch("/api/v1/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify({ password: disablePwd, code: disableCode.trim() }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setDisablePwd("");
      setDisableCode("");
      setRecoveryCodes(null);
      setBanner({ kind: "info", text: "Authentification 2FA désactivée sur votre compte." });
      await loadData();
    } else {
      setBanner({ kind: "error", text: data.detail || "Échec de désactivation MFA." });
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    if (newPwd !== confirmNewPwd) {
      setBanner({ kind: "error", text: "La confirmation du nouveau mot de passe ne correspond pas." });
      return;
    }
    const res = await apiFetch("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: curPwd, new_password: newPwd }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setCurPwd("");
      setNewPwd("");
      setConfirmNewPwd("");
      setBanner({
        kind: "info",
        text: "Mot de passe modifié. Toutes vos sessions Refresh précédentes ont été révoquées.",
      });
      await loadData();
    } else {
      setBanner({ kind: "error", text: data.detail || "Impossible de modifier le mot de passe." });
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    const res = await apiFetch(`/api/v1/auth/sessions/${sessionId}`, { method: "DELETE" });
    if (res.ok) {
      await loadData();
      setBanner({ kind: "info", text: "Session révoquée." });
    }
  };

  const handleLogoutAll = async () => {
    await logout(true);
  };

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2.5">
            <UserCheck className="w-6 h-6 text-cyan-400" />
            <span>Mon Profil, Rôle RBAC &amp; Double Authentification (MFA)</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Gérez vos informations personnelles, votre clé TOTP, vos codes de secours et vos sessions actives.
          </p>
        </div>
        {profile && (
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="px-3 py-1 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 uppercase font-bold">
              Rôle : {profile.role}
            </span>
            <span
              className={`px-3 py-1 rounded-full border font-bold ${
                profile.mfa_enabled
                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                  : "bg-amber-500/15 text-amber-300 border-amber-500/30"
              }`}
            >
              {profile.mfa_enabled ? "2FA ACTIVE" : "2FA INACTIVE"}
            </span>
          </div>
        )}
      </div>

      {banner && (
        <div
          className={`p-3.5 rounded-xl border text-xs flex items-center justify-between gap-3 ${
            banner.kind === "error"
              ? "bg-rose-500/10 border-rose-500/30 text-rose-200"
              : "bg-emerald-500/10 border-emerald-500/30 text-emerald-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {banner.kind === "error" ? (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            )}
            <span>{banner.text}</span>
          </div>
          <button onClick={() => setBanner(null)} className="font-mono text-[11px] opacity-75 hover:opacity-100">
            Fermer
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Carte 1 : Profil & RBAC */}
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-4">
            <h2 className="text-sm font-bold text-white flex items-center gap-2 border-b border-white/[0.06] pb-3">
              <Shield className="w-4 h-4 text-cyan-400" />
              <span>Identité &amp; Droits d&apos;Accès GLPI</span>
            </h2>

            <form onSubmit={handleSaveProfile} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Identifiant</label>
                  <input
                    disabled
                    value={profile?.username || ""}
                    className="w-full px-3 py-2 rounded-xl bg-black/40 border border-white/[0.06] text-slate-400 font-mono"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Entités GLPI autorisées</label>
                  <input
                    disabled
                    value={(profile?.allowed_entities || ["0"]).join(", ")}
                    className="w-full px-3 py-2 rounded-xl bg-black/40 border border-white/[0.06] text-cyan-300 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] text-slate-300 block mb-1">Nom complet</label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Prénom Nom"
                  className="w-full px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-300 block mb-1">Adresse email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
                />
              </div>

              <div>
                <div className="text-[11px] text-slate-400 mb-1.5">Permissions RBAC ({profile?.permissions?.length || 0})</div>
                <div className="flex flex-wrap gap-1.5">
                  {(profile?.permissions || []).map((p) => (
                    <span
                      key={p}
                      className="px-2 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] font-mono text-[10px] text-cyan-300"
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                className="btn-tactile px-4 py-2 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-200 border border-cyan-500/40 font-semibold"
              >
                Enregistrer les modifications
              </button>
            </form>
          </div>
        </div>

        {/* Carte 2 : MFA / TOTP 2FA */}
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-4">
            <h2 className="text-sm font-bold text-white flex items-center gap-2 border-b border-white/[0.06] pb-3">
              {profile?.mfa_enabled ? (
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-amber-400" />
              )}
              <span>Double Authentification (MFA / TOTP Authenticator)</span>
            </h2>

            {recoveryCodes && recoveryCodes.length > 0 && (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 space-y-2 text-xs">
                <div className="font-bold text-emerald-300">
                  Codes de secours à usage unique (affichés une seule fois) :
                </div>
                <div className="grid grid-cols-2 gap-1.5 font-mono text-[11px] text-white">
                  {recoveryCodes.map((c) => (
                    <div key={c} className="px-2 py-1 rounded bg-black/50 border border-white/10 text-center">
                      {c}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!profile?.mfa_enabled ? (
              !mfaSetup ? (
                <div className="space-y-3 text-xs">
                  <p className="text-slate-300 leading-relaxed">
                    Protégez vos actions d&apos;exploitation (approbations HITL, exécution de runbooks, gestion IAM) avec un second facteur TOTP (Google Authenticator, Authy, Microsoft Authenticator ou FreeOTP).
                  </p>
                  <button
                    onClick={handleStartMfaSetup}
                    className="btn-tactile inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 border border-emerald-500/40 font-semibold"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    <span>Configurer la double authentification (QR Code)</span>
                  </button>
                </div>
              ) : (
                <form onSubmit={handleEnableMfa} className="space-y-4 text-xs">
                  <div className="flex flex-col sm:flex-row items-center gap-4">
                    <QrCodeImage value={mfaSetup.otpauth_uri} size={168} />
                    <div className="space-y-2 min-w-0 flex-1">
                      <p className="text-slate-300">
                        1. Scannez ce QR Code localement généré avec votre application Authenticator.
                      </p>
                      <div className="text-[11px] text-slate-400">Ou saisissez manuellement la clé Base32 :</div>
                      <div className="p-2 rounded-lg bg-black/50 border border-white/10 font-mono text-[11px] text-cyan-300 break-all flex items-center justify-between gap-2">
                        <span>{mfaSetup.secret}</span>
                        <button
                          type="button"
                          onClick={() => navigator.clipboard?.writeText(mfaSetup.secret)}
                          className="text-slate-400 hover:text-white shrink-0"
                          title="Copier la clé"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      required
                      maxLength={8}
                      value={enableCode}
                      onChange={(e) => setEnableCode(e.target.value)}
                      placeholder="Code à 6 chiffres (ex: 482910)"
                      className="flex-1 px-3 py-2 rounded-xl bg-obsidian-950 border border-emerald-500/40 text-white font-mono outline-none focus:border-emerald-400"
                    />
                    <button
                      type="submit"
                      className="btn-tactile px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold"
                    >
                      Activer 2FA
                    </button>
                  </div>
                </form>
              )
            ) : (
              <form onSubmit={handleDisableMfa} className="space-y-3 text-xs">
                <p className="text-emerald-300 font-medium">
                  Votre compte est protégé par TOTP RFC 6238 (fenêtre ±30s) et codes de secours hashés SHA-256.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  <input
                    type="password"
                    required
                    value={disablePwd}
                    onChange={(e) => setDisablePwd(e.target.value)}
                    placeholder="Mot de passe actuel"
                    className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-rose-400"
                  />
                  <input
                    type="text"
                    required
                    value={disableCode}
                    onChange={(e) => setDisableCode(e.target.value)}
                    placeholder="Code TOTP ou secours"
                    className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white font-mono outline-none focus:border-rose-400"
                  />
                </div>
                <button
                  type="submit"
                  className="btn-tactile px-4 py-2 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 font-semibold"
                >
                  Désactiver la double authentification
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Carte 3 : Changement mot de passe */}
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-4">
            <h2 className="text-sm font-bold text-white flex items-center gap-2 border-b border-white/[0.06] pb-3">
              <Lock className="w-4 h-4 text-purple-400" />
              <span>Changer le mot de passe</span>
            </h2>

            <form onSubmit={handleChangePassword} className="space-y-3 text-xs">
              <input
                type="password"
                required
                value={curPwd}
                onChange={(e) => setCurPwd(e.target.value)}
                placeholder="Mot de passe actuel"
                className="w-full px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              />
              <input
                type="password"
                required
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
                placeholder="Nouveau mot de passe (min 10 car., maj/min/chiffre/spécial)"
                className="w-full px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              />
              <input
                type="password"
                required
                value={confirmNewPwd}
                onChange={(e) => setConfirmNewPwd(e.target.value)}
                placeholder="Confirmer le nouveau mot de passe"
                className="w-full px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              />
              <button
                type="submit"
                className="btn-tactile px-4 py-2 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 text-purple-200 border border-purple-500/40 font-semibold"
              >
                Mettre à jour le mot de passe
              </button>
            </form>
          </div>
        </div>

        {/* Carte 4 : Sessions actives & Révocation */}
        <div className="bezel-shell">
          <div className="bezel-core p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] pb-3">
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <Laptop className="w-4 h-4 text-cyan-400" />
                <span>Sessions Refresh Token ({sessions.filter((s) => s.is_active).length} active(s))</span>
              </h2>
              <button
                onClick={handleLogoutAll}
                className="px-2.5 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 text-[11px] font-semibold"
              >
                Tout déconnecter
              </button>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
              {sessions.length === 0 ? (
                <div className="py-6 text-center text-slate-500">Aucune session enregistrée.</div>
              ) : (
                sessions.map((s) => (
                  <div
                    key={s.id}
                    className="p-3 rounded-xl bg-obsidian-950/80 border border-white/[0.06] flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0 space-y-0.5">
                      <div className="flex items-center gap-2 font-mono text-[11px]">
                        <span className="text-white">{s.ip_address || "IP locale"}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] uppercase border ${
                            s.is_active
                              ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                              : "bg-slate-500/15 text-slate-400 border-slate-500/30"
                          }`}
                        >
                          {s.is_active ? "Active" : "Révoquée"}
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-500 truncate">{s.user_agent || "Client API"}</div>
                    </div>
                    {s.is_active && (
                      <button
                        onClick={() => handleRevokeSession(s.id)}
                        title="Révoquer cette session"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-300 hover:bg-rose-500/10"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
