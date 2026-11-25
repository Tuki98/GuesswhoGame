import { Crown, Radio, Users } from "lucide-react";

import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { useRoomStore } from "@/stores/roomStore";
import type { MatchState } from "@/types/api";

export function ParticipantsPanel({ state }: { state: MatchState }) {
  const players = useRoomStore((store) => store.players);
  const nameById = new Map(players.map((player) => [player.id, player.nickname]));
  const currentTurnId = state.match.current_turn_id;

  return (
    <Card className="p-5">
      <CardHeader
        title="At the table"
        description="The current turn is highlighted. Teams share a single identity."
        action={<Users className="h-5 w-5 text-slate-500" aria-hidden="true" />}
      />

      <div className="mt-4 space-y-2">
        {state.participants.map((participant) => {
          const isCurrent = participant.id === currentTurnId;
          const isSelf =
            participant.kind === "team"
              ? participant.id === state.self.team_id
              : participant.id === state.self.player_id;
          return (
            <div
              key={participant.id}
              className={cn(
                "rounded-xl border px-3 py-2.5",
                isCurrent
                  ? "border-violet-400/30 bg-violet-500/[0.08]"
                  : "border-white/10 bg-black/20",
              )}
            >
              <div className="flex items-center gap-2.5">
                <div className="relative">
                  <Avatar
                    name={participant.name}
                    size="sm"
                    className={participant.kind === "team" ? "rounded-lg" : undefined}
                  />
                  <span
                    className={cn(
                      "absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-ink-850",
                      participant.is_connected ? "bg-emerald-400" : "bg-slate-600",
                    )}
                    title={participant.is_connected ? "Connected" : "Disconnected"}
                  />
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-white">
                  {participant.name}
                </span>
                {isSelf ? <Badge tone="violet">You</Badge> : null}
                {participant.kind === "team" ? (
                  <Badge tone="cyan">
                    <Users className="h-3 w-3" aria-hidden="true" />
                    Team
                  </Badge>
                ) : null}
                {isCurrent ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-violet-300">
                    <Radio className="h-3 w-3" aria-hidden="true" />
                    Turn
                  </span>
                ) : null}
              </div>

              {participant.kind === "team" && participant.member_player_ids.length > 0 ? (
                <p className="mt-1.5 pl-9 text-[11px] leading-5 text-slate-500">
                  {participant.member_player_ids
                    .map((id) => nameById.get(id))
                    .filter(Boolean)
                    .join(" · ") || "Team members"}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      {state.match.winner_name ? (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-amber-400/20 bg-amber-500/[0.06] px-3 py-2.5 text-sm text-amber-100">
          <Crown className="h-4 w-4 shrink-0 text-amber-300" aria-hidden="true" />
          <span>
            <span className="font-semibold">{state.match.winner_name}</span> won this
            match.
          </span>
        </div>
      ) : null}
    </Card>
  );
}
