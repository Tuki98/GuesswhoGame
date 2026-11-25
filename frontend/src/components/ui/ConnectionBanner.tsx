import { RefreshCw, WifiOff } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { realtime } from "@/realtime/realtime";
import { useConnectionStore } from "@/stores/connectionStore";

export function ConnectionBanner() {
  const status = useConnectionStore((state) => state.status);
  const attempt = useConnectionStore((state) => state.attempt);
  const detail = useConnectionStore((state) => state.detail);

  if (status === "connected" || status === "idle") {
    return null;
  }

  const expired = status === "expired";
  return (
    <div
      className="flex flex-col gap-3 rounded-xl border border-amber-400/20 bg-amber-500/[0.07] px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
      role="status"
    >
      <div className="flex items-start gap-3">
        <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" aria-hidden="true" />
        <div>
          <p className="font-medium text-amber-100">
            {expired ? "Room connection paused" : "Reconnecting to the room"}
            {status === "reconnecting" && attempt > 1 ? ` · attempt ${attempt}` : ""}
          </p>
          <p className="mt-0.5 text-amber-200/70">
            {detail ??
              (expired
                ? "Refresh your session to continue receiving live updates."
                : "Your actions are disabled until the connection returns.")}
          </p>
        </div>
      </div>
      <Button
        size="sm"
        variant="secondary"
        icon={<RefreshCw className="h-4 w-4" />}
        onClick={() => realtime.retryNow()}
      >
        Retry now
      </Button>
    </div>
  );
}
