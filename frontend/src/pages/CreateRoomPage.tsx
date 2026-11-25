import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { errorMessage } from "@/lib/errors";
import { useAuthStore } from "@/stores/authStore";
import type { GameMode } from "@/types/api";

const modes: Array<{
  value: GameMode;
  title: string;
  description: string;
}> = [
  {
    value: "individual",
    title: "Individual",
    description: "Every player has their own secret character.",
  },
  {
    value: "team",
    title: "Teams",
    description: "Teams share a secret and answer as a group.",
  },
];

export function CreateRoomPage() {
  const navigate = useNavigate();
  const createRoom = useAuthStore((state) => state.createRoom);
  const [nickname, setNickname] = useState("");
  const [maxPlayers, setMaxPlayers] = useState(8);
  const [mode, setMode] = useState<GameMode>("individual");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedNickname = nickname.trim();
  const nicknameError =
    trimmedNickname.length === 0
      ? null
      : trimmedNickname.length < 2
        ? "Use at least 2 characters."
        : trimmedNickname.length > 24
          ? "Use at most 24 characters."
          : null;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError(null);
    if (!trimmedNickname) {
      setError("Choose a nickname before creating the room.");
      return;
    }
    if (trimmedNickname.length < 2 || trimmedNickname.length > 24) {
      setError("Nicknames must be between 2 and 24 characters.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await createRoom({
        nickname: trimmedNickname,
        settings: { max_players: maxPlayers, game_mode: mode },
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
          <Badge tone="violet">New room</Badge>
          <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Set the table
          </h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">
            Choose how your group will play. You can adjust settings later while
            the room is still in the lobby.
          </p>
        </div>

        <Card className="mt-7 p-5 sm:p-7">
          <form onSubmit={onSubmit} noValidate className="space-y-7">
            <Field
              label="Your nickname"
              htmlFor="nickname"
              hint="2–24 characters. Other players will see this name."
              error={nicknameError}
              required
            >
              <TextInput
                id="nickname"
                name="nickname"
                value={nickname}
                onChange={(event) => setNickname(event.target.value)}
                placeholder="e.g. Maya"
                autoComplete="nickname"
                autoFocus
                maxLength={24}
                aria-invalid={Boolean(nicknameError)}
                aria-describedby={nicknameError ? "nickname-error" : "nickname-hint"}
              />
            </Field>

            <fieldset>
              <legend className="text-sm font-medium text-slate-200">Game mode</legend>
              <p className="mt-1 text-xs text-slate-500">
                Team mode needs at least two teams with every player assigned
                before the match can start.
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {modes.map((option) => {
                  const selected = mode === option.value;
                  return (
                    <label
                      key={option.value}
                      className={`relative flex cursor-pointer flex-col gap-1.5 rounded-xl border p-4 transition ${
                        selected
                          ? "border-violet-400/60 bg-violet-500/[0.09] ring-1 ring-violet-400/30"
                          : "border-white/10 bg-black/20 hover:border-white/20 hover:bg-white/[0.04]"
                      }`}
                    >
                      <input
                        type="radio"
                        name="mode"
                        value={option.value}
                        checked={selected}
                        onChange={() => setMode(option.value)}
                        className="sr-only"
                      />
                      <span className="flex items-center justify-between">
                        <span className="font-display font-semibold text-white">
                          {option.title}
                        </span>
                        {selected ? (
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-violet-500 text-white">
                            <Check className="h-3 w-3" aria-hidden="true" />
                          </span>
                        ) : (
                          <span className="h-5 w-5 rounded-full border border-white/20" />
                        )}
                      </span>
                      <span className="text-sm leading-5 text-slate-400">
                        {option.description}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <Field
              label="Maximum players"
              htmlFor="max-players"
              hint="You need at least two players to start a match."
            >
              <div className="flex items-center gap-4">
                <input
                  id="max-players"
                  type="range"
                  min={2}
                  max={16}
                  step={1}
                  value={maxPlayers}
                  onChange={(event) => setMaxPlayers(Number(event.target.value))}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-violet-500"
                  aria-describedby="max-players-hint"
                />
                <span className="flex h-10 min-w-[3rem] items-center justify-center rounded-lg border border-white/10 bg-black/25 font-display text-lg font-semibold text-white">
                  {maxPlayers}
                </span>
              </div>
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
                No account required. Your room is private to its code.
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
                  {submitting ? "Creating room" : "Create room"}
                </Button>
              </div>
            </div>
          </form>
        </Card>

        <div className="mt-5 grid gap-3 text-sm text-slate-500 sm:grid-cols-2">
          <p className="flex items-start gap-2">
            <Users className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" aria-hidden="true" />
            Share the room code or invite link after the lobby opens.
          </p>
          <p className="flex items-start gap-2">
            <Loader2 className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" aria-hidden="true" />
            Live updates keep everyone in sync while you set up.
          </p>
        </div>
      </div>
    </PageShell>
  );
}
