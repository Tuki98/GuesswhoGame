import { HelpCircle, Send, Timer } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, Select, TextArea } from "@/components/ui/Field";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { usePendingStore } from "@/stores/pendingStore";
import type { MatchState } from "@/types/api";

export function AskQuestionPanel({ state }: { state: MatchState }) {
  const sendQuestion = useMatchStore((store) => store.sendQuestion);
  const connected = useConnectionStore((store) => store.status === "connected");
  const sending = usePendingStore((store) => Boolean(store.pending.question));
  const recipients = state.participants.filter((participant) =>
    state.allowed_recipient_ids.includes(participant.id),
  );
  const [recipientId, setRecipientId] = useState(recipients[0]?.id ?? "");
  const [content, setContent] = useState("");

  useEffect(() => {
    if (!recipients.some((recipient) => recipient.id === recipientId)) {
      setRecipientId(recipients[0]?.id ?? "");
    }
  }, [recipients, recipientId]);

  useEffect(() => {
    setContent("");
  }, [state.match.current_turn_id]);

  if (!state.self.can_ask) {
    return (
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-slate-400">
            <Timer className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-base font-semibold text-white">
                Waiting for your turn
              </h2>
              <Badge tone="neutral">Turn in progress</Badge>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {state.match.current_turn_name ? (
                <>
                  <span className="font-semibold text-slate-200">
                    {state.match.current_turn_name}
                  </span>{" "}
                  is asking the next question. You can still study the visible
                  characters or make a guess.
                </>
              ) : (
                "The next turn is being prepared. The table will update automatically."
              )}
            </p>
          </div>
        </div>
      </Card>
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = content.trim();
    if (!trimmed || !recipientId) {
      return;
    }
    const sent = sendQuestion(trimmed, recipientId);
    if (sent) {
      setContent("");
    }
  }

  return (
    <Card className="border-violet-400/25 bg-violet-500/[0.05] p-5">
      <CardHeader
        title="Ask your question"
        description="It is your turn. Questions reach the recipient privately; the answer returns to you and is recorded in the match."
        action={
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-500/10 text-violet-200">
            <HelpCircle className="h-5 w-5" aria-hidden="true" />
          </span>
        }
      />

      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
          <Field
            label={state.match.mode === "team" ? "Ask a team" : "Ask a player"}
            htmlFor="question-recipient"
          >
            <Select
              id="question-recipient"
              value={recipientId}
              onChange={(event) => setRecipientId(event.target.value)}
              disabled={!connected || recipients.length === 0}
            >
              {recipients.length === 0 ? (
                <option value="">No available recipients</option>
              ) : (
                recipients.map((recipient) => (
                  <option key={recipient.id} value={recipient.id}>
                    {recipient.name}
                    {recipient.kind === "team" ? " (team)" : ""}
                  </option>
                ))
              )}
            </Select>
          </Field>
          <Field
            label="Question"
            htmlFor="question-content"
            hint={`${content.length}/500 characters`}
          >
            <TextArea
              id="question-content"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="e.g. Does my character wear a hat?"
              maxLength={500}
              rows={3}
              disabled={!connected}
            />
          </Field>
        </div>

        {recipients.length === 0 ? (
          <p className="text-xs text-amber-300">
            There is nobody else to question in this match.
          </p>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-slate-500">
            One unanswered question is allowed at a time.
          </p>
          <Button
            type="submit"
            loading={sending}
            disabled={
              !connected ||
              recipients.length === 0 ||
              content.trim().length === 0 ||
              Boolean(state.pending_question)
            }
            icon={<Send className="h-4 w-4" />}
          >
            Send question
          </Button>
        </div>
      </form>
    </Card>
  );
}
