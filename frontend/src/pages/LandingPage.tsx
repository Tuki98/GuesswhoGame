import {
  ArrowRight,
  HelpCircle,
  LockKeyhole,
  Sparkles,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuthStore } from "@/stores/authStore";

const steps = [
  {
    icon: Users,
    title: "Gather your players",
    body: "Create a private room, share the code, and fill the lobby.",
  },
  {
    icon: Sparkles,
    title: "Everyone gets a secret",
    body: "Each player is assigned a character from the collection — visible to everyone but them.",
  },
  {
    icon: HelpCircle,
    title: "Ask, deduce, guess",
    body: "Take turns asking questions, then gamble on the identity hiding behind your name.",
  },
];

const sampleCards = [
  { name: "Pikachu", franchise: "Pokémon", from: "from-violet-500/30", rotate: "-rotate-6" },
  { name: "Batman", franchise: "DC", from: "from-cyan-500/25", rotate: "rotate-3" },
  { name: "Lara Croft", franchise: "Tomb Raider", from: "from-fuchsia-500/25", rotate: "-rotate-2" },
];

export function LandingPage() {
  const session = useAuthStore((state) => state.session);
  const status = useAuthStore((state) => state.status);
  const notice = useAuthStore((state) => state.notice);
  const signedIn = status === "authenticated" && Boolean(session);

  return (
    <PageShell>
      <section className="grid items-center gap-10 py-6 sm:py-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:gap-14">
        <div className="animate-slide-up">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="violet">
              <LockKeyhole className="h-3 w-3" aria-hidden="true" />
              Private rooms
            </Badge>
            <Badge tone="cyan">Real-time multiplayer</Badge>
          </div>

          <h1 className="mt-5 text-balance font-display text-4xl font-semibold leading-tight tracking-tight text-white sm:text-5xl lg:text-6xl">
            Everyone can see your character.
            <span className="bg-gradient-to-r from-violet-300 via-fuchsia-300 to-cyan-300 bg-clip-text text-transparent">
              {" "}
              Except you.
            </span>
          </h1>

          <p className="mt-5 max-w-xl text-base leading-7 text-slate-400 sm:text-lg sm:leading-8">
            Guess the Character is a reverse deduction game. Read the room, ask
            the right questions, and work out which character is hiding behind
            your own name.
          </p>

          {notice ? (
            <p
              className="mt-5 rounded-xl border border-amber-400/20 bg-amber-500/[0.07] px-4 py-3 text-sm text-amber-200"
              role="status"
            >
              {notice}
            </p>
          ) : null}

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link to="/create" className="sm:flex-1">
              <Button size="lg" fullWidth icon={<Sparkles className="h-4 w-4" />}>
                Create a room
              </Button>
            </Link>
            <Link to="/join" className="sm:flex-1">
              <Button
                size="lg"
                variant="secondary"
                fullWidth
                icon={<ArrowRight className="h-4 w-4" />}
              >
                Join with a code
              </Button>
            </Link>
          </div>

          {signedIn && session ? (
            <div className="mt-6 flex flex-col gap-3 rounded-xl border border-emerald-400/20 bg-emerald-500/[0.06] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-emerald-100">
                You are still signed in as{" "}
                <span className="font-semibold">{session.nickname}</span> in{" "}
                <span className="font-mono font-semibold">{session.roomCode}</span>.
              </p>
              <Link to={`/room/${session.roomCode}`}>
                <Button size="sm" variant="success">
                  Resume room
                </Button>
              </Link>
            </div>
          ) : null}

          <p className="mt-6 text-xs leading-5 text-slate-500">
            No account needed. Your session lasts for this browser tab and is
            recoverable with an encrypted reconnect window.
          </p>
        </div>

        <div className="relative mx-auto hidden w-full max-w-md lg:block" aria-hidden="true">
          <div className="absolute inset-8 rounded-full bg-violet-500/20 blur-3xl" />
          <div className="relative grid gap-4">
            {sampleCards.map((card, index) => (
              <div
                key={card.name}
                className={`${card.rotate} ${
                  index === 1 ? "ml-10" : index === 2 ? "ml-3" : ""
                } animate-fade-in rounded-2xl border border-white/10 bg-ink-850/90 p-4 shadow-panel backdrop-blur`}
                style={{ animationDelay: `${index * 90}ms` }}
              >
                <div
                  className={`aspect-[5/3] rounded-xl border border-white/10 bg-gradient-to-br ${card.from} to-transparent`}
                >
                  <div className="flex h-full items-center justify-center">
                    <Sparkles className="h-9 w-9 text-white/35" />
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <div>
                    <p className="font-display text-sm font-semibold text-white">{card.name}</p>
                    <p className="text-xs text-slate-500">{card.franchise}</p>
                  </div>
                  <Badge tone="green">Not you</Badge>
                </div>
              </div>
            ))}
            <div className="absolute -right-2 top-1/2 -translate-y-1/2 rounded-xl border border-violet-400/30 bg-ink-800/95 px-3 py-2 text-xs font-semibold text-violet-200 shadow-glow">
              Who am I?
            </div>
          </div>
        </div>
      </section>

      <section className="mt-8 grid gap-4 sm:mt-14 sm:grid-cols-3">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <Card key={step.title} className="p-5">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-violet-400/20 bg-violet-500/10 text-violet-200">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Step {index + 1}
                </span>
              </div>
              <h2 className="mt-4 font-display text-base font-semibold text-white">
                {step.title}
              </h2>
              <p className="mt-1.5 text-sm leading-6 text-slate-400">{step.body}</p>
            </Card>
          );
        })}
      </section>

      <section className="mt-10 flex flex-col items-start gap-4 rounded-2xl border border-white/10 bg-gradient-to-r from-violet-500/10 via-transparent to-cyan-500/10 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-display text-lg font-semibold text-white">
            Hosting a game night?
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Rooms support 2–16 players, individual or team matches, and any
            character collection you can imagine.
          </p>
        </div>
        <Link to="/create">
          <Button icon={<ArrowRight className="h-4 w-4" />}>Start a room</Button>
        </Link>
      </section>
    </PageShell>
  );
}
