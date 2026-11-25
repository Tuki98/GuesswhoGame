import { CheckCircle2, Clock3, MessageCircleQuestion } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/Feedback";
import { formatTime } from "@/lib/format";
import type { Question } from "@/types/api";

export function QuestionTimeline({
  questions,
  selfPlayerId,
}: {
  questions: Question[];
  selfPlayerId: string;
}) {
  if (questions.length === 0) {
    return (
      <EmptyState
        icon={<MessageCircleQuestion className="h-6 w-6" />}
        title="No questions yet"
        message="Questions and answers will appear here as the turn passes around the table."
      />
    );
  }

  const ordered = [...questions].sort(
    (left, right) => new Date(right.asked_at).getTime() - new Date(left.asked_at).getTime(),
  );

  return (
    <ol className="space-y-2.5">
      {ordered.map((question) => {
        const mine = question.author_player_id === selfPlayerId;
        return (
          <li
            key={question.id}
            className="rounded-xl border border-white/10 bg-black/20 p-3"
          >
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge tone={mine ? "violet" : "neutral"}>
                {mine ? "You asked" : `${question.author_nickname ?? "Someone"} asked`}
              </Badge>
              <span className="text-slate-500">
                to {question.recipient_name ?? "the room"}
              </span>
              <span className="ml-auto inline-flex items-center gap-1 text-slate-600">
                {question.answer ? (
                  <CheckCircle2 className="h-3 w-3 text-emerald-400" aria-hidden="true" />
                ) : (
                  <Clock3 className="h-3 w-3 text-amber-400" aria-hidden="true" />
                )}
                {formatTime(question.asked_at)}
              </span>
            </div>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-100">
              “{question.content}”
            </p>
            {question.answer ? (
              <div className="mt-2 rounded-lg border border-emerald-400/15 bg-emerald-500/[0.06] px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
                  Answer{question.answer.author_nickname ? ` from ${question.answer.author_nickname}` : ""}
                </p>
                <p className="mt-0.5 text-sm leading-6 text-emerald-50">
                  {question.answer.content}
                </p>
              </div>
            ) : (
              <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-300">
                <Clock3 className="h-3 w-3" aria-hidden="true" />
                Waiting for an answer
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
