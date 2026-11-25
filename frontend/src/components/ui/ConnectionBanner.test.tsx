import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionBanner } from "@/components/ui/ConnectionBanner";
import { ConnectionBadge } from "@/components/ui/ConnectionBadge";
import { useConnectionStore } from "@/stores/connectionStore";

describe("connection feedback", () => {
  it("renders nothing while live", () => {
    useConnectionStore.setState({ status: "connected" });
    const { container } = render(<ConnectionBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("explains that actions are disabled while reconnecting", () => {
    useConnectionStore.setState({ status: "reconnecting", attempt: 2, detail: null });

    render(<ConnectionBanner />);

    expect(screen.getByText(/Reconnecting to the room · attempt 2/)).toBeInTheDocument();
    expect(screen.getByText(/Your actions are disabled/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry now/i })).toBeInTheDocument();
  });

  it("shows a paused state for an expired connection", () => {
    useConnectionStore.setState({ status: "expired" });

    render(<ConnectionBanner />);

    expect(screen.getByText("Room connection paused")).toBeInTheDocument();
    expect(screen.getByText(/Refresh your session/i)).toBeInTheDocument();
  });

  it("labels the connection badge for each transport state", () => {
    useConnectionStore.setState({ status: "reconnecting", attempt: 3 });
    const { rerender } = render(<ConnectionBadge />);
    expect(screen.getByText("Reconnecting")).toBeInTheDocument();

    act(() => useConnectionStore.setState({ status: "connected" }));
    rerender(<ConnectionBadge />);
    expect(screen.getByText("Live")).toBeInTheDocument();

    act(() => useConnectionStore.setState({ status: "expired" }));
    rerender(<ConnectionBadge />);
    expect(screen.getByText("Paused")).toBeInTheDocument();
  });
});
