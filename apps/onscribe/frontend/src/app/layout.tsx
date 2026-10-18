import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OnScribe | Operations Intelligence & Compliance Suite",
  description: "Enterprise operational task management, team capacity orchestration, and compliance auditing with Axio360 AI copilot.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full bg-slate-50 text-slate-900 flex flex-col font-sans overflow-hidden selection:bg-sky-500/20 selection:text-sky-900">
        {children}
      </body>
    </html>
  );
}
