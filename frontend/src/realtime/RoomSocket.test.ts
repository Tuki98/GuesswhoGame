import { beforeEach, describe, expect, it, vi } from "vitest";

import { RoomSocket } from "@/realtime/RoomSocket";
import type { ConnectionStatus } from "@/stores/connectionStore";
import type { ServerEnvelope } from "@/types/events";
import { FakeWebSocket, installFakeWebSocket } from "@/test/fakes";

interface Harness {
  socket: RoomSocket;
  statuses: Array<{ status: ConnectionStatus; attempt: number; detail?: string }>;
  messages: ServerEnvelope[];
  protocolErrors: string[];
  authRequired: ReturnType<typeof vi.fn>;
  authFailure: ReturnType<typeof vi.fn>;
}

function createHarness(
  options: {
    token?: string | null;
    authResult?: string | null;
  } = {},
): Harness {
  const statuses: Harness["statuses"] = [];
  const messages: ServerEnvelope[] = [];
  const protocolErrors: string[] = [];
  let currentToken = "token" in options ? options.token ?? null : "token-1";
  const authRequired = vi.fn(async () => {
    const next = options.authResult ?? null;
    if (next) {
      currentToken = next;
    }
    return next;
  });
  const authFailure = vi.fn();

  const socket = new RoomSocket({
    roomCode: "GTC-ABCD",
    getToken: () => currentToken,
    wsBaseUrl: "ws://test.local",
    baseReconnectDelayMs: 100,
    maxReconnectDelayMs: 400,
    onMessage: (message) => messages.push(message),
    onStatus: (status, attempt, detail) => statuses.push({ status, attempt, detail }),
    onProtocolError: (error) => protocolErrors.push(error.code),
    onAuthRequired: authRequired,
    onAuthFailure: authFailure,
  });

  return { socket, statuses, messages, protocolErrors, authRequired, authFailure };
}

function lastInstance(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) {
    throw new Error("No socket was created.");
  }
  return socket;
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  installFakeWebSocket();
});

describe("RoomSocket connection lifecycle", () => {
  it("opens the exact authenticated room URL", () => {
    const harness = createHarness();
    harness.socket.connect();

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(lastInstance().url).toBe("ws://test.local/ws/rooms/GTC-ABCD?token=token-1");
  });

  it("never opens a second socket while one is connecting or open", () => {
    const harness = createHarness();
    harness.socket.connect();
    harness.socket.connect();
    expect(FakeWebSocket.instances).toHaveLength(1);

    lastInstance().open();
    harness.socket.connect();
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("reports connected once the handshake succeeds", () => {
    const harness = createHarness();
    harness.socket.connect();
    lastInstance().open();

    expect(harness.socket.isOpen).toBe(true);
    expect(harness.statuses.at(-1)).toMatchObject({ status: "connected", attempt: 0 });
  });

  it("sends a unique request id with every outgoing frame", () => {
    const harness = createHarness();
    harness.socket.connect();
    const socket = lastInstance();
    socket.open();

    const first = harness.socket.send("question.submit", { content: "Is it blue?" });
    const second = harness.socket.send("match.get_state", {});

    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(first).not.toBe(second);
    expect(socket.sentFrames()).toEqual([
      {
        event: "question.submit",
        request_id: first,
        payload: { content: "Is it blue?" },
      },
      { event: "match.get_state", request_id: second, payload: {} },
    ]);
  });

  it("refuses to send before the socket is open", () => {
    const harness = createHarness();
    harness.socket.connect();
    expect(harness.socket.send("match.get_state", {})).toBeNull();
  });

  it("rejects over-large frames before they reach the wire", () => {
    const harness = createHarness();
    harness.socket.connect();
    const socket = lastInstance();
    socket.open();

    const result = harness.socket.send("question.submit", { content: "x".repeat(9_000) });

    expect(result).toBeNull();
    expect(socket.sent).toHaveLength(0);
    expect(harness.protocolErrors).toEqual(["message_too_large"]);
  });

  it("passes parsed messages through and reports malformed frames", () => {
    const harness = createHarness();
    harness.socket.connect();
    const socket = lastInstance();
    socket.open();

    socket.receive({ event: "connection.heartbeat", payload: {} });
    socket.receive("definitely-not-json");

    expect(harness.messages).toHaveLength(1);
    expect(harness.messages[0].event).toBe("connection.heartbeat");
    expect(harness.protocolErrors).toEqual(["invalid_message"]);
  });

  it("expires immediately when no token is available", () => {
    const harness = createHarness({ token: null });
    harness.socket.connect();

    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(harness.statuses.at(-1)?.status).toBe("expired");
    expect(harness.authFailure).toHaveBeenCalledTimes(1);
  });
});

describe("RoomSocket reconnection", () => {
  it("backs off exponentially after transport closes", async () => {
    vi.useFakeTimers();
    const harness = createHarness();
    harness.socket.connect();
    lastInstance().open();

    lastInstance().serverClose(4000, "Connection lost.");
    expect(harness.statuses.at(-1)).toMatchObject({
      status: "reconnecting",
      attempt: 1,
      detail: "Connection lost.",
    });

    await vi.advanceTimersByTimeAsync(99);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(2);

    lastInstance().serverClose(4000);
    await vi.advanceTimersByTimeAsync(199);
    expect(FakeWebSocket.instances).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it("caps the backoff delay", async () => {
    vi.useFakeTimers();
    const harness = createHarness();
    harness.socket.connect();

    for (let index = 0; index < 6; index += 1) {
      lastInstance().serverClose(4001);
      await vi.advanceTimersByTimeAsync(400);
    }

    const attempts = harness.statuses
      .filter((entry) => entry.status === "reconnecting")
      .map((entry) => entry.attempt);
    expect(attempts).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("rotates credentials exactly once after a rejected handshake", async () => {
    vi.useFakeTimers();
    const harness = createHarness({ token: "stale-token", authResult: "rotated-token" });
    harness.socket.connect();
    lastInstance().serverClose(1008, "Invalid session");

    await vi.advanceTimersByTimeAsync(0);
    expect(harness.authRequired).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(400);
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(lastInstance().url).toContain("token=rotated-token");
  });

  it("expires when credential rotation fails", async () => {
    vi.useFakeTimers();
    const harness = createHarness({ authResult: null });
    harness.socket.connect();
    lastInstance().serverClose(1008);

    await vi.advanceTimersByTimeAsync(0);

    expect(harness.statuses.at(-1)?.status).toBe("expired");
    expect(harness.authFailure).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("does not reconnect after a client close", async () => {
    vi.useFakeTimers();
    const harness = createHarness();
    harness.socket.connect();
    const socket = lastInstance();
    socket.open();

    harness.socket.close();
    expect(socket.readyState).toBe(FakeWebSocket.CLOSED);
    expect(harness.socket.isOpen).toBe(false);

    await vi.advanceTimersByTimeAsync(5_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("can retry immediately and resets the backoff", async () => {
    vi.useFakeTimers();
    const harness = createHarness();
    harness.socket.connect();
    lastInstance().serverClose(4000);

    harness.socket.retryNow();
    expect(FakeWebSocket.instances).toHaveLength(2);
    lastInstance().open();
    expect(harness.statuses.at(-1)).toMatchObject({ status: "connected", attempt: 0 });
  });
});
