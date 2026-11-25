import { MessageCircleQuestion, MessageSquareReply, Send, Timer } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, TextArea } from "@/components/ui/Field";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { usePendingStore } from "@/stores/pendingStore";
import { useRoomStore } from "@/stores/roomStore";
import type { Question } from "@/types/api";

export function PendingQuestionCard({ question }: { question: Question }) {
  const sendAnswer = useMatchStore((state) => state.sendAnswer);
  const connected = useConnectionStore((state) => state.status === "connected");
  const answering = usePendingStore((state) => Boolean(state.pending.answer));
  const [content, setContent] = useState("");
  const author =
    useRoomStore((state) =>
      question.author_player_id
        ? state.players.find((player) => player.id === question.author_player_id)?.nickname
        : null,
    ) ?? question.author_nickname ?? "Another player";

  useEffect(() => {
    setContent("");
  }, [question.id]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = content.trim();
    if (!trimmed) {
      return;
    }
    const sent = sendAnswer(trimmed, question.id);
    if (sent) {
      setContent("");
    }
  }

  if (!question.can_answer) {
    return (
      <Card className="border-amber-400/20 bg-amber-500/[0.04] p-5">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-amber-400/25 bg-amber-500/10 text-amber-200">
            <Timer className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-base font-semibold text-white">
                Question awaiting an answer
              </h2>
              <Badge tone="amber">Pending</Badge>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              <span className="font-semibold text-white">{author}</span> asked{" "}
              <span className="text-slate-400">
                {question.recipient_name ?? "the room"}
              </span>
              :
            </p>
            <p className="mt-1.5 rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-sm leading-6 text-slate-100">
              “{question.content}”
            </p>
            <p className="mt-2 text-xs text-slate-500">
              The next turn begins when the recipient answers.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="border-violet-400/25 bg-violet-500/[0.05] p-5">
      <CardHeader
        title="Answer the question"
        description={`${author} is waiting on your response.`}
        action={
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-500/10 text-violet-200">
            <MessageSquareReply className="h-5 w-5" aria-hidden="true" />          </span>
        }
      />

      <blockquote className="mt-4 rounded-xl border border-white/10 bg-black/25 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {author} asked
        </p>
        <p className="mt-1 text-sm font-medium leading-6 text-white">
          “{question.content}”
        </p>
      </blockquote>

      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <Field
          label="Your answer"
          htmlFor="answer-content"
          hint="Answers are visible to everyone in the match record. 1–1000 characters."
        >
          <TextArea
            id="answer-content"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="Answer truthfully — the others can see your character…"
            maxLength={1_000}
            rows={3}
            disabled={!connected}
            autoFocus
          />
        </Field>
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
            <MessageCircleQuestion className="h-3.5 w-3.5" aria-hidden="true" />
            Answering passes the turn.
          </span>
          <Button
            type="submit"
            loading={answering}
            disabled={!connected || content.trim().length === 0}
            icon={<Send className="h-4 w-4" />}
          >
            Send answer
          </Button>
        </div>
      </form>
    </Card>
  );
}
