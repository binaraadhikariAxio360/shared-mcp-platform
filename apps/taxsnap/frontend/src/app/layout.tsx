import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TaxSnap | Corporate Tax Intelligence & Financial Compliance",
  description: "Enterprise corporate tax management, deduction analysis, ledger compliance, and AI copilot for Axio360.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full bg-slate-50 text-slate-900 flex flex-col font-sans overflow-hidden selection:bg-indigo-500/20 selection:text-indigo-900">
        {children}
      </body>
    </html>
  );
}
