import type {
  Character,
  GameEvent,
  MatchState,
  PublicPlayer,
  Question,
  Room,
} from "@/types/api";

// Exact outgoing WebSocket event names from app/websockets/handlers.py.
export type ClientEventName =
  | "room.get_state"
  | "player.set_ready"
  | "character.add"
  | "character.delete"
  | "match.start"
  | "match.get_state"
  | "question.submit"
  | "answer.submit"
  | "guess.submit"
  | "match.cancel";

// Exact incoming WebSocket event names from app/websockets/protocol.py.
export type ServerEventName =
  | "room.state"
  | "room.updated"
  | "player.joined"
  | "player.left"
  | "player.connected"
  | "player.disconnected"
  | "player.ready_changed"
  | "character.added"
  | "character.deleted"
  | "match.started"
  | "match.state"
  | "match.turn_changed"
  | "question.received"
  | "answer.received"
  | "guess.incorrect"
  | "match.finished"
  | "match.cancelled"
  | "connection.heartbeat"
  | "error";

export interface ServerEnvelope {
  event: ServerEventName | string;
  payload: Record<string, unknown>;
  request_id?: string;
  event_id?: string;
  sequence_number?: number;
}

export interface WsProtocolError {
  code: string;
  message: string;
}

export interface PlayerLeftPayload {
  player_id: string;
}

export interface PlayerPresencePayload {
  player_id: string;
  nickname?: string;
  room_id?: string;
}

export interface PlayerReadyPayload {
  player_id: string;
  nickname: string;
  ready: boolean;
}

export interface CharacterChangedPayload {
  character_id: string;
  name?: string;
}

export interface MatchStartedPayload {
  match_id: string;
  status: string;
}

export interface MatchTurnChangedPayload {
  current_turn_id: string | null;
}

export interface QuestionReceivedPayload {
  question_id: string;
  content: string;
  author_player_id: string | null;
  recipient_player_id: string | null;
  recipient_team_id: string | null;
}

export interface AnswerReceivedPayload {
  question_id: string;
  answer: string;
  author_player_id: string | null;
}

export interface GuessIncorrectPayload {
  character_id: string;
  correct: false;
}

export interface MatchFinishedPayload {
  winner_player_id: string | null;
  winner_team_id: string | null;
  reason: string;
}

export interface MatchCancelledPayload {
  reason: string;
}

export type ServerEvent =
  | { event: "room.state"; payload: Room; request_id?: string }
  | { event: "room.updated"; payload: Room; request_id?: string }
  | { event: "player.joined"; payload: PublicPlayer }
  | { event: "player.left"; payload: PlayerLeftPayload }
  | { event: "player.connected"; payload: PlayerPresencePayload }
  | { event: "player.disconnected"; payload: PlayerPresencePayload }
  | { event: "player.ready_changed"; payload: PlayerReadyPayload }
  | { event: "character.added"; payload: CharacterChangedPayload }
  | { event: "character.deleted"; payload: CharacterChangedPayload }
  | { event: "match.started"; payload: MatchStartedPayload }
  | { event: "match.state"; payload: MatchState; request_id?: string }
  | { event: "match.turn_changed"; payload: MatchTurnChangedPayload }
  | { event: "question.received"; payload: QuestionReceivedPayload }
  | { event: "answer.received"; payload: AnswerReceivedPayload }
  | { event: "guess.incorrect"; payload: GuessIncorrectPayload }
  | { event: "match.finished"; payload: MatchFinishedPayload }
  | { event: "match.cancelled"; payload: MatchCancelledPayload }
  | { event: "connection.heartbeat"; payload: Record<string, never> }
  | { event: "error"; payload: WsProtocolError; request_id?: string }
  | { event: string; payload: Record<string, unknown>; request_id?: string };

// Useful payload aliases for components/tests.
export type CharacterAddedPayload = CharacterChangedPayload & { name: string };
export type CharacterSnapshot = Character;
export type QuestionSnapshot = Question;
export type MatchEventSnapshot = GameEvent;
