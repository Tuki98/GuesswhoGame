import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useRoomLive } from "@/hooks/useRoomLive";
import { useAuthStore } from "@/stores/authStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { useRoomStore } from "@/stores/roomStore";
import { useUiStore } from "@/stores/uiStore";
import {
  makeMatchInfo,
  makeMatchState,
  makePlayer,
  makeRoom,
  signIn,
} from "@/test/fixtures";
import { FakeWebSocket, installFakeWebSocket } from "@/test/fakes";

const apiMock = vi.hoisted(() => ({
  getMatchHistory: vi.fn(),
  getMatchState: vi.fn(),
  getRoom: vi.fn(),
  listPlayers: vi.fn(),
  listTeams: vi.fn(),
  listCharacters: vi.fn(),
}));

vi.mock("@/api/endpoints", () => ({ api: apiMock }));

function mountLiveHook() {
  const view = renderHook(() => useRoomLive("GTC-ABCD", "room-1"));
  const ws = FakeWebSocket.instances[0];
  if (!ws) {
    throw new Error("The live hook did not open a socket.");
  }
  act(() => ws.open());
  return { ...view, ws };
}

beforeEach(() => {
  signIn({ roomId: "room-1", roomCode: "GTC-ABCD" });
  installFakeWebSocket();
  apiMock.getRoom.mockReset().mockResolvedValue(makeRoom({ id: "room-1" }));
  apiMock.listPlayers.mockReset().mockResolvedValue({ players: [] });
  apiMock.listTeams.mockReset().mockResolvedValue({ teams: [] });
  apiMock.listCharacters.mockReset().mockResolvedValue({ characters: [] });
  apiMock.getMatchHistory
    .mockReset()
    .mockResolvedValue({ events: [], has_more: false, next_after_sequence: null });
  apiMock.getMatchState.mockReset().mockResolvedValue(makeMatchState());
});

describe("useRoomLive transport", () => {
  it("connects with the exact room URL and marks the connection live", () => {
    const { ws } = mountLiveHook();

    expect(ws.url).toBe("ws://localhost:8000/ws/rooms/GTC-ABCD?token=session-token-1");
    expect(useConnectionStore.getState().status).toBe("connected");
  });

  it("closes the socket when the hook unmounts", () => {
    const { ws, unmount } = mountLiveHook();
    unmount();

    expect(ws.readyState).toBe(FakeWebSocket.CLOSED);
    expect(useConnectionStore.getState().status).toBe("disconnected");
  });
});

describe("useRoomLive room events", () => {
  it("applies a room snapshot and refreshes the collections", async () => {
    const { ws } = mountLiveHook();
    const room = makeRoom({ id: "room-1", status: "waiting", player_count: 3 });
    apiMock.listPlayers.mockResolvedValue({
      players: [makePlayer({ id: "p1" }), makePlayer({ id: "p2" }), makePlayer({ id: "p3" })],
    });

    act(() => ws.receive({ event: "room.state", payload: room }));

    expect(useRoomStore.getState().room?.player_count).toBe(3);
    await waitFor(() => expect(useRoomStore.getState().players).toHaveLength(3));
  });

  it("applies readiness broadcasts and finishes the pending action", async () => {
    const { ws } = mountLiveHook();
    const player = makePlayer({ id: "p1", is_ready: false });
    useRoomStore.setState({ players: [player], room: makeRoom({ id: "room-1" }) });

    act(() =>
      ws.receive({
        event: "player.ready_changed",
        payload: { player_id: "p1", nickname: "Maya", ready: true },
      }),
    );

    expect(useRoomStore.getState().players[0].is_ready).toBe(true);
  });

  it("updates presence without discarding the player record", () => {
    const { ws } = mountLiveHook();
    useRoomStore.setState({
      players: [makePlayer({ id: "p1", is_connected: true })],
      room: makeRoom({ id: "room-1" }),
    });

    act(() =>
      ws.receive({ event: "player.disconnected", payload: { player_id: "p1" } }),
    );

    expect(useRoomStore.getState().players).toHaveLength(1);
    expect(useRoomStore.getState().players[0].is_connected).toBe(false);
  });

  it("signs the tab out when the server removes its own player", () => {
    const { ws } = mountLiveHook();
    useRoomStore.setState({
      players: [makePlayer({ id: "self-player" })],
      room: makeRoom({ id: "room-1" }),
    });

    act(() =>
      ws.receive({ event: "player.left", payload: { player_id: "self-player" } }),
    );

    expect(useAuthStore.getState().session).toBeNull();
    expect(useAuthStore.getState().status).toBe("anonymous");
  });

  it("removes other departed players locally", () => {
    const { ws } = mountLiveHook();
    useRoomStore.setState({
      players: [
        makePlayer({ id: "self-player" }),
        makePlayer({ id: "other-player" }),
      ],
      room: makeRoom({ id: "room-1", player_count: 2 }),
    });

    act(() =>
      ws.receive({ event: "player.left", payload: { player_id: "other-player" } }),
    );

    expect(useRoomStore.getState().players.map((player) => player.id)).toEqual([
      "self-player",
    ]);
    expect(useRoomStore.getState().room?.player_count).toBe(1);
  });
});

describe("useRoomLive match events", () => {
  it("opens the table when a match starts", async () => {
    vi.useFakeTimers();
    const { ws } = mountLiveHook();
    useRoomStore.setState({ room: makeRoom({ id: "room-1" }) });

    act(() =>
      ws.receive({ event: "match.started", payload: { match_id: "match-1", status: "in_progress" } }),
    );

    expect(useRoomStore.getState().room?.status).toBe("in_progress");
    await vi.advanceTimersByTimeAsync(0);
    expect(ws.sentFrames().some((frame) => frame.event === "match.get_state")).toBe(true);
  });

  it("applies personalized match state and syncs the history", async () => {
    const { ws } = mountLiveHook();
    useRoomStore.setState({ room: makeRoom({ id: "room-1" }) });
    const state = makeMatchState({
      match: makeMatchInfo({ id: "match-1", status: "active", phase: "in_progress" }),
    });

    act(() => ws.receive({ event: "match.state", payload: state }));

    expect(useMatchStore.getState().state?.match.id).toBe("match-1");
    expect(useRoomStore.getState().room?.status).toBe("in_progress");
    await waitFor(() => expect(apiMock.getMatchHistory).toHaveBeenCalled());
  });

  it("records a wrong guess without revealing a secret", () => {
    const { ws } = mountLiveHook();
    useRoomStore.setState({
      room: makeRoom({ id: "room-1", status: "in_progress" }),
      players: [makePlayer({ id: "self-player" })],
    });
    useMatchStore.setState({ state: makeMatchState() });

    act(() =>
      ws.receive({
        event: "guess.incorrect",
        payload: { character_id: "character-1", correct: false },
      }),
    );

    const toast = useUiStore.getState().toasts.at(-1);
    expect(toast).toMatchObject({ kind: "warning", title: "Not your character" });
    expect(useMatchStore.getState().state?.identity_revealed).toBe(false);
  });

  it("reloads the completed match through REST after match.finished", async () => {
    const { ws } = mountLiveHook();
    useRoomStore.setState({ room: makeRoom({ id: "room-1", status: "in_progress" }) });
    useMatchStore.setState({ state: makeMatchState() });
    const finished = makeMatchState({
      match: makeMatchInfo({
        id: "match-1",
        status: "finished",
        phase: "finished",
        winner_player_id: "self-player",
        winner_name: "Maya",
        finished_at: new Date().toISOString(),
      }),
    });
    apiMock.getMatchState.mockResolvedValue(finished);
    apiMock.getRoom.mockResolvedValue(makeRoom({ id: "room-1", status: "waiting" }));

    act(() =>
      ws.receive({
        event: "match.finished",
        payload: { winner_player_id: "self-player", winner_team_id: null, reason: "correct_guess" },
      }),
    );

    expect(useMatchStore.getState().endedReason).toBe("correct_guess");
    expect(useRoomStore.getState().room?.status).toBe("waiting");
    await waitFor(() => expect(apiMock.getMatchState).toHaveBeenCalledWith("match-1", "session-token-1"));
    await waitFor(() => expect(useMatchStore.getState().state?.match.status).toBe("finished"));
  });

  it("reloads the match state after cancellation and returns the room to the lobby", async () => {
    const { ws } = mountLiveHook();
    useRoomStore.setState({ room: makeRoom({ id: "room-1", status: "in_progress" }) });
    useMatchStore.setState({ state: makeMatchState() });
    apiMock.getMatchState.mockResolvedValue(
      makeMatchState({ match: makeMatchInfo({ id: "match-1", status: "abandoned", phase: "cancelled" }) }),
    );

    act(() =>
      ws.receive({ event: "match.cancelled", payload: { reason: "host_cancelled" } }),
    );

    expect(useMatchStore.getState().endedReason).toBe("host_cancelled");
    expect(useRoomStore.getState().room?.status).toBe("waiting");
    await waitFor(() => expect(useMatchStore.getState().state?.match.status).toBe("abandoned"));
  });
});

describe("useRoomLive errors", () => {
  it("shows a friendly permission message and keeps the session", () => {
    const { ws } = mountLiveHook();

    act(() =>
      ws.receive({
        event: "error",
        payload: { code: "permission_denied", message: "It is not your turn." },
      }),
    );

    expect(useUiStore.getState().toasts.at(-1)).toMatchObject({
      kind: "error",
      title: "Not allowed",
      message: "It is not your turn.",
    });
    expect(useAuthStore.getState().session).not.toBeNull();
  });

  it("hides internal server errors from the user", () => {
    const { ws } = mountLiveHook();

    act(() =>
      ws.receive({
        event: "error",
        payload: { code: "internal_error", message: "Traceback and secrets" },
      }),
    );

    const toast = useUiStore.getState().toasts.at(-1);
    expect(toast?.title).toBe("Server error");
    expect(toast?.message).toBe("The server could not complete that action.");
  });

  it("expires the session when the server reports invalid_session", () => {
    const { ws } = mountLiveHook();

    act(() =>
      ws.receive({
        event: "error",
        payload: { code: "invalid_session", message: "Expired." },
      }),
    );

    expect(useAuthStore.getState().status).toBe("expired");
    expect(useAuthStore.getState().session).toBeNull();
  });
});
