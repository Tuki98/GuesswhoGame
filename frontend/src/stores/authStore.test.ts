import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { SESSION_STORAGE_KEY, readStoredSession, writeStoredSession } from "@/lib/storage";
import { useAuthStore } from "@/stores/authStore";
import {
  isoAt,
  makePlayer,
  makeRoom,
  makeSessionResponse,
  makeSession,
} from "@/test/fixtures";

const apiMock = vi.hoisted(() => ({
  createRoom: vi.fn(),
  joinRoom: vi.fn(),
  reconnect: vi.fn(),
  getRoom: vi.fn(),
}));

vi.mock("@/api/endpoints", () => ({ api: apiMock }));

function resetAuth(): void {
  useAuthStore.setState({
    session: null,
    status: "anonymous",
    notice: null,
    error: null,
  });
}

beforeEach(() => {
  resetAuth();
  apiMock.createRoom.mockReset();
  apiMock.joinRoom.mockReset();
  apiMock.reconnect.mockReset();
  apiMock.getRoom.mockReset();
});

describe("auth session persistence", () => {
  it("persists the session to sessionStorage and never to localStorage", () => {
    const response = makeSessionResponse({
      room: { id: "room-9", code: "GTC-WXYZ" },
      player: { id: "player-9", nickname: "Oscar" },
    });

    useAuthStore.getState().establish(response);

    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.session).toMatchObject({
      roomId: "room-9",
      roomCode: "GTC-WXYZ",
      playerId: "player-9",
      nickname: "Oscar",
      sessionToken: "session-token-1",
    });

    const stored = readStoredSession();
    expect(stored?.sessionToken).toBe("session-token-1");
    expect(stored?.reconnectToken).toBe("reconnect-token-1");
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).not.toBeNull();
    expect(window.localStorage.length).toBe(0);
  });

  it("clears both memory and storage on sign out", () => {
    useAuthStore.getState().establish(makeSessionResponse());
    useAuthStore.getState().signOutLocal();

    expect(useAuthStore.getState().session).toBeNull();
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(readStoredSession()).toBeNull();
  });

  it("marks a session expired and removes it from storage", () => {
    useAuthStore.getState().establish(makeSessionResponse());
    useAuthStore.getState().markExpired("Gone.");

    expect(useAuthStore.getState().status).toBe("expired");
    expect(useAuthStore.getState().session).toBeNull();
    expect(useAuthStore.getState().notice).toBe("Gone.");
    expect(readStoredSession()).toBeNull();
  });

  it("ignores corrupted stored sessions and removes the key", () => {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, "{not-json");
    expect(readStoredSession()).toBeNull();
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });
});

describe("bootstrap", () => {
  it("becomes anonymous when nothing is stored", async () => {
    await useAuthStore.getState().bootstrap();
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(useAuthStore.getState().session).toBeNull();
  });

  it("authenticates a still-valid stored session through the API", async () => {
    const room = makeRoom({ id: "room-1" });
    writeStoredSession(makeSession());
    apiMock.getRoom.mockResolvedValue(room);

    await useAuthStore.getState().bootstrap();

    expect(apiMock.getRoom).toHaveBeenCalledWith("room-1", "session-token-1");
    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(useAuthStore.getState().session?.roomCode).toBe("GTC-ABCD");
  });

  it("keeps valid credentials when the check fails for network reasons", async () => {
    writeStoredSession(makeSession());
    apiMock.getRoom.mockRejectedValue(
      new ApiError({ status: 0, code: "network_error", message: "Offline." }),
    );

    await useAuthStore.getState().bootstrap();

    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(useAuthStore.getState().session).not.toBeNull();
    expect(useAuthStore.getState().error).toBe(
      "Unable to reach the game server. Check your connection and try again.",
    );
  });

  it("rotates an expired session token through the reconnect endpoint", async () => {
    writeStoredSession(makeSession({ sessionExpiresAt: isoAt(-60_000) }));
    const restored = makeSessionResponse({
      sessionToken: "fresh-token",
      reconnectToken: "fresh-reconnect",
    });
    apiMock.reconnect.mockResolvedValue(restored);

    await useAuthStore.getState().bootstrap();

    expect(apiMock.reconnect).toHaveBeenCalledWith("reconnect-token-1");
    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(useAuthStore.getState().session?.sessionToken).toBe("fresh-token");
    expect(readStoredSession()?.sessionToken).toBe("fresh-token");
  });

  it("rotates when the server rejects a not-yet-expired token", async () => {
    writeStoredSession(makeSession());
    apiMock.getRoom.mockRejectedValue(
      new ApiError({ status: 401, code: "invalid_session", message: "Expired." }),
    );
    apiMock.reconnect.mockResolvedValue(makeSessionResponse({ sessionToken: "rotated" }));

    await useAuthStore.getState().bootstrap();

    expect(apiMock.reconnect).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(useAuthStore.getState().session?.sessionToken).toBe("rotated");
  });

  it("expires when both tokens are beyond their windows", async () => {
    writeStoredSession(
      makeSession({
        sessionExpiresAt: isoAt(-120_000),
        reconnectExpiresAt: isoAt(-60_000),
      }),
    );

    await useAuthStore.getState().bootstrap();

    expect(useAuthStore.getState().status).toBe("expired");
    expect(useAuthStore.getState().session).toBeNull();
    expect(readStoredSession()).toBeNull();
    expect(useAuthStore.getState().notice).toMatch(/expired/i);
    expect(apiMock.reconnect).not.toHaveBeenCalled();
  });

  it("expires when the reconnect endpoint rejects the recovery token", async () => {
    writeStoredSession(makeSession({ sessionExpiresAt: isoAt(-60_000) }));
    apiMock.reconnect.mockRejectedValue(
      new ApiError({ status: 401, code: "invalid_session", message: "No." }),
    );

    await useAuthStore.getState().bootstrap();

    expect(useAuthStore.getState().status).toBe("expired");
    expect(useAuthStore.getState().session).toBeNull();
    expect(readStoredSession()).toBeNull();
  });
});

describe("room establishment", () => {
  it("creates a room and persists its session", async () => {
    const response = makeSessionResponse({
      room: { id: "room-3", code: "GTC-NEW1" },
      player: { id: "player-3", nickname: "Host" },
    });
    apiMock.createRoom.mockResolvedValue(response);

    await expect(
      useAuthStore.getState().createRoom({
        nickname: "Host",
        settings: { max_players: 4, game_mode: "team" },
      }),
    ).resolves.toBe(response);

    expect(apiMock.createRoom).toHaveBeenCalledWith({
      nickname: "Host",
      settings: { max_players: 4, game_mode: "team" },
    });
    expect(useAuthStore.getState().session?.roomCode).toBe("GTC-NEW1");
    expect(readStoredSession()?.roomCode).toBe("GTC-NEW1");
  });

  it("joins a room and persists its session", async () => {
    const response = makeSessionResponse({ player: makePlayer({ id: "player-7" }) });
    apiMock.joinRoom.mockResolvedValue(response);

    await useAuthStore.getState().joinRoom({ code: "GTC-ABCD", nickname: "Sam" });

    expect(useAuthStore.getState().session?.playerId).toBe("player-7");
    expect(readStoredSession()?.playerId).toBe("player-7");
  });

  it("updates the cached room code and nickname for the active session only", () => {
    useAuthStore.getState().establish(
      makeSessionResponse({ room: { id: "room-1" }, player: { id: "self-player" } }),
    );

    useAuthStore.getState().updateRoom(makeRoom({ id: "another-room", code: "GTC-OTHER" }));
    expect(useAuthStore.getState().session?.roomCode).toBe("GTC-ABCD");

    useAuthStore.getState().updateRoom(makeRoom({ id: "room-1", code: "GTC-NEW2" }));
    expect(useAuthStore.getState().session?.roomCode).toBe("GTC-NEW2");
    expect(readStoredSession()?.roomCode).toBe("GTC-NEW2");

    useAuthStore.getState().updatePlayer(makePlayer({ id: "room-1", nickname: "Nope" }));
    expect(useAuthStore.getState().session?.nickname).toBe("Maya");

    useAuthStore.getState().updatePlayer(makePlayer({ id: "self-player", nickname: "Maya B" }));
    expect(useAuthStore.getState().session?.nickname).toBe("Maya B");
  });
});
