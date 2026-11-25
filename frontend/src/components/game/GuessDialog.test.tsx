import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GuessDialog } from "@/components/game/GuessDialog";
import { useRoomStore } from "@/stores/roomStore";
import { installFakeRealtime } from "@/test/fakes";
import {
  makeCharacter,
  makeMatchInfo,
  makeMatchState,
  makeTeam,
  makeVisibleCharacter,
} from "@/test/fixtures";

const opponentCharacter = makeCharacter({
  id: "opponent-char",
  name: "Batman",
  contributed_by: "other-player",
});
const ownCharacter = makeCharacter({
  id: "own-char",
  name: "Own Hero",
  contributed_by: "self-player",
});
const freeCharacter = makeCharacter({
  id: "free-char",
  name: "Free Hero",
  contributed_by: null,
});

function seedCollection() {
  useRoomStore.setState({
    characters: [opponentCharacter, ownCharacter, freeCharacter],
    teams: [],
  });
}

describe("GuessDialog", () => {
  it("removes visible opponents and own contributions from the candidates", () => {
    seedCollection();
    installFakeRealtime();
    const state = makeMatchState({
      opponents: [
        makeVisibleCharacter({
          character: opponentCharacter,
          owner_id: "other-player",
          owner_kind: "player",
          owner_name: "Sam",
        }),
      ],
    });

    render(<GuessDialog open onClose={vi.fn()} state={state} />);

    expect(screen.getByText("1 possible")).toBeInTheDocument();
    expect(screen.getByText("2 ruled out")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Free Hero/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Batman/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Own Hero/ })).not.toBeInTheDocument();
  });

  it("submits the selected candidate through the server-authoritative socket", async () => {
    const user = userEvent.setup();
    seedCollection();
    const { frames } = installFakeRealtime();
    const onClose = vi.fn();

    render(<GuessDialog open onClose={onClose} state={makeMatchState()} />);

    await user.click(screen.getByRole("button", { name: /Free Hero/ }));
    await user.click(screen.getByRole("button", { name: /Submit guess/i }));

    expect(frames[0]).toMatchObject({
      event: "guess.submit",
      payload: { character_id: "free-char" },
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps the dialog open while disconnected", async () => {
    const user = userEvent.setup();
    seedCollection();
    installFakeRealtime({ status: "disconnected" });

    render(<GuessDialog open onClose={vi.fn()} state={makeMatchState()} />);

    await user.click(screen.getByRole("button", { name: /Free Hero/ }));
    expect(screen.getByRole("button", { name: /Submit guess/i })).toBeDisabled();
  });

  it("treats characters contributed by teammates as impossible in team mode", () => {
    const teammateCharacter = makeCharacter({
      id: "teammate-char",
      name: "Teammate Hero",
      contributed_by: "teammate-player",
    });
    useRoomStore.setState({
      characters: [teammateCharacter, freeCharacter],
      teams: [
        makeTeam({
          id: "team-1",
          name: "Team Rocket",
          members: [
            { ...makeTeammate(), id: "self-player" },
            makeTeammate(),
          ],
        }),
      ],
    });
    installFakeRealtime();
    const state = makeMatchState({
      match: makeMatchInfo({ mode: "team" }),
      self: {
        ...makeMatchState().self,
        team_id: "team-1",
        team_name: "Team Rocket",
      },
    });

    render(<GuessDialog open onClose={vi.fn()} state={state} />);

    expect(screen.getByText("1 possible")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Free Hero/ })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Teammate Hero/ }),
    ).not.toBeInTheDocument();
  });
});

function makeTeammate() {
  return {
    id: "teammate-player",
    nickname: "Alex",
    is_host: false,
    is_connected: true,
    is_ready: true,
    joined_at: new Date().toISOString(),
  };
}
