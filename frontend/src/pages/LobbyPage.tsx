import { ArrowRight, Radio, Trophy } from "lucide-react";
import { Link } from "react-router-dom";

import { CharactersPanel } from "@/components/room/CharactersPanel";
import { InviteCard } from "@/components/room/InviteCard";
import { PlayersPanel } from "@/components/room/PlayersPanel";
import { RoomSettingsPanel } from "@/components/room/RoomSettingsPanel";
import { StartMatchPanel } from "@/components/room/StartMatchPanel";
import { TeamsPanel } from "@/components/room/TeamsPanel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { titleCaseEnum } from "@/lib/format";
import { useMatchStore } from "@/stores/matchStore";
import { useRoomStore } from "@/stores/roomStore";

export function LobbyPage() {
  const room = useRoomStore((state) => state.room);
  const match = useMatchStore((state) => state.state?.match ?? null);

  if (!room) {
    return null;
  }

  const hasEndedMatch =
    match?.phase === "finished" || match?.phase === "cancelled";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={room.status === "waiting" ? "amber" : "green"}>
              <Radio className="h-3 w-3" aria-hidden="true" />
              {titleCaseEnum(room.status)}
            </Badge>
            <Badge tone="neutral">
              {room.settings.game_mode === "team" ? "Team match" : "Individual match"}
            </Badge>
          </div>
          <h1 className="mt-2 font-display text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            {room.status === "waiting" ? "Lobby" : "Match in progress"}
          </h1>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            {room.status === "waiting"
              ? "Build the collection, form teams, and start when everyone is ready."
              : "The live table is open. Follow the match there."}
          </p>
        </div>

        {room.status === "in_progress" ? (
          <Link to={`/room/${room.code}/play`}>
            <Button icon={<ArrowRight className="h-4 w-4" />}>Open live table</Button>
          </Link>
        ) : hasEndedMatch ? (
          <Link to={`/room/${room.code}/play`}>
            <Button variant="secondary" icon={<Trophy className="h-4 w-4" />}>
              View last result
            </Button>
          </Link>
        ) : null}
      </div>

      {hasEndedMatch ? (
        <Card className="flex flex-col gap-3 border-violet-400/15 bg-violet-500/[0.05] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <Trophy className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold text-white">
                {match?.phase === "cancelled" ? "Last match was cancelled" : "Last match finished"}
              </p>
              <p className="mt-0.5 text-xs text-slate-400">
                {match?.winner_name
                  ? `${match.winner_name} won. The room is waiting for a rematch.`
                  : "The room is waiting. Review the table or start a new match."}
              </p>
            </div>
          </div>
          <Link to={`/room/${room.code}/play`}>
            <Button size="sm" variant="secondary">
              Review result
            </Button>
          </Link>
        </Card>
      ) : null}

      <InviteCard
        roomCode={room.code}
        playerCount={room.player_count}
        maxPlayers={room.settings.max_players}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <PlayersPanel />
          <TeamsPanel />
        </div>
        <div className="space-y-4">
          <StartMatchPanel />
          <RoomSettingsPanel />
        </div>
      </div>

      <CharactersPanel />
    </div>
  );
}
