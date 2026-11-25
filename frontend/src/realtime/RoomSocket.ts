import {
  WS_BASE_RECONNECT_DELAY_MS,
  WS_MAX_FRAME_BYTES,
  WS_MAX_RECONNECT_DELAY_MS,
  WS_BASE_URL,
} from "@/config";
import { newRequestId } from "@/lib/ids";
import { parseServerMessage } from "@/realtime/protocol";
import type { ConnectionStatus } from "@/stores/connectionStore";
import type { ServerEnvelope, WsProtocolError } from "@/types/events";

export interface RoomSocketOptions {
  roomCode: string;
  getToken: () => string | null;
  onMessage: (message: ServerEnvelope) => void;
  onStatus?: (status: ConnectionStatus, attempt: number, detail?: string) => void;
  onProtocolError?: (error: WsProtocolError) => void;
  /** Called on close code 1008. Return the rotated session token, or null. */
  onAuthRequired?: () => Promise<string | null>;
  onAuthFailure?: () => void;
  baseReconnectDelayMs?: number;
  maxReconnectDelayMs?: number;
  wsBaseUrl?: string;
}

/**
 * One authenticated, room-scoped WebSocket client. It never queues actions,
 * never opens a second socket while one is connecting/open, and rejoins with
 * exponential backoff after transport failures. A rejected handshake triggers
 * exactly one credential-rotation attempt before reconnecting.
 */
export class RoomSocket {
  private readonly options: RoomSocketOptions;
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private closedByClient = false;
  private authFailed = false;
  private authInFlight = false;
  private lastStatus: ConnectionStatus = "idle";

  constructor(options: RoomSocketOptions) {
    this.options = options;
  }

  get isOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  get status(): ConnectionStatus {
    return this.lastStatus;
  }

  connect(): void {
    this.closedByClient = false;
    this.authFailed = false;
    this.open();
  }

  retryNow(): void {
    if (this.closedByClient) {
      return;
    }
    this.clearReconnectTimer();
    this.authFailed = false;
    this.authInFlight = false;
    this.open();
  }

  send(event: string, payload: Record<string, unknown>, requestId?: string): string | null {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return null;
    }
    const id = requestId ?? newRequestId();
    const encoded = JSON.stringify({ event, request_id: id, payload });
    const byteLength =
      typeof TextEncoder === "undefined"
        ? encoded.length
        : new TextEncoder().encode(encoded).byteLength;
    if (byteLength > WS_MAX_FRAME_BYTES) {
      this.options.onProtocolError?.({
        code: "message_too_large",
        message: "That message is too large to send.",
      });
      return null;
    }
    try {
      this.socket.send(encoded);
      return id;
    } catch {
      this.options.onProtocolError?.({
        code: "send_failed",
        message: "The message could not be sent.",
      });
      return null;
    }
  }

  close(): void {
    this.closedByClient = true;
    this.clearReconnectTimer();
    this.setStatus("disconnected");
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      try {
        socket.close(1000, "client closed");
      } catch {
        // The socket may already be closing.
      }
    }
  }

  private open(): void {
    if (this.closedByClient || this.authFailed) {
      return;
    }
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    const token = this.options.getToken();
    if (!token) {
      this.authFailed = true;
      this.setStatus("expired");
      this.options.onAuthFailure?.();
      return;
    }

    const base = (this.options.wsBaseUrl ?? WS_BASE_URL).replace(/\/+$/, "");
    const url = `${base}/ws/rooms/${encodeURIComponent(
      this.options.roomCode,
    )}?token=${encodeURIComponent(token)}`;
    this.setStatus("connecting", this.attempt);

    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      this.scheduleReconnect("The game server is not reachable.");
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      if (this.socket !== socket) {
        return;
      }
      this.attempt = 0;
      this.setStatus("connected");
    };

    socket.onmessage = (event: MessageEvent) => {
      if (this.socket !== socket || typeof event.data !== "string") {
        return;
      }
      const parsed = parseServerMessage(event.data);
      if ("code" in parsed) {
        this.options.onProtocolError?.(parsed);
        return;
      }
      this.options.onMessage(parsed.envelope);
    };

    socket.onerror = () => {
      // A close event always follows; reconnection is handled there.
    };

    socket.onclose = (event: CloseEvent) => {
      if (this.socket === socket) {
        this.socket = null;
      }
      if (this.closedByClient) {
        return;
      }
      if (event.code === 1008) {
        void this.refreshAuthentication();
        return;
      }
      this.scheduleReconnect(
        event.reason || "Connection lost. Reconnecting to the room.",
      );
    };
  }

  private async refreshAuthentication(): Promise<void> {
    if (this.authInFlight || this.closedByClient) {
      return;
    }
    this.authInFlight = true;
    this.setStatus("reconnecting", Math.max(1, this.attempt), "Refreshing your session…");
    try {
      const token = await this.options.onAuthRequired?.();
      if (!token || this.closedByClient) {
        this.authFailed = true;
        this.setStatus("expired");
        this.options.onAuthFailure?.();
        return;
      }
      this.clearReconnectTimer();
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        this.open();
      }, 400);
    } catch {
      this.authFailed = true;
      this.setStatus("expired");
      this.options.onAuthFailure?.();
    } finally {
      this.authInFlight = false;
    }
  }

  private scheduleReconnect(detail: string): void {
    if (this.closedByClient || this.authFailed || this.reconnectTimer) {
      return;
    }
    this.attempt += 1;
    const base = this.options.baseReconnectDelayMs ?? WS_BASE_RECONNECT_DELAY_MS;
    const max = this.options.maxReconnectDelayMs ?? WS_MAX_RECONNECT_DELAY_MS;
    const delay = Math.min(max, base * 2 ** Math.min(this.attempt - 1, 10));
    this.setStatus("reconnecting", this.attempt, detail);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setStatus(status: ConnectionStatus, attempt = this.attempt, detail?: string): void {
    this.lastStatus = status;
    this.options.onStatus?.(status, attempt, detail);
  }
}
