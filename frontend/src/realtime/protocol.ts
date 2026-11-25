import type { ServerEnvelope, WsProtocolError } from "@/types/events";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const ROOM_EVENTS = new Set(["room.state", "room.updated"]);
const CHARACTER_EVENTS = new Set(["character.added", "character.deleted"]);
const MATCH_EVENTS = new Set([
  "match.started",
  "match.state",
  "match.turn_changed",
  "question.received",
  "answer.received",
  "guess.incorrect",
  "match.finished",
  "match.cancelled",
]);

function isRoomLike(payload: JsonRecord): boolean {
  return (
    typeof payload.id === "string" &&
    typeof payload.code === "string" &&
    typeof payload.status === "string" &&
    isRecord(payload.settings) &&
    typeof payload.settings.max_players === "number" &&
    typeof payload.settings.game_mode === "string"
  );
}

function isMatchStateLike(payload: JsonRecord): boolean {
  return (
    isRecord(payload.match) &&
    typeof payload.match.id === "string" &&
    typeof payload.match.status === "string" &&
    isRecord(payload.self) &&
    typeof payload.self.player_id === "string" &&
    Array.isArray(payload.opponents) &&
    Array.isArray(payload.participants) &&
    Array.isArray(payload.allowed_recipient_ids)
  );
}

function payloadIsShapeValid(event: string, payload: JsonRecord): boolean {
  if (ROOM_EVENTS.has(event)) {
    return isRoomLike(payload);
  }
  if (event === "player.joined") {
    return typeof payload.id === "string" && typeof payload.nickname === "string";
  }
  if (event === "player.left" || event === "player.connected" || event === "player.disconnected") {
    return typeof payload.player_id === "string";
  }
  if (event === "player.ready_changed") {
    return typeof payload.player_id === "string" && typeof payload.ready === "boolean";
  }
  if (CHARACTER_EVENTS.has(event)) {
    return typeof payload.character_id === "string";
  }
  if (event === "match.state") {
    return isMatchStateLike(payload);
  }
  if (event === "match.started") {
    return typeof payload.match_id === "string";
  }
  if (event === "match.turn_changed") {
    return payload.current_turn_id === null || typeof payload.current_turn_id === "string";
  }
  if (event === "question.received") {
    return typeof payload.question_id === "string" && typeof payload.content === "string";
  }
  if (event === "answer.received") {
    return typeof payload.question_id === "string" && typeof payload.answer === "string";
  }
  if (event === "guess.incorrect") {
    return typeof payload.character_id === "string" && payload.correct === false;
  }
  if (event === "match.finished") {
    return typeof payload.reason === "string";
  }
  if (event === "match.cancelled") {
    return typeof payload.reason === "string";
  }
  if (event === "connection.heartbeat" || event === "error") {
    return true;
  }
  if (MATCH_EVENTS.has(event)) {
    return true;
  }
  return true;
}

export interface ParsedServerMessage {
  envelope: ServerEnvelope;
}

export function parseServerMessage(raw: string): ParsedServerMessage | WsProtocolError {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { code: "invalid_message", message: "The server sent malformed JSON." };
  }
  if (!isRecord(parsed) || typeof parsed.event !== "string" || parsed.event.length === 0) {
    return { code: "invalid_message", message: "The server sent an invalid event envelope." };
  }
  const payload = parsed.payload === undefined ? {} : parsed.payload;
  if (!isRecord(payload)) {
    return { code: "invalid_message", message: "The server event payload was not an object." };
  }
  if (
    (parsed.request_id !== undefined && typeof parsed.request_id !== "string") ||
    (parsed.event_id !== undefined && typeof parsed.event_id !== "string") ||
    (parsed.sequence_number !== undefined &&
      (typeof parsed.sequence_number !== "number" ||
        !Number.isInteger(parsed.sequence_number)))
  ) {
    return { code: "invalid_message", message: "The server event envelope had invalid fields." };
  }
  if (!payloadIsShapeValid(parsed.event, payload)) {
    return {
      code: "invalid_payload",
      message: "The server event payload did not match the expected shape.",
    };
  }
  if (parsed.event === "error") {
    if (typeof payload.code !== "string" || typeof payload.message !== "string") {
      return { code: "invalid_payload", message: "The server error event was malformed." };
    }
  }
  return {
    envelope: {
      event: parsed.event,
      payload,
      request_id: parsed.request_id as string | undefined,
      event_id: parsed.event_id as string | undefined,
      sequence_number: parsed.sequence_number as number | undefined,
    },
  };
}

export function isProtocolError(value: unknown): value is WsProtocolError {
  return (
    isRecord(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string"
  );
}
