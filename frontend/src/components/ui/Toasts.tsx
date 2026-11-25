import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { useUiStore, type ToastKind } from "@/stores/uiStore";

const icons: Record<ToastKind, ReactNode> = {
  info: <Info className="h-5 w-5 text-cyan-300" />,
  success: <CheckCircle2 className="h-5 w-5 text-emerald-300" />,
  warning: <AlertTriangle className="h-5 w-5 text-amber-300" />,
  error: <XCircle className="h-5 w-5 text-rose-300" />,
};

const tones: Record<ToastKind, string> = {
  info: "border-cyan-400/20",
  success: "border-emerald-400/20",
  warning: "border-amber-400/20",
  error: "border-rose-400/25",
};

export function Toasts() {
  const toasts = useUiStore((state) => state.toasts);
  const dismiss = useUiStore((state) => state.dismissToast);

  return (
    <div
      className="pointer-events-none fixed inset-x-0 top-4 z-[60] flex flex-col items-center gap-2 px-4 sm:left-auto sm:right-4 sm:items-end"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role={toast.kind === "error" ? "alert" : "status"}
          className={cn(
            "pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-xl border bg-ink-800/95 p-3 shadow-panel backdrop-blur animate-slide-up",
            tones[toast.kind],
          )}
        >
          <div className="mt-0.5 shrink-0">{icons[toast.kind]}</div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-white">{toast.title}</p>
            {toast.message ? (
              <p className="mt-0.5 break-words text-sm leading-5 text-slate-400">
                {toast.message}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => dismiss(toast.id)}
            className="rounded p-1 text-slate-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
            aria-label="Dismiss notification"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
