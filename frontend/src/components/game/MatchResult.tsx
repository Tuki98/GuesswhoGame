import {
  ArrowLeft,
  Ban,
  Crown,
  EyeOff,
  Flag,
  Timer,
  Trophy,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { formatDuration, titleCaseEnum } from "@/lib/format";
import { useRoomStore } from "@/stores/roomStore";
import type { MatchState } from "@/types/api";

export function MatchResult({
  state,
  endedReason,
  isHost,
}: {
  state: MatchState;
  endedReason: string | null;
  isHost: boolean;
}) {
  const room = useRoomStore((store) => store.room);
  const cancelled = state.match.phase === "cancelled";
  const won =
    state.match.winner_player_id === state.self.player_id ||
    (Boolean(state.self.team_id) && state.match.winner_team_id === state.self.team_id);
  const mode = titleCaseEnum(state.match.mode);
  const questionCount = state.question_history.length;
  const duration = formatDuration(state.match.started_at, state.match.finished_at);

  return (
    <Card
      className={`overflow-hidden ${
        cancelled
          ? "border-slate-400/15"
          : won
            ? "border-emerald-400/25"
            : "border-violet-400/20"
      }`}
    >
      <div
        className={`relative px-5 py-7 text-center sm:px-8 ${
          cancelled
            ? "bg-gradient-to-b from-slate-500/10 to-transparent"
            : won
              ? "bg-gradient-to-b from-emerald-500/15 via-emerald-500/[0.04] to-transparent"
              : "bg-gradient-to-b from-violet-500/15 via-violet-500/[0.04] to-transparent"
        }`}
      >
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-white/15 bg-ink-900/70 shadow-panel">
          {cancelled ? (
            <Ban className="h-8 w-8 text-slate-300" aria-hidden="true" />
          ) : won ? (
            <Trophy className="h-8 w-8 text-amber-300" aria-hidden="true" />
          ) : (
            <Flag className="h-8 w-8 text-violet-200" aria-hidden="true" />
          )}
        </div>

        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Badge tone={cancelled ? "neutral" : won ? "green" : "violet"}>
            {cancelled ? "Match cancelled" : "Match complete"}
          </Badge>
          <Badge tone="cyan">{mode}</Badge>
          {endedReason ? <Badge tone="neutral">{titleCaseEnum(endedReason)}</Badge> : null}
        </div>

        <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-white">
          {cancelled
            ? "The table has closed"
            : won
              ? state.match.mode === "team"
                ? "Your team found its character"
                : "You found your character"
              : state.match.winner_name
                ? `${state.match.winner_name} wins`
                : "The match is over"}
        </h1>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-400">
          {cancelled
            ? "The host cancelled the match. Everyone is back in the lobby and the room is ready for another game."
            : won
              ? "A correct guess ended the match immediately. The rest of the room will see the result and the full history."
              : state.match.winner_name
                ? `${state.match.winner_name} guessed their secret identity first. Review the questions below to see how it unfolded.`
                : "The match ended without a winner."}
        </p>

        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {room ? (
            <Link to={`/room/${room.code}`}>
              <Button variant="secondary" icon={<ArrowLeft className="h-4 w-4" />}>
                Back to lobby
              </Button>
            </Link>
          ) : null}
          {room && isHost && !cancelled ? (
            <Link to={`/room/${room.code}`}>
              <Button icon={<Trophy className="h-4 w-4" />}>Set up a rematch</Button>
            </Link>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 border-t border-white/10 p-5 sm:grid-cols-3">
        <ResultStat
          icon={<Users className="h-4 w-4" />}
          label={state.match.mode === "team" ? "Teams" : "Players"}
          value={String(state.match.participant_count)}
        />
        <ResultStat
          icon={<Timer className="h-4 w-4" />}
          label="Duration"
          value={duration}
        />
        <ResultStat
          icon={<Crown className="h-4 w-4" />}
          label="Winner"
          value={state.match.winner_name ?? "No winner"}
        />
      </div>

      <div className="border-t border-white/10 px-5 py-4">
        <div className="flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-xs leading-5 text-slate-400">
          <EyeOff className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <p>
            Secret identities stay hidden in the server&apos;s completion view
            (<span className="font-mono text-[11px]">identity_revealed: false</span>).
            The room saw your character all along — compare notes with them.
          </p>
        </div>
        <p className="mt-3 text-center text-xs text-slate-600">
          {questionCount} {questionCount === 1 ? "question" : "questions"} recorded ·{" "}
          {titleCaseEnum(state.match.phase)}
        </p>
      </div>
    </Card>
  );
}

function ResultStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.05] text-slate-400">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </p>
        <p className="truncate text-sm font-semibold text-white">{value}</p>
      </div>
    </div>
  );
}
