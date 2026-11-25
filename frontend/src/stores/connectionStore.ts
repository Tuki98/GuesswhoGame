import { create } from "zustand";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "expired";

interface ConnectionState {
  status: ConnectionStatus;
  attempt: number;
  lastMessageAt: number | null;
  detail: string | null;
  setStatus: (status: ConnectionStatus, attempt?: number, detail?: string | null) => void;
  noteMessage: () => void;
  reset: () => void;
}

export const useConnectionStore = create<ConnectionState>()((set) => ({
  status: "idle",
  attempt: 0,
  lastMessageAt: null,
  detail: null,
  setStatus: (status, attempt = 0, detail = null) =>
    set({ status, attempt, detail: status === "connected" ? null : detail }),
  noteMessage: () => set({ lastMessageAt: Date.now() }),
  reset: () =>
    set({
      status: "idle",
      attempt: 0,
      lastMessageAt: null,
      detail: null,
    }),
}));
