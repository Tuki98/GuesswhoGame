import { Plus, Shield, UserMinus, Users, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Feedback";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useRoomStore } from "@/stores/roomStore";

export function TeamsPanel() {
  const session = useAuthStore((state) => state.session);
  const room = useRoomStore((state) => state.room);
  const players = useRoomStore((state) => state.players);
  const teams = useRoomStore((state) => state.teams);
  const createTeam = useRoomStore((state) => state.createTeam);
  const assignTeam = useRoomStore((state) => state.assignTeam);
  const connected = useConnectionStore((state) => state.status === "connected");
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyPlayer, setBusyPlayer] = useState<string | null>(null);

  if (!session || !room || room.settings.game_mode !== "team") {
    return null;
  }

  const isHost = room.host_player_id === session.playerId;
  const editable = isHost && room.status === "waiting";
  const assignedIds = new Set(teams.flatMap((team) => team.members.map((member) => member.id)));
  const unassigned = players.filter((player) => !assignedIds.has(player.id));
  const emptyTeams = teams.filter((team) => team.members.length === 0);

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || creating) {
      return;
    }
    setCreating(true);
    const created = await createTeam(trimmed);
    setCreating(false);
    if (created) {
      setName("");
    }
  }

  async function onChangeTeam(playerId: string, teamId: string) {
    setBusyPlayer(playerId);
    await assignTeam(playerId, teamId || null);
    setBusyPlayer(null);
  }

  return (
    <Card className="p-5">
      <CardHeader
        title="Teams"
        description="Each team shares one secret identity. Every player must be assigned before the match can start."
        action={
          <Badge tone={teams.length >= 2 ? "green" : "amber"}>
            {teams.length} {teams.length === 1 ? "team" : "teams"}
          </Badge>
        }
      />

      {editable ? (
        <form onSubmit={onCreate} className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field label="New team" htmlFor="team-name" className="flex-1">
            <TextInput
              id="team-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Team Rocket"
              maxLength={40}
              disabled={!connected}
            />
          </Field>
          <Button
            type="submit"
            variant="secondary"
            loading={creating}
            disabled={!connected || name.trim().length === 0}
            icon={<Plus className="h-4 w-4" />}
          >
            Add team
          </Button>
        </form>
      ) : null}

      {teams.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            icon={<Shield className="h-6 w-6" />}
            title="No teams yet"
            message={
              editable
                ? "Create at least two teams, then assign every player."
                : "The host has not created any teams yet."
            }
          />
        </div>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {teams.map((team) => (
            <div
              key={team.id}
              className="rounded-xl border border-white/10 bg-black/20 p-3.5"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="truncate font-display text-sm font-semibold text-white">
                  {team.name}
                </h3>
                <span className="shrink-0 text-xs text-slate-500">
                  {team.members.length}{" "}
                  {team.members.length === 1 ? "member" : "members"}
                </span>
              </div>
              <div className="mt-2.5 space-y-1.5">
                {team.members.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-white/10 px-2.5 py-2 text-xs text-slate-500">
                    Empty team
                  </p>
                ) : (
                  team.members.map((member) => (
                    <div
                      key={member.id}
                      className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-2 py-1.5"
                    >
                      <Avatar name={member.nickname} size="sm" />
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-200">
                        {member.nickname}
                        {member.id === session.playerId ? (
                          <span className="ml-1 text-xs text-violet-300">(you)</span>
                        ) : null}
                      </span>
                      {member.is_ready ? (
                        <span
                          className="h-2 w-2 rounded-full bg-emerald-400"
                          title="Ready"
                        />
                      ) : null}
                      {editable ? (
                        <button
                          type="button"
                          onClick={() => void onChangeTeam(member.id, "")}
                          disabled={!connected || busyPlayer === member.id}
                          className="rounded p-1 text-slate-500 transition hover:bg-rose-500/10 hover:text-rose-300 disabled:opacity-50"
                          title={`Remove ${member.nickname} from ${team.name}`}
                          aria-label={`Remove ${member.nickname} from ${team.name}`}
                        >
                          <UserMinus className="h-3.5 w-3.5" />
                        </button>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {editable ? (
        <div className="mt-5 border-t border-white/10 pt-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Users className="h-4 w-4 text-slate-400" aria-hidden="true" />
              Unassigned players
            </h3>
            {unassigned.length === 0 && players.length > 0 ? (
              <Badge tone="green">All assigned</Badge>
            ) : (
              <Badge tone={unassigned.length > 0 ? "amber" : "neutral"}>
                {unassigned.length} left
              </Badge>
            )}
          </div>

          <div className="mt-3 space-y-2">
            {unassigned.length === 0 ? (
              <p className="text-xs text-slate-500">
                Every player belongs to a team.
              </p>
            ) : (
              unassigned.map((player) => (
                <div
                  key={player.id}
                  className="flex flex-col gap-2 rounded-xl border border-white/10 bg-black/20 p-2.5 sm:flex-row sm:items-center"
                >
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <Avatar name={player.nickname} size="sm" />
                    <span className="truncate text-sm text-slate-200">
                      {player.nickname}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Select
                      aria-label={`Assign ${player.nickname} to a team`}
                      defaultValue=""
                      disabled={!connected || teams.length === 0 || busyPlayer === player.id}
                      onChange={(event) => void onChangeTeam(player.id, event.target.value)}
                      className="h-9 w-full py-1 text-xs sm:w-44"
                    >
                      <option value="">Choose team…</option>
                      {teams.map((team) => (
                        <option key={team.id} value={team.id}>
                          {team.name}
                        </option>
                      ))}
                    </Select>
                  </div>
                </div>
              ))
            )}
          </div>

          {teams.length < 2 ? (
            <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-amber-300">
              <X className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              Create at least two teams before starting a team match.
            </p>
          ) : emptyTeams.length > 0 ? (
            <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-amber-300">
              <X className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {emptyTeams.map((team) => team.name).join(", ")} needs at least one player.
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
