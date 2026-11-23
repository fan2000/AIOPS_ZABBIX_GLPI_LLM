"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  Plus,
  RefreshCw,
  Shield,
  ShieldOff,
  Users,
} from "lucide-react";
import { AuthUserSummary, apiFetch, getStoredAuthUser } from "@/lib/api";

interface AdminUserRow {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  role: "admin" | "operator" | "viewer";
  permissions: string[];
  allowed_entities: string[];
  is_active: boolean;
  mfa_enabled: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

interface RoleInfo {
  id: string;
  name: string;
  description?: string | null;
  permissions: string[];
}

export default function AdminUsersPage() {
  const [me, setMe] = useState<AuthUserSummary | null>(null);
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [edits, setEdits] = useState<
    Record<string, { role: "admin" | "operator" | "viewer"; entitiesText: string; is_active: boolean }>
  >({});
  const [showCreate, setShowCreate] = useState(false);
  const [newUser, setNewUser] = useState({
    username: "",
    email: "",
    full_name: "",
    password: "",
    role: "operator" as "admin" | "operator" | "viewer",
    entitiesText: "0",
  });
  const [resetTarget, setResetTarget] = useState<{ id: string; username: string } | null>(null);
  const [resetPwdValue, setResetPwdValue] = useState("");
  const [banner, setBanner] = useState<{ kind: "info" | "error"; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [uRes, rRes] = await Promise.all([
        apiFetch("/api/v1/users"),
        apiFetch("/api/v1/users/roles"),
      ]);
      if (uRes.ok) {
        const list: AdminUserRow[] = await uRes.json();
        setUsers(list);
        const map: Record<
          string,
          { role: "admin" | "operator" | "viewer"; entitiesText: string; is_active: boolean }
        > = {};
        for (const u of list) {
          map[u.id] = {
            role: u.role,
            entitiesText: (u.allowed_entities || ["0"]).join(","),
            is_active: u.is_active,
          };
        }
        setEdits(map);
      }
      if (rRes.ok) {
        setRoles(await rRes.json());
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const current = getStoredAuthUser();
    setMe(current);
    if (current?.role?.toLowerCase() === "admin") {
      loadAll();
    } else {
      setLoading(false);
    }
  }, []);

  if (me && me.role?.toLowerCase() !== "admin") {
    return (
      <div className="bezel-shell max-w-xl">
        <div className="bezel-core p-8 text-center space-y-3">
          <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto" />
          <h1 className="text-lg font-bold text-white">Accès Restreint — Administrateur Requis</h1>
          <p className="text-xs text-slate-400">
            Votre rôle actuel est <strong className="text-cyan-300 uppercase">{me.role}</strong>. Seul le rôle <code>admin</code> peut gérer les utilisateurs, rôles RBAC et réinitialisations MFA.
          </p>
        </div>
      </div>
    );
  }

  const handleSaveUser = async (userId: string) => {
    const draft = edits[userId];
    if (!draft) return;
    setBanner(null);
    const entities = draft.entitiesText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const res = await apiFetch(`/api/v1/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({
        role: draft.role,
        allowed_entities: entities.length ? entities : ["0"],
        is_active: draft.is_active,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setBanner({ kind: "info", text: `Compte "${data.username}" mis à jour (${data.role}).` });
      await loadAll();
    } else {
      setBanner({ kind: "error", text: data.detail || "Erreur mise à jour utilisateur." });
    }
  };

  const handleResetMfa = async (u: AdminUserRow) => {
    setBanner(null);
    const res = await apiFetch(`/api/v1/users/${u.id}/reset-mfa`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setBanner({ kind: "info", text: `MFA réinitialisée pour "${u.username}".` });
      await loadAll();
    } else {
      setBanner({ kind: "error", text: data.detail || "Échec réinitialisation MFA." });
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const entities = newUser.entitiesText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const res = await apiFetch("/api/v1/users", {
      method: "POST",
      body: JSON.stringify({
        username: newUser.username.trim(),
        email: newUser.email.trim(),
        full_name: newUser.full_name.trim() || undefined,
        password: newUser.password,
        role: newUser.role,
        allowed_entities: entities.length ? entities : ["0"],
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setShowCreate(false);
      setNewUser({
        username: "",
        email: "",
        full_name: "",
        password: "",
        role: "operator",
        entitiesText: "0",
      });
      setBanner({ kind: "info", text: `Utilisateur "${data.username}" créé avec rôle "${data.role}".` });
      await loadAll();
    } else {
      setBanner({ kind: "error", text: data.detail || "Erreur création utilisateur." });
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetTarget) return;
    setBanner(null);
    const res = await apiFetch(`/api/v1/users/${resetTarget.id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: resetPwdValue }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setBanner({ kind: "info", text: `Mot de passe réinitialisé pour "${resetTarget.username}".` });
      setResetTarget(null);
      setResetPwdValue("");
    } else {
      setBanner({ kind: "error", text: data.detail || "Erreur réinitialisation mot de passe." });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2.5">
            <Users className="w-6 h-6 text-cyan-400" />
            <span>Administration IAM — Utilisateurs, Rôles &amp; Entités GLPI</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Contrôle RBAC hiérarchique, isolation multi-entités GLPI et gouvernance MFA/sessions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadAll}
            disabled={loading}
            className="btn-tactile inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.1] text-xs font-semibold text-slate-200"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Actualiser</span>
          </button>
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="btn-tactile inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Nouvel utilisateur</span>
          </button>
        </div>
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

      {/* Matrice des Rôles RBAC */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {roles.map((r) => (
          <div key={r.id} className="p-4 rounded-xl bg-obsidian-950/90 border border-white/[0.08] space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white uppercase flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-cyan-400" />
                {r.name}
              </span>
              <span className="text-[10px] font-mono text-slate-400">{r.permissions.length} perm.</span>
            </div>
            <p className="text-[11px] text-slate-400">{r.description}</p>
            <div className="flex flex-wrap gap-1">
              {r.permissions.map((p) => (
                <span
                  key={p}
                  className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] font-mono text-[10px] text-cyan-300"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Formulaire de création */}
      {showCreate && (
        <div className="bezel-shell">
          <div className="bezel-core p-6">
            <form onSubmit={handleCreateUser} className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <input
                type="text"
                required
                placeholder="Identifiant (ex: j.dupont)"
                value={newUser.username}
                onChange={(e) => setNewUser((p) => ({ ...p, username: e.target.value }))}
                className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              />
              <input
                type="email"
                required
                placeholder="Email"
                value={newUser.email}
                onChange={(e) => setNewUser((p) => ({ ...p, email: e.target.value }))}
                className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              />
              <input
                type="text"
                placeholder="Nom complet"
                value={newUser.full_name}
                onChange={(e) => setNewUser((p) => ({ ...p, full_name: e.target.value }))}
                className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              />
              <input
                type="password"
                required
                placeholder="Mot de passe fort (>= 10 car.)"
                value={newUser.password}
                onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))}
                className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              />
              <select
                value={newUser.role}
                onChange={(e) => setNewUser((p) => ({ ...p, role: e.target.value as any }))}
                className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white outline-none focus:border-cyan-400"
              >
                <option value="viewer">viewer</option>
                <option value="operator">operator</option>
                <option value="admin">admin</option>
              </select>
              <input
                type="text"
                placeholder="Entités GLPI (ex: 0,1,2)"
                value={newUser.entitiesText}
                onChange={(e) => setNewUser((p) => ({ ...p, entitiesText: e.target.value }))}
                disabled={newUser.role === "admin"}
                className="px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white font-mono outline-none focus:border-cyan-400 disabled:opacity-50"
              />
              <div className="md:col-span-3 flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-3.5 py-2 rounded-xl border border-white/[0.1] text-slate-300"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  className="btn-tactile px-4 py-2 rounded-xl bg-cyan-500 text-slate-950 font-bold"
                >
                  Créer le compte
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {resetTarget && (
        <div className="bezel-shell">
          <div className="bezel-core p-5">
            <form onSubmit={handleResetPassword} className="flex flex-wrap items-center gap-3 text-xs">
              <span className="text-white font-semibold">
                Nouveau mot de passe pour <code className="text-cyan-300">{resetTarget.username}</code> :
              </span>
              <input
                type="password"
                required
                value={resetPwdValue}
                onChange={(e) => setResetPwdValue(e.target.value)}
                placeholder="Min 10 car. + Maj/Min/Chiffre/Spécial"
                className="flex-1 min-w-[240px] px-3 py-2 rounded-xl bg-obsidian-950 border border-white/[0.1] text-white"
              />
              <button
                type="submit"
                className="px-3.5 py-2 rounded-xl bg-amber-500 text-slate-950 font-bold"
              >
                Appliquer
              </button>
              <button
                type="button"
                onClick={() => {
                  setResetTarget(null);
                  setResetPwdValue("");
                }}
                className="px-3 py-2 rounded-xl border border-white/[0.1] text-slate-400"
              >
                Annuler
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Liste des utilisateurs */}
      <div className="bezel-shell">
        <div className="bezel-core p-6 space-y-3">
          {users.map((u) => {
            const draft = edits[u.id] || {
              role: u.role,
              entitiesText: u.allowed_entities.join(","),
              is_active: u.is_active,
            };
            const isSelf = me?.username === u.username;
            return (
              <div
                key={u.id}
                className="p-4 rounded-xl bg-obsidian-950/85 border border-white/[0.06] flex flex-col xl:flex-row xl:items-center justify-between gap-4 text-xs"
              >
                <div className="space-y-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-white text-sm">{u.username}</span>
                    {u.full_name && <span className="text-slate-400">({u.full_name})</span>}
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-mono border ${
                        u.mfa_enabled
                          ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                          : "bg-slate-500/15 text-slate-400 border-slate-500/30"
                      }`}
                    >
                      {u.mfa_enabled ? "MFA 2FA" : "Sans 2FA"}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-mono border ${
                        u.is_active
                          ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
                          : "bg-rose-500/15 text-rose-300 border-rose-500/30"
                      }`}
                    >
                      {u.is_active ? "Actif" : "Désactivé"}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    {u.email}
                    {u.last_login_at
                      ? ` • Dernière connexion : ${new Date(u.last_login_at).toLocaleString()}`
                      : " • Jamais connecté"}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  <select
                    value={draft.role}
                    disabled={isSelf}
                    onChange={(e) =>
                      setEdits((prev) => ({
                        ...prev,
                        [u.id]: { ...draft, role: e.target.value as any },
                      }))
                    }
                    className="px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/[0.1] text-white font-mono disabled:opacity-50"
                  >
                    <option value="viewer">viewer</option>
                    <option value="operator">operator</option>
                    <option value="admin">admin</option>
                  </select>

                  <input
                    type="text"
                    value={draft.role === "admin" ? "*" : draft.entitiesText}
                    disabled={draft.role === "admin"}
                    onChange={(e) =>
                      setEdits((prev) => ({
                        ...prev,
                        [u.id]: { ...draft, entitiesText: e.target.value },
                      }))
                    }
                    title="Entités GLPI autorisées (séparées par virgules)"
                    className="w-24 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/[0.1] text-cyan-300 font-mono disabled:opacity-50"
                  />

                  <label className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/40 border border-white/[0.08] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={draft.is_active}
                      disabled={isSelf}
                      onChange={(e) =>
                        setEdits((prev) => ({
                          ...prev,
                          [u.id]: { ...draft, is_active: e.target.checked },
                        }))
                      }
                    />
                    <span>Actif</span>
                  </label>

                  <button
                    onClick={() => handleSaveUser(u.id)}
                    className="btn-tactile px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-200 border border-cyan-500/40 font-semibold"
                  >
                    Enregistrer
                  </button>

                  {u.mfa_enabled && (
                    <button
                      onClick={() => handleResetMfa(u)}
                      title="Réinitialiser 2FA"
                      className="btn-tactile inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30"
                    >
                      <ShieldOff className="w-3.5 h-3.5" />
                      <span>Reset 2FA</span>
                    </button>
                  )}

                  <button
                    onClick={() => setResetTarget({ id: u.id, username: u.username })}
                    title="Réinitialiser mot de passe"
                    className="btn-tactile inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-slate-300 border border-white/[0.1]"
                  >
                    <KeyRound className="w-3.5 h-3.5" />
                    <span>MDP</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
