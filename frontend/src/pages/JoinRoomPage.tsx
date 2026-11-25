import { ArrowLeft, ArrowRight, Hash, ShieldCheck, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { errorMessage } from "@/lib/errors";
import { normalizeRoomCode } from "@/lib/format";
import { useAuthStore } from "@/stores/authStore";

export function JoinRoomPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const joinRoom = useAuthStore((state) => state.joinRoom);
  const currentSession = useAuthStore((state) => state.session);
  const [code, setCode] = useState(() =>
    normalizeRoomCode(searchParams.get("code") ?? ""),
  );
  const [nickname, setNickname] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedNickname = nickname.trim();
  const normalizedCode = normalizeRoomCode(code);
  const nicknameError =
    trimmedNickname.length > 0 &&
    (trimmedNickname.length < 2 || trimmedNickname.length > 24)
      ? "Nicknames must be between 2 and 24 characters."
      : null;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError(null);
    if (!normalizedCode) {
      setError("Enter the room code from your host.");
      return;
    }
    if (trimmedNickname.length < 2 || trimmedNickname.length > 24) {
      setError("Choose a nickname between 2 and 24 characters.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await joinRoom({
        code: normalizedCode,
        nickname: trimmedNickname,
      });
      navigate(`/room/${response.room.code}`, { replace: true });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageShell>
      <div className="mx-auto max-w-3xl py-4 sm:py-8">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 rounded-lg px-1 py-1 text-sm text-slate-400 transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back
        </Link>

        <div className="mt-5">
          <Badge tone="cyan">Invitation</Badge>
          <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Join the room
          </h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">
            Enter the code your host shared. You will join the lobby immediately
            and can see the room settings before the game starts.
          </p>
        </div>

        <Card className="mt-7 p-5 sm:p-7">
          <form onSubmit={onSubmit} noValidate className="space-y-6">
            {currentSession ? (
              <div className="rounded-xl border border-amber-400/20 bg-amber-500/[0.07] px-4 py-3 text-sm text-amber-200">
                You are currently signed in as{" "}
                <span className="font-semibold">{currentSession.nickname}</span> in{" "}
                <span className="font-mono font-semibold">{currentSession.roomCode}</span>.
                Joining another room replaces this tab&apos;s session.
              </div>
            ) : null}

            <Field
              label="Room code"
              htmlFor="room-code"
              hint="Codes look like GTC-ABCD."
              required
            >
              <div className="relative">
                <Hash
                  className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
                  aria-hidden="true"
                />
                <TextInput
                  id="room-code"
                  name="code"
                  value={code}
                  onChange={(event) => setCode(event.target.value.toUpperCase())}
                  placeholder="GTC-ABCD"
                  autoComplete="off"
                  autoCapitalize="characters"
                  spellCheck={false}
                  maxLength={16}
                  className="pl-10 font-mono text-base tracking-[0.2em]"
                  autoFocus
                  aria-describedby="room-code-hint"
                />
              </div>
            </Field>

            <Field
              label="Your nickname"
              htmlFor="join-nickname"
              hint="2–24 characters, unique within the room."
              error={nicknameError}
              required
            >
              <TextInput
                id="join-nickname"
                name="nickname"
                value={nickname}
                onChange={(event) => setNickname(event.target.value)}
                placeholder="e.g. Sam"
                autoComplete="nickname"
                maxLength={24}
                aria-invalid={Boolean(nicknameError)}
                aria-describedby={nicknameError ? "join-nickname-error" : "join-nickname-hint"}
              />
            </Field>

            {error ? (
              <p
                className="rounded-xl border border-rose-400/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
                role="alert"
              >
                {error}
              </p>
            ) : null}

            <div className="flex flex-col-reverse gap-3 border-t border-white/10 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="flex items-center gap-2 text-xs text-slate-500">
                <ShieldCheck className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                Your session token stays in this tab.
              </p>
              <div className="flex gap-2">
                <Link to="/">
                  <Button type="button" variant="ghost">
                    Cancel
                  </Button>
                </Link>
                <Button
                  type="submit"
                  loading={submitting}
                  icon={submitting ? undefined : <ArrowRight className="h-4 w-4" />}
                >
                  {submitting ? "Joining" : "Join room"}
                </Button>
              </div>
            </div>
          </form>
        </Card>

        <p className="mt-5 flex items-start gap-2 text-sm text-slate-500">
          <Users className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" aria-hidden="true" />
          Ask your host to resend the invite link if the code does not work.
        </p>
      </div>
    </PageShell>
  );
}
