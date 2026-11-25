import { Loader2, Wifi, WifiOff } from "lucide-react";

import { cn } from "@/lib/cn";
import { useConnectionStore } from "@/stores/connectionStore";

export function ConnectionBadge({ compact = false }: { compact?: boolean }) {
  const status = useConnectionStore((state) => state.status);
  const labels = {
    idle: "Offline",
    connecting: "Connecting",
    connected: "Live",
    reconnecting: "Reconnecting",
    disconnected: "Offline",
    expired: "Paused",
  };
  const tone = {
    idle: "border-slate-500/30 bg-slate-500/10 text-slate-300",
    connecting: "border-cyan-400/25 bg-cyan-500/10 text-cyan-200",
    connected: "border-emerald-400/25 bg-emerald-500/10 text-emerald-200",
    reconnecting: "border-amber-400/25 bg-amber-500/10 text-amber-200",
    disconnected: "border-slate-500/30 bg-slate-500/10 text-slate-300",
    expired: "border-rose-400/25 bg-rose-500/10 text-rose-200",
  };
  const Icon = status === "connected" ? Wifi : status === "connecting" || status === "reconnecting" ? Loader2 : WifiOff;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
        tone[status],
      )}
      title={`WebSocket status: ${status}`}
    >
      <Icon
        className={cn(
          "h-3.5 w-3.5",
          (status === "connecting" || status === "reconnecting") && "animate-spin",
        )}
        aria-hidden="true"
      />
      {compact ? null : labels[status]}
      {status === "reconnecting" ? <ConnectionAttempt /> : null}
    </span>
  );
}

function ConnectionAttempt() {
  const attempt = useConnectionStore((state) => state.attempt);
  return attempt > 0 ? <span>{attempt}</span> : null;
}
