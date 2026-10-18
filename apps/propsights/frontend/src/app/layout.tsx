import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PropSights | Luxury Real Estate Advisory & Broker Deal Intelligence",
  description: "Enterprise brokerage intelligence, MLS property management, buyer affinity matching, and deal pipeline for Axio360.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full bg-slate-50 text-slate-900 flex flex-col font-sans overflow-hidden selection:bg-rose-500/20 selection:text-rose-900">
        {children}
      </body>
    </html>
  );
}
