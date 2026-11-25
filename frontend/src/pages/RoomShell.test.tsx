import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RoomShell } from "@/pages/RoomShell";
import { useAuthStore } from "@/stores/authStore";
import { signIn } from "@/test/fixtures";

function renderRoom(path = "/room/GTC-BBBB") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/room/:code" element={<RoomShell />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RoomShell access guard", () => {
  it("refuses to render a room that does not match this tab's session", () => {
    signIn({ roomCode: "GTC-AAAA" });

    renderRoom("/room/GTC-BBBB");

    expect(screen.getByText("You are signed into GTC-AAAA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open GTC-AAAA" })).toHaveAttribute(
      "href",
      "/room/GTC-AAAA",
    );
    expect(screen.getByRole("link", { name: "Join GTC-BBBB" })).toHaveAttribute(
      "href",
      "/join?code=GTC-BBBB",
    );
  });

  it("asks anonymous visitors to join first", () => {
    useAuthStore.setState({ session: null, status: "anonymous", notice: null });

    renderRoom("/room/GTC-ABCD");

    expect(screen.getByText("Join this room first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Join GTC-ABCD" })).toHaveAttribute(
      "href",
      "/join?code=GTC-ABCD",
    );
  });

  it("explains an expired session instead of showing a lobby", () => {
    useAuthStore.setState({
      session: null,
      status: "expired",
      notice: "Your session could not be restored. Join the room again.",
    });

    renderRoom("/room/GTC-ABCD");

    expect(screen.getByText("Your session expired")).toBeInTheDocument();
    expect(
      screen.getByText("Your session could not be restored. Join the room again."),
    ).toBeInTheDocument();
  });
});
