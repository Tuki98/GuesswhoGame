import { History, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Feedback";
import { Spinner } from "@/components/ui/Feedback";
import { formatTime, titleCaseEnum } from "@/lib/format";
import { useMatchStore } from "@/stores/matchStore";
import { useRoomStore } from "@/stores/roomStore";
import type { GameEvent } from "@/types/api";

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function MatchHistoryPanel({ events }: { events: GameEvent[] }) {
  const players = useRoomStore((store) => store.players);
  const teams = useRoomStore((store) => store.teams);
  const syncing = useMatchStore((store) => store.syncing);
  const hasMore = useMatchStore((store) => store.historyHasMore);
  const syncHistory = useMatchStore((store) => store.syncHistory);
  const nameById = new Map(players.map((player) => [player.id, player.nickname]));
  const teamNameById = new Map(teams.map((team) => [team.id, team.name]));

  function describe(event: GameEvent): { title: string; detail?: string; tone: "neutral" | "violet" | "green" | "rose" | "amber" } {
    const payload = event.payload;
    const actor = event.actor_player_id ? nameById.get(event.actor_player_id) : null;
    switch (event.event_type) {
      case "match_started":
        return { title: "Match started", tone: "violet" };
      case "turn_changed":
        return { title: "Turn passed", tone: "neutral" };
      case "question_sent": {
        const content = asString(payload.content);
        return {
          title: `${actor ?? "A player"} asked a question`,
          detail: content ? `“${content}”` : undefined,
          tone: "violet",
        };
      }
      case "answer_sent": {
        const answer = asString(payload.answer);
        return {
          title: `${actor ?? "A player"} answered`,
          detail: answer ? `“${answer}”` : undefined,
          tone: "green",
        };
      }
      case "guess_submitted":
        return {
          title: `${actor ?? "A player"} submitted a guess`,
          detail: payload.correct === true ? "Correct" : "Recorded without revealing the character",
          tone: "amber",
        };
      case "guess_incorrect":
        return { title: `${actor ?? "A player"} guessed wrong`, tone: "rose" };
      case "guess_correct":
        return { title: `${actor ?? "A player"} found their character`, tone: "green" };
      case "match_finished": {
        const winnerPlayer = asString(payload.winner_player_id);
        const winnerTeam = asString(payload.winner_team_id);
        const winner =
          (winnerPlayer ? nameById.get(winnerPlayer) : null) ??
          (winnerTeam ? teamNameById.get(winnerTeam) : null);
        return {
          title: winner ? `${winner} won the match` : "Match finished",
          detail: asString(payload.reason) ? titleCaseEnum(asString(payload.reason)!) : undefined,
          tone: "green",
        };
      }
      case "match_cancelled":
        return {
          title: "Match cancelled",
          detail: asString(payload.reason) ? titleCaseEnum(asString(payload.reason)!) : undefined,
          tone: "rose",
        };
      case "player_joined":
        return { title: `${actor ?? "A player"} joined`, tone: "neutral" };
      case "player_left":
        return { title: `${actor ?? "A player"} left`, tone: "neutral" };
      default:
        return { title: titleCaseEnum(event.event_type), tone: "neutral" };
    }
  }

  return (
    <Card className="p-5">
      <CardHeader
        title="Match history"
        description="Ordered server events. The sequence numbers come from the backend log."
        action={
          <Button
            size="sm"
            variant="secondary"
            loading={syncing}
            onClick={() => void syncHistory()}
            icon={syncing ? undefined : <RefreshCw className="h-4 w-4" />}
          >
            Sync
          </Button>
        }
      />

      {events.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            icon={<History className="h-6 w-6" />}
            title="No events yet"
            message="Match events appear here in sequence as soon as the server records them."
          />
        </div>
      ) : (
        <>
          <ol className="mt-4 max-h-80 space-y-1.5 overflow-y-auto pr-1">
            {events.map((event) => {
              const described = describe(event);
              return (
                <li
                  key={event.id}
                  className="flex items-start gap-3 rounded-lg border border-white/[0.07] bg-black/15 px-3 py-2"
                >
                  <span className="mt-0.5 w-7 shrink-0 font-mono text-[10px] text-slate-600">
                    #{event.sequence_number}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-slate-200">
                        {described.title}
                      </span>
                      <Badge tone={described.tone} className="px-1.5 py-0 text-[9px]">
                        {titleCaseEnum(event.event_type)}
                      </Badge>
                    </div>
                    {described.detail ? (
                      <p className="mt-0.5 break-words text-xs leading-5 text-slate-500">
                        {described.detail}
                      </p>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-[10px] text-slate-600">
                    {formatTime(event.created_at)}
                  </span>
                </li>
              );
            })}
          </ol>
          {hasMore ? (
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-300">
              <Spinner className="h-3.5 w-3.5" />
              More events are available — press Sync.
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}
