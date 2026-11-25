import { apiRequest } from "@/api/client";
import type {
  AssignTeamResponse,
  Character,
  CharacterListResponse,
  CreateCharacterPayload,
  CreateRoomPayload,
  GameMode,
  GuessResult,
  JoinRoomPayload,
  MatchDetails,
  MatchHistory,
  MatchState,
  PlayerListResponse,
  PublicPlayer,
  Room,
  RoomSessionResponse,
  Team,
  TeamListResponse,
} from "@/types/api";

function uid(value: string): string {
  return encodeURIComponent(value);
}

export const api = {
  createRoom(payload: CreateRoomPayload): Promise<RoomSessionResponse> {
    return apiRequest<RoomSessionResponse>("/api/rooms", {
      method: "POST",
      body: payload,
    });
  },

  joinRoom(payload: JoinRoomPayload): Promise<RoomSessionResponse> {
    return apiRequest<RoomSessionResponse>("/api/rooms/join", {
      method: "POST",
      body: payload,
    });
  },

  reconnect(reconnectToken: string): Promise<RoomSessionResponse> {
    return apiRequest<RoomSessionResponse>("/api/sessions/reconnect", {
      method: "POST",
      body: { reconnect_token: reconnectToken },
    });
  },

  getRoom(roomId: string, token: string): Promise<Room> {
    return apiRequest<Room>(`/api/rooms/${uid(roomId)}`, { token });
  },

  listPlayers(roomId: string, token: string): Promise<PlayerListResponse> {
    return apiRequest<PlayerListResponse>(`/api/rooms/${uid(roomId)}/players`, { token });
  },

  updateSettings(
    roomId: string,
    token: string,
    payload: { max_players?: number; game_mode?: GameMode },
  ): Promise<Room> {
    return apiRequest<Room>(`/api/rooms/${uid(roomId)}/settings`, {
      method: "PATCH",
      token,
      body: payload,
    });
  },

  removePlayer(roomId: string, playerId: string, token: string): Promise<void> {
    return apiRequest<void>(
      `/api/rooms/${uid(roomId)}/players/${uid(playerId)}`,
      { method: "DELETE", token },
    );
  },

  leaveRoom(roomId: string, token: string): Promise<void> {
    return apiRequest<void>(`/api/rooms/${uid(roomId)}/leave`, {
      method: "POST",
      token,
    });
  },

  closeRoom(roomId: string, token: string): Promise<Room> {
    return apiRequest<Room>(`/api/rooms/${uid(roomId)}/close`, {
      method: "POST",
      token,
    });
  },

  listCharacters(roomId: string, token: string): Promise<CharacterListResponse> {
    return apiRequest<CharacterListResponse>(`/api/rooms/${uid(roomId)}/characters`, {
      token,
    });
  },

  createCharacter(
    roomId: string,
    token: string,
    payload: CreateCharacterPayload & { image_url?: string },
    image?: File,
  ): Promise<Character> {
    const path = `/api/rooms/${uid(roomId)}/characters`;
    if (image) {
      const form = new FormData();
      form.append("name", payload.name);
      if (payload.franchise) {
        form.append("franchise", payload.franchise);
      }
      form.append("category", payload.category);
      form.append("attributes", JSON.stringify(payload.attributes));
      form.append("image", image);
      return apiRequest<Character>(path, {
        method: "POST",
        token,
        formData: form,
        timeoutMs: 45_000,
      });
    }
    return apiRequest<Character>(path, {
      method: "POST",
      token,
      body: payload,
      timeoutMs: 45_000,
    });
  },

  deleteCharacter(roomId: string, characterId: string, token: string): Promise<void> {
    return apiRequest<void>(
      `/api/rooms/${uid(roomId)}/characters/${uid(characterId)}`,
      { method: "DELETE", token },
    );
  },

  listTeams(roomId: string, token: string): Promise<TeamListResponse> {
    return apiRequest<TeamListResponse>(`/api/rooms/${uid(roomId)}/teams`, { token });
  },

  createTeam(roomId: string, token: string, name: string): Promise<Team> {
    return apiRequest<Team>(`/api/rooms/${uid(roomId)}/teams`, {
      method: "POST",
      token,
      body: { name },
    });
  },

  assignTeam(
    roomId: string,
    playerId: string,
    token: string,
    teamId: string | null,
  ): Promise<AssignTeamResponse> {
    return apiRequest<AssignTeamResponse>(
      `/api/rooms/${uid(roomId)}/players/${uid(playerId)}/team`,
      {
        method: "PUT",
        token,
        body: { team_id: teamId },
      },
    );
  },

  getMatch(matchId: string, token: string): Promise<MatchDetails> {
    return apiRequest<MatchDetails>(`/api/matches/${uid(matchId)}`, { token });
  },

  getMatchState(matchId: string, token: string): Promise<MatchState> {
    return apiRequest<MatchState>(`/api/matches/${uid(matchId)}/state`, { token });
  },

  getMatchHistory(
    matchId: string,
    token: string,
    options: { limit?: number; afterSequence?: number | null } = {},
  ): Promise<MatchHistory> {
    const query = new URLSearchParams();
    query.set("limit", String(options.limit ?? 50));
    if (
      options.afterSequence !== null &&
      options.afterSequence !== undefined &&
      options.afterSequence >= 1
    ) {
      query.set("after_sequence", String(options.afterSequence));
    }
    return apiRequest<MatchHistory>(
      `/api/matches/${uid(matchId)}/history?${query.toString()}`,
      { token },
    );
  },

  // Kept for completeness of the documented REST contract. The frontend uses
  // the WebSocket `guess.submit` action; this is useful for diagnostics/tests.
  submitGuess(matchId: string, token: string, characterId: string): Promise<GuessResult> {
    return apiRequest<GuessResult>(`/api/matches/${uid(matchId)}/guesses`, {
      method: "POST",
      token,
      body: { character_id: characterId },
    });
  },

  getPlayers(roomId: string, token: string): Promise<PublicPlayer[]> {
    return this.listPlayers(roomId, token).then((response) => response.players);
  },
};
