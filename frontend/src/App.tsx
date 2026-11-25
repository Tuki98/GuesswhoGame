import { useEffect } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import { PageShell } from "@/components/layout/PageShell";
import { Toasts } from "@/components/ui/Toasts";
import { Spinner } from "@/components/ui/Feedback";
import { CreateRoomPage } from "@/pages/CreateRoomPage";
import { GamePage } from "@/pages/GamePage";
import { JoinRoomPage } from "@/pages/JoinRoomPage";
import { LandingPage } from "@/pages/LandingPage";
import { LobbyPage } from "@/pages/LobbyPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RoomShell } from "@/pages/RoomShell";
import { useAuthStore } from "@/stores/authStore";

function BootSplash() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 text-slate-100">
      <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-ink-850/80 px-5 py-4 shadow-panel">
        <Spinner />
        <span className="text-sm text-slate-300">Restoring your room session…</span>
      </div>
    </div>
  );
}

function ScrollToTop() {
  const location = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);
  return null;
}

export default function App() {
  const bootstrap = useAuthStore((state) => state.bootstrap);
  const status = useAuthStore((state) => state.status);
  const session = useAuthStore((state) => state.session);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  if (status === "loading" && !session) {
    return <BootSplash />;
  }

  return (
    <BrowserRouter>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/create" element={<CreateRoomPage />} />
        <Route path="/join" element={<JoinRoomPage />} />
        <Route path="/room/:code" element={<RoomShell />}>
          <Route index element={<LobbyPage />} />
          <Route path="play" element={<GamePage />} />
        </Route>
        <Route path="/lobby" element={<Navigate to="/" replace />} />
        <Route
          path="*"
          element={
            <PageShell>
              <NotFoundPage />
            </PageShell>
          }
        />
      </Routes>
      <Toasts />
    </BrowserRouter>
  );
}
