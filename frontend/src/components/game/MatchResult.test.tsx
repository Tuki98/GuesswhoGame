import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { MatchResult } from "@/components/game/MatchResult";
import { useRoomStore } from "@/stores/roomStore";
import { makeMatchInfo, makeMatchState, makeQuestion, makeRoom } from "@/test/fixtures";

function renderResult(
  overrides: Parameters<typeof makeMatchState>[0] = {},
  endedReason: string | null = "correct_guess",
) {
  useRoomStore.setState({ room: makeRoom({ id: "room-1", code: "GTC-ABCD" }) });
  return render(
    <MemoryRouter>
      <MatchResult state={makeMatchState(overrides)} endedReason={endedReason} isHost={false} />
    </MemoryRouter>,
  );
}

describe("MatchResult", () => {
  it("celebrates a winning guess without revealing the secret identity", () => {
    renderResult({
      match: makeMatchInfo({
        status: "finished",
        phase: "finished",
        winner_player_id: "self-player",
        winner_name: "Maya",
        finished_at: new Date().toISOString(),
      }),
    });

    expect(screen.getByText("Match complete")).toBeInTheDocument();
    expect(screen.getByText("You found your character")).toBeInTheDocument();
    expect(screen.getByText(/identity_revealed: false/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to lobby/i })).toHaveAttribute(
      "href",
      "/room/GTC-ABCD",
    );
  });

  it("names the other winner", () => {
    renderResult({
      match: makeMatchInfo({
        status: "finished",
        phase: "finished",
        winner_player_id: "other-player",
        winner_name: "Sam",
        finished_at: new Date().toISOString(),
      }),
    });

    expect(screen.getByText("Sam wins")).toBeInTheDocument();
  });

  it("reports a team victory for a team member", () => {
    renderResult({
      match: makeMatchInfo({
        mode: "team",
        status: "finished",
        phase: "finished",
        winner_team_id: "team-1",
        winner_name: "Team Rocket",
        finished_at: new Date().toISOString(),
      }),
      self: {
        ...makeMatchState().self,
        team_id: "team-1",
        team_name: "Team Rocket",
      },
    });

    expect(screen.getByText("Your team found its character")).toBeInTheDocument();
  });

  it("reports cancellation and the server reason", () => {
    renderResult(
      { match: makeMatchInfo({ status: "abandoned", phase: "cancelled" }) },
      "host_cancelled",
    );

    expect(screen.getByText("The table has closed")).toBeInTheDocument();
    expect(screen.getByText("Match cancelled")).toBeInTheDocument();
    expect(screen.getByText("Host Cancelled")).toBeInTheDocument();
  });

  it("summarizes the recorded questions", () => {
    renderResult({
      match: makeMatchInfo({
        status: "finished",
        phase: "finished",
        winner_name: "Maya",
        finished_at: new Date().toISOString(),
      }),
      question_history: [
        makeQuestion({ id: "q1" }),
        makeQuestion({ id: "q2" }),
      ],
    });

    expect(screen.getByText(/2 questions recorded/)).toBeInTheDocument();
  });
});
