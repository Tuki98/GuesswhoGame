import { Check, Copy, Link2, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { toastError, toastSuccess } from "@/stores/uiStore";

async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Fall through to the legacy selection-based copy path.
  }
  try {
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
}

export function InviteCard({
  roomCode,
  playerCount,
  maxPlayers,
}: {
  roomCode: string;
  playerCount: number;
  maxPlayers: number;
}) {
  const [copied, setCopied] = useState<"code" | "link" | null>(null);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(null), 2_000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const inviteUrl =
    typeof window === "undefined"
      ? `/join?code=${encodeURIComponent(roomCode)}`
      : `${window.location.origin}/join?code=${encodeURIComponent(roomCode)}`;

  async function share(kind: "code" | "link") {
    const value = kind === "code" ? roomCode : inviteUrl;
    const ok = await copyText(value);
    if (ok) {
      setCopied(kind);
      toastSuccess(
        kind === "code" ? "Room code copied" : "Invite link copied",
        kind === "code" ? roomCode : undefined,
      );
    } else {
      toastError("Could not copy", "Select and copy the code manually.");
    }
  }

  return (
    <Card className="p-4 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-500/10 text-violet-200">
            <Users className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Invite players
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-2xl font-semibold tracking-[0.18em] text-white">
                {roomCode}
              </span>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void share("code")}
                icon={
                  copied === "code" ? (
                    <Check className="h-4 w-4 text-emerald-300" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )
                }
              >
                {copied === "code" ? "Copied" : "Copy code"}
              </Button>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {playerCount} of {maxPlayers} players in the lobby
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <p className="max-w-[20rem] truncate rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-xs text-slate-400 lg:max-w-[18rem]">
            {inviteUrl}
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void share("link")}
            icon={
              copied === "link" ? (
                <Check className="h-4 w-4 text-emerald-300" />
              ) : (
                <Link2 className="h-4 w-4" />
              )
            }
          >
            {copied === "link" ? "Copied" : "Copy invite link"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
