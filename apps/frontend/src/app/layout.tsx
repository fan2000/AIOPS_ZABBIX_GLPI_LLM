import type { Metadata } from "next";
import { Navigation } from "@/components/Navigation";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI IT Operations | AIOps Platform",
  description: "Plateforme AIOps intelligente connectant Zabbix, GLPI et LangGraph",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className="dark">
      <body className="flex min-h-screen bg-obsidian-950 text-slate-100 antialiased selection:bg-cyan-500/30 selection:text-cyan-200">
        <Navigation />
        <main className="flex-1 overflow-y-auto px-6 py-8 md:px-10 lg:px-12">{children}</main>
      </body>
    </html>
  );
}
