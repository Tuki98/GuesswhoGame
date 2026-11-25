import { Check, Play, ShieldAlert, X } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { usePendingStore } from "@/stores/pendingStore";
import { useRoomStore } from "@/stores/roomStore";

export function StartMatchPanel() {
  const session = useAuthStore((state) => state.session);
  const room = useRoomStore((state) => state.room);
  const players = useRoomStore((state) => state.players);
  const teams = useRoomStore((state) => state.teams);
  const characters = useRoomStore((state) => state.characters);
  const startMatch = useMatchStore((state) => state.startMatch);
  const connected = useConnectionStore((state) => state.status === "connected");
  const starting = usePendingStore((state) => Boolean(state.pending.match_start));

  if (!session || !room) {
    return null;
  }

  const isHost = room.host_player_id === session.playerId;
  const waiting = room.status === "waiting";
  const teamMode = room.settings.game_mode === "team";
  const assignedCount = new Set(
    teams.flatMap((team) => team.members.map((member) => member.id)),
  ).size;
  const emptyTeams = teams.filter((team) => team.members.length === 0);

  const checks = [
    {
      ok: players.length >= 2,
      label: "At least two players",
      detail: `${players.length} in the lobby`,
    },
    teamMode
      ? {
          ok: teams.length >= 2,
          label: "At least two teams",
          detail: `${teams.length} created`,
        }
      : {
          ok: characters.length >= players.length && players.length > 0,
          label: "Characters for every player",
          detail: `${characters.length} characters / ${players.length} players`,
        },
    ...(teamMode
      ? [
          {
            ok: players.length > 0 && assignedCount === players.length,
            label: "Every player assigned to a team",
            detail: `${assignedCount} of ${players.length} assigned`,
          },
          {
            ok: teams.length > 0 && emptyTeams.length === 0,
            label: "No empty teams",
            detail:
              emptyTeams.length === 0
                ? "Every team has at least one player"
                : `${emptyTeams.length} empty`,
          },
          {
            ok: characters.length >= teams.length && teams.length > 0,
            label: "A character for every team",
            detail: `${characters.length} characters / ${teams.length} teams`,
          },
        ]
      : []),
  ];

  const allReady = checks.every((check) => check.ok);
  const readyPlayers = players.filter((player) => player.is_ready).length;

  return (
    <Card className="p-5">
      <CardHeader
        title={isHost ? "Start the match" : "Waiting for the host"}
        description={
          isHost
            ? "Requirements are checked again by the server when you start."
            : "The host will start the match when everyone is ready."
        }
        action={
          <Badge tone={allReady ? "green" : "amber"}>
            {allReady ? "Ready to start" : "Setup needed"}
          </Badge>
        }
      />

      <ul className="mt-4 space-y-2">
        {checks.map((check) => (
          <li
            key={check.label}
            className={cn(
              "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
              check.ok
                ? "border-emerald-400/15 bg-emerald-500/[0.05] text-emerald-100"
                : "border-amber-400/15 bg-amber-500/[0.05] text-amber-100",
            )}
          >
            <span
              className={cn(
                "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full",
                check.ok ? "bg-emerald-400/20 text-emerald-300" : "bg-amber-400/20 text-amber-300",
              )}
            >
              {check.ok ? (
                <Check className="h-3 w-3" aria-hidden="true" />
              ) : (
                <X className="h-3 w-3" aria-hidden="true" />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className="font-medium">{check.label}</span>
              <span className="mt-0.5 block text-xs opacity-70">{check.detail}</span>
            </span>
          </li>
        ))}
      </ul>

      {isHost ? (
        <div className="mt-4 space-y-3 border-t border-white/10 pt-4">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>
              {readyPlayers} of {players.length} players ready
            </span>
            <span>{teamMode ? "Team match" : "Individual match"}</span>
          </div>
          <Button
            fullWidth
            size="lg"
            loading={starting}
            disabled={!waiting || !allReady || !connected}
            onClick={() => startMatch()}
            icon={starting ? undefined : <Play className="h-4 w-4" />}
          >
            {starting ? "Starting match" : "Start match"}
          </Button>
          {!waiting ? (
            <p className="flex items-center gap-1.5 text-xs text-slate-500">
              <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
              A match is already in progress in this room.
            </p>
          ) : !connected ? (
            <p className="text-xs text-amber-300">
              Reconnect to the room before starting the match.
            </p>
          ) : null}
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-xs leading-5 text-slate-400">
          Use the “I&apos;m ready” button so the host knows you are set. The match
          starts automatically for everyone.
        </div>
      )}
    </Card>
  );
}
