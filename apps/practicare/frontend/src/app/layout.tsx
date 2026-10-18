import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PractiCare | Clinical Operations & Practice Management",
  description: "Enterprise healthcare operations, staff management, room turnover, and inventory control with PostgreSQL.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full bg-slate-50 text-slate-900 flex flex-col font-sans overflow-hidden selection:bg-emerald-500/20 selection:text-emerald-800">
        {children}
      </body>
    </html>
  );
}
