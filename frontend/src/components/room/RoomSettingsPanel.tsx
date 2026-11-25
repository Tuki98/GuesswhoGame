import { Lock, Settings2, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, Select } from "@/components/ui/Field";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useRoomStore } from "@/stores/roomStore";
import type { GameMode } from "@/types/api";

const playerOptions = Array.from({ length: 15 }, (_, index) => index + 2);

export function RoomSettingsPanel() {
  const session = useAuthStore((state) => state.session);
  const room = useRoomStore((state) => state.room);
  const updateSettings = useRoomStore((state) => state.updateSettings);
  const connected = useConnectionStore((state) => state.status === "connected");
  const [maxPlayers, setMaxPlayers] = useState(room?.settings.max_players ?? 8);
  const [mode, setMode] = useState<GameMode>(room?.settings.game_mode ?? "individual");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (room) {
      setMaxPlayers(room.settings.max_players);
      setMode(room.settings.game_mode);
    }
  }, [room?.id, room?.settings.max_players, room?.settings.game_mode]);

  if (!session || !room) {
    return null;
  }

  const isHost = room.host_player_id === session.playerId;
  const waiting = room.status === "waiting";
  const dirty =
    maxPlayers !== room.settings.max_players || mode !== room.settings.game_mode;
  const tooFewSlots = maxPlayers < room.player_count;

  async function onSave() {
    setSaving(true);
    await updateSettings({ max_players: maxPlayers, game_mode: mode });
    setSaving(false);
  }

  return (
    <Card className="p-5">
      <CardHeader
        title="Room settings"
        description={isHost ? "You control how this room plays." : "Only the host can change these."}
        action={
          <Settings2 className="h-5 w-5 text-slate-500" aria-hidden="true" />
        }
      />

      {!waiting ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-xs leading-5 text-slate-400">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Settings are locked while a match is in progress or the room is closed.
        </div>
      ) : null}

      <div className="mt-4 space-y-4">
        <Field
          label="Maximum players"
          htmlFor="settings-max-players"
          hint={
            tooFewSlots
              ? "This is below the current player count and will be rejected."
              : "From 2 to 16 players."
          }
        >
          <Select
            id="settings-max-players"
            value={maxPlayers}
            disabled={!isHost || !waiting}
            onChange={(event) => setMaxPlayers(Number(event.target.value))}
          >
            {playerOptions.map((count) => (
              <option key={count} value={count}>
                {count} players
              </option>
            ))}
          </Select>
        </Field>

        <fieldset disabled={!isHost || !waiting}>
          <legend className="text-sm font-medium text-slate-200">Game mode</legend>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {(["individual", "team"] as const).map((value) => (
              <label
                key={value}
                className={`cursor-pointer rounded-xl border p-3 text-center text-sm font-medium transition ${
                  mode === value
                    ? "border-violet-400/50 bg-violet-500/10 text-white"
                    : "border-white/10 bg-black/20 text-slate-400 hover:border-white/20"
                } ${!isHost || !waiting ? "cursor-not-allowed opacity-70" : ""}`}
              >
                <input
                  type="radio"
                  name="settings-mode"
                  value={value}
                  checked={mode === value}
                  onChange={() => setMode(value)}
                  className="sr-only"
                />
                {value === "individual" ? "Individual" : "Teams"}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      {isHost ? (
        <div className="mt-5 flex items-center justify-between gap-3 border-t border-white/10 pt-4">
          <Badge tone={dirty ? "amber" : "neutral"}>
            {dirty ? "Unsaved changes" : "Saved"}
          </Badge>
          <Button
            size="sm"
            onClick={() => void onSave()}
            loading={saving}
            disabled={!waiting || !dirty || tooFewSlots || !connected}
          >
            Save settings
          </Button>
        </div>
      ) : (
        <div className="mt-5 flex items-center gap-2 border-t border-white/10 pt-4 text-xs text-slate-500">
          <Users className="h-3.5 w-3.5" aria-hidden="true" />
          {room.settings.max_players} player capacity ·{" "}
          {room.settings.game_mode === "team" ? "Team match" : "Individual match"}
        </div>
      )}
    </Card>
  );
}
