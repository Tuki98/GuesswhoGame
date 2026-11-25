import { beforeEach, describe, expect, it, vi } from "vitest";

import { mergeEvents, useMatchStore } from "@/stores/matchStore";
import { usePendingStore } from "@/stores/pendingStore";
import { useUiStore } from "@/stores/uiStore";
import { installFakeRealtime } from "@/test/fakes";
import {
  makeEvent,
  makeMatchInfo,
  makeMatchState,
  signIn,
} from "@/test/fixtures";

const apiMock = vi.hoisted(() => ({
  getMatchHistory: vi.fn(),
  getMatchState: vi.fn(),
}));

vi.mock("@/api/endpoints", () => ({ api: apiMock }));

beforeEach(() => {
  signIn();
  apiMock.getMatchHistory.mockReset();
  apiMock.getMatchState.mockReset();
});

describe("mergeEvents", () => {
  it("deduplicates by sequence and keeps ascending order", () => {
    const first = makeEvent({ id: "event-1", sequence_number: 1, event_type: "match_started" });
    const third = makeEvent({ id: "event-3", sequence_number: 3, event_type: "turn_changed" });
    const second = makeEvent({ id: "event-2", sequence_number: 2, event_type: "question_sent" });
    const replacedThird = makeEvent({
      id: "event-3",
      sequence_number: 3,
      event_type: "answer_sent",
    });

    expect(mergeEvents([first, third], [second, replacedThird])).toEqual([
      first,
      second,
      replacedThird,
    ]);
  });
});

describe("match state", () => {
  it("resets history when the match id changes", () => {
    useMatchStore.setState({
      state: makeMatchState(),
      history: [makeEvent({ sequence_number: 1 })],
      lastSequence: 1,
      endedReason: "correct_guess",
    });

    useMatchStore.getState().setState(
      makeMatchState({ match: makeMatchInfo({ id: "match-2" }) }),
    );

    expect(useMatchStore.getState().history).toEqual([]);
    expect(useMatchStore.getState().lastSequence).toBeNull();
    expect(useMatchStore.getState().endedReason).toBeNull();
  });

  it("keeps history when the same match is refreshed", () => {
    const state = makeMatchState();
    const event = makeEvent({ sequence_number: 5 });
    useMatchStore.setState({ state, history: [event], lastSequence: 5 });

    useMatchStore.getState().setState(
      makeMatchState({ match: makeMatchInfo({ current_turn_id: "other-player" }) }),
    );

    expect(useMatchStore.getState().history).toEqual([event]);
    expect(useMatchStore.getState().state?.match.current_turn_id).toBe("other-player");
  });

  it("loads the authoritative state through REST", async () => {
    const state = makeMatchState();
    apiMock.getMatchState.mockResolvedValue(state);

    await expect(useMatchStore.getState().loadState("match-1")).resolves.toBe(true);

    expect(apiMock.getMatchState).toHaveBeenCalledWith("match-1", "session-token-1");
    expect(useMatchStore.getState().state?.match.id).toBe("match-1");
  });

  it("exposes a sanitized error when the state request fails", async () => {
    apiMock.getMatchState.mockRejectedValue(
      new Error("The game server hit a problem. Please try again."),
    );

    await expect(useMatchStore.getState().loadState("match-1")).resolves.toBe(false);
    expect(useMatchStore.getState().error).toBe(
      "The game server hit a problem. Please try again.",
    );
  });
});

describe("match history synchronization", () => {
  it("pages with after_sequence and merges without duplicates", async () => {
    useMatchStore.getState().setState(makeMatchState());
    apiMock.getMatchHistory
      .mockResolvedValueOnce({
        events: [makeEvent({ id: "e1", sequence_number: 1 })],
        has_more: true,
        next_after_sequence: 1,
      })
      .mockResolvedValueOnce({
        events: [
          makeEvent({ id: "e3", sequence_number: 3 }),
          makeEvent({ id: "e2", sequence_number: 2 }),
        ],
        has_more: false,
        next_after_sequence: null,
      });

    await useMatchStore.getState().syncHistory();

    expect(apiMock.getMatchHistory).toHaveBeenCalledTimes(2);
    expect(apiMock.getMatchHistory.mock.calls[0][2]).toMatchObject({
      limit: 100,
      afterSequence: null,
    });
    expect(apiMock.getMatchHistory.mock.calls[1][2]).toMatchObject({ afterSequence: 1 });
    expect(useMatchStore.getState().history.map((event) => event.sequence_number)).toEqual([
      1, 2, 3,
    ]);
    expect(useMatchStore.getState().lastSequence).toBe(3);
    expect(useMatchStore.getState().historyHasMore).toBe(false);
    expect(useMatchStore.getState().syncing).toBe(false);
  });

  it("continues from the highest known sequence on a later sync", async () => {
    useMatchStore.setState({ lastSequence: 7 });
    useMatchStore.getState().setState(makeMatchState());
    useMatchStore.setState({ lastSequence: 7 });
    apiMock.getMatchHistory.mockResolvedValue({
      events: [makeEvent({ id: "e8", sequence_number: 8 })],
      has_more: false,
      next_after_sequence: null,
    });

    await useMatchStore.getState().syncHistory();

    expect(apiMock.getMatchHistory.mock.calls[0][2]).toMatchObject({ afterSequence: 7 });
  });

  it("stops when the server reports more pages without progress", async () => {
    useMatchStore.getState().setState(makeMatchState());
    apiMock.getMatchHistory.mockResolvedValue({
      events: [],
      has_more: true,
      next_after_sequence: null,
    });

    await useMatchStore.getState().syncHistory();

    expect(apiMock.getMatchHistory).toHaveBeenCalledTimes(1);
    expect(useMatchStore.getState().historyHasMore).toBe(true);
  });

  it("records a sync failure without dropping existing history", async () => {
    const event = makeEvent({ sequence_number: 1 });
    useMatchStore.getState().setState(makeMatchState());
    useMatchStore.setState({ history: [event], lastSequence: 1 });
    apiMock.getMatchHistory.mockRejectedValue(new Error("History unavailable."));

    await useMatchStore.getState().syncHistory();

    expect(useMatchStore.getState().history).toEqual([event]);
    expect(useMatchStore.getState().error).toBe("History unavailable.");
    expect(useMatchStore.getState().syncing).toBe(false);
  });
});

describe("match actions", () => {
  it("does not submit anything while disconnected", () => {
    useMatchStore.getState().setState(makeMatchState());
    installFakeRealtime({ status: "disconnected" });

    expect(useMatchStore.getState().submitGuess("character-1")).toBeNull();
    expect(useMatchStore.getState().startMatch()).toBeNull();
  });

  it("submits a guess with the selected character", () => {
    const { frames } = installFakeRealtime();

    const id = useMatchStore.getState().submitGuess("character-42");

    expect(id).not.toBeNull();
    expect(frames).toEqual([
      {
        event: "guess.submit",
        request_id: id,
        payload: { character_id: "character-42" },
      },
    ]);
    expect(usePendingStore.getState().pending.guess).toBeDefined();
  });

  it("cancels the active match through the socket", () => {
    const { frames } = installFakeRealtime();

    useMatchStore.getState().cancelMatch();

    expect(frames[0].event).toBe("match.cancel");
    expect(frames[0].payload).toEqual({});
  });

  it("submits an individual question to the chosen player", () => {
    vi.useFakeTimers();
    useMatchStore.getState().setState(makeMatchState());
    const { frames } = installFakeRealtime();

    const id = useMatchStore
      .getState()
      .sendQuestion("   Does mine wear a hat?   ", "other-player");

    expect(id).not.toBeNull();
    expect(frames[0]).toMatchObject({
      event: "question.submit",
      payload: { content: "Does mine wear a hat?", recipient_player_id: "other-player" },
    });
    expect(frames[0].payload).not.toHaveProperty("recipient_team_id");
  });

  it("submits a team question to the chosen team", () => {
    vi.useFakeTimers();
    useMatchStore.getState().setState(
      makeMatchState({ match: makeMatchInfo({ mode: "team" }) }),
    );
    const { frames } = installFakeRealtime();

    useMatchStore.getState().sendQuestion("Is it animated?", "team-1");

    expect(frames[0].payload).toEqual({
      content: "Is it animated?",
      recipient_team_id: "team-1",
    });
  });

  it("rejects empty and over-long questions locally", () => {
    vi.useFakeTimers();
    useMatchStore.getState().setState(makeMatchState());
    const { frames } = installFakeRealtime();

    expect(useMatchStore.getState().sendQuestion("   ", "other-player")).toBeNull();
    expect(
      useMatchStore.getState().sendQuestion("x".repeat(501), "other-player"),
    ).toBeNull();

    expect(frames).toHaveLength(0);
    expect(useUiStore.getState().toasts.at(-1)?.kind).toBe("error");
  });

  it("rejects empty and over-long answers locally", () => {
    const { frames } = installFakeRealtime();

    expect(useMatchStore.getState().sendAnswer(" ", "question-1")).toBeNull();
    expect(useMatchStore.getState().sendAnswer("x".repeat(1_001), "question-1")).toBeNull();
    expect(frames).toHaveLength(0);
  });

  it("sends a trimmed answer with the question id", () => {
    const { frames } = installFakeRealtime();

    const id = useMatchStore.getState().sendAnswer("  Yes.  ", "question-9");

    expect(id).not.toBeNull();
    expect(frames[0]).toMatchObject({
      event: "answer.submit",
      payload: { content: "Yes.", question_id: "question-9" },
    });
  });

  it("requests a personalized state snapshot only while the socket is open", async () => {
    vi.useFakeTimers();
    const connected = installFakeRealtime();

    useMatchStore.getState().requestState(120);
    await vi.advanceTimersByTimeAsync(119);
    expect(connected.frames).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(connected.frames[0]).toMatchObject({ event: "match.get_state", payload: {} });

    const disconnected = installFakeRealtime({ status: "disconnected" });
    useMatchStore.getState().requestState(0);
    await vi.advanceTimersByTimeAsync(0);
    expect(disconnected.frames).toHaveLength(0);
  });
});
