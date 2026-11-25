import type {
  Answer,
  Character,
  GameEvent,
  MatchInfo,
  MatchParticipant,
  MatchState,
  PublicPlayer,
  Question,
  Room,
  RoomSessionResponse,
  Team,
  VisibleCharacter,
} from "@/types/api";
import type { AppSession } from "@/stores/authStore";
import { useAuthStore } from "@/stores/authStore";

let sequence = 0;

/** Stable, unique ids: tests only need identity, not RFC 4122 validity. */
export function fixtureId(prefix = "fixture"): string {
  sequence += 1;
  return `${prefix}-${String(sequence).padStart(4, "0")}`;
}

export function isoAt(offsetMs = 0): string {
  return new Date(Date.now() + offsetMs).toISOString();
}

export function makePlayer(overrides: Partial<PublicPlayer> = {}): PublicPlayer {
  const id = overrides.id ?? fixtureId("player");
  return {
    id,
    nickname: "Maya",
    is_host: false,
    is_connected: true,
    is_ready: false,
    joined_at: isoAt(-60_000),
    ...overrides,
  };
}

export function makeRoom(overrides: Partial<Room> = {}): Room {
  const id = overrides.id ?? fixtureId("room");
  return {
    id,
    code: "GTC-ABCD",
    status: "waiting",
    host_player_id: null,
    player_count: 2,
    created_at: isoAt(-120_000),
    updated_at: isoAt(-1_000),
    ...overrides,
    settings: {
      max_players: 8,
      game_mode: "individual",
      ...overrides.settings,
    },
  };
}

export function makeCharacter(overrides: Partial<Character> = {}): Character {
  const id = overrides.id ?? fixtureId("character");
  return {
    id,
    room_id: "room-1",
    name: "Pikachu",
    franchise: "Pokémon",
    category: "anime",
    image_url: `/media/characters/${id}.webp`,
    attributes: { color: "yellow" },
    contributed_by: null,
    created_at: isoAt(-90_000),
    ...overrides,
  };
}

export function makeTeam(overrides: Partial<Team> = {}): Team {
  return {
    id: fixtureId("team"),
    room_id: "room-1",
    name: "Team Rocket",
    members: [],
    ...overrides,
  };
}

export function makeParticipant(
  overrides: Partial<MatchParticipant> = {},
): MatchParticipant {
  return {
    id: fixtureId("participant"),
    name: "Sam",
    kind: "player",
    is_connected: true,
    member_player_ids: [],
    ...overrides,
  };
}

export function makeAnswer(overrides: Partial<Answer> = {}): Answer {
  return {
    content: "Yes, it is.",
    author_player_id: "other-player",
    author_nickname: "Sam",
    answered_at: isoAt(-30_000),
    ...overrides,
  };
}

export function makeQuestion(overrides: Partial<Question> = {}): Question {
  return {
    id: fixtureId("question"),
    author_player_id: "self-player",
    author_nickname: "Maya",
    recipient_player_id: "other-player",
    recipient_team_id: null,
    recipient_name: "Sam",
    content: "Does my character wear a hat?",
    asked_at: isoAt(-20_000),
    answer: null,
    can_answer: false,
    ...overrides,
  };
}

export function makeMatchInfo(overrides: Partial<MatchInfo> = {}): MatchInfo {
  return {
    id: "match-1",
    room_id: "room-1",
    mode: "individual",
    status: "active",
    phase: "in_progress",
    turn_index: 0,
    current_turn_id: "self-player",
    current_turn_kind: "player",
    current_turn_name: "Maya",
    participant_count: 2,
    started_at: isoAt(-300_000),
    finished_at: null,
    winner_player_id: null,
    winner_team_id: null,
    winner_name: null,
    ...overrides,
  };
}

type VisibleCharacterOverrides = Omit<Partial<VisibleCharacter>, "character"> & {
  character?: Partial<Character>;
};

export function makeVisibleCharacter(
  overrides: VisibleCharacterOverrides = {},
): VisibleCharacter {
  const { character, ...rest } = overrides;
  const source: Partial<Character> = character ?? {};
  return {
    owner_id: source.contributed_by ?? "other-player",
    owner_kind: "player",
    owner_name: "Sam",
    ...rest,
    character: {
      id: source.id ?? fixtureId("visible"),
      name: source.name ?? "Batman",
      franchise: source.franchise ?? "DC",
      category: source.category ?? "comics",
      image_url: source.image_url ?? "/media/characters/batman.webp",
      attributes: source.attributes ?? {},
    },
  };
}

export function makeMatchState(overrides: Partial<MatchState> = {}): MatchState {
  return {
    match: makeMatchInfo(),
    self: {
      player_id: "self-player",
      nickname: "Maya",
      team_id: null,
      team_name: null,
      is_your_turn: true,
      can_ask: true,
    },
    identity_assigned: true,
    identity_revealed: false,
    opponents: [],
    participants: [
      makeParticipant({ id: "self-player", name: "Maya" }),
      makeParticipant({ id: "other-player", name: "Sam" }),
    ],
    pending_question: null,
    question_history: [],
    allowed_recipient_ids: ["other-player"],
    ...overrides,
  };
}

export function makeEvent(overrides: Partial<GameEvent> = {}): GameEvent {
  return {
    id: fixtureId("event"),
    match_id: "match-1",
    actor_player_id: null,
    event_type: "match_started",
    payload: {},
    sequence_number: 1,
    created_at: isoAt(-100_000),
    ...overrides,
  };
}

export function makeSessionResponse(
  overrides: {
    room?: Partial<Room>;
    player?: Partial<PublicPlayer>;
    sessionToken?: string;
    reconnectToken?: string;
    sessionExpiresInMs?: number;
    reconnectExpiresInMs?: number;
  } = {},
): RoomSessionResponse {
  return {
    room: makeRoom(overrides.room),
    player: makePlayer(overrides.player),
    credentials: {
      token_type: "bearer",
      session_token: overrides.sessionToken ?? "session-token-1",
      session_expires_at: isoAt(overrides.sessionExpiresInMs ?? 3_600_000),
      reconnect_token: overrides.reconnectToken ?? "reconnect-token-1",
      reconnect_expires_at: isoAt(overrides.reconnectExpiresInMs ?? 7_200_000),
    },
  };
}

export function makeSession(overrides: Partial<AppSession> = {}): AppSession {
  return {
    roomId: "room-1",
    roomCode: "GTC-ABCD",
    playerId: "self-player",
    nickname: "Maya",
    sessionToken: "session-token-1",
    sessionExpiresAt: isoAt(3_600_000),
    reconnectToken: "reconnect-token-1",
    reconnectExpiresAt: isoAt(7_200_000),
    ...overrides,
  };
}

/** Put a signed-in session into the auth store without touching storage. */
export function signIn(overrides: Partial<AppSession> = {}): AppSession {
  const session = makeSession(overrides);
  useAuthStore.setState({
    session,
    status: "authenticated",
    notice: null,
    error: null,
  });
  return session;
}
