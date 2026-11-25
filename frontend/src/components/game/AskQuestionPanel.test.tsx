import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AskQuestionPanel } from "@/components/game/AskQuestionPanel";
import { useMatchStore } from "@/stores/matchStore";
import { installFakeRealtime } from "@/test/fakes";
import { makeMatchState, makeParticipant } from "@/test/fixtures";

describe("AskQuestionPanel", () => {
  it("sends the question to the selected player in individual mode", async () => {
    const user = userEvent.setup();
    const { frames } = installFakeRealtime();
    const state = makeMatchState({
      allowed_recipient_ids: ["other-player"],
      participants: [
        makeParticipant({ id: "self-player", name: "Maya" }),
        makeParticipant({ id: "other-player", name: "Sam" }),
      ],
    });

    useMatchStore.setState({ state });
    render(<AskQuestionPanel state={state} />);

    await user.type(screen.getByLabelText("Question"), "Does mine wear a hat?");
    await user.click(screen.getByRole("button", { name: /Send question/i }));

    expect(frames[0]).toMatchObject({
      event: "question.submit",
      payload: {
        content: "Does mine wear a hat?",
        recipient_player_id: "other-player",
      },
    });
    expect(frames[0].payload).not.toHaveProperty("recipient_team_id");
  });

  it("addresses teams in team mode", async () => {
    const user = userEvent.setup();
    const { frames } = installFakeRealtime();
    const state = makeMatchState({
      match: { ...makeMatchState().match, mode: "team" },
      allowed_recipient_ids: ["team-1"],
      participants: [
        makeParticipant({ id: "self-team", name: "Team Rocket", kind: "team" }),
        makeParticipant({ id: "team-1", name: "Team Aqua", kind: "team" }),
      ],
    });

    useMatchStore.setState({ state });
    render(<AskQuestionPanel state={state} />);

    await user.type(screen.getByLabelText("Question"), "Is it animated?");
    await user.click(screen.getByRole("button", { name: /Send question/i }));

    expect(frames[0].payload).toEqual({
      content: "Is it animated?",
      recipient_team_id: "team-1",
    });
  });

  it("shows the waiting state when it is not the player's turn", () => {
    const state = makeMatchState({
      self: { ...makeMatchState().self, is_your_turn: false, can_ask: false },
    });

    render(<AskQuestionPanel state={state} />);

    expect(screen.getByText("Waiting for your turn")).toBeInTheDocument();
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
  });

  it("disables the composer while disconnected", () => {
    installFakeRealtime({ status: "reconnecting" });

    render(<AskQuestionPanel state={makeMatchState()} />);

    expect(screen.getByLabelText("Question")).toBeDisabled();
    expect(screen.getByRole("button", { name: /Send question/i })).toBeDisabled();
  });
});
