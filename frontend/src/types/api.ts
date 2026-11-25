// Exact public API contracts mirrored from the FastAPI Pydantic schemas.

export type Uuid = string;
export type RoomStatus = "waiting" | "in_progress" | "closed";
export type GameMode = "individual" | "team";
/** Raw persisted match state returned by the backend. */
export type MatchStatus = "pending" | "active" | "paused" | "finished" | "abandoned";
/** Friendly lifecycle vocabulary the backend derives from ``status``. */
export type MatchPhase = "created" | "in_progress" | "finished" | "cancelled";
export type OwnerKind = "player" | "team";

export const CHARACTER_CATEGORIES = [
  "anime",
  "manga",
  "video_games",
  "movies",
  "tv",
  "cartoons",
  "comics",
  "internet_personalities",
  "other",
] as const;

export type CharacterCategory = (typeof CHARACTER_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<CharacterCategory, string> = {
  anime: "Anime",
  manga: "Manga",
  video_games: "Video games",
  movies: "Movies",
  tv: "TV",
  cartoons: "Cartoons",
  comics: "Comics",
  internet_personalities: "Internet personalities",
  other: "Other",
};

export interface RoomSettings {
  max_players: number;
  game_mode: GameMode;
}

export interface Room {
  id: Uuid;
  code: string;
  status: RoomStatus;
  host_player_id: Uuid | null;
  settings: RoomSettings;
  player_count: number;
  created_at: string;
  updated_at: string;
}

export interface PublicPlayer {
  id: Uuid;
  nickname: string;
  is_host: boolean;
  is_connected: boolean;
  is_ready: boolean;
  joined_at: string;
}

export interface SessionCredentials {
  token_type: "bearer";
  session_token: string;
  session_expires_at: string;
  reconnect_token: string;
  reconnect_expires_at: string;
}

export interface RoomSessionResponse {
  room: Room;
  player: PublicPlayer;
  credentials: SessionCredentials;
}

export interface PlayerListResponse {
  players: PublicPlayer[];
}

export interface Character {
  id: Uuid;
  room_id: Uuid;
  name: string;
  franchise: string | null;
  category: CharacterCategory;
  image_url: string;
  attributes: Record<string, unknown>;
  contributed_by: Uuid | null;
  created_at: string;
}

export interface CharacterListResponse {
  characters: Character[];
}

export interface Team {
  id: Uuid;
  room_id: Uuid;
  name: string;
  members: PublicPlayer[];
}

export interface TeamListResponse {
  teams: Team[];
}

export interface AssignTeamResponse {
  player_id: Uuid;
  team: Team | null;
}

export interface MatchInfo {
  id: Uuid;
  room_id: Uuid;
  mode: GameMode;
  status: MatchStatus;
  phase: MatchPhase;
  turn_index: number;
  current_turn_id: Uuid | null;
  current_turn_kind: OwnerKind;
  current_turn_name: string | null;
  participant_count: number;
  started_at: string | null;
  finished_at: string | null;
  winner_player_id: Uuid | null;
  winner_team_id: Uuid | null;
  winner_name: string | null;
}

export interface MatchParticipant {
  id: Uuid;
  name: string;
  kind: OwnerKind;
  is_connected: boolean;
  member_player_ids: Uuid[];
}

export interface MatchCharacter {
  id: Uuid;
  name: string;
  franchise: string | null;
  category: CharacterCategory;
  image_url: string;
  attributes: Record<string, unknown>;
}

export interface VisibleCharacter {
  owner_id: Uuid;
  owner_kind: OwnerKind;
  owner_name: string;
  character: MatchCharacter;
}

export interface Answer {
  content: string;
  author_player_id: Uuid | null;
  author_nickname: string | null;
  answered_at: string;
}

export interface Question {
  id: Uuid;
  author_player_id: Uuid | null;
  author_nickname: string | null;
  recipient_player_id: Uuid | null;
  recipient_team_id: Uuid | null;
  recipient_name: string | null;
  content: string;
  asked_at: string;
  answer: Answer | null;
  can_answer: boolean;
}

export interface MatchSelf {
  player_id: Uuid;
  nickname: string;
  team_id: Uuid | null;
  team_name: string | null;
  is_your_turn: boolean;
  can_ask: boolean;
}

export interface MatchState {
  match: MatchInfo;
  self: MatchSelf;
  identity_assigned: boolean;
  identity_revealed: boolean;
  opponents: VisibleCharacter[];
  participants: MatchParticipant[];
  pending_question: Question | null;
  question_history: Question[];
  allowed_recipient_ids: Uuid[];
}

export interface MatchDetails {
  match: MatchInfo;
  participants: MatchParticipant[];
}

export interface GuessResult {
  correct: boolean;
  match: MatchInfo;
}

export interface GameEvent {
  id: Uuid;
  match_id: Uuid;
  actor_player_id: Uuid | null;
  event_type: string;
  payload: Record<string, unknown>;
  sequence_number: number;
  created_at: string;
}

export interface MatchHistory {
  events: GameEvent[];
  has_more: boolean;
  next_after_sequence: number | null;
}

export interface CreateRoomPayload {
  nickname: string;
  settings: RoomSettings;
}

export interface JoinRoomPayload {
  code: string;
  nickname: string;
}

export interface CreateCharacterPayload {
  name: string;
  franchise?: string | null;
  category: CharacterCategory;
  attributes: Record<string, unknown>;
}

export interface UpdateSettingsPayload {
  max_players?: number;
  game_mode?: GameMode;
}
