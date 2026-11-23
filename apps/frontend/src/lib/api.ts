/** Client API centralisé avec authentification JWT, Refresh Token rotation & gestion MFA. */

export const API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) || "http://localhost:8005";

const TOKEN_STORAGE_KEY = "aiops_jwt_token";
const REFRESH_STORAGE_KEY = "aiops_refresh_token";
const USER_STORAGE_KEY = "aiops_auth_user";

export interface AuthUserSummary {
  id: string | null;
  username: string;
  email?: string | null;
  full_name?: string | null;
  role: string;
  permissions: string[];
  allowed_entities?: string[];
  mfa_enabled?: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

export interface LoginOutcome {
  mfaRequired: boolean;
  mfaChallengeToken?: string;
  user: AuthUserSummary;
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_STORAGE_KEY);
}

export function getStoredAuthUser(): AuthUserSummary | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUserSummary;
  } catch {
    return null;
  }
}

export function setStoredAuthUser(user: AuthUserSummary): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    notifyAuthChanged();
  }
}

function storeSessionTokens(accessToken: string, refreshToken: string | null | undefined, user: AuthUserSummary): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
    if (refreshToken) {
      window.localStorage.setItem(REFRESH_STORAGE_KEY, refreshToken);
    }
    window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    notifyAuthChanged();
  }
}

export function clearLocalAuth(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    window.localStorage.removeItem(REFRESH_STORAGE_KEY);
    window.localStorage.removeItem(USER_STORAGE_KEY);
    notifyAuthChanged();
  }
}

function notifyAuthChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("aiops-auth-changed"));
  }
}

export async function login(username: string, password: string, totpCode?: string): Promise<LoginOutcome> {
  const payload: Record<string, string> = { username, password };
  if (totpCode && totpCode.trim()) {
    payload.totp_code = totpCode.trim();
  }
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Échec d'authentification");
  }
  const data = await res.json();
  if (data.mfa_required && data.mfa_challenge_token) {
    return {
      mfaRequired: true,
      mfaChallengeToken: data.mfa_challenge_token,
      user: data.user as AuthUserSummary,
    };
  }
  storeSessionTokens(data.access_token, data.refresh_token, data.user as AuthUserSummary);
  return {
    mfaRequired: false,
    user: data.user as AuthUserSummary,
  };
}

export async function verifyMfaLogin(mfaChallengeToken: string, code: string): Promise<AuthUserSummary> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/mfa/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mfa_challenge_token: mfaChallengeToken, code: code.trim() }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Code MFA invalide");
  }
  const data = await res.json();
  storeSessionTokens(data.access_token, data.refresh_token, data.user as AuthUserSummary);
  return data.user as AuthUserSummary;
}

export async function register(params: {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}): Promise<AuthUserSummary> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Échec lors de la création du compte");
  }
  const data = await res.json();
  storeSessionTokens(data.access_token, data.refresh_token, data.user as AuthUserSummary);
  return data.user as AuthUserSummary;
}

let refreshInFlight: Promise<boolean> | null = null;

export async function refreshAccessToken(): Promise<boolean> {
  const rt = getRefreshToken();
  if (!rt) return false;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) {
        clearLocalAuth();
        return false;
      }
      const data = await res.json();
      storeSessionTokens(data.access_token, data.refresh_token, data.user as AuthUserSummary);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export async function fetchCurrentProfile(): Promise<AuthUserSummary | null> {
  const res = await apiFetch("/api/v1/auth/me");
  if (!res.ok) return null;
  const user = (await res.json()) as AuthUserSummary;
  setStoredAuthUser(user);
  return user;
}

export async function logout(allSessions = false): Promise<void> {
  const rt = getRefreshToken();
  const token = getAuthToken();
  clearLocalAuth();
  try {
    if (rt || token) {
      await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ refresh_token: rt || undefined, all_sessions: allSessions }),
      });
    }
  } catch {
    // Nettoyage local garanti même si l'API est injoignable
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const buildHeaders = (): Headers => {
    const h = new Headers(init.headers || {});
    const token = getAuthToken();
    if (token && !h.has("Authorization")) {
      h.set("Authorization", `Bearer ${token}`);
    }
    if (init.body && !h.has("Content-Type")) {
      h.set("Content-Type", "application/json");
    }
    return h;
  };

  let res = await fetch(`${API_BASE_URL}${normalizedPath}`, {
    ...init,
    headers: buildHeaders(),
  });

  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await fetch(`${API_BASE_URL}${normalizedPath}`, {
        ...init,
        headers: buildHeaders(),
      });
    } else if (getAuthToken()) {
      clearLocalAuth();
    }
  }
  return res;
}
