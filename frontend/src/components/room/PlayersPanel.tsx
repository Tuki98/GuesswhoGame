import {
  CheckCircle2,
  Circle,
  Crown,
  UserMinus,
  UserRound,
  WifiOff,
} from "lucide-react";
import { useState } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Feedback";
import { Modal } from "@/components/ui/Modal";
import { cn } from "@/lib/cn";
import { pluralize } from "@/lib/format";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { usePendingStore } from "@/stores/pendingStore";
import { useRoomStore } from "@/stores/roomStore";
import type { PublicPlayer } from "@/types/api";

export function PlayersPanel() {
  const session = useAuthStore((state) => state.session);
  const room = useRoomStore((state) => state.room);
  const players = useRoomStore((state) => state.players);
  const setReady = useRoomStore((state) => state.setReady);
  const removePlayer = useRoomStore((state) => state.removePlayer);
  const connected = useConnectionStore((state) => state.status === "connected");
  const selfPending = usePendingStore((state) =>
    session ? state.pending[`ready:${session.playerId}`] : undefined,
  );
  const [removeTarget, setRemoveTarget] = useState<PublicPlayer | null>(null);
  const [removing, setRemoving] = useState(false);

  if (!session || !room) {
    return null;
  }

  const isHost = room.host_player_id === session.playerId;
  const waiting = room.status === "waiting";
  const me = players.find((player) => player.id === session.playerId);
  const readyCount = players.filter((player) => player.is_ready).length;

  async function onRemove() {
    if (!removeTarget) {
      return;
    }
    setRemoving(true);
    const removed = await removePlayer(removeTarget.id);
    setRemoving(false);
    if (removed) {
      setRemoveTarget(null);
    }
  }

  return (
    <Card className="p-5">
      <CardHeader
        title="Players"
        description={`${players.length} ${pluralize(players.length, "player")} · ${readyCount} ready`}
        action={
          me && waiting ? (
            <Button
              size="sm"
              variant={me.is_ready ? "success" : "secondary"}
              loading={Boolean(selfPending)}
              disabled={!connected}
              onClick={() => setReady(!me.is_ready)}
              icon={
                me.is_ready ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <Circle className="h-4 w-4" />
                )
              }
            >
              {me.is_ready ? "Ready" : "I'm ready"}
            </Button>
          ) : null
        }
      />

      <div className="mt-4 space-y-2">
        {players.length === 0 ? (
          <EmptyState
            icon={<UserRound className="h-6 w-6" />}
            title="No players yet"
            message="Share the invite link to bring people into the lobby."
          />
        ) : (
          players.map((player) => {
            const isSelf = player.id === session.playerId;
            const isPlayerHost = player.id === room.host_player_id;
            return (
              <div
                key={player.id}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-3 py-2.5",
                  isSelf
                    ? "border-violet-400/25 bg-violet-500/[0.06]"
                    : "border-white/10 bg-black/20",
                )}
              >
                <div className="relative">
                  <Avatar name={player.nickname} />
                  <span
                    className={cn(
                      "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-ink-850",
                      player.is_connected ? "bg-emerald-400" : "bg-slate-600",
                    )}
                    title={player.is_connected ? "Connected" : "Disconnected"}
                  />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate text-sm font-semibold text-white">
                      {player.nickname}
                    </span>
                    {isSelf ? <Badge tone="violet">You</Badge> : null}
                    {isPlayerHost ? (
                      <Badge tone="amber">
                        <Crown className="h-3 w-3" aria-hidden="true" />
                        Host
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                    {player.is_ready ? (
                      <span className="inline-flex items-center gap-1 text-emerald-300">
                        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                        Ready
                      </span>
                    ) : (
                      <span>Not ready</span>
                    )}
                    {!player.is_connected ? (
                      <span className="inline-flex items-center gap-1 text-amber-300">
                        <WifiOff className="h-3 w-3" aria-hidden="true" />
                        Offline
                      </span>
                    ) : null}
                  </div>
                </div>

                {isHost && waiting && !isSelf ? (
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={!connected}
                      onClick={() => setReady(!player.is_ready, player.id)}
                      title={player.is_ready ? "Mark as not ready" : "Mark as ready"}
                    >
                      {player.is_ready ? "Unready" : "Ready"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={!connected}
                      onClick={() => setRemoveTarget(player)}
                      title={`Remove ${player.nickname}`}
                      aria-label={`Remove ${player.nickname}`}
                      className="text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
                    >
                      <UserMinus className="h-4 w-4" />
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>

      <Modal
        open={Boolean(removeTarget)}
        onClose={() => setRemoveTarget(null)}
        title="Remove player?"
        description={
          removeTarget
            ? `${removeTarget.nickname} will be removed from the lobby and will need a new invite to return.`
            : undefined
        }
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRemoveTarget(null)} disabled={removing}>
              Cancel
            </Button>
            <Button variant="danger" loading={removing} onClick={() => void onRemove()}>
              Remove player
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-slate-400">
          Only the host can remove players, and only while the room is waiting.
        </p>
      </Modal>
    </Card>
  );
}
