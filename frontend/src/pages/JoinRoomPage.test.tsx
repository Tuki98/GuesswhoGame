import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { JoinRoomPage } from "@/pages/JoinRoomPage";
import { useAuthStore } from "@/stores/authStore";
import { makeSessionResponse } from "@/test/fixtures";

const apiMock = vi.hoisted(() => ({ joinRoom: vi.fn() }));

vi.mock("@/api/endpoints", () => ({ api: apiMock }));

function renderJoin(entry = "/join?code=gtc-abcd") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/join" element={<JoinRoomPage />} />
        <Route path="/room/:code" element={<p>Room probe</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiMock.joinRoom.mockReset();
});

describe("JoinRoomPage", () => {
  it("normalizes the invitation code from the link", () => {
    renderJoin();
    expect(screen.getByLabelText(/Room code/i)).toHaveValue("GTC-ABCD");
  });

  it("joins and navigates to the room on success", async () => {
    const user = userEvent.setup();
    apiMock.joinRoom.mockResolvedValue(makeSessionResponse({ room: { code: "GTC-ABCD" } }));

    renderJoin();

    await user.type(screen.getByLabelText(/Your nickname/i), "Sam");
    await user.click(screen.getByRole("button", { name: /Join room/i }));

    expect(apiMock.joinRoom).toHaveBeenCalledWith({
      code: "GTC-ABCD",
      nickname: "Sam",
    });
    expect(await screen.findByText("Room probe")).toBeInTheDocument();
    expect(useAuthStore.getState().session?.nickname).toBe("Maya");
  });

  it("validates the nickname before calling the server", async () => {
    const user = userEvent.setup();

    renderJoin();

    await user.click(screen.getByRole("button", { name: /Join room/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/between 2 and 24 characters/i);
    expect(apiMock.joinRoom).not.toHaveBeenCalled();
  });

  it("surfaces the server's refusal instead of a raw internal message", async () => {
    const user = userEvent.setup();
    apiMock.joinRoom.mockRejectedValue(
      new ApiError({ status: 409, code: "conflict", message: "This room is full." }),
    );

    renderJoin();

    await user.type(screen.getByLabelText(/Your nickname/i), "Sam");
    await user.click(screen.getByRole("button", { name: /Join room/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This room is full.");
  });

  it("requires a room code", async () => {
    const user = userEvent.setup();
    renderJoin("/join");

    await user.type(screen.getByLabelText(/Your nickname/i), "Sam");
    await user.click(screen.getByRole("button", { name: /Join room/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/Enter the room code/i);
    expect(apiMock.joinRoom).not.toHaveBeenCalled();
  });
});
