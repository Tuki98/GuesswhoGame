import { EyeOff, Fingerprint, ShieldQuestion, Trophy } from "lucide-react";
import { useState } from "react";

import { GuessDialog } from "@/components/game/GuessDialog";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useConnectionStore } from "@/stores/connectionStore";
import { usePendingStore } from "@/stores/pendingStore";
import type { MatchState } from "@/types/api";

export function IdentityCard({ state }: { state: MatchState }) {
  const connected = useConnectionStore((store) => store.status === "connected");
  const guessing = usePendingStore((store) => Boolean(store.pending.guess));
  const [open, setOpen] = useState(false);

  return (
    <>
      <Card className="overflow-hidden border-violet-400/20">
        <div className="grid gap-0 sm:grid-cols-[15rem_minmax(0,1fr)]">
          <div className="relative flex min-h-44 items-center justify-center overflow-hidden bg-gradient-to-br from-violet-600/30 via-fuchsia-600/15 to-cyan-500/10 p-5">
            <div
              className="absolute inset-0 opacity-40 [background-image:radial-gradient(circle_at_center,rgba(255,255,255,0.16)_1px,transparent_1px)] [background-size:18px_18px]"
              aria-hidden="true"
            />
            <div className="relative flex h-28 w-24 rotate-3 flex-col items-center justify-center rounded-2xl border border-white/25 bg-ink-900/80 shadow-panel">
              <ShieldQuestion className="h-10 w-10 text-violet-200" aria-hidden="true" />
              <span className="mt-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                Secret
              </span>
            </div>
            <span className="absolute bottom-3 inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-black/40 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-300">
              <EyeOff className="h-3 w-3" aria-hidden="true" />
              You cannot see this
            </span>
          </div>

          <div className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="violet">
                <Fingerprint className="h-3 w-3" aria-hidden="true" />
                Your identity
              </Badge>
              {state.self.team_name ? (
                <Badge tone="cyan">Team {state.self.team_name}</Badge>
              ) : null}
              {state.identity_revealed ? <Badge tone="green">Revealed</Badge> : null}
            </div>

            <h2 className="mt-3 font-display text-2xl font-semibold tracking-tight text-white">
              {state.identity_revealed
                ? "Your identity is revealed"
                : "A character is hiding behind your name"}
            </h2>
            <p className="mt-2 max-w-lg text-sm leading-6 text-slate-400">
              {state.identity_revealed
                ? "The match has ended. The server's personalized view decides whether a secret identity can be shown."
                : "Every other participant can see which character belongs to you. Use their answers, the visible characters, and the process of elimination to work it out."}
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button
                onClick={() => setOpen(true)}
                disabled={!connected || guessing}
                loading={guessing}
                icon={guessing ? undefined : <Trophy className="h-4 w-4" />}
              >
                {guessing ? "Checking guess" : "Guess my character"}
              </Button>
              <span className="text-xs text-slate-500">
                A wrong guess is public in the match record.
              </span>
            </div>

            {!state.identity_assigned ? (
              <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/[0.07] px-3 py-2 text-xs text-amber-200">
                Assignments have not reached this connection yet. Reconnecting
                will re-request your personalized state.
              </p>
            ) : null}
          </div>
        </div>
      </Card>

      <GuessDialog open={open} onClose={() => setOpen(false)} state={state} />
    </>
  );
}
