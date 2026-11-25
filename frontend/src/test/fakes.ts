import { vi } from "vitest";

import { realtime } from "@/realtime/realtime";
import type { RoomSocket } from "@/realtime/RoomSocket";
import { useConnectionStore } from "@/stores/connectionStore";
import type { ConnectionStatus } from "@/stores/connectionStore";

/**
 * Minimal EventTarget-free WebSocket stand-in. RoomSocket only needs the four
 * readyState constants, a URL, send(), close(), and the four handlers.
 */
export class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readonly url: string;
  readyState: number = FakeWebSocket.CONNECTING;
  readonly sent: string[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    if (this.readyState !== FakeWebSocket.OPEN) {
      throw new Error("WebSocket is not open.");
    }
    this.sent.push(data);
  }

  close(code = 1000, reason = ""): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }

  // -- helpers used by tests -------------------------------------------------

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  receive(value: unknown): void {
    const data = typeof value === "string" ? value : JSON.stringify(value);
    this.onmessage?.({ data } as MessageEvent);
  }

  serverClose(code: number, reason = ""): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }

  lastSent(): Record<string, unknown> {
    const raw = this.sent.at(-1);
    if (!raw) {
      throw new Error("No frame has been sent yet.");
    }
    return JSON.parse(raw) as Record<string, unknown>;
  }

  sentFrames(): Array<Record<string, unknown>> {
    return this.sent.map((raw) => JSON.parse(raw) as Record<string, unknown>);
  }
}

export function installFakeWebSocket(): typeof FakeWebSocket {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  return FakeWebSocket;
}

export interface SentFrame {
  event: string;
  request_id: string;
  payload: Record<string, unknown>;
}

export interface FakeRealtime {
  isOpen: boolean;
  send: ReturnType<typeof vi.fn>;
  retryNow: ReturnType<typeof vi.fn>;
}

/**
 * Replace the realtime singleton with a recording double. Returns the recorded
 * frames so action tests can assert the exact outgoing envelope.
 */
export function installFakeRealtime(
  options: { status?: ConnectionStatus; sendResult?: "request-id" | null } = {},
): { fake: FakeRealtime; frames: SentFrame[] } {
  const status = options.status ?? "connected";
  const sendResult = options.sendResult === undefined ? "request-id" : options.sendResult;
  const frames: SentFrame[] = [];
  const fake: FakeRealtime = {
    isOpen: status === "connected",
    send: vi.fn(
      (event: string, payload: Record<string, unknown>, requestId?: string) => {
        const id = requestId ?? `generated-${frames.length + 1}`;
        if (sendResult !== null) {
          frames.push({ event, request_id: id, payload });
          return id;
        }
        return null;
      },
    ),
    retryNow: vi.fn(),
  };
  realtime.replaceForTests(fake as unknown as RoomSocket);
  useConnectionStore.setState({
    status,
    attempt: 0,
    lastMessageAt: null,
    detail: null,
  });
  return { fake, frames };
}

export function resetFakeRealtime(): void {
  realtime.replaceForTests(null);
  useConnectionStore.getState().reset();
}
