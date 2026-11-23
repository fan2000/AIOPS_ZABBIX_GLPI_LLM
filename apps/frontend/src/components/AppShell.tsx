"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Activity } from "lucide-react";
import { Navigation } from "@/components/Navigation";
import {
  fetchCurrentProfile,
  getAuthToken,
  getRefreshToken,
  refreshAccessToken,
} from "@/lib/api";

const PUBLIC_ROUTES = new Set(["/login", "/register"]);

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const isPublic = PUBLIC_ROUTES.has(pathname);
  const [authState, setAuthState] = useState<"checking" | "authenticated" | "unauthenticated">(
    "checking"
  );

  useEffect(() => {
    let cancelled = false;

    const verifySession = async () => {
      let token = getAuthToken();
      if (!token && getRefreshToken()) {
        const refreshed = await refreshAccessToken();
        if (refreshed) token = getAuthToken();
      }

      if (!token) {
        if (!cancelled) {
          setAuthState("unauthenticated");
          if (!isPublic) {
            const nextParam = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
            router.replace(`/login${nextParam}`);
          }
        }
        return;
      }

      // En mode public (/login ou /register), si déjà connecté -> rediriger vers le dashboard
      const profile = await fetchCurrentProfile();
      if (cancelled) return;
      if (profile) {
        setAuthState("authenticated");
        if (isPublic) {
          router.replace("/");
        }
      } else {
        setAuthState("unauthenticated");
        if (!isPublic) {
          const nextParam = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
          router.replace(`/login${nextParam}`);
        }
      }
    };

    verifySession();

    const onAuthChanged = () => {
      const hasToken = Boolean(getAuthToken());
      setAuthState(hasToken ? "authenticated" : "unauthenticated");
      if (!hasToken && !PUBLIC_ROUTES.has(window.location.pathname)) {
        router.replace("/login");
      }
    };
    window.addEventListener("aiops-auth-changed", onAuthChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("aiops-auth-changed", onAuthChanged);
    };
  }, [isPublic, pathname, router]);

  if (isPublic) {
    return (
      <main className="min-h-screen w-full bg-obsidian-950 flex items-center justify-center p-4 md:p-8">
        {children}
      </main>
    );
  }

  if (authState !== "authenticated") {
    return (
      <div className="min-h-screen w-full bg-obsidian-950 flex flex-col items-center justify-center gap-3 text-slate-300">
        <div className="w-11 h-11 rounded-2xl bg-obsidian-900 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
          <Activity className="w-5 h-5 animate-pulse" />
        </div>
        <p className="text-xs font-mono text-slate-400">
          Vérification de session sécurisée Zero-Trust...
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen w-full bg-obsidian-950">
      <Navigation />
      <main className="flex-1 overflow-y-auto px-6 py-8 md:px-10 lg:px-12">{children}</main>
    </div>
  );
}
