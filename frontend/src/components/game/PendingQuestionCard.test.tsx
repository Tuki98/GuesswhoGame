import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PendingQuestionCard } from "@/components/game/PendingQuestionCard";
import { installFakeRealtime } from "@/test/fakes";
import { makePlayer, makeQuestion } from "@/test/fixtures";
import { useRoomStore } from "@/stores/roomStore";

describe("PendingQuestionCard", () => {
  it("answers the pending question and passes the turn", async () => {
    const user = userEvent.setup();
    const { frames } = installFakeRealtime();
    useRoomStore.setState({
      players: [makePlayer({ id: "other-player", nickname: "Sam" })],
    });
    const question = makeQuestion({
      id: "question-7",
      author_player_id: "other-player",
      can_answer: true,
      content: "Does your character wear a hat?",
    });

    render(<PendingQuestionCard question={question} />);

    expect(screen.getByText(/Sam is waiting on your response/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your answer"), "  Yes, a top hat.  ");
    await user.click(screen.getByRole("button", { name: /Send answer/i }));

    expect(frames[0]).toMatchObject({
      event: "answer.submit",
      payload: { content: "Yes, a top hat.", question_id: "question-7" },
    });
  });

  it("shows a read-only pending notice for other players", () => {
    const question = makeQuestion({
      author_player_id: "other-player",
      can_answer: false,
      content: "Is your character blue?",
    });

    render(<PendingQuestionCard question={question} />);

    expect(screen.getByText("Question awaiting an answer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Send answer/i })).not.toBeInTheDocument();
  });

  it("disables answering while the room is disconnected", () => {
    installFakeRealtime({ status: "disconnected" });

    render(
      <PendingQuestionCard
        question={makeQuestion({ can_answer: true, content: "Is it blue?" })}
      />,
    );

    expect(screen.getByLabelText("Your answer")).toBeDisabled();
  });
});
