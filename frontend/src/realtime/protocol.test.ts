import { describe, expect, it } from "vitest";

import { isProtocolError, parseServerMessage } from "@/realtime/protocol";
import { makeMatchState, makeRoom } from "@/test/fixtures";

function parsed(raw: string) {
  const result = parseServerMessage(raw);
  if ("code" in result) {
    throw new Error(`Expected a valid envelope, got ${result.code}`);
  }
  return result.envelope;
}

function rejected(raw: string) {
  const result = parseServerMessage(raw);
  if (!("code" in result)) {
    throw new Error("Expected a protocol error.");
  }
  return result;
}

describe("parseServerMessage", () => {
  it("parses a complete match state envelope", () => {
    const envelope = parsed(
      JSON.stringify({
        event: "match.state",
        request_id: "req-1",
        sequence_number: 4,
        payload: makeMatchState(),
      }),
    );

    expect(envelope.event).toBe("match.state");
    expect(envelope.request_id).toBe("req-1");
    expect(envelope.sequence_number).toBe(4);
    expect(envelope.payload).toHaveProperty("self");
  });

  it("accepts a room snapshot without optional envelope fields", () => {
    const envelope = parsed(JSON.stringify({ event: "room.state", payload: makeRoom() }));
    expect(envelope.event).toBe("room.state");
    expect(envelope.request_id).toBeUndefined();
  });

  it("preserves error payloads", () => {
    const envelope = parsed(
      JSON.stringify({
        event: "error",
        request_id: "req-9",
        payload: { code: "permission_denied", message: "Not your turn." },
      }),
    );
    expect(envelope.payload).toEqual({
      code: "permission_denied",
      message: "Not your turn.",
    });
  });

  it("rejects malformed JSON", () => {
    expect(rejected("not-json")).toMatchObject({ code: "invalid_message" });
  });

  it("rejects envelopes without an event name", () => {
    expect(rejected(JSON.stringify({ payload: {} }))).toMatchObject({
      code: "invalid_message",
    });
  });

  it("rejects non-object payloads", () => {
    expect(rejected(JSON.stringify({ event: "room.state", payload: [] }))).toMatchObject({
      code: "invalid_message",
    });
  });

  it("rejects invalid optional envelope fields", () => {
    expect(
      rejected(JSON.stringify({ event: "room.state", payload: {}, request_id: 7 })),
    ).toMatchObject({ code: "invalid_message" });
    expect(
      rejected(JSON.stringify({ event: "room.state", payload: {}, sequence_number: 1.5 })),
    ).toMatchObject({ code: "invalid_message" });
  });

  it("rejects payloads that do not match the documented shapes", () => {
    expect(rejected(JSON.stringify({ event: "room.state", payload: { id: "room-1" } }))).toMatchObject(
      { code: "invalid_payload" },
    );
    expect(
      rejected(JSON.stringify({ event: "player.ready_changed", payload: { player_id: "p1" } })),
    ).toMatchObject({ code: "invalid_payload" });
    expect(
      rejected(
        JSON.stringify({
          event: "match.state",
          payload: { match: { id: "m1", status: "active" } },
        }),
      ),
    ).toMatchObject({ code: "invalid_payload" });
    expect(
      rejected(JSON.stringify({ event: "guess.incorrect", payload: { character_id: "c1" } })),
    ).toMatchObject({ code: "invalid_payload" });
  });

  it("rejects malformed error frames", () => {
    expect(
      rejected(JSON.stringify({ event: "error", payload: { code: "oops" } })),
    ).toMatchObject({ code: "invalid_payload" });
  });

  it("allows connection heartbeats with empty payloads", () => {
    expect(parsed(JSON.stringify({ event: "connection.heartbeat", payload: {} })).event).toBe(
      "connection.heartbeat",
    );
  });
});

describe("isProtocolError", () => {
  it("recognizes protocol errors", () => {
    expect(isProtocolError({ code: "x", message: "y" })).toBe(true);
    expect(isProtocolError({ code: "x" })).toBe(false);
    expect(isProtocolError(null)).toBe(false);
  });
});
