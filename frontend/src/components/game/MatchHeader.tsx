import { Ban, Clock3, Swords, Users } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { formatTime, titleCaseEnum } from "@/lib/format";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { usePendingStore } from "@/stores/pendingStore";
import { useRoomStore } from "@/stores/roomStore";
import type { MatchState } from "@/types/api";

export function MatchHeader({ state }: { state: MatchState }) {
  const session = useAuthStore((store) => store.session);
  const room = useRoomStore((store) => store.room);
  const cancelMatch = useMatchStore((store) => store.cancelMatch);
  const connected = useConnectionStore((store) => store.status === "connected");
  const cancelling = usePendingStore((store) => Boolean(store.pending.match_cancel));
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!session || !room) {
    return null;
  }

  const isHost = room.host_player_id === session.playerId;
  const yourTurn = state.self.is_your_turn;
  const pending = state.pending_question;

  function onCancel() {
    const sent = cancelMatch();
    if (sent) {
      setConfirmOpen(false);
    }
  }

  return (
    <>
      <Card
        className={`p-5 ${
          yourTurn
            ? "border-violet-400/30 bg-gradient-to-r from-violet-500/[0.12] via-fuchsia-500/[0.05] to-transparent"
            : ""
        }`}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <span
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border ${
                yourTurn
                  ? "border-violet-400/30 bg-violet-500/15 text-violet-200"
                  : "border-white/10 bg-white/[0.04] text-slate-400"
              }`}
            >
              <Swords className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={yourTurn ? "violet" : "neutral"}>
                  {yourTurn ? "Your turn" : "Live match"}
                </Badge>
                <Badge tone="cyan">{titleCaseEnum(state.match.mode)}</Badge>
                <Badge tone="neutral">{titleCaseEnum(state.match.phase)}</Badge>
              </div>
              <h1 className="mt-2 font-display text-2xl font-semibold tracking-tight text-white">
                {yourTurn
                  ? pending
                    ? "Your question is on the table"
                    : "Ask the room"
                  : state.match.current_turn_name
                    ? `${state.match.current_turn_name} is taking a turn`
                    : "The table is turning"}
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                {yourTurn
                  ? pending
                    ? `Waiting for ${pending.recipient_name ?? "the recipient"} to answer.`
                    : "Choose a participant, ask anything, and read the answer carefully."
                  : "Watch the questions come in. You can still study characters or make a guess."}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5" aria-hidden="true" />
              {state.match.participant_count}{" "}
              {state.match.mode === "team" ? "teams" : "players"}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
              Started {formatTime(state.match.started_at)}
            </span>
            {isHost ? (
              <Button
                size="sm"
                variant="danger"
                disabled={!connected}
                loading={cancelling}
                onClick={() => setConfirmOpen(true)}
                icon={<Ban className="h-4 w-4" />}
              >
                Cancel match
              </Button>
            ) : null}
          </div>
        </div>
      </Card>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Cancel this match?"
        description="All progress ends immediately. The room returns to the lobby with its players, teams, and characters intact."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={cancelling}>
              Keep playing
            </Button>
            <Button variant="danger" loading={cancelling} onClick={onCancel}>
              Cancel match
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-slate-400">
          Everyone will receive a cancellation notice and the match record stays
          available for review.
        </p>
      </Modal>
    </>
  );
}
