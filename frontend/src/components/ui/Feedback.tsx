import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-violet-300", className)} />;
}

export function LoadingPanel({
  title = "Loading",
  message = "Fetching the latest room state…",
  compact = false,
}: {
  title?: string;
  message?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-ink-850/70 text-center",
        compact ? "gap-2 p-6" : "gap-4 p-12",
      )}
      role="status"
      aria-live="polite"
    >
      <Spinner className={compact ? "h-5 w-5" : "h-8 w-8"} />
      <div>
        <p className="font-display font-semibold text-white">{title}</p>
        <p className="mt-1 text-sm text-slate-400">{message}</p>
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon?: ReactNode;
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-white/10 bg-white/[0.02] px-6 py-10 text-center">
      {icon ? <div className="text-slate-500">{icon}</div> : null}
      <div>
        <p className="font-display font-semibold text-slate-200">{title}</p>
        <p className="mt-1 max-w-sm text-sm leading-6 text-slate-500">{message}</p>
      </div>
      {action}
    </div>
  );
}
