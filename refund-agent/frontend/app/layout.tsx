import type { Metadata } from "next";
import Link from "next/link";
import { PennyAvatar } from "@/components/Mascot";
import "./globals.css";

export const metadata: Metadata = {
  title: "ACME Customer Support · Penny",
  description:
    "AI customer-support agent for e-commerce refunds, replacements, and damages",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-white/40 bg-white/70 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-3">
              <PennyAvatar size={38} online />
              <div className="leading-tight">
                <div className="text-base font-bold text-gray-900">
                  ACME Customer Support
                </div>
                <div className="text-xs text-gray-500">
                  with <span className="font-semibold text-sky-600">Penny</span>,
                  here to help with refunds, replacements &amp; damages
                </div>
              </div>
            </Link>
            <nav className="flex items-center gap-1 text-sm font-medium">
              <Link
                href="/"
                className="rounded-lg px-3 py-1.5 text-gray-700 transition hover:bg-sky-50 hover:text-sky-700"
              >
                My Orders
              </Link>
              <Link
                href="/admin"
                className="rounded-lg px-3 py-1.5 text-gray-700 transition hover:bg-sky-50 hover:text-sky-700"
              >
                Admin
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
