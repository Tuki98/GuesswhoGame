import { create } from "zustand";

import { newRequestId } from "@/lib/ids";

export type ToastKind = "info" | "success" | "error" | "warning";

export interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  message?: string;
}

interface UiState {
  toasts: Toast[];
  pushToast: (kind: ToastKind, title: string, message?: string) => string;
  dismissToast: (id: string) => void;
  clearToasts: () => void;
}

const toastTimers = new Map<string, ReturnType<typeof setTimeout>>();
const TOAST_TTL_MS = 5_500;

export const useUiStore = create<UiState>()((set, get) => ({
  toasts: [],
  pushToast: (kind, title, message) => {
    const id = newRequestId();
    set((state) => ({
      toasts: [...state.toasts.slice(-3), { id, kind, title, message }],
    }));
    const timer = setTimeout(() => {
      toastTimers.delete(id);
      get().dismissToast(id);
    }, TOAST_TTL_MS);
    toastTimers.set(id, timer);
    return id;
  },
  dismissToast: (id) => {
    const timer = toastTimers.get(id);
    if (timer) {
      clearTimeout(timer);
      toastTimers.delete(id);
    }
    set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }));
  },
  clearToasts: () => {
    toastTimers.forEach((timer) => clearTimeout(timer));
    toastTimers.clear();
    set({ toasts: [] });
  },
}));

export function toastError(title: string, message?: string): void {
  useUiStore.getState().pushToast("error", title, message);
}

export function toastSuccess(title: string, message?: string): void {
  useUiStore.getState().pushToast("success", title, message);
}
