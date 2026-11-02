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
      <body className="flex min-h-screen bg-navy-900 text-slate-100">
        <Navigation />
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </body>
    </html>
  );
}
