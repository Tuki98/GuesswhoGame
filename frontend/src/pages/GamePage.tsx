import {
  AlertTriangle,
  ArrowLeft,
  HelpCircle,
  MessageCircleQuestion,
  RefreshCw,
  Swords,
} from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";

import { AskQuestionPanel } from "@/components/game/AskQuestionPanel";
import { IdentityCard } from "@/components/game/IdentityCard";
import { MatchHeader } from "@/components/game/MatchHeader";
import { MatchHistoryPanel } from "@/components/game/MatchHistoryPanel";
import { MatchResult } from "@/components/game/MatchResult";
import { OpponentsPanel } from "@/components/game/OpponentsPanel";
import { ParticipantsPanel } from "@/components/game/ParticipantsPanel";
import { PendingQuestionCard } from "@/components/game/PendingQuestionCard";
import { QuestionTimeline } from "@/components/game/QuestionTimeline";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { LoadingPanel } from "@/components/ui/Feedback";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { useRoomStore } from "@/stores/roomStore";

export function GamePage() {
  const session = useAuthStore((store) => store.session);
  const room = useRoomStore((store) => store.room);
  const state = useMatchStore((store) => store.state);
  const history = useMatchStore((store) => store.history);
  const error = useMatchStore((store) => store.error);
  const endedReason = useMatchStore((store) => store.endedReason);
  const requestState = useMatchStore((store) => store.requestState);
  const connected = useConnectionStore((store) => store.status === "connected");

  const match = state && room && state.match.room_id === room.id ? state : null;

  useEffect(() => {
    if (!room || !connected || match) {
      return;
    }
    if (room.status === "in_progress") {
      requestState(0);
    }
  }, [room?.status, connected, match, requestState]);

  if (!room) {
    return null;
  }

  if (!match) {
    if (room.status === "in_progress") {
      return (
        <div className="space-y-4">
          <LoadingPanel
            title="Joining the live table"
            message="Requesting your personalized match state from the server."
          />
          {error ? (
            <Card className="p-5">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  className="mt-0.5 h-5 w-5 shrink-0 text-amber-300"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm font-semibold text-white">
                    The match snapshot could not be refreshed
                  </p>
                  <p className="mt-1 text-sm text-slate-400">{error}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!connected}
                      onClick={() => requestState(0)}
                      icon={<RefreshCw className="h-4 w-4" />}
                    >
                      Try again
                    </Button>
                    <Link to={`/room/${room.code}`}>
                      <Button size="sm" variant="ghost" icon={<ArrowLeft className="h-4 w-4" />}>
                        Back to lobby
                      </Button>
                    </Link>
                  </div>
                </div>
              </div>
            </Card>
          ) : null}
        </div>
      );
    }

    return (
      <Card className="p-8 text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-400">
          <Swords className="h-6 w-6" aria-hidden="true" />
        </span>
        <h1 className="mt-4 font-display text-xl font-semibold text-white">
          No active match
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">
          The table opens automatically when the host starts a match. You can
          review the lobby, add characters, or get ready in the meantime.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <Link to={`/room/${room.code}`}>
            <Button variant="secondary" icon={<ArrowLeft className="h-4 w-4" />}>
              Back to lobby
            </Button>
          </Link>
        </div>
      </Card>
    );
  }

  const isHost = room.host_player_id === session?.playerId;
  // ``status`` is the persisted enum (``active``); ``phase`` is the friendly
  // lifecycle value (``in_progress``) that the UI reasons about.
  const active = match.match.phase === "in_progress";
  const pendingQuestionId = match.pending_question?.id ?? null;
  // The pending question is rendered in its own answer card; avoid duplicating
  // it at the end of the shared question record.
  const timelineQuestions = pendingQuestionId
    ? match.question_history.filter((question) => question.id !== pendingQuestionId)
    : match.question_history;

  if (!active) {
    return (
      <div className="space-y-4">
        <MatchResult state={match} endedReason={endedReason} isHost={Boolean(isHost)} />
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <Card className="p-5">
            <CardHeader
              title="Question record"
              description="Every question and answer from this match."
              action={
                <MessageCircleQuestion className="h-5 w-5 text-slate-500" aria-hidden="true" />
              }
            />
            <div className="mt-4">
              <QuestionTimeline
                questions={timelineQuestions}
                selfPlayerId={match.self.player_id}
              />
            </div>
          </Card>
          <ParticipantsPanel state={match} />
        </div>
        <MatchHistoryPanel events={history} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <MatchHeader state={match} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <IdentityCard state={match} />

          {match.pending_question ? (
            <PendingQuestionCard question={match.pending_question} />
          ) : (
            <AskQuestionPanel state={match} />
          )}

          <OpponentsPanel opponents={match.opponents} />

          <Card className="p-5">
            <CardHeader
              title="Question record"
              description="Newest first. Answers are part of the shared match record."
              action={
                <MessageCircleQuestion className="h-5 w-5 text-slate-500" aria-hidden="true" />
              }
            />
            <div className="mt-4">
              <QuestionTimeline
                questions={timelineQuestions}
                selfPlayerId={match.self.player_id}
              />
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <ParticipantsPanel state={match} />

          <Card className="p-5">
            <CardHeader
              title="How to win"
              description="A short reminder while the questions fly."
              action={<HelpCircle className="h-5 w-5 text-slate-500" aria-hidden="true" />}
            />
            <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-400">
              <li className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                Everyone can see your character except you. The visible
                characters belong to the other participants.
              </li>
              <li className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                Ask narrow yes/no questions. The recipient answers, then the turn
                passes on.
              </li>
              <li className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                When you are sure, submit a guess. A correct guess wins
                immediately — a wrong one is recorded.
              </li>
            </ul>
          </Card>
        </div>
      </div>

      <MatchHistoryPanel events={history} />
    </div>
  );
}
