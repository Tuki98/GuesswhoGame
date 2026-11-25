import { AlertTriangle, Loader2, LogIn, RefreshCw, ShieldX } from "lucide-react";
import { useEffect } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import { RoomHeader } from "@/components/room/RoomHeader";
import { Brand } from "@/components/layout/Brand";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConnectionBanner } from "@/components/ui/ConnectionBanner";
import { LoadingPanel } from "@/components/ui/Feedback";
import { useRoomLive } from "@/hooks/useRoomLive";
import { useAuthStore } from "@/stores/authStore";
import { useMatchStore } from "@/stores/matchStore";
import { useRoomStore } from "@/stores/roomStore";

export function RoomShell() {
  const params = useParams<{ code: string }>();
  const code = (params.code ?? "").toUpperCase();
  const navigate = useNavigate();
  const location = useLocation();
  const status = useAuthStore((state) => state.status);
  const session = useAuthStore((state) => state.session);
  const notice = useAuthStore((state) => state.notice);
  const room = useRoomStore((state) => state.room);
  const loading = useRoomStore((state) => state.loading);
  const error = useRoomStore((state) => state.error);
  const load = useRoomStore((state) => state.load);
  const matchState = useMatchStore((state) => state.state);

  const matchesSession =
    Boolean(session) && session!.roomCode.toUpperCase() === code;
  const canLive = Boolean(session && matchesSession);
  useRoomLive(code, canLive ? session!.roomId : null, canLive);

  useEffect(() => {
    if (!canLive || !session) {
      return;
    }
    // A new room id means an entirely new seat: discard any previous room
    // snapshot and match so stale status can never redirect this tab.
    useMatchStore.getState().reset();
    useRoomStore.getState().reset();
    void load(session.roomId);
  }, [canLive, load, session?.roomId]);

  useEffect(() => {
    if (!room || room.code.toUpperCase() !== code) {
      return;
    }
    const active =
      room.status === "in_progress" ||
      matchState?.match.phase === "in_progress";
    if (active && !location.pathname.endsWith("/play")) {
      navigate(`/room/${room.code}/play`, { replace: true });
    }
  }, [room?.status, room?.code, matchState?.match.phase, code, location.pathname, navigate]);

  if (status === "loading" && !session) {
    return <RoomBootSplash />;
  }

  if (!session || status === "anonymous" || status === "expired" || !matchesSession) {
    return (
      <RoomAccessState
        status={status}
        code={code}
        storedCode={session?.roomCode ?? null}
        notice={notice}
      />
    );
  }

  if (!room) {
    if (loading) {
      return (
        <RoomFrame>
          <LoadingPanel
            title="Opening the room"
            message="Checking your seat and loading the lobby."
          />
        </RoomFrame>
      );
    }
    return (
      <RoomFrame>
        <Card className="mx-auto max-w-xl p-6 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-rose-400/25 bg-rose-500/10 text-rose-300">
            <AlertTriangle className="h-6 w-6" aria-hidden="true" />
          </span>
          <h1 className="mt-4 font-display text-xl font-semibold text-white">
            This room could not be opened
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            {error ?? "The room may have been closed, or your seat is no longer valid."}
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <Button
              variant="secondary"
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={() => void load(session.roomId)}
            >
              Try again
            </Button>
            <Link to={`/join?code=${encodeURIComponent(code)}`}>
              <Button>Join again</Button>
            </Link>
          </div>
        </Card>
      </RoomFrame>
    );
  }

  if (room.status === "closed") {
    return (
      <RoomFrame>
        <Card className="mx-auto max-w-xl p-6 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-slate-400/20 bg-slate-500/10 text-slate-300">
            <ShieldX className="h-6 w-6" aria-hidden="true" />
          </span>
          <h1 className="mt-4 font-display text-xl font-semibold text-white">
            This room is closed
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            The host closed <span className="font-mono text-slate-200">{room.code}</span>.
            The lobby, collection, and any match history are no longer live.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <Link to="/">
              <Button variant="secondary">Back home</Button>
            </Link>
            <Link to="/create">
              <Button>Create a new room</Button>
            </Link>
          </div>
        </Card>
      </RoomFrame>
    );
  }

  const inGame = room.status === "in_progress";

  return (
    <div className="relative min-h-screen bg-ink-950 text-slate-100">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(124,58,237,0.13),transparent_50%),radial-gradient(ellipse_at_bottom_right,rgba(34,211,238,0.06),transparent_45%)]"
        aria-hidden="true"
      />
      <div className="relative">
        <RoomHeader />
        <div className="border-b border-white/[0.06] bg-ink-900/50">
          <div className="mx-auto flex w-full max-w-7xl items-center gap-1 px-4 sm:px-6 lg:px-8">
            <RoomTab to={`/room/${room.code}`} end>
              Lobby
            </RoomTab>
            <RoomTab to={`/room/${room.code}/play`}>
              {inGame
                ? "Live table"
                : matchState?.match.phase === "finished"
                  ? "Last result"
                  : matchState?.match.phase === "cancelled"
                    ? "Last result"
                    : "Table"}
            </RoomTab>
            {inGame ? (
              <span className="ml-2 inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
                <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-emerald-400" />
                Match live
              </span>
            ) : null}
          </div>
        </div>

        <main className="mx-auto w-full max-w-7xl space-y-4 px-4 pb-16 pt-5 sm:px-6 lg:px-8">
          <ConnectionBanner />
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function RoomTab({
  to,
  end = false,
  children,
}: {
  to: string;
  end?: boolean;
  children: React.ReactNode;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `-mb-px border-b-2 px-3 py-3 text-sm font-medium transition ${
          isActive
            ? "border-violet-400 text-white"
            : "border-transparent text-slate-400 hover:text-slate-200"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

function RoomFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen bg-ink-950 text-slate-100">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(124,58,237,0.13),transparent_50%)]"
        aria-hidden="true"
      />
      <div className="relative">
        <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-5 sm:px-6 lg:px-8">
          <Brand />
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 pb-16 pt-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}

function RoomBootSplash() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950">
      <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-ink-850/80 px-5 py-4 text-sm text-slate-300">
        <Loader2 className="h-5 w-5 animate-spin text-violet-300" aria-hidden="true" />
        Restoring your seat…
      </div>
    </div>
  );
}

function RoomAccessState({
  status,
  code,
  storedCode,
  notice,
}: {
  status: string;
  code: string;
  storedCode: string | null;
  notice: string | null;
}) {
  const differentRoom = Boolean(storedCode) && storedCode!.toUpperCase() !== code;
  return (
    <RoomFrame>
      <Card className="mx-auto max-w-xl p-6 text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-violet-400/25 bg-violet-500/10 text-violet-200">
          {differentRoom ? (
            <LogIn className="h-6 w-6" aria-hidden="true" />
          ) : (
            <ShieldX className="h-6 w-6" aria-hidden="true" />
          )}
        </span>
        <h1 className="mt-4 font-display text-xl font-semibold text-white">
          {differentRoom
            ? `You are signed into ${storedCode}`
            : status === "expired"
              ? "Your session expired"
              : "Join this room first"}
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          {notice ??
            (differentRoom
              ? "Each browser tab holds one player seat. Open the other room in its own tab, or join this room and replace the current seat."
              : "A valid session is needed to open the lobby. Enter the room code and choose a nickname to join.")}
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {differentRoom && storedCode ? (
            <Link to={`/room/${storedCode}`}>
              <Button variant="secondary">Open {storedCode}</Button>
            </Link>
          ) : null}
          <Link to={`/join?code=${encodeURIComponent(code)}`}>
            <Button>Join {code}</Button>
          </Link>
          <Link to="/">
            <Button variant="ghost">Home</Button>
          </Link>
        </div>
      </Card>
    </RoomFrame>
  );
}
