import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PlayersPanel } from "@/components/room/PlayersPanel";
import { useRoomStore } from "@/stores/roomStore";
import { installFakeRealtime } from "@/test/fakes";
import { makePlayer, makeRoom, signIn } from "@/test/fixtures";

function seedRoom(options: { hostId?: string; connected?: boolean } = {}) {
  const self = makePlayer({ id: "self-player", nickname: "Maya" });
  const other = makePlayer({ id: "other-player", nickname: "Sam" });
  signIn({ playerId: "self-player", nickname: "Maya" });
  useRoomStore.setState({
    room: makeRoom({
      id: "room-1",
      host_player_id: options.hostId ?? "self-player",
      player_count: 2,
    }),
    players: [self, other],
  });
  return { self, other, connected: options.connected ?? true };
}

describe("PlayersPanel", () => {
  it("sends a readiness update over the socket", async () => {
    const user = userEvent.setup();
    seedRoom();
    const { frames } = installFakeRealtime();

    render(<PlayersPanel />);

    await user.click(screen.getByRole("button", { name: /I'm ready/i }));

    expect(frames[0]).toMatchObject({
      event: "player.set_ready",
      payload: { ready: true },
    });
    expect(frames[0].payload).not.toHaveProperty("target_player_id");
  });

  it("disables readiness while disconnected", () => {
    seedRoom();
    installFakeRealtime({ status: "reconnecting" });

    render(<PlayersPanel />);

    expect(screen.getByRole("button", { name: /I'm ready/i })).toBeDisabled();
  });

  it("lets the host mark another player ready", async () => {
    const user = userEvent.setup();
    seedRoom();
    const { frames } = installFakeRealtime();

    render(<PlayersPanel />);

    await user.click(screen.getAllByRole("button", { name: "Ready" })[0]);

    expect(frames[0]).toMatchObject({
      event: "player.set_ready",
      payload: { ready: true, target_player_id: "other-player" },
    });
  });

  it("shows removal controls only to the host", () => {
    seedRoom({ hostId: "other-player" });
    installFakeRealtime();

    render(<PlayersPanel />);

    expect(screen.queryByRole("button", { name: /Remove Sam/i })).not.toBeInTheDocument();
  });

  it("confirms a host removal before acting", async () => {
    const user = userEvent.setup();
    seedRoom();
    installFakeRealtime();

    render(<PlayersPanel />);

    await user.click(screen.getByRole("button", { name: /Remove Sam/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Sam will be removed from the lobby/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows offline presence without hiding the player", () => {
    signIn({ playerId: "self-player" });
    useRoomStore.setState({
      room: makeRoom({ id: "room-1", host_player_id: "self-player" }),
      players: [
        makePlayer({ id: "self-player", nickname: "Maya" }),
        makePlayer({ id: "other-player", nickname: "Sam", is_connected: false }),
      ],
    });
    installFakeRealtime();

    render(<PlayersPanel />);

    expect(screen.getByText("Offline")).toBeInTheDocument();
  });
});
