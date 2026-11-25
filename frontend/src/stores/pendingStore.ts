import { create } from "zustand";

export interface PendingEntry {
  key: string;
  label: string;
  requestId: string;
  startedAt: number;
}

interface PendingState {
  pending: Record<string, PendingEntry>;
  begin: (key: string, label: string, requestId: string, timeoutMs?: number) => void;
  finish: (key: string) => void;
  finishByRequestId: (requestId: string) => void;
  clear: () => void;
}

const timers = new Map<string, ReturnType<typeof setTimeout>>();

export const usePendingStore = create<PendingState>()((set, get) => ({
  pending: {},
  begin: (key, label, requestId, timeoutMs = 12_000) => {
    const existing = timers.get(key);
    if (existing) {
      clearTimeout(existing);
    }
    set((state) => ({
      pending: {
        ...state.pending,
        [key]: { key, label, requestId, startedAt: Date.now() },
      },
    }));
    const timer = setTimeout(() => {
      timers.delete(key);
      const current = get().pending[key];
      if (current?.requestId === requestId) {
        get().finish(key);
      }
    }, timeoutMs);
    timers.set(key, timer);
  },
  finish: (key) => {
    const timer = timers.get(key);
    if (timer) {
      clearTimeout(timer);
      timers.delete(key);
    }
    set((state) => {
      if (!(key in state.pending)) {
        return state;
      }
      const next = { ...state.pending };
      delete next[key];
      return { pending: next };
    });
  },
  finishByRequestId: (requestId) => {
    const entry = Object.values(get().pending).find((row) => row.requestId === requestId);
    if (entry) {
      get().finish(entry.key);
    }
  },
  clear: () => {
    timers.forEach((timer) => clearTimeout(timer));
    timers.clear();
    set({ pending: {} });
  },
}));
