import { describe, expect, it } from "vitest";

import { dispatchSocketAction } from "@/realtime/actions";
import { usePendingStore } from "@/stores/pendingStore";
import { useUiStore } from "@/stores/uiStore";
import { installFakeRealtime } from "@/test/fakes";

describe("dispatchSocketAction", () => {
  it("refuses to queue while the room is disconnected", () => {
    const { frames } = installFakeRealtime({ status: "reconnecting" });

    const requestId = dispatchSocketAction(
      "guess.submit",
      { character_id: "character-1" },
      { key: "guess", label: "Guessing" },
    );

    expect(requestId).toBeNull();
    expect(frames).toHaveLength(0);
    expect(usePendingStore.getState().pending).toEqual({});
    expect(useUiStore.getState().toasts.at(-1)).toMatchObject({
      kind: "error",
      title: "You are not connected",
    });
  });

  it("sends one frame with a fresh request id and tracks it as pending", () => {
    const { frames } = installFakeRealtime();

    const requestId = dispatchSocketAction(
      "question.submit",
      { content: "Is it blue?", recipient_player_id: "player-2" },
      { key: "question", label: "Sending your question" },
    );

    expect(requestId).not.toBeNull();
    expect(frames).toEqual([
      {
        event: "question.submit",
        request_id: requestId,
        payload: { content: "Is it blue?", recipient_player_id: "player-2" },
      },
    ]);
    expect(usePendingStore.getState().pending.question).toMatchObject({
      key: "question",
      label: "Sending your question",
      requestId,
    });
  });

  it("clears the pending entry and warns when the transport drops mid-send", () => {
    const { frames } = installFakeRealtime({ sendResult: null });

    const requestId = dispatchSocketAction(
      "match.start",
      {},
      { key: "match_start", label: "Starting the match" },
    );

    expect(requestId).toBeNull();
    expect(frames).toHaveLength(0);
    expect(usePendingStore.getState().pending).toEqual({});
    expect(useUiStore.getState().toasts.at(-1)).toMatchObject({
      kind: "error",
      title: "Message not sent",
    });
  });
});
