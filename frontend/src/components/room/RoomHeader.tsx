import { LogOut, Radio, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Brand } from "@/components/layout/Brand";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConnectionBadge } from "@/components/ui/ConnectionBadge";
import { Modal } from "@/components/ui/Modal";
import { useAuthStore } from "@/stores/authStore";
import { useRoomStore } from "@/stores/roomStore";
import { titleCaseEnum } from "@/lib/format";

const statusTone = {
  waiting: "amber",
  in_progress: "green",
  closed: "rose",
} as const;

export function RoomHeader() {
  const navigate = useNavigate();
  const session = useAuthStore((state) => state.session);
  const room = useRoomStore((state) => state.room);
  const leaveRoom = useRoomStore((state) => state.leaveRoom);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);

  if (!session || !room) {
    return null;
  }

  const isHost = room.host_player_id === session.playerId;

  async function onLeave() {
    setLeaving(true);
    const left = await leaveRoom();
    setLeaving(false);
    if (left) {
      setConfirmOpen(false);
      navigate("/", { replace: true });
    }
  }

  return (
    <>
      <header className="border-b border-white/[0.07] bg-ink-950/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5 sm:px-6 lg:px-8">
          <Brand compact />

          <div className="hidden h-6 w-px bg-white/10 sm:block" aria-hidden="true" />

          <div className="flex min-w-0 items-center gap-2">
            <Link
              to="/"
              className="truncate font-mono text-lg font-semibold tracking-[0.14em] text-white transition hover:text-violet-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
              title="Room code"
            >
              {room.code}
            </Link>
            <Badge tone={statusTone[room.status]}>{titleCaseEnum(room.status)}</Badge>
          </div>

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <span className="hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs text-slate-400 sm:inline-flex">
              <Users className="h-3.5 w-3.5" aria-hidden="true" />
              {room.player_count}/{room.settings.max_players}
            </span>
            <span className="hidden items-center gap-1.5 text-xs text-slate-400 md:inline-flex">
              <Radio className="h-3.5 w-3.5 text-violet-300" aria-hidden="true" />
              {titleCaseEnum(room.settings.game_mode)}
            </span>
            <ConnectionBadge />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirmOpen(true)}
              icon={<LogOut className="h-4 w-4" />}
            >
              <span className="sr-only sm:not-sr-only">Leave</span>
            </Button>
          </div>
        </div>
      </header>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Leave this room?"
        description={
          isHost
            ? "You are the host. Leaving may hand the room to another player or close it."
            : "You can rejoin later with the room code if the host keeps the room open."
        }
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={leaving}>
              Stay
            </Button>
            <Button variant="danger" loading={leaving} onClick={() => void onLeave()}>
              Leave room
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-slate-400">
          Your session for <span className="font-mono text-slate-200">{room.code}</span>{" "}
          will be removed from this browser tab.
        </p>
      </Modal>
    </>
  );
}
