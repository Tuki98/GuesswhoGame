import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Brand } from "@/components/layout/Brand";

export function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-ink-950 text-slate-100">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(124,58,237,0.16),transparent_52%),radial-gradient(ellipse_at_bottom_left,rgba(34,211,238,0.07),transparent_45%)]"
        aria-hidden="true"
      />
      <div className="relative">
        <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-5 sm:px-6 lg:px-8">
          <Brand />
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-400 transition hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Home
          </Link>
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 pb-16 pt-2 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
