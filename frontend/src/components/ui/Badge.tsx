import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "neutral" | "violet" | "green" | "amber" | "rose" | "cyan";

const tones: Record<Tone, string> = {
  neutral: "border-white/10 bg-white/[0.05] text-slate-300",
  violet: "border-violet-400/25 bg-violet-500/10 text-violet-200",
  green: "border-emerald-400/25 bg-emerald-500/10 text-emerald-200",
  amber: "border-amber-400/25 bg-amber-500/10 text-amber-200",
  rose: "border-rose-400/25 bg-rose-500/10 text-rose-200",
  cyan: "border-cyan-400/25 bg-cyan-500/10 text-cyan-200",
};

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
