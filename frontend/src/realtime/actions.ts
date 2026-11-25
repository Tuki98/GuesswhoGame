import { realtime } from "@/realtime/realtime";
import type { ClientEventName } from "@/types/events";
import { newRequestId } from "@/lib/ids";
import { useConnectionStore } from "@/stores/connectionStore";
import { usePendingStore } from "@/stores/pendingStore";
import { toastError } from "@/stores/uiStore";

export interface DispatchOptions {
  key: string;
  label: string;
  timeoutMs?: number;
}

/**
 * Send one explicit WebSocket action. Actions are never queued: if the socket
 * is not open the user is told to wait for reconnection, preventing duplicate
 * or unknown-outcome submissions.
 */
export function dispatchSocketAction(
  event: ClientEventName,
  payload: Record<string, unknown>,
  options: DispatchOptions,
): string | null {
  const connection = useConnectionStore.getState().status;
  if (connection !== "connected" || !realtime.isOpen) {
    toastError(
      "You are not connected",
      "Wait for the room connection to recover before trying that action.",
    );
    return null;
  }

  const requestId = newRequestId();
  usePendingStore.getState().begin(
    options.key,
    options.label,
    requestId,
    options.timeoutMs,
  );
  const sent = realtime.send(event, payload, requestId);
  if (!sent) {
    usePendingStore.getState().finish(options.key);
    toastError("Message not sent", "The room connection dropped before the action was sent.");
    return null;
  }
  return requestId;
}
