import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { GamePage } from "@/pages/GamePage";
import { useConnectionStore } from "@/stores/connectionStore";
import { useMatchStore } from "@/stores/matchStore";
import { useRoomStore } from "@/stores/roomStore";
import {
  makeMatchInfo,
  makeMatchState,
  makeRoom,
  signIn,
} from "@/test/fixtures";

function renderGame(state: ReturnType<typeof makeMatchState>) {
  signIn({ roomId: "room-1", roomCode: "GTC-ABCD", playerId: "self-player" });
  useRoomStore.setState({
    room: makeRoom({ id: "room-1", code: "GTC-ABCD", status: "in_progress" }),
  });
  useMatchStore.setState({ state, history: [], error: null, endedReason: null });
  useConnectionStore.setState({ status: "connected" });

  return render(
    <MemoryRouter initialEntries={["/room/GTC-ABCD/play"]}>
      <GamePage />
    </MemoryRouter>,
  );
}

describe("GamePage match lifecycle", () => {
  beforeEach(() => {
    useMatchStore.getState().reset();
    useRoomStore.getState().reset();
  });

  it("renders the live table for an active match using the backend status", () => {
    renderGame(
      makeMatchState({
        // These are the exact values the backend sends for a running match.
        match: makeMatchInfo({ status: "active", phase: "in_progress" }),
      }),
    );

    expect(screen.queryByText("The match is over")).not.toBeInTheDocument();
    expect(screen.queryByText("Match complete")).not.toBeInTheDocument();
    expect(screen.getByText("Your turn")).toBeInTheDocument();
    expect(screen.getByText("How to win")).toBeInTheDocument();
  });

  it("renders the result screen for a finished match", () => {
    renderGame(
      makeMatchState({
        match: makeMatchInfo({
          status: "finished",
          phase: "finished",
          winner_player_id: "self-player",
          winner_name: "Maya",
          finished_at: new Date().toISOString(),
        }),
      }),
    );

    expect(screen.getByText("Match complete")).toBeInTheDocument();
    expect(screen.getByText("You found your character")).toBeInTheDocument();
    expect(screen.queryByText("How to win")).not.toBeInTheDocument();
  });

  it("renders the cancellation view for an abandoned match", () => {
    renderGame(
      makeMatchState({
        match: makeMatchInfo({ status: "abandoned", phase: "cancelled" }),
      }),
    );

    expect(screen.getByText("Match cancelled")).toBeInTheDocument();
    expect(screen.getByText("The table has closed")).toBeInTheDocument();
  });
});
